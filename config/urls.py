from django.conf import settings
from django.conf.urls.static import static
from django.urls import re_path
from django.views.static import serve as media_serve
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView

from core.sitemaps import SITEMAPS

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("blog/", include("blog.urls")),
    path("forms/", include("submissions.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    path(
        "robots.txt",
        TemplateView.as_view(template_name="robots.txt", content_type="text/plain"),
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif getattr(settings, "SERVE_MEDIA", False):
    # Demo hosts without a media server (Render free tier). Django's static()
    # helper refuses to run with DEBUG off, so mount the view directly.
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", media_serve,
                            {"document_root": settings.MEDIA_ROOT})]

handler404 = "core.views.page_not_found"
