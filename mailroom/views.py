"""The webhook mail arrives through, and the staff mailbox at /staff/mail/."""
import logging
from email.utils import parseaddr

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core import mailmerge
from core.staff import staff_required
from core.staff_views import page_links, shell
from submissions.email_presentation import paragraph_parts

from . import mailboxes, rendering, services
from .forms import MessageForm
from .models import Attachment, Conversation, Message

log = logging.getLogger(__name__)


# ================================================================== webhook
@csrf_exempt
@require_POST
def inbound(request):
    """One received email, raw, from the Cloudflare Email Worker.

    Answers 2xx once the message is stored (or was already), so the worker
    stops; 5xx when it could not be stored, so the worker retries; 4xx for a
    request that will never succeed. Switched off (404) until a secret is set.
    """
    secret = settings.MAIL_INBOUND_SECRET
    if not secret:
        raise Http404("Receiving mail is not switched on.")
    if not constant_time_compare(request.headers.get("Authorization", ""), f"Bearer {secret}"):
        return JsonResponse({"error": "unauthorised"}, status=401)

    limit = settings.MAIL_INBOUND_MAX_BYTES
    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = 0
    if declared > limit:
        return JsonResponse({"error": "too large"}, status=413)
    # read(), not .body: .body is capped at DATA_UPLOAD_MAX_MEMORY_SIZE (2.5 MB),
    # and an email with one photo attached is bigger than that.
    raw = request.read(limit + 1)
    if len(raw) > limit:
        return JsonResponse({"error": "too large"}, status=413)
    if not raw.strip():
        return JsonResponse({"error": "empty"}, status=400)

    try:
        result = services.receive(
            raw, envelope_from=request.headers.get("X-Envelope-From", ""),
            envelope_to=request.headers.get("X-Envelope-To", ""))
    except Exception:
        log.exception("Received email could not be stored")
        return JsonResponse({"error": "could not store"}, status=500)
    return JsonResponse({"outcome": result.outcome,
                         "id": result.message.pk if result.message else None})


# ================================================================== folders
FOLDERS = {
    "inbox": ("Inbox", "What people have sent the team. Archive a conversation "
                       "once it is dealt with; a new reply brings it back."),
    "sent": ("Sent", "Conversations the team has written in, from here or from "
                     "the applicant screens."),
    "archived": ("Archived", "Dealt with. Nothing here is deleted."),
    "junk": ("Junk", "Mail that failed the sender's own domain checks, or came "
                     "from a blocked sender. Check before ignoring it."),
    "all": ("All mail", "Every conversation except junk."),
}


def _in_folder(folder):
    qs = Conversation.objects.all()
    if folder == "inbox":
        return qs.filter(has_inbound=True, archived=False, junk=False)
    if folder == "sent":
        return qs.filter(has_outbound=True, junk=False)
    if folder == "archived":
        return qs.filter(archived=True, junk=False)
    if folder == "junk":
        return qs.filter(junk=True)
    return qs.filter(junk=False)


def _when(value):
    value = timezone.localtime(value)
    today = timezone.localdate()
    if value.date() == today:
        return f"{value:%H:%M}"
    if value.year == today.year:
        return f"{value.day} {value:%b}"
    return f"{value.day} {value:%b %Y}"


@never_cache
@staff_required
def mail_list(request, folder="inbox"):
    if folder not in FOLDERS:
        raise Http404("No such folder.")
    qs = _in_folder(folder)
    query = request.GET.get("q", "").strip()
    if query:
        qs = qs.filter(Q(subject__icontains=query) | Q(participants__icontains=query)
                       | Q(contact_name__icontains=query)
                       | Q(messages__text__icontains=query)).distinct()
    unread_only = request.GET.get("unread") == "1"
    if unread_only:
        qs = qs.filter(unread=True)
    # Ordered again here: an aggregate query drops Meta.ordering, and an
    # unordered list can show the same conversation on two pages.
    qs = qs.annotate(message_count=Count("messages", distinct=True)).order_by(
        "-last_message_at", "-pk")

    paginator = Paginator(qs, 50)
    page = paginator.get_page(request.GET.get("page"))
    rows = list(page.object_list)
    for row in rows:
        row.when = _when(row.last_message_at)

    title, blurb = FOLDERS[folder]
    tabs = [{"key": key, "title": name, "url": reverse("staff:mail") if key == "inbox"
             else reverse("staff:mail_folder", args=[key])} for key, (name, _) in FOLDERS.items()]
    return render(request, "mailroom/list.html", shell(
        request, page_title=title, nav=f"mail-{folder}", folder=folder, title=title,
        blurb=blurb, tabs=tabs, rows=rows, pages=page_links(request, page), page=page,
        total=paginator.count, query=query, unread_only=unread_only,
        receiving=bool(settings.MAIL_INBOUND_SECRET),
    ))


# ============================================================ writing mail
def _mailbox_name(address):
    name = parseaddr(mailboxes.formatted(address))[0]
    return name or "IADEBAYO Foundation"


def _signature(user, address):
    who = user.get_full_name() or user.get_username()
    return f"\n\n\nKind regards,\n{who}\n{_mailbox_name(address)}"


