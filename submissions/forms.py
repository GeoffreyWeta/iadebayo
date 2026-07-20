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
            css = "form-input"
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("rows", 4)
                css = "form-input form-textarea"
            elif isinstance(field.widget, forms.Select):
                css = "form-input form-select"
            field.widget.attrs["class"] = css
            field.widget.attrs.setdefault("placeholder", field.label)

    def clean_website_url(self):
        if self.cleaned_data.get("website_url"):
            raise forms.ValidationError("Spam detected.")
        return ""


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


class EmbarkApplicationForm(BaseStyledForm):
    class Meta:
        model = models.EmbarkApplication
        fields = ["name", "email", "phone", "country", "city", "applicant_status",
                  "institution", "business_name", "business_sector", "business_description", "motivation"]


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
