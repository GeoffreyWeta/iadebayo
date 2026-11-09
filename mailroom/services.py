"""Receiving mail, sending it, and filing both into conversations.

Threading
---------
A received message joins a conversation by, in order:

1. `In-Reply-To` / `References` naming a message we already hold - exact, and
   what every mail client sends when someone presses Reply;
2. failing that, the same subject (Re:/Fwd: ignored) with an address already on
   the conversation, within THREAD_WINDOW - the fallback Gmail itself uses.

The second rule matters more than it looks. ZeptoMail stamps its own
Message-ID on what we send and does not report it back, so a reply to staff
mail sent through it usually names an ID we never saw. Rule 2 is what files it.

Sending
-------
`send()` sends first and files second, and only what was accepted is filed. A
failed send therefore leaves nothing behind - the same promise the applicant
screens make ("nothing was recorded, so nothing is lost by trying again").
"""
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from email.utils import make_msgid, parseaddr

from django.core.exceptions import FieldDoesNotExist
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from . import mailboxes, parsing
from .mailboxes import bare
from .models import Attachment, Conversation, Message

log = logging.getLogger(__name__)

THREAD_WINDOW = timedelta(days=120)
PREFIX = re.compile(r"^\s*(?:(?:re|fw|fwd|aw|sv|vs|antw|wg|tr|rif)\s*(?:\[\d+\])?\s*:\s*)+", re.I)
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def clean_subject(subject):
    """The subject without its Re:/Fwd: chain."""
    subject = " ".join((subject or "").split())
    return PREFIX.sub("", subject).strip() or subject


def subject_key(subject):
    return clean_subject(subject).lower()[:255]


def find_conversation(thread_ids=(), subject="", addresses=()):
    thread_ids = [m for m in thread_ids if m]
    if thread_ids:
        known = {m.message_id: m.conversation for m in
                 Message.objects.filter(message_id__in=thread_ids).select_related("conversation")}
        for message_id in thread_ids:
            if message_id in known:
                return known[message_id]

    key = subject_key(subject)
    addresses = [a for a in {bare(a) for a in addresses} if a]
    if not key or not addresses:
        return None
    anyone = Q()
    for address in addresses:
        anyone |= Q(participants__contains=f" {address} ")
    return (Conversation.objects
            .filter(anyone, subject_key=key,
                    last_message_at__gte=timezone.now() - THREAD_WINDOW)
            .order_by("-last_message_at", "-pk").first())


def _listed(pairs):
    return ", ".join(mailboxes.display(n, a) for n, a in pairs)


def _shown_filename(name):
    name = CONTROL.sub("", (name or "").replace("\\", "/").rsplit("/", 1)[-1]).strip()
    return name[:200] or "attachment"


def _store_attachment(message, filename, data, content_type, content_id=""):
    attachment = Attachment(message=message, filename=_shown_filename(filename),
                            content_type=(content_type or "application/octet-stream")[:150],
                            size=len(data), content_id=(content_id or "")[:255])
    attachment.file.save(attachment.filename, ContentFile(data), save=True)
    return attachment


# ================================================================= receiving
@dataclass
class Received:
    outcome: str                  # "stored", "duplicate" or "ignored"
    message: Message | None = None


def _sender_blocked(address):
    from submissions.models import ContactSender
    return ContactSender.objects.filter(email=bare(address), blocked=True).exists()


