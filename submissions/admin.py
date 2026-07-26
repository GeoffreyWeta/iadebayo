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
            "fields": ("name", "gender", "applicant_status", "email", "phone",
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


@admin.register(models.FacultyApplication)
class FacultyAdmin(SubmissionAdmin):
    search_fields = ("name", "email")
    list_filter = ("reviewed", "faculty_option")


@admin.register(models.VolunteerApplication)
class VolunteerAdmin(SubmissionAdmin):
    search_fields = ("name", "email", "skills")


@admin.register(models.PartnershipInquiry)
class PartnerAdmin(SubmissionAdmin):
    search_fields = ("organization", "name", "email")


@admin.register(models.NewsletterSubscriber)
class NewsletterAdmin(SubmissionAdmin):
    search_fields = ("email",)
