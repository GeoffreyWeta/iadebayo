"""/staff/ - sign-in, the team's content admin, and the analytics dashboard.

Its own URL module rather than more entries in core.urls: everything in there is
a public marketing page in the sitemap, and none of this is either.

Everything under `<slug>/` is generic. The slug names a collection in
core.staff_content and the view looks it up; there is no per-model route, which
is what keeps "add something the team can edit" down to one entry in that file.
Routes are ordered so the fixed segments (`new/`, `reorder/`, `export/`) are
matched before `<int:pk>/`, which cannot collide with them anyway but reads
better in the order it is tried.
"""
from django.urls import path

from . import staff, staff_views

app_name = "staff"
urlpatterns = [
    path("", staff_views.dashboard, name="home"),
    path("login/", staff.StaffLoginView.as_view(), name="login"),
    path("logout/", staff.StaffLogoutView.as_view(), name="logout"),
    path("analytics/", staff.analytics_dashboard, name="analytics"),
    path("password/", staff.staff_required(
        staff.StaffPasswordChangeView.as_view()), name="password_change"),
    path("messages/<int:pk>/sender/", staff_views.contact_sender, name="contact_sender"),

    # ------------------------------------------------- content and submissions
    path("c/<slug:slug>/", staff_views.collection_list, name="list"),
    path("c/<slug:slug>/new/", staff_views.collection_edit, name="new"),
    path("c/<slug:slug>/export/", staff_views.collection_export, name="export"),
    path("c/<slug:slug>/reorder/", staff_views.collection_reorder, name="reorder"),
    path("c/<slug:slug>/bulk/", staff_views.collection_bulk, name="bulk"),
    path("c/<slug:slug>/email/", staff_views.collection_email_many, name="email_many"),
    path("c/<slug:slug>/<int:pk>/", staff_views.submission_detail, name="detail"),
    path("c/<slug:slug>/<int:pk>/edit/", staff_views.collection_edit, name="edit"),
    path("c/<slug:slug>/<int:pk>/delete/", staff_views.collection_delete, name="delete"),
    path("c/<slug:slug>/<int:pk>/toggle/", staff_views.collection_toggle, name="toggle"),
    path("c/<slug:slug>/<int:pk>/decide/", staff_views.collection_decide, name="decide"),
    path("c/<slug:slug>/<int:pk>/email/", staff_views.collection_email, name="email"),
]
