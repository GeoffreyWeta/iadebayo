from datetime import date

from django import forms
from . import models


class BaseStyledForm(forms.ModelForm):
    """Adds consistent CSS classes + honeypot spam trap to every form."""
    website_url = forms.CharField(required=False, widget=forms.HiddenInput)  # honeypot

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name == "website_url":
                continue
            # Radio / checkbox groups: no class here. Django copies widget.attrs
            # onto every option input, so styling hangs off the wrapping
            # .form-field.is-choices instead. (RadioSelect is not a Select —
            # check it first.)
            if isinstance(field.widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)):
                continue
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check"
                continue
            css = "form-input"
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("rows", 4)
                field.widget.attrs.setdefault("placeholder", "")  # label is enough
                css = "form-input form-textarea"
            elif isinstance(field.widget, forms.Select):
                css = "form-input form-select"
                self._label_blank_choice(field)
            elif isinstance(field.widget, forms.FileInput):
                css = "form-input form-file"
            field.widget.attrs["class"] = css
            if not isinstance(field.widget, (forms.Select, forms.FileInput)):
                field.widget.attrs.setdefault("placeholder", field.label)

    @staticmethod
    def _label_blank_choice(field):
        """Replace Django's '---------' placeholder with a readable prompt."""
        choices = list(field.widget.choices)
        if choices and choices[0][0] in ("", None):
            choices[0] = ("", "Select…")
            field.widget.choices = choices

    def clean_website_url(self):
        if self.cleaned_data.get("website_url"):
            raise forms.ValidationError("Spam detected.")
        return ""


class SectionedFormMixin:
    """Splits a long form into named steps the template can render as fieldsets.

    Subclasses define SECTIONS as [(title, blurb, [field names])] and, optionally,
    REQUIRED as the set of field names an applicant must answer (the models stay
    permissive so historic rows remain valid).
    """
    SECTIONS: list = []
    REQUIRED: set = set()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in self.REQUIRED:
            self.fields[name].required = True

    # Widgets that need the full width of the two-column grid.
    WIDE_WIDGETS = (forms.Textarea, forms.RadioSelect, forms.CheckboxSelectMultiple,
                    forms.CheckboxInput, forms.FileInput)

    def sections(self):
        """Yield one dict per step, with the layout already decided.

        Deciding 'is this a radio group / full width / a lone tickbox' here
        keeps the template free of widget introspection, which the Django
        template language does badly (a missing attribute resolves to '').
        """
        total = len(self.SECTIONS)
        for index, (title, blurb, names) in enumerate(self.SECTIONS, start=1):
            rows = [self._row(n) for n in names]
            yield {
                "index": index,
                "total": total,
                "title": title,
                "blurb": blurb,
                "rows": rows,
                "has_errors": any(r["field"].errors for r in rows),
            }

    def _row(self, name):
        bound = self[name]
        widget = bound.field.widget
        return {
            "field": bound,
            "full": isinstance(widget, self.WIDE_WIDGETS),
            "choices": isinstance(widget, (forms.RadioSelect, forms.CheckboxSelectMultiple)),
            "single_check": isinstance(widget, forms.CheckboxInput),
        }


class ContactForm(BaseStyledForm):
    class Meta:
        model = models.ContactMessage
        fields = ["name", "email", "subject", "message"]


class NewsletterForm(forms.ModelForm):
    class Meta:
        model = models.NewsletterSubscriber
        fields = ["email"]
        widgets = {"email": forms.EmailInput(attrs={"class": "form-input", "placeholder": "Your email address"})}

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if models.NewsletterSubscriber.objects.filter(email=email).exists():
            raise forms.ValidationError("You're already subscribed — thank you!")
        return email


