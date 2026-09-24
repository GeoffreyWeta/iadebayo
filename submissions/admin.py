import csv
import os
import shutil
import tempfile
import zipfile

from django.contrib import admin, messages
from django.http import FileResponse, HttpResponse
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
                    "video_link", "created_at", "decision", "reviewed")
    list_filter = ("decision", "reviewed", "applicant_status", "gender", "device",
                   "reliable_internet", "heard_about", "country", "created_at")
    readonly_fields = ("created_at", "limiting_factors", "video_link_display",
                       "video_download")
    actions = ["download_videos_zip"]
    fieldsets = (
        ("Section A - About the applicant", {
            "fields": ("name", "gender", "applicant_status", "email",
                       ("phone_code", "phone"),
                       "date_of_birth", "institution", ("country", "state", "city"),
                       "linkedin", ("social_handle", "social_handle_2")),
        }),
        ("Section B - Business information", {
            "description": "Applicants link their video from Google Drive rather than "
                           "uploading it. The brief asks them to cover three things - who "
                           "they are, what the business does, and why they should be "
                           "chosen - so all three are fair to score. If the link does not "
                           "open for you, the applicant left sharing restricted and needs "
                           "an email asking them to set it to “Anyone with the link”.",
            "fields": ("business_name", "business_sector",
                       "video_link_display", "business_video_url",
                       ("business_website", "business_social_handle"),
                       "year_established",
                       ("revenue_last_year", "revenue_this_year"), "major_challenge",
                       "limiting_factors", "growth_limits", "growth_limits_other",
                       "entrepreneurship_view"),
        }),
        ("Commitment", {
            "fields": ("device", "will_participate", "reliable_internet",
                       "heard_about", "heard_about_other", "media_consent"),
        }),
        ("Review", {"fields": ("reviewed", "created_at")}),
        ("Legacy answers (earlier forms)", {
            "classes": ("collapse",),
            "description": "Applications submitted before 2026-08-01 uploaded the video "
                           "itself. Those files are still here and still download through "
                           "the button - nothing new is written to this section.",
            "fields": ("video_download", "business_video",
                       "business_description", "motivation"),
        }),
    )

    @admin.display(description="Limiting factors (as ticked)")
    def limiting_factors(self, obj):
        return obj.growth_limits_display or "-"

    # ------------------------------------------------------------ video links
    @admin.display(description="Applicant video")
    def video_link_display(self, obj):
        if not obj.business_video_url:
            return "- no link supplied -"
        return format_html(
            '<a class="button" href="{}" target="_blank" rel="noopener">▶ Open video</a>',
            obj.business_video_url)

    # ------------------------------- video downloads (pre-2026-08 uploads only)
    @admin.display(description="Applicant video")
    def video_download(self, obj):
        if not obj.pk or not obj.business_video:
            return "- no video uploaded -"
        try:
            size = filesizeformat(obj.business_video.size)
        except (FileNotFoundError, OSError):
            return format_html(
                '<span style="color:#b91c1c">Missing from storage: {}</span>',
                obj.business_video.name)
        return format_html(
            '<a class="button" href="{}">⬇ Download video</a>'
            '<span style="margin-left:.75rem;color:#666">{} - {}</span>',
            reverse("submissions:download_video", args=[obj.pk]),
            os.path.basename(obj.business_video.name), size)

    @admin.display(description="Video")
    def video_link(self, obj):
        if obj.business_video_url:
            return format_html('<a href="{}" target="_blank" rel="noopener">Open</a>',
                               obj.business_video_url)
        if obj.business_video:
            return format_html('<a href="{}">Download</a>',
                               reverse("submissions:download_video", args=[obj.pk]))
        return "-"

    @admin.action(description="Download videos for selected applications (ZIP)")
    def download_videos_zip(self, request, queryset):
        with_video = [a for a in queryset if a.business_video]
        if not with_video:
            self.message_user(request, "None of the selected applications has a video.",
                              messages.WARNING)
            return None

        # A tempfile rather than BytesIO: sixty 60 MB clips would not fit in the
        # droplet's RAM. ZIP_STORED because video is already compressed -
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
                request, "Left out of the ZIP - missing from storage: "
                         + "; ".join(missing), messages.WARNING)

        archive_file.seek(0)
        return FileResponse(archive_file, as_attachment=True,
                            filename="embark-application-videos.zip")