def receive(raw, envelope_from="", envelope_to="", use_date_header=False):
    """File one received email. Safe to call twice with the same message.

    Live mail (the webhook) is timed by when it arrived, not by its Date
    header: the sender's clock is theirs, and a reply stamped a few seconds
    "before" the message it answers would sort above it. Mail imported after
    the fact (`receive_email`) passes use_date_header so it keeps its own time.
    """
    parsed = parsing.parse(raw)
    sender = (parsed.from_email or bare(envelope_from)).strip()
    if mailboxes.is_automatic(sender):
        return Received("ignored")

    existing = Message.objects.filter(message_id=parsed.message_id).first()
    if existing:
        return Received("duplicate", existing)

    everyone = parsed.to + parsed.cc
    # Our own address on the From line is a member of staff writing from a
    # mail app with a copy to the team inbox: file it as sent, with the person
    # they wrote to as the contact.
    ours = mailboxes.is_ours(sender)
    if ours:
        outside = [(n, a) for n, a in everyone if not mailboxes.is_ours(a)]
        contact = outside[0] if outside else ("", "")
        mailbox = bare(sender)
    else:
        outside = [(parsed.from_name, sender)] + [
            (n, a) for n, a in everyone + parsed.reply_to if not mailboxes.is_ours(a)]
        contact = (parsed.from_name, sender)
        mailbox = (bare(envelope_to) if mailboxes.is_ours(envelope_to) else
                   next((bare(a) for _, a in everyone if mailboxes.is_ours(a)),
                        bare(envelope_to) or mailboxes.default()))

    suspicious = parsed.auth.get("dmarc") == "fail"
    blocked = not ours and _sender_blocked(sender)
    addresses = [a for _, a in outside]

    try:
        with transaction.atomic():
            conversation = find_conversation(parsed.thread_ids, parsed.subject, addresses)
            if conversation is None:
                conversation = Conversation(
                    subject=clean_subject(parsed.subject)[:255],
                    subject_key=subject_key(parsed.subject),
                    contact_email=bare(contact[1])[:254],
                    contact_name=(contact[0] or "")[:200],
                    mailbox=mailbox[:254],
                    junk=suspicious or blocked)
            else:
                if blocked:
                    conversation.junk = True
                # Started by us to a bare address; now they have told us
                # their name.
                if (not ours and not conversation.contact_name and parsed.from_name
                        and conversation.contact_email == bare(sender)):
                    conversation.contact_name = parsed.from_name[:200]
            conversation.add_participants(addresses)
            if not ours:
                conversation.unread = True
                if not conversation.junk:
                    conversation.archived = False
            conversation.save()

            message = Message.objects.create(
                conversation=conversation,
                direction=Message.OUT if ours else Message.IN,
                message_id=parsed.message_id,
                in_reply_to=parsed.in_reply_to,
                references=" ".join(parsed.references),
                from_email=bare(sender)[:254],
                from_name=parsed.from_name[:200],
                to=_listed(parsed.to), cc=_listed(parsed.cc),
                reply_to=_listed(parsed.reply_to),
                envelope_to=bare(envelope_to)[:254],
                subject=parsed.subject[:255],
                text=parsed.text, html=parsed.html,
                sent_at=(parsed.date if use_date_header and parsed.date else timezone.now()),
                auth_results=" ".join(f"{k}={v}" for k, v in sorted(parsed.auth.items()))[:200],
                suspicious=suspicious)
            message.raw.save("message.eml", ContentFile(raw), save=True)
            for part in parsed.attachments:
                _store_attachment(message, part.filename, part.data,
                                  part.content_type, part.content_id)
            conversation.refresh()
    except IntegrityError:
        # The same message arriving twice at once (two of our addresses on
        # the To line make Cloudflare deliver it twice): the other one won.
        existing = Message.objects.filter(message_id=parsed.message_id).first()
        if existing:
            return Received("duplicate", existing)
        raise
    return Received("stored", message)


# =================================================================== sending
@dataclass
class Sent:
    ok: bool
    message: Message | None = None
    error: str = ""


