from django.urls import path
from . import views

app_name = "submissions"
urlpatterns = [
    path("contact/", views.contact, name="contact"),
    path("newsletter/", views.newsletter, name="newsletter"),
    path("apply/", views.apply_embark, name="apply"),
    # Background save from the apply form while it is being filled in.
    path("apply/progress/", views.apply_progress, name="apply_progress"),
    path("faculty/", views.faculty, name="faculty"),
    path("volunteer/", views.volunteer, name="volunteer"),
    path("partner/", views.partner, name="partner"),
    path("applications/<int:pk>/video/", views.download_application_video,
         name="download_video"),
]
