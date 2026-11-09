"""Which addresses are ours: the ones staff write from, and the site's own.

STAFF_MAILBOXES in settings is the list a staff member chooses From in. "Ours"
is wider: it also covers the site's automatic sender and the team inbox, so a
copy of our own mail is never filed as somebody else writing to us.
"""
from email.utils import getaddresses, parseaddr

from django.conf import settings


def bare(value):
    """'Embark <Embark@X.org>' -> 'embark@x.org'."""
    return parseaddr(value or "")[1].strip().lower()


def display(name, address):
    """Name <address>, unencoded: for screens. Django encodes it for sending."""
    name = (name or "").replace('"', "").strip()
    return f"{name} <{address}>" if name else address


def configured():
    """[(bare address, display form)] in settings order, without repeats."""
    seen, out = set(), []
    for value in settings.STAFF_MAILBOXES:
        name, address = parseaddr(value)
        key = address.strip().lower()
        if "@" not in key or key in seen:
            continue
        seen.add(key)
        out.append((key, display(name, address.strip())))
    return out


def default():
    boxes = configured()
    return boxes[0][0] if boxes else bare(settings.DEFAULT_FROM_EMAIL)


def formatted(address):
    """The configured display form of one of our addresses, or it unchanged."""
    key = bare(address)
    for box, shown in configured():
        if box == key:
            return shown
    return address


def is_ours(address):
    key = bare(address)
    return bool(key) and key in {box for box, _ in configured()} | {
        bare(settings.DEFAULT_FROM_EMAIL),
        bare(settings.FOUNDATION_NOTIFY_EMAIL),
        bare(settings.EMBARK_FROM_EMAIL),
        bare(settings.EMBARK_REPLY_TO),
    }


def is_automatic(address):
    """The site's own no-reply sender (form notifications, acknowledgements).

    Mail from it reaching the inbox is the site notifying the team inbox about
    a submission - already in the staff area under Submissions, so not a
    conversation.
    """
    return bare(address) == bare(settings.DEFAULT_FROM_EMAIL)


def split(values):
    """[(name, address)] out of header-style strings, dropping non-addresses."""
    return [(n, a.strip()) for n, a in getaddresses([v for v in values if v])
            if "@" in a]
