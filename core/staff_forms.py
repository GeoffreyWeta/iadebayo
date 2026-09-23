"""The edit form behind every `/staff/` content collection.

One ModelForm, built at request time from the `Collection` the URL named. What
this adds over `modelform_factory` on its own is the part a team member actually
feels:

  * **Native date and time pickers.** Django's default renders a DateTimeField
    as a text box that wants "2026-09-15 14:30" and rejects everything else. On
    a phone that is a guessing game. `type="datetime-local"` gives the device's
    own picker and the browser does the formatting.
  * **Widget classes**, so the fields look like the sign-in form rather than
    like unstyled HTML, without a class attribute repeated in every template.
  * **Groups**, so `form.grouped` yields the titled blocks declared on the
    collection instead of one undifferentiated stack of inputs.

Model `help_text` is rendered through `|safe` in the template, exactly as the
public form templates already do (see includes/form_section.html) - a couple of
fields carry deliberate markup, most notably EmbarkApplication.business_video_url.
Nothing user-supplied ever reaches help text; it is all written in models.py.
"""
from django import forms
from django.forms import modelform_factory

DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%dT%H:%M"


class StaffModelForm(forms.ModelForm):
    """Base for every generated content form.

    `collection` is set by `form_class_for` so `grouped` can walk the declared
    groups. It is a class attribute rather than a constructor argument because
    Django instantiates forms in half a dozen places and each extra required
    argument is another call site to keep in step.
    """
    collection = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            self._dress(name, field)

    # ------------------------------------------------------------- appearance
    def _dress(self, name, field):
        widget = field.widget
        classes = ["staff-input"]

        if isinstance(widget, forms.CheckboxInput):
            classes = ["staff-check"]
        elif isinstance(widget, forms.Textarea):
            classes.append("staff-textarea")
            # 4 rows for a one-paragraph field, 12 for a write-up. Guessing from
            # the model's max_length is wrong for TextField (it has none), so
            # this keys off the name of the long-form fields instead.
            widget.attrs.setdefault(
                "rows", 12 if name in ("body", "story", "bio", "proposal") else 5)
        elif isinstance(widget, forms.Select):
            classes.append("staff-select")
        elif isinstance(widget, (forms.ClearableFileInput, forms.FileInput)):
            classes = ["staff-file"]
            if isinstance(field, forms.ImageField):
                widget.attrs.setdefault("accept", "image/*")
            widget.attrs.setdefault("data-file-preview", "")
        elif isinstance(widget, forms.DateTimeInput):
            widget.input_type = "datetime-local"
            widget.format = DATETIME_FORMAT
            field.input_formats = [DATETIME_FORMAT, *field.input_formats]
        elif isinstance(widget, forms.DateInput):
            widget.input_type = "date"
            widget.format = DATE_FORMAT
            field.input_formats = [DATE_FORMAT, *field.input_formats]
        elif isinstance(widget, forms.URLInput):
            widget.attrs.setdefault("placeholder", "https://")
        elif isinstance(widget, forms.NumberInput):
            classes.append("staff-input-narrow")

        existing = widget.attrs.get("class", "")
        widget.attrs["class"] = " ".join(filter(None, [existing, *classes]))

        # A required field is marked in the label, so tell the browser too - but
        # not for file inputs on an edit form, where the existing upload already
        # satisfies the requirement and `required` would refuse to submit.
        if field.required and not isinstance(widget, (forms.ClearableFileInput,
                                                      forms.FileInput)):
            widget.attrs.setdefault("required", "required")

        if name == "slug":
            widget.attrs.setdefault("data-slug-from", "title")

        # The order column is a position, not an answer. The model declares it
        # `default=0`, which makes it a *required* form field - so a team member
        # adding a milestone would have to invent a number before they could
        # save, and every new row would land at 0 and jump to the top. Optional
        # here, and filled in by `clean` and by staff_views._place_new_at_end.
        if self.collection and name == self.collection.order_field:
            field.required = False
            widget.attrs.pop("required", None)
            field.help_text = field.help_text or (
                "Lower numbers come first. Leave it blank to put this last - you "
                "can drag rows into place on the list afterwards.")

    def clean(self):
        """Blank order means "leave it where it is", never NULL.

        The column is NOT NULL, so an empty box has to resolve to something. For
        an existing row that is the order it already had; for a new one, 0, and
        `staff_views._place_new_at_end` then moves it to the end.
        """
        cleaned = super().clean()
        name = self.collection.order_field if self.collection else ""
        if name and name in self.fields and cleaned.get(name) is None:
            cleaned[name] = getattr(self.instance, name, None) or 0
        return cleaned

    # ----------------------------------------------------------------- layout
    def _preview(self, name):
        """What is already uploaded in this field, if anything.

        An edit form that says "Currently: promos/flier_3.png" and stops there is
        asking someone to remember which flier that was. For an image we can just
        show it; for anything else, the real filename and a link that opens it.
        """
        value = getattr(self.instance, name, None)
        if not value or not hasattr(value, "url"):
            return None
        try:
            url = value.url
        except ValueError:
            return None
        return {
            "url": url,
            "name": value.name.rsplit("/", 1)[-1],
            "is_image": isinstance(self.fields[name], forms.ImageField),
        }

    @property
    def grouped(self):
        """The form's fields as the collection's declared blocks.

        Each entry is the bound field plus whatever the template cannot work out
        for itself - currently the existing upload. Anything the collection
        forgot to list still gets rendered, in a final "Other" block: a field
        that exists on the form but appears in no group would otherwise be
        silently unfillable, which for a required field means a form that can
        never be saved and no way to see why.
        """
        def entry(name):
            return {"field": self[name], "preview": self._preview(name)}

        blocks, placed = [], set()
        for group in (self.collection.groups if self.collection else ()):
            fields = [entry(name) for name in group.fields if name in self.fields]
            if not fields:
                continue
            placed.update(group.fields)
            blocks.append({"title": group.title, "note": group.note, "fields": fields})

        leftover = [entry(name) for name in self.fields if name not in placed]
        if leftover:
            blocks.append({"title": "Other", "note": "", "fields": leftover})
        return blocks


