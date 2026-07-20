from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from . import forms
from .services import acknowledge, notify_team, verify_recaptcha

SUCCESS = "Thank you! Your submission has been received. A confirmation email is on its way to you."
RECAPTCHA_FAIL = "We couldn't verify that you're human. Please complete the reCAPTCHA and try again."


def _handle(request, form_class, ack_text, notify_subject, redirect_to):
    form = form_class(request.POST)
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
    # Redisplay origin page with errors flashed
    return redirect(request.META.get("HTTP_REFERER", redirect_to))


def _summary(obj):
    skip = {"id", "created_at", "reviewed"}
    lines = []
    for f in obj._meta.fields:
        if f.name in skip:
            continue
        lines.append(f"{f.verbose_name.title()}: {getattr(obj, f.name)}")
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
    return _handle(request, forms.EmbarkApplicationForm,
                   "applying to the Embark Entrepreneurship Academy",
                   "New Embark application", "core:apply")


@require_POST
def faculty(request):
    return _handle(request, forms.FacultyApplicationForm,
                   "applying to join our faculty",
                   "New faculty application", "core:get_involved")


@require_POST
def volunteer(request):
    return _handle(request, forms.VolunteerApplicationForm,
                   "offering to volunteer with IADEBAYO Foundation",
                   "New volunteer application", "core:get_involved")


@require_POST
def partner(request):
    return _handle(request, forms.PartnershipInquiryForm,
                   "your interest in partnering with IADEBAYO Foundation",
                   "New partnership inquiry", "core:partner")
