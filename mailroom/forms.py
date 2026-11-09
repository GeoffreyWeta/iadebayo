"""The one form staff write mail with: a new message and a reply are the same."""
import re
from email.utils import parseaddr

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.template.defaultfilters import filesizeformat

from core import mailmerge

from . import mailboxes

# Commas and semicolons separate addresses, except inside "quoted, names".
SEPARATOR = re.compile(r"""[,;](?=(?:[^"]*"[^"]*")*[^"]*$)""")
MAX_ADDRESSES = 50
MAX_FILES = 10


class AddressListField(forms.CharField):
    """'ada@x.org, Chidi Okafor <chidi@y.com>' -> a list, every address checked.

    Bad addresses are named in the error rather than dropped: a recipient who
    silently fell off the list is a person who never hears back.
    """

    def clean(self, value):
        value = super().clean(value)
        if not value:
            return []
        found, bad, seen = [], [], set()
        for token in SEPARATOR.split(value):
            token = token.strip()
            if not token:
                continue
            name, address = parseaddr(token)
            address = address.strip()
            try:
                validate_email(address)
            except ValidationError:
                bad.append(token)
                continue
            if address.lower() not in seen:
                seen.add(address.lower())
                found.append(mailboxes.display(name, address))
        if bad:
            raise ValidationError("Not an email address: %(bad)s",
                                  params={"bad": ", ".join(bad)})
        if not found and self.required:
            raise ValidationError(self.error_messages["required"])
        if len(found) > MAX_ADDRESSES:
            raise ValidationError(f"At most {MAX_ADDRESSES} addresses on one message.")
        return found


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        items = data if isinstance(data, (list, tuple)) else [data]
        return [f for f in (single(item, initial) for item in items if item) if f]


def _input(**attrs):
    return forms.TextInput(attrs={"class": "staff-input", "autocomplete": "off", **attrs})


class MessageForm(forms.Form):
    from_address = forms.ChoiceField(label="From")
    to = AddressListField(label="To", widget=_input(list="mail-contacts"))
    cc = AddressListField(label="Cc", required=False, widget=_input(list="mail-contacts"))
    bcc = AddressListField(label="Bcc", required=False, widget=_input(list="mail-contacts"))
    subject = forms.CharField(max_length=255, widget=_input())
    body = forms.CharField(label="Message", widget=forms.Textarea(
        attrs={"class": "staff-input staff-textarea", "rows": 14}))
    attachments = MultipleFileField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["from_address"].choices = mailboxes.configured()
        self.fields["from_address"].widget.attrs["class"] = "staff-input staff-select"

    def clean_attachments(self):
        files = self.cleaned_data.get("attachments") or []
        if len(files) > MAX_FILES:
            raise ValidationError(f"At most {MAX_FILES} files on one message.")
        limit = settings.MAIL_ATTACHMENTS_MAX_BYTES
        if sum(f.size for f in files) > limit:
            raise ValidationError(
                f"Attachments add up to more than {filesizeformat(limit)}. "
                "Share large files as a link instead.")
        return files

    def clean(self):
        cleaned = super().clean()
        bad = mailmerge.unknown(cleaned.get("subject", ""), cleaned.get("body", ""))
        if bad:
            raise ValidationError(
                "This site cannot fill in: %(bad)s. Fix or remove it before sending.",
                params={"bad": ", ".join(f"{{{{ {b} }}}}" for b in bad)})
        return cleaned