def form_class_for(collection):
    """A ModelForm for this collection's editable fields."""
    return modelform_factory(
        collection.model,
        form=type(f"{collection.model.__name__}StaffForm", (StaffModelForm,),
                  {"collection": collection}),
        fields=list(collection.form_fields),
    )


class ApplicantEmailForm(forms.Form):
    """The message about to be sent to one applicant.

    Not a ModelForm: nothing here is saved. The subject and body arrive already
    substituted for this applicant (the compose view renders the chosen template
    before it ever reaches the browser), so what a staff member reads in these
    two boxes is what the applicant receives - no second pass, no surprise.

    Placeholders are still substituted once more on send, so that someone who
    types `{{ first_name }}` into the box by hand gets what they expect. By then
    the rendered text has none left, which makes the second pass a no-op in the
    ordinary case.
    """
    subject = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"class": "staff-input"}))
    body = forms.CharField(
        widget=forms.Textarea(attrs={"class": "staff-input staff-textarea", "rows": 18}))

    def clean(self):
        """Refuse a placeholder nothing can fill, rather than mail it out.

        EmailTemplate.clean already blocks these when the template is saved, but
        this box is free text - someone can type one straight in here, and this
        is the last point before it is somebody's email.
        """
        cleaned = super().clean()
        from . import mailmerge
        bad = mailmerge.unknown(cleaned.get("subject", ""), cleaned.get("body", ""))
        if bad:
            raise forms.ValidationError(
                "This site cannot fill in: %(bad)s. Fix or remove it before sending."
                % {"bad": ", ".join(f"{{{{ {b} }}}}" for b in bad)})
        return cleaned
