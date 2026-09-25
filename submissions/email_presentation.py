"""Safe branded HTML alongside the original, readable text message."""
import re
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.core.signing import BadSignature, TimestampSigner
from django.template.loader import render_to_string
from django.urls import reverse


def _personal_resume_url(value, obj):
    from .models import PartialApplication
    if not isinstance(obj, PartialApplication):
        return False
    try:
        actual = urlsplit(value)
    except ValueError:
        return False
    expected = urlsplit(settings.SITE_BASE_URL.rstrip("/") + reverse("core:apply"))
    if actual.scheme not in ("http", "https") or (actual.scheme, actual.netloc, actual.path) != (
            expected.scheme, expected.netloc, expected.path):
        return False
    token = parse_qs(actual.query).get("resume", [""])[0]
    try:
        draft_id = TimestampSigner(salt=obj.RESUME_SALT).unsign(
            token, max_age=obj.RESUME_MAX_AGE_DAYS * 86400)
    except BadSignature:
        return False
    return draft_id == obj.draft_id


def applicant_email_html(body, obj=None):
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", body.strip()):
        parts = []
        for text in re.split(r"(\*\*.+?\*\*|https?://[^\s<>]+)", paragraph, flags=re.S):
            if not text:
                continue
            bold = text.startswith("**") and text.endswith("**")
            text = text[2:-2] if bold else text
            parts.append({"text": text, "bold": bold,
                          "button": _personal_resume_url(text, obj) if text.startswith(("https://", "http://")) else False})
        paragraphs.append(parts)
    return render_to_string("emails/applicant.html", {"paragraphs": paragraphs})
