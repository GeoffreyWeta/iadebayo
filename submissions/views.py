import mimetypes
import re
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models as db_models
from django.db.models.functions import Lower, Trim
from django.http import (FileResponse, Http404, HttpResponse, HttpResponseBadRequest,
                         JsonResponse)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.staff import staff_required

from . import forms, models
from .services import acknowledge, notify_team, verify_recaptcha

SUCCESS = "Thank you! Your submission has been received. A confirmation email is on its way to you."
RECAPTCHA_FAIL = "We couldn't verify that you're human. Please complete the reCAPTCHA and try again."


def _pixel(request, event):
    """Queue one Meta Pixel conversion event for the page we redirect to.

    Only ever a fixed name from Meta's standard list - never anything typed by
    a visitor, and never carrying who they are. See templates/includes/
    meta_pixel.html. A no-op when no pixel id is configured, so nothing is put
    in the session (and no session cookie is set on a visitor) on a site that
    is not running one.
    """
    if event and getattr(settings, "META_PIXEL_ID", ""):
        request.session["meta_pixel_event"] = event


def _handle(request, form_class, ack_text, notify_subject, redirect_to,
            on_invalid=None, pixel_event=None, on_saved=None):
    """Validate, save, notify.

    `on_invalid(form)` lets a caller re-render its page with the bound form so
    the visitor's answers survive; without it we fall back to flashing the
    errors and bouncing back to the referring page.

    `pixel_event` fires on the page after a *successful* save, so the ads
    platform counts a conversion only when there is a row to show for it.
    """
    form = form_class(request.POST, request.FILES)
    if not verify_recaptcha(request):
        messages.error(request, RECAPTCHA_FAIL)
    elif form.is_valid():
        try:
            obj = form.save()
        except ValidationError as error:
            form.add_error(None, error)
            if on_invalid is not None:
                return on_invalid(form)
            messages.error(request, "; ".join(error.messages))
            return redirect(redirect_to)
        if on_saved is not None:
            on_saved(obj)
        name = getattr(obj, "name", "") or "friend"
        email = getattr(obj, "email", "")
        notify_team(notify_subject, f"New submission on the website:\n\n{_summary(obj)}\n\nReview it in the admin.")
        if email:
            # obj= stamps acknowledged_at, so the backfill command knows
            # this person has already been written to and skips them.
            acknowledge(email, name.split()[0], ack_text, obj=obj)
        _pixel(request, pixel_event)
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
                   "New contact message", "core:contact", pixel_event="Contact")


@require_POST
def newsletter(request):
    form = forms.NewsletterForm(request.POST)
    if form.is_valid():
        form.save()
        _pixel(request, "Subscribe")
        messages.success(request, "You're subscribed! Welcome to the community.")
    else:
        for errs in form.errors.values():
            messages.error(request, "; ".join(errs))
    return redirect(request.META.get("HTTP_REFERER", "core:home"))


@require_POST
def apply_embark(request):
    def rerender(form):
        # Long form: re-render in place so nothing typed is lost. (The video
        # input can't be repopulated by any browser - the template says so.)
        from core.views import apply_context
        return render(request, "core/apply.html", apply_context(form))

    # SubmitApplication, not Lead: this is the conversion the ads are actually
    # buying, and keeping it distinct from the other forms is what makes the
    # cost-per-application figure in Ads Manager mean anything.
    response = _handle(request, forms.EmbarkApplicationForm,
                       "applying to the Embark Entrepreneurship Academy",
                       "New Embark application", "core:apply", on_invalid=rerender,
                       pixel_event="SubmitApplication",
                       on_saved=lambda obj: _close_partial(request))
    return response


def _close_partial(request):
    """Mark the unfinished row this application came from as finished.

    Matched on the draft id the form carries, and on the email address as well:
    someone who starts on their phone and finishes on a laptop has two draft
    ids and one email, and chasing them about an application they have already
    sent is the one thing this whole feature must not cause.
    """
    draft_id = _clean_draft_id(request.POST.get("draft_id"))
    from .applicants import normalized_email
    email = normalized_email(request.POST.get("email"))
    match = db_models.Q(pk__in=[])
    if draft_id:
        match |= db_models.Q(draft_id=draft_id)
    if email:
        match |= db_models.Q(email_key=email)
    models.PartialApplication.objects.annotate(email_key=Lower(Trim("email"))) \
        .filter(match, completed_at__isnull=True) \
        .update(completed_at=timezone.now())


# ------------------------------------------------ unfinished-application capture
#
# The apply form posts here while it is being filled in, so an applicant who
# never reaches Submit still leaves the Foundation a way to reach them. See
# models.PartialApplication for what is kept and why.

DRAFT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
PROGRESS_VALUE_CAP = 2000    # per answer; the longest real answer is a paragraph
PROGRESS_TOTAL_CAP = 20000   # per row, across every answer


