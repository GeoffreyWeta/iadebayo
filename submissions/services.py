"""reCAPTCHA verification + notification / acknowledgement emails."""
import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.mail import EmailMessage, send_mail
from django.utils import timezone

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
    """Email the Foundation team about a new submission.

    `fail_silently=False` with the failure caught here, rather than
    `fail_silently=True` and no handler. The two are not the same: passing True
    makes `send_mail` swallow the SMTPException internally and return 0, so the
    `except` below never runs and `log.exception` never fires. That is how a
    misconfigured mail host loses every notification with no trace anywhere -
    the submission saves, the page says thank you, and nobody is told.

    Raising is still not an option: the row is already committed by this point,
    so a dead SMTP host must not turn a successful submission into a 500. Hence
    catch-and-log - the send fails, the applicant is unaffected, and there is a
    line in the log saying so.
    """
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL,
                  [settings.FOUNDATION_NOTIFY_EMAIL], fail_silently=False)
    except Exception:
        log.exception("Team notification email failed (subject=%r)", subject)


def acknowledge(to_email: str, first_name: str, what: str, obj=None,
                connection=None):
    """Auto-acknowledgement email to the person who submitted the form.

    Returns True if the message was accepted for delivery, False if it was
    not. The form views ignore that -- a failed acknowledgement must never
    affect a submission that already saved -- but the backfill command needs
    it to decide whether to stamp the row and whether to keep going.

    `obj` is the row being acknowledged. When given, `acknowledged_at` is
    stamped on success, which is what stops a re-run of the backfill from
    mailing the same person twice. The stamp goes through `queryset.update()`
    rather than `obj.save()` on purpose: save() would rewrite every column
    from a possibly stale in-memory copy, and on a row someone happens to be
    editing in the admin that silently reverts their edit.

    `connection` lets a bulk caller reuse one SMTP connection for a whole run.
    Left None, every send opens and tears down its own -- fine for a single
    message from a form view, needlessly slow for hundreds.
    """
    body = (
        f"Dear {first_name},\n\n"
        f"Thank you for {what}. We have received your submission and our team "
        f"will review it and get back to you as soon as possible.\n\n"
        f"Warm regards,\n"
        f"IADEBAYO Foundation\n"
        f"hello@iadebayo.foundation | www.iadebayo.foundation"
    )
    # Same catch-and-log as notify_team, and for the same reason - see there.
    try:
        send_mail("We received your submission - IADEBAYO Foundation", body,
                  settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False,
                  connection=connection)
    except Exception:
        log.exception("Acknowledgement email failed (to=%r)", to_email)
        return False

    if obj is not None:
        type(obj).objects.filter(pk=obj.pk).update(acknowledged_at=timezone.now())
    return True


def send_to_applicant(to_email: str, subject: str, body: str, obj=None,
                      stamp_field="decision_email_sent_at") -> bool:
    """One message, written by a staff member, to one applicant.

    Unlike `notify_team` and `acknowledge` this is not automatic - somebody
    pressed send on text they had just read. So the failure handling is the
    opposite way round: the caller is a person waiting at a screen, and they
    have to be told it did not go, otherwise they tick the applicant off a list
    that nothing was ever sent to. Hence a bool the view turns into a visible
    error, rather than a log line nobody reads.

    `reply_to` is set because these are messages an applicant is meant to answer.
    Sent from `EMBARK_FROM_EMAIL` and answered to `EMBARK_REPLY_TO`, so the
    From address can be a send-only mailbox without the reply bouncing.

    The row is stamped only on success, for the reason `acknowledged_at` exists:
    a stamp written before the send would make a failed send indistinguishable
    from a delivered one, and the applicant would never be written to again.
    """
    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.EMBARK_FROM_EMAIL,
        to=[to_email],
        reply_to=[settings.EMBARK_REPLY_TO] if settings.EMBARK_REPLY_TO else None,
    )
    try:
        message.send(fail_silently=False)
    except Exception:
        log.exception("Applicant email failed (to=%r, subject=%r)", to_email, subject)
        return False

    if obj is not None and stamp_field:
        type(obj).objects.filter(pk=obj.pk).update(**{stamp_field: timezone.now()})
    return True
