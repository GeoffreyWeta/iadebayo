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
        "SITE_NAME": settings.SITE_NAME,
        "SITE_BASE_URL": settings.SITE_BASE_URL,
        "RECAPTCHA_SITE_KEY": settings.RECAPTCHA_SITE_KEY,
        "footer_newsletter_form": NewsletterForm(),
    }
