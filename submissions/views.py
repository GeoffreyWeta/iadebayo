import mimetypes
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import models as db_models
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import forms, models
from .services import acknowledge, notify_team, verify_recaptcha

SUCCESS = "Thank you! Your submission has been received. A confirmation email is on its way to you."
RECAPTCHA_FAIL = "We couldn't verify that you're human. Please complete the reCAPTCHA and try again."


def _handle(request, form_class, ack_text, notify_subject, redirect_to, on_invalid=None):
    """Validate, save, notify.

    `on_invalid(form)` lets a caller re-render its page with the bound form so
    the visitor's answers survive; without it we fall back to flashing the
    errors and bouncing back to the referring page.
    """
    form = form_class(request.POST, request.FILES)
    if not verify_recaptcha(request):
        messages.error(request, RECAPTCHA_FAIL)
    elif form.is_valid():
        obj = form.save()
        name = getattr(obj, "name", "") or "friend"
        email = getattr(obj, "email", "")
        notify_team(notify_subject, f"New submission on the website:\n\n{_summary(obj)}\n\nReview it in the admin.")
        if email:
            acknowledge(email, name.split()[0], ack_text)
        messages.success(request, SUCCESS)
        return redirect(redirect_to)
    else:
        for field, errs in form.errors.items():
            label = form.fields[field].label if field in form.fields else ""
            messages.error(request, f"{label + ': ' if label else ''}{'; '.join(errs)}")
        if on_invalid is not None:
            return on_invalid(form)
    # Redisplay origin page with errors flashed
    return redirect(request.META.get("HTTP_REFERER", redirect_to))


def _staff_download_url(obj):
    """Link to the applicant's video for the team's notification email, or None.

    Applications now carry a Drive link the applicant shared, so that is what the
    team follows. Applications submitted before 2026-08-01 uploaded the file
    itself and still go through the staff-only download view.
    """
    if not isinstance(obj, models.EmbarkApplication) or not obj.pk:
        return None
    if obj.business_video_url:
        return obj.business_video_url
    if obj.business_video:
        return (settings.SITE_BASE_URL.rstrip("/")
                + reverse("submissions:download_video", args=[obj.pk]))
    return None


def _summary(obj):
    """Readable field dump for the team's notification email."""
    skip = {"id", "created_at", "reviewed", "phone_code"}  # code shown via phone_display
    lines = []
    for f in obj._meta.fields:
        if f.name in skip:
            continue
        value = getattr(obj, f.name)
        if value in ("", None):
            continue
        friendly = getattr(obj, f"{f.name}_display", None)        # e.g. growth_limits
        get_display = getattr(obj, f"get_{f.name}_display", None)  # choice fields
        if friendly is not None:
            value = friendly
        elif get_display is not None:
            value = get_display()
        elif isinstance(f, db_models.FileField):
            # Not the /media/ URL: applicant uploads aren't public files, so
            # the team gets the staff-only download link instead.
            value = _staff_download_url(obj) or getattr(value, "name", value)
        elif isinstance(f, db_models.BooleanField):
            value = "Yes" if value else "No"
        label = f.verbose_name[:1].upper() + f.verbose_name[1:]
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


@require_POST
def contact(request):
    return _handle(request, forms.ContactForm, "contacting IADEBAYO Foundation",
                   "New contact message", "core:contact")


@require_POST
def newsletter(request):
    form = forms.NewsletterForm(request.POST)
    if form.is_valid():
        form.save()
        messages.success(request, "You're subscribed! Welcome to the community.")
    else:
        for errs in form.errors.values():
            messages.error(request, "; ".join(errs))
    return redirect(request.META.get("HTTP_REFERER", "core:home"))


@require_POST
def apply_embark(request):
    def rerender(form):
        # Long form: re-render in place so nothing typed is lost. (The video
        # input can't be repopulated by any browser — the template says so.)
        from core.views import apply_context
        return render(request, "core/apply.html", apply_context(form))

    return _handle(request, forms.EmbarkApplicationForm,
                   "applying to the Embark Entrepreneurship Academy",
                   "New Embark application", "core:apply", on_invalid=rerender)


@require_POST
def faculty(request):
    def rerender(form):
        from core.views import join_faculty_context
        return render(request, "core/join_faculty.html", join_faculty_context(form))

    return _handle(request, forms.FacultyApplicationForm,
                   "applying to join our faculty",
                   "New faculty application", "core:join_faculty", on_invalid=rerender)


@require_POST
def volunteer(request):
    def rerender(form):
        from core.views import volunteer_context
        return render(request, "core/volunteer.html", volunteer_context(form))

    return _handle(request, forms.VolunteerApplicationForm,
                   "offering to volunteer with IADEBAYO Foundation",
                   "New volunteer application", "core:volunteer", on_invalid=rerender)


@require_POST
def partner(request):
    return _handle(request, forms.PartnershipInquiryForm,
                   "your interest in partnering with IADEBAYO Foundation",
                   "New partnership inquiry", "core:partner")


# --------------------------------------------------------- staff-only download
@staff_member_required
def download_application_video(request, pk):
    """Hand an applicant's video to a signed-in staff member as a download.

    The only way to read an application video: /media/applications/ is blocked
    at the web server because these clips show the applicant's face and business
    and the storage path is guessable. `staff_member_required` bounces anyone
    else to the admin login rather than 403-ing, which is what a team member who
    clicked a link from an email expects.
    """
    application = get_object_or_404(models.EmbarkApplication, pk=pk)
    if not application.business_video:
        raise Http404("This application has no video.")

    filename = application.video_download_name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    if settings.X_ACCEL_REDIRECT:
        # nginx does the transfer; Gunicorn's worker is free immediately.
        response = HttpResponse(content_type=content_type)
        response["X-Accel-Redirect"] = quote(
            settings.X_ACCEL_MEDIA_PREFIX + application.business_video.name)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    try:
        handle = application.business_video.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("The video file is missing from storage.")
    return FileResponse(handle, as_attachment=True, filename=filename,
                        content_type=content_type)
