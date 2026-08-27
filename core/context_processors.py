from django.conf import settings
from django.urls import reverse

from submissions.forms import NewsletterForm


def _promo_for(request):
    """The campaign popup, unless this page is the wrong place for it.

    Suppressed on the application form (the visitor is already doing the thing
    the flier asks for) and anywhere in the admin (staff, not audience).
    """
    from core.models import PromoPopup

    path = request.path
    if path.startswith("/admin/") or path == reverse("core:apply"):
        return None
    try:
        return PromoPopup.current()
    except Exception:  # during migrations / before the table exists
        return None


def _pixel_event(request):
    """The conversion event to fire on this page, if a form just set one.

    Popped, not read: it must fire exactly once, on the page the visitor is
    redirected to after a successful submission. Leaving it in the session would
    report a fresh application on every page they visited afterwards.

    `pop` only marks the session modified when the key is actually there, so a
    visitor who has submitted nothing is never given a session cookie for this.
    """
    try:
        return request.session.pop("meta_pixel_event", None)
    except AttributeError:      # no session middleware (tests, some commands)
        return None


def site_meta(request):
    from core.models import PageMeta
    override = {}
    try:
        pm = PageMeta.objects.filter(path=request.path).first()
        if pm:
            override = {"page_meta_title": pm.title, "page_meta_description": pm.description}
    except Exception:  # during migrations / before tables exist
        pass
    return {
        **override,
        "promo": _promo_for(request),
        "GA_MEASUREMENT_ID": getattr(settings, "GA_MEASUREMENT_ID", ""),
        "META_PIXEL_ID": getattr(settings, "META_PIXEL_ID", ""),
        "meta_pixel_event": _pixel_event(request),
        "SITE_NAME": settings.SITE_NAME,
        "SITE_BASE_URL": settings.SITE_BASE_URL,
        "RECAPTCHA_SITE_KEY": settings.RECAPTCHA_SITE_KEY,
        "footer_newsletter_form": NewsletterForm(),
    }
