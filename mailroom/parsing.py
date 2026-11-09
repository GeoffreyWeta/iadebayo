"""A received email, as raw RFC 5322 bytes, taken apart into what we store.

Standard library only. Real-world mail is malformed often enough that every
step here assumes it might be: an unknown charset, a header the strict parser
chokes on, a body with no text part. Anything that fails degrades to "less
information", never to an exception that would lose the whole message - the
webhook would answer 500, the worker would retry, and it would fail the same
way every time.
"""
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from html.parser import HTMLParser

from django.utils import timezone

MSGID = re.compile(r"<[^<>\s]+>")
AUTH = re.compile(r"\b(spf|dkim|dmarc)\s*=\s*([a-z]+)", re.I)
MAX_ATTACHMENTS = 50


@dataclass
class Part:
    filename: str
    content_type: str
    data: bytes
    content_id: str = ""


@dataclass
class Parsed:
    message_id: str
    in_reply_to: str = ""
    references: list = field(default_factory=list)
    subject: str = ""
    from_name: str = ""
    from_email: str = ""
    reply_to: list = field(default_factory=list)
    to: list = field(default_factory=list)
    cc: list = field(default_factory=list)
    date: datetime | None = None
    text: str = ""
    html: str = ""
    attachments: list = field(default_factory=list)
    auth: dict = field(default_factory=dict)

    @property
    def thread_ids(self):
        """Message-IDs this one answers, the most specific first."""
        ids = [self.in_reply_to] if self.in_reply_to else []
        ids += [r for r in reversed(self.references) if r not in ids]
        return ids


# ------------------------------------------------------------------ headers
def _raw_values(msg, name):
    """Header values without the strict parser, RFC 2047 words decoded."""
    out = []
    for key, value in msg.raw_items():
        if key.lower() == name.lower():
            try:
                out.append(str(make_header(decode_header(value))))
            except Exception:
                out.append(str(value))
    return out


def _header(msg, name):
    try:
        value = msg.get(name)
        text = "" if value is None else str(value)
    except Exception:
        values = _raw_values(msg, name)
        text = values[0] if values else ""
    return " ".join(text.split())


def _addresses(msg, name):
    out = []
    try:
        for header in msg.get_all(name, []):
            for address in getattr(header, "addresses", ()):
                if address.addr_spec and "@" in address.addr_spec:
                    out.append((address.display_name or "", address.addr_spec))
    except Exception:
        out = [(n, a) for n, a in getaddresses(_raw_values(msg, name)) if "@" in a]
    return out


def clean_message_id(value):
    """'<abc@x>' from whatever the header held. Over-long ones are hashed."""
    match = MSGID.search(value or "")
    found = match.group(0) if match else ""
    if len(found) > 255:
        found = f"<{hashlib.sha256(found.encode()).hexdigest()}@long.invalid>"
    return found


def _date(msg):
    """The Date header, unless it is missing, unreadable or in the future.

    Spam is routinely dated next year to sit at the top of an inbox, so a date
    ahead of now is replaced by now rather than believed.
    """
    try:
        value = parsedate_to_datetime(_header(msg, "Date"))
    except (TypeError, ValueError, IndexError):
        return None
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt_timezone.utc)
    if value > timezone.now() + timedelta(minutes=10):
        return None
    return value


def _auth_results(msg):
    """{'spf': 'pass', 'dkim': 'pass', 'dmarc': 'fail'} from the receiving
    server's verdict - the topmost Authentication-Results header, which is the
    one our own receiving server (Cloudflare) added."""
    for name in ("Authentication-Results", "ARC-Authentication-Results"):
        for value in _raw_values(msg, name):
            found = AUTH.findall(value)
            if not found:
                continue
            results = {}
            for method, result in found:
                method, result = method.lower(), result.lower()
                # Several DKIM signatures: one passing is a pass.
                if results.get(method) != "pass":
                    results[method] = result
            return results
    return {}


