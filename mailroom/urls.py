"""Public, machine-facing: where the Cloudflare Email Worker delivers mail.

The staff mailbox pages are under /staff/mail/ in core.staff_urls, with the
rest of the staff area.
"""
from django.urls import path

from . import views

app_name = "mailroom"
urlpatterns = [
    path("email/", views.inbound, name="inbound"),
]
