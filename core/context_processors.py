from django.conf import settings
from submissions.forms import NewsletterForm


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
        "GA_MEASUREMENT_ID": getattr(settings, "GA_MEASUREMENT_ID", ""),
        "SITE_NAME": settings.SITE_NAME,
        "SITE_BASE_URL": settings.SITE_BASE_URL,
        "RECAPTCHA_SITE_KEY": settings.RECAPTCHA_SITE_KEY,
        "footer_newsletter_form": NewsletterForm(),
    }