# --------------------------------------------------------------------- bodies
def _text_content(part):
    try:
        content = part.get_content()
        if isinstance(content, str):
            return content
    except Exception:
        pass
    payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def _body(msg, kind):
    try:
        return msg.get_body(preferencelist=(kind,))
    except Exception:
        return None


def _leaves(part):
    """Every leaf part, treating an attached email as one leaf (an .eml)."""
    if part.get_content_type() == "message/rfc822":
        yield part
    elif part.is_multipart():
        for sub in part.iter_parts():
            yield from _leaves(sub)
    else:
        yield part


EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
              "image/webp": ".webp", "application/pdf": ".pdf",
              "text/calendar": ".ics", "message/rfc822": ".eml",
              "text/plain": ".txt", "text/html": ".html"}


def _attachment(part, index):
    ctype = part.get_content_type()
    if ctype == "message/rfc822":
        payload = part.get_payload()
        inner = payload[0] if isinstance(payload, list) and payload else payload
        try:
            data = inner.as_bytes()
        except Exception:
            data = b""
        name = part.get_filename() or f"{_header(inner, 'Subject') or 'forwarded'}.eml"
    else:
        data = part.get_payload(decode=True) or b""
        name = part.get_filename()
    if not name:
        name = f"attachment-{index}{EXTENSIONS.get(ctype, '')}"
    cid = (part.get("Content-ID") or "").strip().strip("<>")
    return Part(filename=str(name), content_type=ctype, data=data, content_id=cid)


def parse(raw):
    msg = BytesParser(policy=policy.default).parsebytes(raw)

    senders = _addresses(msg, "From")
    from_name, from_email = senders[0] if senders else ("", "")
    message_id = clean_message_id(_header(msg, "Message-ID"))
    if not message_id:
        message_id = f"<{hashlib.sha256(raw).hexdigest()}@received.invalid>"

    parsed = Parsed(
        message_id=message_id,
        in_reply_to=clean_message_id(_header(msg, "In-Reply-To")),
        references=[m for m in MSGID.findall(_header(msg, "References")) if len(m) <= 255],
        subject=_header(msg, "Subject"),
        from_name=from_name,
        from_email=from_email.strip(),
        reply_to=_addresses(msg, "Reply-To"),
        to=_addresses(msg, "To"),
        cc=_addresses(msg, "Cc"),
        date=_date(msg),
        auth=_auth_results(msg),
    )

    text_part, html_part = _body(msg, "plain"), _body(msg, "html")
    parsed.text = _text_content(text_part) if text_part is not None else ""
    parsed.html = _text_content(html_part) if html_part is not None else ""

    extra_text = []
    for index, leaf in enumerate(_leaves(msg), start=1):
        if leaf is text_part or leaf is html_part:
            continue
        unnamed_text = (leaf.get_content_maintype() == "text" and not leaf.get_filename()
                        and leaf.get_content_disposition() != "attachment")
        if unnamed_text:
            # Some clients split one body around an inline image into several
            # text parts. Keep the plain ones rather than lose the words.
            if leaf.get_content_type() == "text/plain":
                extra_text.append(_text_content(leaf))
            continue
        if len(parsed.attachments) < MAX_ATTACHMENTS:
            parsed.attachments.append(_attachment(leaf, index))
    if extra_text:
        parsed.text = "\n\n".join([parsed.text, *extra_text]).strip()
    return parsed


# ------------------------------------------------------------- html -> text
class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "li", "tr", "table", "blockquote", "section", "article",
             "header", "footer", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "hr"}
    SKIP = {"script", "style", "head", "title"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skipping = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping += 1
        elif tag == "br" or tag in self.BLOCK:
            self.out.append("\n")
            if tag == "li":
                self.out.append("• ")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skipping = max(0, self.skipping - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.out.append(re.sub(r"\s+", " ", data))


def html_to_text(html):
    """Readable plain text out of an HTML email, for previews and quoting."""
    extractor = _TextExtractor()
    try:
        extractor.feed(html or "")
        extractor.close()
    except Exception:
        pass
    lines = [line.strip() for line in "".join(extractor.out).splitlines()]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
