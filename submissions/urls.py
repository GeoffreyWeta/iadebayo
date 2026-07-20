from django.urls import path
from . import views

app_name = "submissions"
urlpatterns = [
    path("contact/", views.contact, name="contact"),
    path("newsletter/", views.newsletter, name="newsletter"),
    path("apply/", views.apply_embark, name="apply"),
    path("faculty/", views.faculty, name="faculty"),
    path("volunteer/", views.volunteer, name="volunteer"),
    path("partner/", views.partner, name="partner"),
]
