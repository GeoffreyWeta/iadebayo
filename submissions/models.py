"""One model per form in the spec. All reviewable in Django admin."""
from django.db import models


class TimestampedSubmission(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed = models.BooleanField(default=False, help_text="Tick once the team has handled this")

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class ContactMessage(TimestampedSubmission):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()

    def __str__(self):
        return f"{self.name} — {self.subject}"


class NewsletterSubscriber(TimestampedSubmission):
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.email


class EmbarkApplication(TimestampedSubmission):
    STATUS_CHOICES = [("student", "Undergraduate student"), ("graduate", "Recent graduate")]
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=32)
    country = models.CharField(max_length=80)
    city = models.CharField(max_length=80)
    applicant_status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    institution = models.CharField("University / institution", max_length=160)
    business_name = models.CharField(max_length=160)
    business_description = models.TextField(help_text="What the business does and its traction so far")
    business_sector = models.CharField(max_length=120)
    motivation = models.TextField("Why do you want to join Embark?")

    def __str__(self):
        return f"{self.name} — {self.business_name}"


class FacultyApplication(TimestampedSubmission):
    OPTION_CHOICES = [("facilitator", "Facilitator"), ("mentor", "Mentor"), ("both", "Both")]
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=32)
    email = models.EmailField()
    faculty_option = models.CharField(max_length=20, choices=OPTION_CHOICES)
    country = models.CharField(max_length=80)
    city = models.CharField(max_length=80)
    motivation = models.TextField("Your motivation")
    about = models.TextField("Tell us a little about you")
    linkedin = models.URLField("Your LinkedIn", blank=True)
    instagram = models.CharField("Your IG", max_length=120, blank=True)

    def __str__(self):
        return f"{self.name} ({self.get_faculty_option_display()})"


class VolunteerApplication(TimestampedSubmission):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=32)
    email = models.EmailField()
    skills = models.CharField(max_length=200)
    country = models.CharField(max_length=80)
    city = models.CharField(max_length=80)
    motivation = models.TextField("Your motivation")
    about = models.TextField("About you")
    linkedin = models.URLField("LinkedIn", blank=True)
    instagram = models.CharField("IG", max_length=120, blank=True)

    def __str__(self):
        return self.name


class PartnershipInquiry(TimestampedSubmission):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=32)
    email = models.EmailField()
    organization = models.CharField("Organization name", max_length=160)
    website = models.URLField(blank=True)
    country = models.CharField(max_length=80)
    city = models.CharField(max_length=80)
    proposal = models.TextField("How do you intend to partner with us?")

    def __str__(self):
        return f"{self.organization} ({self.name})"
