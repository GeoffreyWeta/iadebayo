import os
import shutil
import tempfile
import zipfile

from django.contrib import admin, messages
from django.http import FileResponse
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django.utils.html import format_html

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
                    "video_link", "created_at", "reviewed")
    list_filter = ("reviewed", "applicant_status", "gender", "device",
                   "reliable_internet", "heard_about", "country", "created_at")
    readonly_fields = ("created_at", "limiting_factors", "video_download")
    actions = ["download_videos_zip"]
    fieldsets = (
        ("Section A — About the applicant", {
            "fields": ("name", "gender", "applicant_status", "email",
                       ("phone_code", "phone"),
                       "date_of_birth", "institution", ("city", "state", "country"),
                       "social_handle"),
        }),
        ("Section B — Business information", {
            "description": "The video downloads through the button below. The "
                           "“Currently” link on the upload box is deliberately "
                           "blocked — applicant videos aren’t public files.",
            "fields": ("business_name", "video_download", "business_video",
                       "year_established",
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

    # ------------------------------------------------------- video downloads
    @admin.display(description="Applicant video")
    def video_download(self, obj):
        if not obj.pk or not obj.business_video:
            return "— no video uploaded —"
        try:
            size = filesizeformat(obj.business_video.size)
        except (FileNotFoundError, OSError):
            return format_html(
                '<span style="color:#b91c1c">Missing from storage: {}</span>',
                obj.business_video.name)
        return format_html(
            '<a class="button" href="{}">⬇ Download video</a>'
            '<span style="margin-left:.75rem;color:#666">{} — {}</span>',
            reverse("submissions:download_video", args=[obj.pk]),
            os.path.basename(obj.business_video.name), size)

    @admin.display(description="Video")
    def video_link(self, obj):
        if not obj.business_video:
            return "—"
        return format_html('<a href="{}">Download</a>',
                           reverse("submissions:download_video", args=[obj.pk]))

    @admin.action(description="Download videos for selected applications (ZIP)")
    def download_videos_zip(self, request, queryset):
        with_video = [a for a in queryset if a.business_video]
        if not with_video:
            self.message_user(request, "None of the selected applications has a video.",
                              messages.WARNING)
            return None

        # A tempfile rather than BytesIO: sixty 60 MB clips would not fit in the
        # droplet's RAM. ZIP_STORED because video is already compressed —
        # deflating it just burns CPU on a one-core box for no size win.
        archive_file = tempfile.TemporaryFile()
        missing = []
        with zipfile.ZipFile(archive_file, "w", zipfile.ZIP_STORED) as archive:
            for application in with_video:
                try:
                    with application.business_video.open("rb") as source, \
                            archive.open(application.video_download_name, "w") as target:
                        shutil.copyfileobj(source, target)
                except (FileNotFoundError, OSError):
                    missing.append(str(application))

        if len(missing) == len(with_video):
            archive_file.close()
            self.message_user(request, "Every selected video is missing from storage.",
                              messages.ERROR)
            return None
        if missing:
            self.message_user(
                request, "Left out of the ZIP — missing from storage: "
                         + "; ".join(missing), messages.WARNING)

        archive_file.seek(0)
        return FileResponse(archive_file, as_attachment=True,
                            filename="embark-application-videos.zip")


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