def _addresses(text):
    return [address for _, address in mailboxes.split([text or ""])]


def _contacts():
    """Recent addresses for the To box's autocomplete."""
    return list(Conversation.objects.exclude(contact_email="")
                .values_list("contact_email", flat=True).distinct()[:300])


def _send(request, form, conversation=None, parent=None):
    data = form.cleaned_data
    subject, body = data["subject"], data["body"]
    if mailmerge.TOKEN.search(subject + body):
        person = services.person_for(data["to"] + data["cc"] + data["bcc"])
        if person is None:
            return services.Sent(False, error=(
                "Placeholders such as {{ first_name }} are only filled in when "
                "writing to one person the site has a record for. Replace them "
                "with the real words before sending."))
        context = mailmerge.context_for(person)
        subject, body = mailmerge.render(subject, context), mailmerge.render(body, context)

    quote = rendering.quote_for(parent) if parent is not None else None
    files = [(f.name, f.read(), getattr(f, "content_type", "") or "application/octet-stream")
             for f in data["attachments"]]
    return services.send(
        from_email=mailboxes.formatted(data["from_address"]),
        to=data["to"], cc=data["cc"], bcc=data["bcc"], subject=subject,
        text=rendering.outgoing_text(body, quote), html=rendering.outgoing_html(body, quote),
        attachments=files, conversation=conversation, parent=parent, user=request.user)


def _report(request, result):
    if result.ok:
        messages.success(request, "Sent.")
        if result.message is None:
            messages.warning(request, "It was sent, but could not be saved in the "
                                      "mailbox. The server log has the details.")
    else:
        # Not a redirect: the text stays in the box, so trying again costs
        # nothing. Nothing was filed, so nothing needs undoing either.
        messages.error(request, f"Not sent. {result.error} Nothing was recorded, "
                                f"so nothing is lost by trying again.")


@never_cache
@staff_required
def mail_compose(request):
    from core.models import EmailTemplate

    templates = list(EmailTemplate.objects.all())
    chosen = None
    if request.method == "POST":
        form = MessageForm(request.POST, request.FILES)
        if form.is_valid():
            result = _send(request, form)
            _report(request, result)
            if result.ok:
                if result.message:
                    return redirect("staff:mail_thread", pk=result.message.conversation_id)
                return redirect("staff:mail_folder", folder="sent")
        to = request.POST.get("to", "")
    else:
        to = request.GET.get("to", "").strip()
        from_address = mailboxes.default()
        subject = request.GET.get("subject", "")
        body = _signature(request.user, from_address)
        want = request.GET.get("template")
        if want:
            chosen = next((t for t in templates if str(t.pk) == want), None)
        if chosen:
            # Filled in now, on the way into the box, when the address belongs
            # to someone the site knows - so what is read is what is sent.
            person = services.person_for(_addresses(to))
            context = mailmerge.context_for(person) if person else None
            subject = mailmerge.render(chosen.subject, context) if context else chosen.subject
            body = mailmerge.render(chosen.body, context) if context else chosen.body
        form = MessageForm(initial={"from_address": from_address, "to": to,
                                    "subject": subject, "body": body})

    person = services.person_for(_addresses(to))
    return render(request, "mailroom/compose.html", shell(
        request, page_title="Write an email", nav="mail-compose", form=form,
        templates=templates, chosen=chosen, to=to, person=person,
        records=services.records_for(person.email) if person else [],
        placeholders=mailmerge.catalogue(), contacts=_contacts(),
        max_attachments=settings.MAIL_ATTACHMENTS_MAX_BYTES,
    ))


# ============================================================ a conversation
def _reply_defaults(conversation, target, user):
    """Who a reply goes to: the sender (or their Reply-To), with everyone else
    who was on their message copied - reply-all, shown and editable."""
    from_address = (conversation.mailbox if conversation.mailbox in dict(mailboxes.configured())
                    else mailboxes.default())
    to, cc = [], []
    if target is not None and target.is_inbound:
        to = [target.reply_to] if target.reply_to else [
            mailboxes.display(target.from_name, target.from_email)]
        taken = {mailboxes.bare(a) for a in mailboxes.split(to)}
        for name, address in mailboxes.split([target.to, target.cc]):
            key = address.lower()
            if key not in taken and not mailboxes.is_ours(address):
                taken.add(key)
                cc.append(mailboxes.display(name, address))
    elif target is not None:
        to, cc = [target.to], [target.cc] if target.cc else []
    elif conversation.contact_email:
        to = [mailboxes.display(conversation.contact_name, conversation.contact_email)]

    subject = conversation.subject or (target.subject if target else "")
    if not services.PREFIX.match(subject):
        subject = f"Re: {subject}" if subject else ""
    return {"from_address": from_address, "to": ", ".join(t for t in to if t),
            "cc": ", ".join(c for c in cc if c), "subject": subject,
            "body": _signature(user, from_address)}


