"""reCAPTCHA verification + notification / acknowledgement emails."""
import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

log = logging.getLogger(__name__)


def verify_recaptcha(request) -> bool:
    """Verify Google reCAPTCHA v2. If no keys are configured, allow (dev mode)."""
    if not settings.RECAPTCHA_SECRET_KEY:
        return True
    token = request.POST.get("g-recaptcha-response", "")
    if not token:
        return False
    data = urllib.parse.urlencode({
        "secret": settings.RECAPTCHA_SECRET_KEY,
        "response": token,
        "remoteip": request.META.get("REMOTE_ADDR", ""),
    }).encode()
    try:
        req = urllib.request.Request("https://www.google.com/recaptcha/api/siteverify", data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp).get("success", False)
    except Exception:  # network hiccup shouldn't 500 the form
        log.exception("reCAPTCHA verification failed")
        return False


def notify_team(subject: str, body: str):
    """Email the Foundation team about a new submission."""
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [settings.FOUNDATION_NOTIFY_EMAIL], fail_silently=not settings.DEBUG)
    except Exception:
        log.exception("Team notification email failed")


def acknowledge(to_email: str, first_name: str, what: str):
    """Auto-acknowledgement email to the person who submitted the form."""
    body = (
        f"Dear {first_name},\n\n"
        f"Thank you for {what}. We have received your submission and our team "
        f"will review it and get back to you as soon as possible.\n\n"
        f"Warm regards,\n"
        f"IADEBAYO Foundation\n"
        f"hello@iadebayo.foundation | www.iadebayo.foundation"
    )
    try:
        send_mail("We received your submission — IADEBAYO Foundation", body,
                  settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=not settings.DEBUG)
    except Exception:
        log.exception("Acknowledgement email failed")
