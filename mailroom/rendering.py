"""How staff mail looks going out, and how received mail is shown to staff.

Received HTML is written by whoever sent it, so it is never put into a staff
page as markup. It is shown inside an <iframe sandbox srcdoc="..."> with no
script permission (see templates/mailroom/thread.html), and the document handed
to that frame carries its own Content-Security-Policy that blocks every remote
fetch by default. That stops scripts, forms, tracking pixels and "this email
was opened" beacons; remote images load only when a staff member asks for them
on that one message.
"""
import base64
import re

from django.template.loader import render_to_string
from django.utils import timezone

from submissions.email_presentation import paragraph_parts

from .mailboxes import display

ON_WROTE = re.compile(r"^On\b.{0,300}\bwrote:\s*$", re.I)
ORIGINAL = re.compile(r"^-{2,}\s*Original Message\s*-{2,}$", re.I)
OUTLOOK_RULE = re.compile(r"^_{10,}$")
META_REFRESH = re.compile(r"<meta\b[^>]*http-equiv\s*=\s*[\"']?\s*refresh[^>]*>", re.I)
REMOTE = re.compile(r"""(?:src|background)\s*=\s*["']?\s*https?:|url\(\s*["']?\s*https?:""", re.I)
INLINE_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
INLINE_MAX_BYTES = 8 * 1024 * 1024


def split_quote(text):
    """(what they wrote, the history they quoted) - for folding the history away.

    Recognises the shapes the common clients use: "On <date>, <name> wrote:"
    (Gmail, Apple Mail; sometimes wrapped over two lines), Outlook's rule and
    "-----Original Message-----", and a trailing block of "> " lines. If the
    whole message is quote, nothing is folded - hiding all of it helps nobody.
    """
    text = (text or "").strip()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        here = line.strip()
        after = lines[i + 1].strip() if i + 1 < len(lines) else ""
        starts = (ON_WROTE.match(here)
                  or (here.startswith("On ") and ON_WROTE.match(f"{here} {after}"))
                  or ORIGINAL.match(here)
                  or (OUTLOOK_RULE.match(here) and after.lower().startswith("from:")))
        if starts:
            fresh = "\n".join(lines[:i]).strip()
            if fresh:
                return fresh, "\n".join(lines[i:]).strip()
            break

    start = len(lines)
    while start > 0 and (lines[start - 1].startswith(">") or not lines[start - 1].strip()):
        start -= 1
    if any(line.startswith(">") for line in lines[start:]):
        fresh = "\n".join(lines[:start]).strip()
        if fresh:
            return fresh, "\n".join(lines[start:]).strip()
    return text, ""


def quote_for(message):
    """The "On ..., X wrote:" header and text a reply carries below it."""
    when = timezone.localtime(message.sent_at)
    who = display(message.from_name, message.from_email)
    return {
        "header": f"On {when:%a} {when.day} {when:%b %Y} at {when:%H:%M}, {who} wrote:",
        "text": message.body_text().strip(),
    }


def outgoing_text(body, quote=None):
    text = (body or "").rstrip()
    if quote and quote["text"]:
        quoted = "\n".join(f"> {line}" if line else ">" for line in quote["text"].splitlines())
        text = f"{text}\n\n{quote['header']}\n{quoted}"
    return text


def outgoing_html(body, quote=None):
    """A plain, personal-looking HTML part: paragraphs, links, **bold**.

    Deliberately not the Embark banner layout the applicant decision emails
    use. A reply in a conversation that arrives dressed as a newsletter reads
    as a mass mailing, and is filtered like one.
    """
    return render_to_string("mailroom/email.html", {
        "paragraphs": paragraph_parts(body),
        "quote": quote if quote and quote["text"] else None,
    })


def has_remote_content(html):
    return bool(REMOTE.search(html or ""))


def _inline_images(html, attachments):
    """Swap cid: references for data: URIs, so inline images show without any
    request leaving the frame. Returns (html, ids of the attachments used)."""
    used, budget = set(), INLINE_MAX_BYTES
    for attachment in attachments:
        cid = attachment.content_id
        if not cid or attachment.content_type not in INLINE_IMAGE_TYPES:
            continue
        pattern = re.compile(r"cid:" + re.escape(cid), re.I)
        if not pattern.search(html) or attachment.size > budget:
            continue
        try:
            with attachment.file.open("rb") as handle:
                data = handle.read()
        except (FileNotFoundError, OSError, ValueError):
            continue
        budget -= len(data)
        uri = f"data:{attachment.content_type};base64,{base64.b64encode(data).decode()}"
        html = pattern.sub(lambda _: uri, html)
        used.add(attachment.pk)
    return html, used


def viewer_document(message, attachments=(), allow_remote=False):
    """The document for a received message's sandboxed frame, and the ids of
    attachments it already shows inline (so the list below need not repeat
    them)."""
    html = META_REFRESH.sub("", message.html or "")
    html, used = _inline_images(html, attachments)
    images = "data: https: http:" if allow_remote else "data:"
    policy = (f"default-src 'none'; img-src {images}; style-src 'unsafe-inline'; "
              "font-src data:; form-action 'none'")
    document = (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<meta http-equiv=\"Content-Security-Policy\" content=\"{policy}\">"
        "<meta name=\"referrer\" content=\"no-referrer\">"
        "<base target=\"_blank\">"
        "<style>html,body{margin:0;padding:0;background:#fff}"
        "body{padding:2px;color:#20262d;font:14px/1.55 -apple-system,BlinkMacSystemFont,"
        "'Segoe UI',sans-serif;overflow-wrap:anywhere}"
        "img{max-width:100%;height:auto}table{max-width:100%}</style>"
        "</head><body>" + html + "</body></html>")
    return document, used