@never_cache
@staff_required
def mail_thread(request, pk):
    conversation = get_object_or_404(Conversation, pk=pk)
    thread = list(conversation.messages.select_related("sent_by").prefetch_related("attachments"))
    inbound = [m for m in thread if m.is_inbound]
    target = inbound[-1] if inbound else (thread[-1] if thread else None)

    if request.method == "POST":
        form = MessageForm(request.POST, request.FILES)
        if form.is_valid():
            result = _send(request, form, conversation=conversation, parent=target)
            _report(request, result)
            if result.ok:
                return redirect(reverse("staff:mail_thread", args=[pk]) + "#latest")
    else:
        if conversation.unread:
            conversation.unread = False
            conversation.save(update_fields=["unread"])
        form = MessageForm(initial=_reply_defaults(conversation, target, request.user))

    show_images = request.GET.get("images", "")
    items = []
    for message in thread:
        attachments = list(message.attachments.all())
        item = {"m": message, "attachments": attachments, "frame": "", "remote": False}
        if message.is_inbound and message.html.strip():
            allow = show_images == str(message.pk)
            item["frame"], used = rendering.viewer_document(message, attachments, allow)
            item["remote"] = rendering.has_remote_content(message.html) and not allow
            item["attachments"] = [a for a in attachments if a.pk not in used]
        else:
            item["fresh"], item["quoted"] = rendering.split_quote(message.body_text())
            if message.direction == Message.OUT and not message.sent_elsewhere:
                # Written here, so **bold** and links are our own markup:
                # show it the way the recipient's HTML part shows it.
                item["paragraphs"] = paragraph_parts(item["fresh"])
        items.append(item)

    folder = "junk" if conversation.junk else "archived" if conversation.archived else (
        "inbox" if conversation.has_inbound else "sent")
    return render(request, "mailroom/thread.html", shell(
        request, page_title=str(conversation)[:60], nav=f"mail-{folder}",
        conversation=conversation, items=items, form=form, folder=folder,
        folder_title=FOLDERS[folder][0],
        folder_url=reverse("staff:mail") if folder == "inbox"
        else reverse("staff:mail_folder", args=[folder]),
        records=services.records_for(conversation.contact_email),
        sender_blocked=services._sender_blocked(conversation.contact_email)
        if conversation.contact_email else False,
        contacts=_contacts(), placeholders=mailmerge.catalogue(),
        max_attachments=settings.MAIL_ATTACHMENTS_MAX_BYTES,
        here=request.get_full_path(),
    ))


@require_POST
@staff_required
def mail_action(request, pk):
    from submissions.contact_protection import set_sender_blocked

    conversation = get_object_or_404(Conversation, pk=pk)
    action = request.POST.get("action", "")
    to_list = False
    if action == "archive":
        conversation.archived, note, to_list = True, "Archived.", True
    elif action == "inbox":
        conversation.archived, conversation.junk, note = False, False, "Moved to the inbox."
    elif action == "unread":
        conversation.unread, note, to_list = True, "Marked unread.", True
    elif action == "junk":
        conversation.junk, note, to_list = True, "Moved to junk.", True
    elif action == "notjunk":
        conversation.junk, note = False, "Moved out of junk."
    elif action in ("block", "unblock") and conversation.contact_email:
        blocked = action == "block"
        set_sender_blocked(conversation.contact_email, blocked=blocked)
        conversation.junk = blocked
        to_list = blocked
        note = (f"{conversation.contact_email} is blocked: their mail goes to junk "
                f"and the contact form refuses them." if blocked
                else f"{conversation.contact_email} is unblocked.")
    else:
        raise Http404("Not an action this page offers.")
    conversation.save()
    messages.success(request, note)

    target = request.POST.get("next", "")
    if to_list:
        target = reverse("staff:mail")
    if not url_has_allowed_host_and_scheme(target, {request.get_host()},
                                           require_https=request.is_secure()):
        target = reverse("staff:mail_thread", args=[pk])
    return redirect(target)


# ================================================================ files
# Shown in the browser only when the browser cannot be made to run them. An
# HTML or SVG attachment opened on our own domain would be a script running as
# the signed-in staff member, so everything else is a download.
VIEWABLE = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}


@never_cache
@staff_required
def mail_attachment(request, pk):
    attachment = get_object_or_404(Attachment, pk=pk)
    try:
        handle = attachment.file.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("That file is missing from storage.")
    viewable = attachment.content_type in VIEWABLE and request.GET.get("download") != "1"
    response = FileResponse(
        handle, as_attachment=not viewable, filename=attachment.filename,
        content_type=attachment.content_type if viewable else "application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    if attachment.content_type != "application/pdf":
        # PDF is left out because the browser's PDF viewer will not run in
        # a sandboxed document.
        response["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'"
    return response


@never_cache
@staff_required
def mail_source(request, pk):
    """The message exactly as received, headers and all, as an .eml file -
    for checking SPF/DKIM/DMARC by hand or handing to the mail provider."""
    message = get_object_or_404(Message, pk=pk)
    if not message.raw:
        raise Http404("Only received messages keep their original.")
    try:
        handle = message.raw.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("The original is missing from storage.")
    response = FileResponse(handle, as_attachment=True, filename=f"message-{message.pk}.eml",
                            content_type="message/rfc822")
    response["X-Content-Type-Options"] = "nosniff"
    return response