def _clean_draft_id(value):
    value = (value or "").strip()
    return value if DRAFT_ID_RE.match(value) else ""


def _valid_email(value):
    try:
        validate_email(value)
    except ValidationError:
        return ""
    return value


def _reachable(email, phone):
    """Is there enough here to contact this person?

    A half-typed email or three digits of a phone number is not - this is the
    line between "someone we can help finish" and keystrokes we have no business
    keeping.
    """
    return bool(email) or len(re.sub(r"\D", "", phone)) >= 7


@require_POST
def apply_progress(request):
    """Save the part-filled Embark application behind the scenes.

    Answers only, no side effects: no acknowledgement email, no team
    notification, no reCAPTCHA (the applicant has not finished, and a challenge
    they have not touched yet would reject every save). The honeypot still
    applies, and a row is written only once there is a usable email or phone -
    between them that is enough to keep the table free of bot noise and of
    people who typed two letters and left.
    """
    if request.POST.get("website_url"):          # honeypot - a bot filled it in
        return JsonResponse({"saved": False}, status=202)

    draft_id = _clean_draft_id(request.POST.get("draft_id"))
    if not draft_id:
        return HttpResponseBadRequest("Bad draft id.")

    fields = forms.EmbarkApplicationForm.Meta.fields
    answers, total = {}, 0
    for name in fields:
        values = [v.strip() for v in request.POST.getlist(name) if v.strip()]
        if not values:
            continue
        value = values if len(values) > 1 else values[0]
        text = ", ".join(values)[:PROGRESS_VALUE_CAP]
        if total + len(text) > PROGRESS_TOTAL_CAP:
            continue
        total += len(text)
        answers[name] = value[:PROGRESS_VALUE_CAP] if isinstance(value, str) else value

    email = _valid_email(answers.get("email", ""))
    phone = answers.get("phone", "")
    if not _reachable(email, phone):
        return JsonResponse({"saved": False}, status=202)

    # Mirror the columns the team works from, each clipped to what the column
    # holds - the form is unvalidated at this point, so nothing may be trusted
    # to fit.
    caps = {f.name: f.max_length for f in models.PartialApplication._meta.fields
            if getattr(f, "max_length", None)}
    mirrored = {"email": email}
    for name in models.PartialApplication.MIRRORED:
        if name == "email":
            continue
        value = answers.get(name, "")
        mirrored[name] = value[:caps.get(name, 160)] if isinstance(value, str) else ""

    step = request.POST.get("furthest_step", "1")
    mirrored["furthest_step"] = int(step) if step.isdigit() and 0 < int(step) < 100 else 1
    mirrored["answers"] = answers

    # A late autosave or a new device must not reopen a submitted applicant.
    from .applicants import normalized_email
    submitted = models.EmbarkApplication.objects.annotate(
        email_key=Lower(Trim("email"))).filter(email_key=normalized_email(email))
    if email and submitted.exists():
        mirrored["completed_at"] = timezone.now()

    row, created = models.PartialApplication.objects.get_or_create(
        draft_id=draft_id, defaults=mirrored)
    if not created:
        # Never walk a step counter backwards: the applicant flicking back to
        # section 1 to fix a typo has still reached section 3.
        mirrored["furthest_step"] = max(mirrored["furthest_step"], row.furthest_step)
        for key, value in mirrored.items():
            setattr(row, key, value)
        row.save(update_fields=list(mirrored) + ["updated_at"])
    return JsonResponse({"saved": True})


@require_POST
def faculty(request):
    def rerender(form):
        from core.views import join_faculty_context
        return render(request, "core/join_faculty.html", join_faculty_context(form))

    return _handle(request, forms.FacultyApplicationForm,
                   "applying to join our faculty",
                   "New faculty application", "core:join_faculty", on_invalid=rerender,
                   pixel_event="Lead")


@require_POST
def volunteer(request):
    def rerender(form):
        from core.views import volunteer_context
        return render(request, "core/volunteer.html", volunteer_context(form))

    return _handle(request, forms.VolunteerApplicationForm,
                   "offering to volunteer with IADEBAYO Foundation",
                   "New volunteer application", "core:volunteer", on_invalid=rerender,
                   pixel_event="Lead")


@require_POST
def partner(request):
    return _handle(request, forms.PartnershipInquiryForm,
                   "your interest in partnering with IADEBAYO Foundation",
                   "New partnership inquiry", "core:partner", pixel_event="Lead")


# --------------------------------------------------------- staff-only download
@staff_required
def download_application_video(request, pk):
    """Hand an applicant's video to a signed-in staff member as a download.

    The only way to read an application video: /media/applications/ is blocked
    at the web server because these clips show the applicant's face and business
    and the storage path is guessable. `staff_required` bounces anyone else to
    the staff sign-in with `?next=` set, rather than 403-ing - a team member who
    clicked a link in a notification email expects to sign in and land on the
    file, not to be told off.
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
