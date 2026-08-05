"""/staff/ — sign-in and the analytics dashboard.

Its own URL module rather than more entries in core.urls: everything in there is
a public marketing page in the sitemap, and these are neither.
"""
from django.urls import path

from . import staff

app_name = "staff"
urlpatterns = [
    path("", staff.staff_home, name="home"),
    path("login/", staff.StaffLoginView.as_view(), name="login"),
    path("logout/", staff.StaffLogoutView.as_view(), name="logout"),
    path("analytics/", staff.analytics_dashboard, name="analytics"),
]
