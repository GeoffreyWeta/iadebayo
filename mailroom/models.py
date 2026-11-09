"""Conversations, the messages in them, and the files those messages carried.

A conversation is what the team thinks of as "the thread with Chidi about her
application": every message the staff area sent and every reply that came back,
in order. Messages are records of what went over the wire, so nothing here is
editable after the fact - the only things that change on a conversation are the
team's own bookkeeping (read, archived, junk).

The summary columns on Conversation (last_message_at, snippet, has_inbound, ...)
are denormalised on purpose. The inbox list is the page staff open most, and
working those out from the messages table on every load would be a join and an
aggregate per row. `Conversation.refresh()` is the one place they are written.
"""
import os
import uuid

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils import timezone
from django.utils.text import get_valid_filename


class MailStorage(FileSystemStorage):
    """Private files: outside MEDIA_ROOT, and never given a public URL.

    nginx serves /media/ to anyone who knows a path, so an applicant's emailed
    passport scan must never land there. The location is read from settings on
    every use (not fixed at import) so tests can point it at a temporary dir.
    """

    @property
    def base_location(self):
        return os.fspath(settings.MAIL_FILES_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    def url(self, name):
        raise ValueError("Mail files are served only through the staff views.")


_storage = MailStorage()


def mail_storage():
    return _storage


def _month():
    return timezone.now().strftime("%Y/%m")


def raw_path(instance, filename):
    return f"raw/{_month()}/{uuid.uuid4().hex}.eml"


def safe_filename(name, fallback="attachment"):
    """A filename that is safe on disk and still recognisable to a person."""
    name = os.path.basename((name or "").replace("\\", "/")).strip()
    try:
        cleaned = get_valid_filename(name)
    except SuspiciousFileOperation:
        cleaned = ""
    if not cleaned:
        return fallback
    stem, ext = os.path.splitext(cleaned)
    return stem[:100] + ext[:20]


def attachment_path(instance, filename):
    # A directory per file keeps the original name readable on disk without
    # two "CV.pdf" uploads in the same month overwriting each other.
    return f"attachments/{_month()}/{uuid.uuid4().hex}/{safe_filename(filename)}"


class Conversation(models.Model):
    subject = models.CharField(max_length=255, blank=True)
    # The subject with Re:/Fwd: stripped and lowercased: how a reply that lost
    # its threading headers is still matched to the conversation it answers.
    subject_key = models.CharField(max_length=255, blank=True, db_index=True)
    # The person on the other end, as shown in the list.
    contact_email = models.CharField(max_length=254, blank=True, db_index=True)
    contact_name = models.CharField(max_length=200, blank=True)
    # Every outside address that has been on this conversation, space-separated
    # with a space at each end, so `participants__contains=" a@b.c "` is an
    # exact-address match on any database.
    participants = models.TextField(blank=True, default="")
    # Which of our addresses the conversation is with (embark@, hello@, ...).
    mailbox = models.CharField(max_length=254, blank=True)

    last_message_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_direction = models.CharField(max_length=3, blank=True)
    snippet = models.CharField(max_length=200, blank=True)
    has_inbound = models.BooleanField(default=False)
    has_outbound = models.BooleanField(default=False)

    unread = models.BooleanField(default=False, db_index=True)
    archived = models.BooleanField(default=False, db_index=True)
    junk = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_message_at", "-pk"]

    def __str__(self):
        return self.subject or "(no subject)"

    @property
    def contact_label(self):
        return self.contact_name or self.contact_email or "(unknown sender)"

    def participant_list(self):
        return self.participants.split()

    def add_participants(self, addresses):
        known = self.participant_list()
        for address in addresses:
            address = (address or "").strip().lower()
            if address and "@" in address and address not in known:
                known.append(address)
        self.participants = f" {' '.join(known)} " if known else ""

    def refresh(self):
        """Recompute the list summary from the messages actually stored."""
        latest = self.messages.order_by("-sent_at", "-pk").first()
        if latest is not None:
            self.last_message_at = latest.sent_at
            self.last_direction = latest.direction
            self.snippet = latest.snippet()
        self.has_inbound = self.messages.filter(direction=Message.IN).exists()
        self.has_outbound = self.messages.filter(direction=Message.OUT).exists()
        self.save()


class Message(models.Model):
    IN = "in"
    OUT = "out"
    DIRECTION_CHOICES = [(IN, "Received"), (OUT, "Sent")]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE,
                                     related_name="messages")
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    # Always set and unique: received mail without one gets a hash of its raw
    # bytes. That uniqueness is what makes a re-delivered message (the worker
    # retrying, or the same email sent to two of our addresses) a no-op.
    message_id = models.CharField(max_length=255, unique=True)
    in_reply_to = models.CharField(max_length=255, blank=True)
    references = models.TextField(blank=True)

    from_email = models.CharField(max_length=254)
    from_name = models.CharField(max_length=200, blank=True)
    to = models.TextField(blank=True)
    cc = models.TextField(blank=True)
    bcc = models.TextField(blank=True)
    reply_to = models.TextField(blank=True)
    # The address the mail server delivered to - the only record of which of
    # our mailboxes got a Bcc'd message, since it is not in the headers.
    envelope_to = models.CharField(max_length=254, blank=True)

    subject = models.CharField(max_length=255, blank=True)
    text = models.TextField(blank=True)
    html = models.TextField(blank=True)

    sent_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name="+")

    # What the receiving mail server concluded about the sender, e.g.
    # "spf=pass dkim=pass dmarc=fail". Advisory: shown to staff, and a DMARC
    # failure sends a new conversation to Junk.
    auth_results = models.CharField(max_length=200, blank=True)
    suspicious = models.BooleanField(default=False)
    raw = models.FileField(storage=mail_storage, upload_to=raw_path, blank=True,
                           max_length=255)

    class Meta:
        ordering = ["sent_at", "pk"]

    def __str__(self):
        return f"{self.get_direction_display()}: {self.subject}"

    @property
    def is_inbound(self):
        return self.direction == self.IN

    @property
    def sender_label(self):
        return self.from_name or self.from_email

    @property
    def sent_elsewhere(self):
        """One of our addresses, sent from a mail app rather than from here."""
        return self.direction == self.OUT and bool(self.raw)

    def body_text(self):
        if self.text.strip():
            return self.text
        if self.html:
            from .parsing import html_to_text
            return html_to_text(self.html)
        return ""

    def snippet(self):
        from .rendering import split_quote
        fresh, _ = split_quote(self.body_text())
        if self.direction == self.OUT:
            fresh = fresh.replace("**", "")   # our own bold markers
        return " ".join(fresh.split())[:200]


class Attachment(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE,
                                related_name="attachments")
    file = models.FileField(storage=mail_storage, upload_to=attachment_path,
                            max_length=255)
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=150, default="application/octet-stream")
    size = models.PositiveIntegerField(default=0)
    # For images an HTML email shows inline via <img src="cid:...">.
    content_id = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["pk"]

    def __str__(self):
        return self.filename
