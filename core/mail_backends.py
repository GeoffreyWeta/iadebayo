"""A Django email backend that sends through ZeptoMail's HTTP API.

Exists because DigitalOcean blocks outbound SMTP (25/465/587) on droplets, so
the stock SMTP backend times out there no matter how right the credentials are.
HTTPS on 443 is never blocked. Everything that calls `send_mail` or
`EmailMessage.send` keeps working unchanged — only EMAIL_BACKEND moves.

Standard library only (urllib), so no new dependency on the droplet.
"""
import base64
import json
import logging
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

log = logging.getLogger(__name__)

API_URL = "https://api.zeptomail.com/v1.1/email"


class ZeptoMailError(Exception):
    pass


def _address(value):
    """'Name <a@b>' -> {"address": "a@b", "name": "Name"} (name omitted if blank)."""
    name, address = parseaddr(value)
    out = {"address": address}
    if name:
        out["name"] = name
    return out


def _recipients(values):
    return [{"email_address": _address(v)} for v in values]


def _attachment(item):
    # EmailMessage.attachments holds either (filename, content, mimetype)
    # tuples or ready-made MIMEBase objects, depending on how it was attached.
    if isinstance(item, tuple):
        filename, content, mimetype = item
        if isinstance(content, str):
            content = content.encode()
    else:
        filename = item.get_filename()
        content = item.get_payload(decode=True)
        mimetype = item.get_content_type()
    return {
        "name": filename or "attachment",
        "mime_type": mimetype or "application/octet-stream",
        "content": base64.b64encode(content).decode(),
    }


def build_payload(message):
    payload = {
        "from": _address(message.from_email or settings.DEFAULT_FROM_EMAIL),
        "to": _recipients(message.to),
        "subject": message.subject,
    }
    if message.cc:
        payload["cc"] = _recipients(message.cc)
    if message.bcc:
        payload["bcc"] = _recipients(message.bcc)
    if message.reply_to:
        payload["reply_to"] = [_address(v) for v in message.reply_to]

    if message.content_subtype == "html":
        payload["htmlbody"] = message.body
    else:
        payload["textbody"] = message.body
    for content, mimetype in getattr(message, "alternatives", []):
        if mimetype == "text/html":
            payload["htmlbody"] = content

    if message.attachments:
        payload["attachments"] = [_attachment(a) for a in message.attachments]
    return payload


class ZeptoMailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, token=None, timeout=15, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        token = token or getattr(settings, "ZEPTOMAIL_TOKEN", "")
        # The dashboard shows the token with its scheme ("Zoho-enczapikey ...");
        # accept it pasted either way.
        prefix = "Zoho-enczapikey "
        self.token = token[len(prefix):] if token.startswith(prefix) else token
        self.timeout = timeout

    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages:
            if not message.recipients():
                continue
            try:
                self._send(message)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
                log.exception("ZeptoMail send failed (subject=%r)", message.subject)
        return sent

    def _send(self, message):
        if not self.token:
            raise ZeptoMailError("ZEPTOMAIL_TOKEN is empty.")
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(build_payload(message)).encode(),
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Zoho-enczapikey {self.token}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            # ZeptoMail explains a rejection in the body (unverified sender,
            # bad token, ...). Without it all you get is "HTTP Error 400".
            detail = exc.read().decode(errors="replace")[:1000]
            raise ZeptoMailError(f"HTTP {exc.code}: {detail}") from exc