@admin.register(models.PartialApplication)
class PartialApplicationAdmin(admin.ModelAdmin):
    """People who started an Embark application and never sent it.

    Deliberately not a SubmissionAdmin: these are not submissions. Nobody here
    pressed submit, nobody ticked the media consent, and nothing in this table
    should ever be read as an application. It exists so the team can send one
    "you were nearly there" note - see models.PartialApplication.
    """

    def get_queryset(self, request):
        from .applicants import unfinished_applicants
        return unfinished_applicants(super().get_queryset(request))

    list_display = ("who", "email", "phone_display", "business_name", "country",
                    "furthest_step", "updated_at", "status")
    list_filter = ("furthest_step", "reviewed", "country", "updated_at")
    search_fields = ("name", "email", "phone", "business_name", "institution", "country")
    readonly_fields = ("draft_id", "created_at", "updated_at", "completed_at",
                       "everything_typed")
    actions = ["export_csv", "mark_followed_up"]
    fieldsets = (
        ("How to reach them", {
            "description": "The whole point of this record. Contact them about "
                           "finishing the application they started, and nothing else "
                           "- they have not consented to anything beyond that.",
            "fields": ("name", "email", ("phone_code", "phone"),
                       ("country", "city"), "institution", "business_name"),
        }),
        ("How far they got", {
            "fields": ("furthest_step", "everything_typed"),
        }),
        ("Follow-up", {
            "fields": ("reviewed", "created_at", "updated_at", "completed_at", "draft_id"),
        }),
    )

    @admin.display(description="Applicant", ordering="name")
    def who(self, obj):
        return obj.name or "- no name yet -"

    @admin.display(description="Phone")
    def phone_display(self, obj):
        return obj.phone_display or "-"

    @admin.display(description="Status")
    def status(self, obj):
        if obj.is_complete:
            return format_html('<span style="color:#15803d">Finished &amp; submitted</span>')
        if obj.reviewed:
            return format_html('<span style="color:#666">Followed up</span>')
        return format_html('<b style="color:#b45309">Unfinished</b>')

    @admin.display(description="Everything they typed")
    def everything_typed(self, obj):
        return format_html('<pre style="white-space:pre-wrap;margin:0">{}</pre>',
                           obj.answers_display or "- nothing beyond the contact details -")

    @admin.action(description="Export selected to CSV (for a follow-up mail-out)")
    def export_csv(self, request, queryset):
        from .applicants import unfinished_applicants
        queryset = unfinished_applicants(queryset)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = \
            'attachment; filename="unfinished-embark-applications.csv"'
        writer = csv.writer(response)
        writer.writerow(["Name", "Email", "Phone", "Business", "Institution",
                         "Country", "City", "Furthest step", "Started", "Last typed",
                         "Finished later", "Business sector"])
        for row in queryset:
            writer.writerow([
                row.name, row.email, row.phone_display, row.business_name,
                row.institution, row.country, row.city, row.furthest_step,
                row.created_at.strftime("%Y-%m-%d %H:%M"),
                row.updated_at.strftime("%Y-%m-%d %H:%M"),
                "yes" if row.is_complete else "no", row.business_sector_display])
        return response

    @admin.action(description="Mark selected as followed up")
    def mark_followed_up(self, request, queryset):
        updated = queryset.update(reviewed=True)
        self.message_user(request, f"{updated} marked as followed up.", messages.SUCCESS)


class PhoneColumnMixin:
    """Shows the dialling code and number as one readable value."""

    @admin.display(description="Phone")
    def phone_display(self, obj):
        return obj.phone_display or "-"


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