class EmbarkApplicationForm(SectionedFormMixin, BaseStyledForm):
    """The three-section Embark application."""

    SECTIONS = [
        ("Section A — About the applicant",
         "Tell us who you are. Use an email address you check often; that is where "
         "every update about your application will go.",
         ["name", "gender", "applicant_status", "email", "phone", "date_of_birth",
          "institution", "city", "state", "country", "social_handle"]),
        ("Section B — Business information",
         "Now the venture itself. The one-minute video matters as much as the "
         "written answers — filmed on a phone is perfectly fine.",
         ["business_name", "business_video", "year_established", "revenue_last_year",
          "revenue_this_year", "major_challenge", "growth_limits", "growth_limits_other"]),
        ("Commitment",
         "Embark runs on live sessions, assignments, mentorship, networking, and a "
         "capstone project. These answers tell us you can see it through.",
         ["device", "will_participate", "reliable_internet", "heard_about",
          "heard_about_other", "media_consent"]),
    ]

    REQUIRED = {
        "name", "gender", "applicant_status", "email", "phone", "date_of_birth",
        "institution", "city", "country",
        "business_name", "business_video", "year_established", "major_challenge",
        "growth_limits",
        "device", "will_participate", "reliable_internet", "heard_about", "media_consent",
    }

    # Ticked checkboxes come in as a list and are stored comma-separated.
    growth_limits = forms.MultipleChoiceField(
        label="What do you believe is the biggest factor limiting the growth of your "
              "business right now?",
        choices=models.EmbarkApplication.GROWTH_LIMIT_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        help_text="Tick everything that applies.",
        error_messages={"required": "Please tick at least one factor."})

    class Meta:
        model = models.EmbarkApplication
        fields = [
            "name", "gender", "applicant_status", "email", "phone", "date_of_birth",
            "institution", "city", "state", "country", "social_handle",
            "business_name", "business_video", "year_established", "revenue_last_year",
            "revenue_this_year", "major_challenge", "growth_limits", "growth_limits_other",
            "device", "will_participate", "reliable_internet", "heard_about",
            "heard_about_other", "media_consent",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "year_established": forms.NumberInput(attrs={"min": 1950}),
            "device": forms.RadioSelect,
            "will_participate": forms.RadioSelect,
            "reliable_internet": forms.RadioSelect,
            "heard_about": forms.RadioSelect,
        }
        labels = {
            "heard_about": "How did you hear about Embark?",
            "will_participate": "Are you willing to actively participate throughout the programme?",
            "reliable_internet": "Do you have reliable internet access for live virtual sessions?",
            "device": "Which device will you primarily use to participate?",
            "media_consent": "I agree that photos and video recorded during the programme "
                             "may be used by IADEBAYO Foundation.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["media_consent"].error_messages["required"] = (
            "We need this consent to enrol you — photos and video are part of how the "
            "programme is documented.")
        # Nothing in the future: no unborn applicants, no unfounded businesses.
        today = date.today()
        self.fields["date_of_birth"].widget.attrs["max"] = today.isoformat()
        self.fields["year_established"].widget.attrs["max"] = today.year

    def clean_growth_limits(self):
        """MultipleChoiceField gives a list; the model column holds a string."""
        return ",".join(self.cleaned_data.get("growth_limits") or [])

    def clean_date_of_birth(self):
        dob = self.cleaned_data["date_of_birth"]
        if dob and dob > date.today():
            raise forms.ValidationError("That date is in the future.")
        return dob

    def clean_year_established(self):
        year = self.cleaned_data["year_established"]
        if year and year > date.today().year:
            raise forms.ValidationError("That year is in the future.")
        return year

    def clean(self):
        cleaned = super().clean()
        if "other" in (cleaned.get("growth_limits") or "").split(",") \
                and not cleaned.get("growth_limits_other"):
            self.add_error("growth_limits_other",
                           "You ticked “Other” above — please tell us what it is.")
        if cleaned.get("heard_about") == "other" and not cleaned.get("heard_about_other"):
            self.add_error("heard_about_other",
                           "You chose “Other” — please tell us where you heard about Embark.")
        if cleaned.get("will_participate") == "no":
            self.add_error("will_participate",
                           "Embark is a commitment-based programme, so we can only accept "
                           "applicants who can take part throughout.")
        return cleaned


class FacultyApplicationForm(BaseStyledForm):
    class Meta:
        model = models.FacultyApplication
        fields = ["name", "phone", "email", "faculty_option", "country", "city",
                  "motivation", "about", "linkedin", "instagram"]


class VolunteerApplicationForm(BaseStyledForm):
    class Meta:
        model = models.VolunteerApplication
        fields = ["name", "phone", "email", "skills", "country", "city",
                  "motivation", "about", "linkedin", "instagram"]


class PartnershipInquiryForm(BaseStyledForm):
    class Meta:
        model = models.PartnershipInquiry
        fields = ["name", "phone", "email", "organization", "website", "country", "city", "proposal"]
