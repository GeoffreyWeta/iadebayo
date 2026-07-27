from django.contrib import admin
from . import models


class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "created_at", "reviewed")
    list_filter = ("reviewed", "created_at")
    list_editable = ("reviewed",)
    readonly_fields = ("created_at",)


@admin.register(models.ContactMessage)
class ContactAdmin(SubmissionAdmin):
    search_fields = ("name", "email", "subject")


@admin.register(models.EmbarkApplication)
class EmbarkAdmin(SubmissionAdmin):
    search_fields = ("name", "email", "business_name", "country", "institution")
    list_display = ("name", "business_name", "applicant_status", "country",
                    "created_at", "reviewed")
    list_filter = ("reviewed", "applicant_status", "gender", "device",
                   "reliable_internet", "heard_about", "country", "created_at")
    readonly_fields = ("created_at", "limiting_factors")
    fieldsets = (
        ("Section A — About the applicant", {
            "fields": ("name", "gender", "applicant_status", "email",
                       ("phone_code", "phone"),
                       "date_of_birth", "institution", ("city", "state", "country"),
                       "social_handle"),
        }),
        ("Section B — Business information", {
            "fields": ("business_name", "business_video", "year_established",
                       ("revenue_last_year", "revenue_this_year"), "major_challenge",
                       "limiting_factors", "growth_limits", "growth_limits_other"),
        }),
        ("Commitment", {
            "fields": ("device", "will_participate", "reliable_internet",
                       "heard_about", "heard_about_other", "media_consent"),
        }),
        ("Review", {"fields": ("reviewed", "created_at")}),
        ("Legacy answers (2025 form)", {
            "classes": ("collapse",),
            "fields": ("business_description", "business_sector", "motivation"),
        }),
    )

    @admin.display(description="Limiting factors (as ticked)")
    def limiting_factors(self, obj):
        return obj.growth_limits_display or "—"


class PhoneColumnMixin:
    """Shows the dialling code and number as one readable value."""

    @admin.display(description="Phone")
    def phone_display(self, obj):
        return obj.phone_display or "—"


@admin.register(models.FacultyApplication)
class FacultyAdmin(PhoneColumnMixin, SubmissionAdmin):
    search_fields = ("name", "email", "country")
    list_display = ("name", "faculty_option", "phone_display", "country",
                    "created_at", "reviewed")
    list_filter = ("reviewed", "faculty_option", "country", "created_at")


@admin.register(models.VolunteerApplication)
class VolunteerAdmin(PhoneColumnMixin, SubmissionAdmin):
    search_fields = ("name", "email", "skills", "country")
    list_display = ("name", "area", "skills", "phone_display", "country",
                    "created_at", "reviewed")
    list_filter = ("reviewed", "area", "country", "created_at")


@admin.register(models.PartnershipInquiry)
class PartnerAdmin(PhoneColumnMixin, SubmissionAdmin):
    search_fields = ("organization", "name", "email", "country")
    list_display = ("organization", "name", "phone_display", "country",
                    "created_at", "reviewed")
    list_filter = ("reviewed", "country", "created_at")


@admin.register(models.NewsletterSubscriber)
class NewsletterAdmin(SubmissionAdmin):
    search_fields = ("email",)
