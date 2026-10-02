"""Contact moderation shared by staff controls and the public form."""
from datetime import timedelta
import re

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.functions import Lower, Trim
from django.utils import timezone

from .applicants import normalized_email
from .models import ContactMessage, ContactSender


# Match the whole generated subject, not ordinary questions mentioning prices.
_PRICING_SPAM_SUBJECT = re.compile(
    r"(?:hello|hallo|hi|aloha)\s+(?:i\s+)?(?:am\s+)?"
    r"(?:write|wrote|writing)\s+about\s+"
    r"(?:your\s+)?(?:the\s+)?prices?(?:\s+for\s+reseller)?"
)


def is_contact_spam(subject):
    words = " ".join(re.findall(r"\w+", subject.casefold()))
    return _PRICING_SPAM_SUBJECT.fullmatch(words) is not None


def sender_messages(email):
    return ContactMessage.objects.annotate(email_key=Lower(Trim("email"))).filter(
        email_key=normalized_email(email))


def _lock_sender(email):
    sender, _ = ContactSender.objects.get_or_create(email=normalized_email(email))
    # A write serializes checks across workers, including SQLite deployments.
    ContactSender.objects.filter(pk=sender.pk).update(updated_at=timezone.now())
    sender.refresh_from_db()
    return sender


@transaction.atomic
def set_sender_blocked(email, blocked=True):
    sender = _lock_sender(email)
    sender.blocked = blocked
    sender.save(update_fields=["blocked", "updated_at"])
    return sender_messages(email).filter(reviewed=False).update(reviewed=True) if blocked else 0


@transaction.atomic
def save_contact(message):
    if is_contact_spam(message.subject):
        raise ValidationError("This message cannot be accepted.")
    message.email = normalized_email(message.email)
    sender = _lock_sender(message.email)
    if sender.blocked:
        raise ValidationError("This message cannot be accepted.")
    now = timezone.now()
    recent = sender_messages(message.email).filter(created_at__gte=now - timedelta(days=1))
    normalize = lambda value: " ".join(value.split()).casefold()
    text = normalize(message.message)
    if any(normalize(previous) == text for previous in recent.values_list("message", flat=True)):
        raise ValidationError("We already received this message. Please give the team time to reply.")
    if recent.filter(created_at__gte=now - timedelta(hours=1)).count() >= 3:
        raise ValidationError("You have sent several messages recently. Please try again in an hour.")
    if recent.count() >= 6:
        raise ValidationError("You have sent several messages today. Please try again tomorrow.")
    message.save()
    return message
