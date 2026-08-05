"""The staff area: a branded sign-in, and the analytics dashboard behind it.

Auth is Django's, unchanged — same `auth_user` table, same password hashing, same
sessions, and the same `is_staff` flag the admin and the applicant-video download
already gate on (submissions.views.download_application_video). Nothing here
introduces a second idea of who a staff member is; it only puts a page the team
recognises in front of it, instead of the bare Django admin form.

Accounts are still created in the admin. That is deliberate — there is no
self-service registration, because every account here can read applicants'
personal data.
"""
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.cache import never_cache

from . import analytics

# A signed-in non-staff user is bounced to the dashboard login rather than the
# admin's, which is what someone who followed a link from the dashboard expects.
# `login_url` is explicit so this keeps working if LOGIN_URL is ever repointed.
staff_required = user_passes_test(
    lambda u: u.is_active and u.is_staff,
    login_url="staff:login",
    redirect_field_name="next",
)

# Throttle: attempts per (IP, username) before the form stops checking passwords.
LOCK_ATTEMPTS = 8
LOCK_SECONDS = 15 * 60


def _throttle_key(request, username):
    # REMOTE_ADDR, not X-Forwarded-For: behind a proxy the client can set the
    # latter freely, so trusting it would let an attacker rotate their own key
    # and opt out of the throttle entirely.
    return f"staff-login:{request.META.get('REMOTE_ADDR', '?')}:{username.lower()[:64]}"


class StaffLoginForm(AuthenticationForm):
    """Django's login form, restricted to staff and rate-limited.

    Rejecting non-staff in `confirm_login_allowed` rather than after login keeps
    a non-staff account from ever getting a session here, and reuses the same
    error slot the wrong-password case uses — so the message never reveals which
    of the two went wrong.
    """
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "That username and password don't match a staff account.",
        "throttled": "Too many sign-in attempts. Please try again in about "
                     "%(minutes)s minutes.",
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.setdefault(
                "autocomplete", "username" if name == "username" else "current-password")

    def clean(self):
        username = (self.cleaned_data.get("username") or "").strip()
        # Checked before super(), so a locked-out key never reaches the password
        # hasher — otherwise the throttle still pays the bcrypt cost per attempt
        # and the endpoint stays useful for tying up workers.
        #
        # Note: the default LocMemCache is per-process, so with several Gunicorn
        # workers the effective ceiling is LOCK_ATTEMPTS × workers. That still
        # closes off password spraying; point CACHES at Redis/Memcached to make
        # the limit exact.
        if self.request and username:
            if cache.get(_throttle_key(self.request, username), 0) >= LOCK_ATTEMPTS:
                raise ValidationError(self.error_messages["throttled"],
                                      code="throttled",
                                      params={"minutes": LOCK_SECONDS // 60})
        return super().clean()

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise self.get_invalid_login_error()


class StaffLoginView(auth_views.LoginView):
    """Branded sign-in for the staff area.

    `redirect_authenticated_user` is left off on purpose: it turns this URL into
    an open-redirect gadget when `?next=` is attacker-supplied, and the cost is
    only that an already-signed-in staffer sees the form again.
    """
    template_name = "staff/login.html"
    authentication_form = StaffLoginForm
    extra_context = {"page_title": "Staff sign-in"}

    def form_valid(self, form):
        cache.delete(_throttle_key(self.request, form.cleaned_data.get("username", "")))
        return super().form_valid(form)

    def form_invalid(self, form):
        username = (form.data.get("username") or "").strip()
        if username:
            key = _throttle_key(self.request, username)
            # add() then incr() so the TTL is set once and the window does not
            # slide forward on every further attempt.
            if cache.add(key, 1, LOCK_SECONDS) is False:
                try:
                    cache.incr(key)
                except ValueError:      # entry expired between add and incr
                    cache.add(key, 1, LOCK_SECONDS)
        return super().form_invalid(form)


class StaffLogoutView(auth_views.LogoutView):
    next_page = reverse_lazy("staff:login")


@never_cache
@staff_required
def analytics_dashboard(request):
    """Submission analytics for the team.

    `never_cache` because the page is per-user and behind auth: without it a
    shared proxy is free to hand one staffer's dashboard to the next visitor.
    """
    data = analytics.dashboard(request.GET.get("range"))
    return render(request, "staff/analytics.html", {
        "page_title": "Analytics",
        "nav": "analytics",
        **data,
    })


@never_cache
@staff_required
def staff_home(request):
    """`/staff/` — nothing to choose between yet, so go straight to the numbers."""
    return redirect("staff:analytics")
