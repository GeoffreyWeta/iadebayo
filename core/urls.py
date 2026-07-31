from django.urls import path
from . import views

app_name = "core"
urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("embark/", views.embark, name="embark"),
    path("embark/apply/", views.apply, name="apply"),
    # Not /media/: that is MEDIA_URL, and nginx maps the prefix straight to the
    # uploads directory, so a request for /media/ never reaches Django — it just
    # 403s on a directory listing it will not index. Keep this page off it.
    path("gallery/", views.gallery, name="gallery"),
    path("embark/alumni/", views.alumni, name="alumni"),
    path("partner-with-us/", views.partner, name="partner"),
    path("get-involved/", views.get_involved, name="get_involved"),
    path("get-involved/faculty/", views.join_faculty, name="join_faculty"),
    path("get-involved/volunteer/", views.volunteer, name="volunteer"),
    path("resources/", views.resources, name="resources"),
    path("contact/", views.contact, name="contact"),
    path("privacy-policy/", views.privacy, name="privacy"),
    path("terms-of-use/", views.terms, name="terms"),
]