def send(*, from_email, to, subject, text, html="", cc=(), bcc=(), reply_to=(),
         attachments=(), conversation=None, parent=None, user=None):
    """Send one message and file it.

    `to`/`cc`/`bcc`/`reply_to` are lists of "Name <address>" or bare
    addresses. `attachments` is [(filename, bytes, content type)]. `parent` is
    the message being answered: it sets In-Reply-To/References so the
    recipient's mail app threads the reply under what they wrote.
    """
    domain = bare(from_email).rsplit("@", 1)[-1] or "localhost"
    message_id = make_msgid(domain=domain)
    headers = {"Message-ID": message_id}
    references = ""
    if parent is not None:
        references = " ".join((parent.references.split() + [parent.message_id])[-20:])
        headers["In-Reply-To"] = parent.message_id
        headers["References"] = references

    email = EmailMultiAlternatives(
        subject=subject, body=text, from_email=from_email, to=list(to),
        cc=list(cc), bcc=list(bcc), reply_to=list(reply_to) or None, headers=headers)
    if html:
        email.attach_alternative(html, "text/html")
    for filename, data, content_type in attachments:
        email.attach(filename, data, content_type)

    try:
        if email.send(fail_silently=False) != 1:
            return Sent(False, error="The mail server did not accept the message.")
    except Exception as exc:
        log.exception("Staff email failed (to=%r, subject=%r)", list(to), subject)
        return Sent(False, error=str(exc)[:500])

    # Sent is sent. If filing it fails, say so in the log and still report
    # success - telling the sender it failed would make them send it again.
    try:
        with transaction.atomic():
            if conversation is None:
                conversation = find_conversation(subject=subject, addresses=list(to) + list(cc))
            if conversation is None:
                name, address = parseaddr(to[0]) if to else ("", "")
                conversation = Conversation.objects.create(
                    subject=clean_subject(subject)[:255], subject_key=subject_key(subject),
                    contact_email=bare(address)[:254], contact_name=name[:200],
                    mailbox=bare(from_email)[:254])
            conversation.add_participants(
                [bare(a) for a in list(to) + list(cc) + list(bcc) if not mailboxes.is_ours(a)])
            conversation.unread = False
            conversation.save()
            message = Message.objects.create(
                conversation=conversation, direction=Message.OUT,
                message_id=message_id[:255],
                in_reply_to=parent.message_id if parent is not None else "",
                references=references,
                from_email=bare(from_email)[:254], from_name=parseaddr(from_email)[0][:200],
                to=", ".join(to), cc=", ".join(cc), bcc=", ".join(bcc),
                reply_to=", ".join(reply_to), subject=subject[:255],
                text=text, html=html or "", sent_by=user)
            for filename, data, content_type in attachments:
                _store_attachment(message, filename, data, content_type)
            conversation.refresh()
    except Exception:
        log.exception("Sent, but could not be filed in the mailbox (to=%r)", list(to))
        return Sent(True)
    return Sent(True, message)


# ================================================================== people
def _inbox_collections():
    from core import staff_content
    for collection in staff_content.COLLECTIONS:
        if not collection.is_inbox:
            continue
        try:
            collection.model._meta.get_field("email")
        except FieldDoesNotExist:
            continue
        yield collection


def records_for(address, limit=5):
    """Everything the site holds from this address, as links into the staff area."""
    key = bare(address)
    out = []
    if not key:
        return out
    for collection in _inbox_collections():
        for obj in collection.queryset().filter(email__iexact=key)[:limit]:
            out.append({"kind": collection.label, "title": str(obj),
                        "url": collection.url("detail", pk=obj.pk),
                        "created_at": getattr(obj, "created_at", None)})
    return out


def person_for(addresses):
    """The record to fill {{ placeholders }} from: only when writing to exactly
    one person the site knows. Applications are checked before anything else."""
    keys = {bare(a) for a in addresses if bare(a)}
    if len(keys) != 1:
        return None
    key = keys.pop()
    for collection in _inbox_collections():
        obj = collection.queryset().filter(email__iexact=key).order_by("-pk").first()
        if obj is not None:
            return obj
    return None


def conversations_with(address, limit=10):
    key = bare(address)
    if not key:
        return Conversation.objects.none()
    return Conversation.objects.filter(participants__contains=f" {key} ")[:limit]


def unread_count():
    return Conversation.objects.filter(unread=True, has_inbound=True,
                                       archived=False, junk=False).count()
