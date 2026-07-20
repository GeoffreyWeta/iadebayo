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
    search_fields = ("name", "email", "business_name", "country")
    list_filter = ("reviewed", "applicant_status", "country")


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
