"""Tests for the staff area: who gets in, and whether the numbers are right.

The analytics assertions deliberately go through `analytics.*` rather than
scraping the rendered page — the arithmetic is the part that can be wrong in a
way nobody notices, and it is worth pinning down separately from the markup.
"""
import datetime as dt

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from submissions.models import (ContactMessage, EmbarkApplication,
                                NewsletterSubscriber)

from . import analytics, cohort

PASSWORD = "pw-for-tests-only"

# Same reason as submissions.tests: with DEBUG off, SecurityMiddleware answers
# plain-http test requests with a 301 to https and every assertion below drifts.
SSL_REDIRECT_OFF = override_settings(SECURE_SSL_REDIRECT=False)


def make_application(**kwargs):
    fields = {"name": "Ada Obi", "email": "ada@example.com", "phone": "8012345678",
              "city": "Lagos", "country": "Nigeria", "business_name": "Acme Crafts"}
    fields.update(kwargs)
    return EmbarkApplication.objects.create(**fields)


def backdate(obj, when):
    """Move a row's auto_now_add timestamp. `update()` skips auto_now_add."""
    type(obj).objects.filter(pk=obj.pk).update(created_at=timezone.make_aware(when))


@SSL_REDIRECT_OFF
class StaffAccessTests(TestCase):
    """Nothing behind /staff/ opens without an active staff account."""

    def setUp(self):
        cache.clear()          # the login throttle is cache-backed

    def sign_in(self, username, **flags):
        User.objects.create_user(username, password=PASSWORD, **flags)
        return self.client.login(username=username, password=PASSWORD)

    def test_dashboard_bounces_anonymous_to_the_staff_login(self):
        response = self.client.get(reverse("staff:analytics"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("staff:login"), response["Location"])

    def test_dashboard_bounces_a_signed_in_non_staff_user(self):
        self.sign_in("member")
        response = self.client.get(reverse("staff:analytics"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("staff:login"), response["Location"])

    def test_inactive_staff_cannot_sign_in(self):
        User.objects.create_user("dormant", password=PASSWORD, is_staff=True,
                                 is_active=False)
        response = self.client.post(reverse("staff:login"),
                                    {"username": "dormant", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)          # re-rendered form
        self.assertFalse(response.context["user"].is_authenticated)

    def test_non_staff_password_is_rejected_without_saying_why(self):
        """A correct password on a non-staff account must not be distinguishable
        from a wrong one, or the form becomes an account-enumeration oracle."""
        User.objects.create_user("member", password=PASSWORD)
        response = self.client.post(reverse("staff:login"),
                                    {"username": "member", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["user"].is_authenticated)
        self.assertContains(response, "match a staff account")

    def test_staff_reach_the_dashboard(self):
        self.assertTrue(self.sign_in("staffer", is_staff=True))
        response = self.client.get(reverse("staff:analytics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Applications per day")

    def test_staff_root_redirects_to_analytics(self):
        self.sign_in("staffer", is_staff=True)
        response = self.client.get(reverse("staff:home"))
        self.assertRedirects(response, reverse("staff:analytics"))

    def test_dashboard_is_not_indexable_or_cacheable(self):
        self.sign_in("staffer", is_staff=True)
        response = self.client.get(reverse("staff:analytics"))
        self.assertContains(response, "noindex")
        self.assertIn("no-store", response["Cache-Control"])

    def test_login_page_renders_for_anonymous(self):
        response = self.client.get(reverse("staff:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff sign-in")

    def test_logout_needs_a_post(self):
        self.sign_in("staffer", is_staff=True)
        self.assertEqual(self.client.get(reverse("staff:logout")).status_code, 405)
        self.client.post(reverse("staff:logout"))
        self.assertEqual(self.client.get(reverse("staff:analytics")).status_code, 302)

    def test_repeated_failures_lock_the_username_out(self):
        User.objects.create_user("staffer", password=PASSWORD, is_staff=True)
        url = reverse("staff:login")
        from .staff import LOCK_ATTEMPTS
        for _ in range(LOCK_ATTEMPTS):
            self.client.post(url, {"username": "staffer", "password": "wrong"})
        # The real password now fails too — that is the point of the throttle.
        response = self.client.post(url, {"username": "staffer", "password": PASSWORD})
        self.assertFalse(response.context["user"].is_authenticated)
        self.assertContains(response, "Too many sign-in attempts")


@SSL_REDIRECT_OFF
class AnalyticsNumbersTests(TestCase):
    """The arithmetic, independent of how it is drawn."""

    def test_percentages_are_of_the_answered_rows_not_everyone(self):
        """The blank-field trap: most applicant fields are optional, so counting
        blanks into a denominator would quietly understate every share."""
        make_application(gender="female")
        make_application(gender="female")
        make_application(gender="male")
        make_application()                      # never answered
        result = analytics.breakdown(EmbarkApplication.objects.all(),
                                     "gender", EmbarkApplication.GENDER_CHOICES)
        self.assertEqual(result["answered"], 3)
        by_label = {r["label"]: r for r in result["rows"]}
        self.assertEqual(by_label["Female"]["value"], 2)
        self.assertEqual(by_label["Female"]["pct"], 67)     # 2/3, not 2/4

    def test_choice_codes_are_shown_as_the_labels_applicants_saw(self):
        make_application(heard_about="linkedin")
        rows = analytics.breakdown(EmbarkApplication.objects.all(), "heard_about",
                                   EmbarkApplication.REFERRAL_CHOICES)["rows"]
        self.assertEqual(rows[0]["label"], "LinkedIn")

    def test_long_tails_fold_into_other(self):
        for i in range(6):
            make_application(country=f"Country {i}")
        result = analytics.breakdown(EmbarkApplication.objects.all(), "country", limit=3)
        self.assertEqual(len(result["rows"]), 4)
        self.assertEqual(result["rows"][-1]["label"], "Other")
        self.assertEqual(sum(r["value"] for r in result["rows"]), 6)

    def test_multi_select_counts_people_not_ticks(self):
        make_application(growth_limits="funding,customers")
        make_application(growth_limits="funding")
        result = analytics.multi_breakdown(EmbarkApplication.objects.all(),
                                           "growth_limits",
                                           EmbarkApplication.GROWTH_LIMIT_CHOICES)
        self.assertEqual(result["answered"], 2)             # two applicants
        self.assertEqual(result["total"], 3)                # three ticks
        by_label = {r["label"]: r["pct"] for r in result["rows"]}
        self.assertEqual(by_label["Lack of funding"], 100)  # 2 of 2 people

    def test_quiet_days_are_zero_filled_not_skipped(self):
        day = dt.date(2026, 8, 5)
        backdate(make_application(), dt.datetime(2026, 8, 5, 10, 0))
        series = analytics.daily_counts(EmbarkApplication.objects.all(),
                                        day - dt.timedelta(days=2), day)
        self.assertEqual([p["value"] for p in series], [0, 0, 1])

    def test_business_age_bands_stay_in_band_order(self):
        make_application(year_established=2026)     # under 1
        make_application(year_established=2020)     # 6-10
        make_application(year_established=2020)
        make_application(year_established=2099)     # a typo, dropped
        result = analytics.bucketed_business_age(
            EmbarkApplication.objects.all(), dt.date(2026, 8, 3))
        self.assertEqual(result["answered"], 3)
        self.assertEqual([r["label"] for r in result["rows"]],
                         ["Under 1 year", "1–2 years", "3–5 years",
                          "6–10 years", "Over 10 years"])
        self.assertEqual(result["rows"][3]["value"], 2)

    def test_funnel_reports_the_drop_between_stages(self):
        make_application(business_video_url="https://drive.example/x", reviewed=True)
        make_application(business_video_url="https://drive.example/y")
        make_application()                          # nothing to review
        stages = analytics._funnel(EmbarkApplication.objects.all())
        self.assertEqual([s["value"] for s in stages], [3, 2, 1])
        self.assertIsNone(stages[0]["drop"])
        self.assertEqual(stages[1]["drop"], 1)
        self.assertEqual(stages[2]["drop"], 1)

    def test_bar_width_scales_to_the_largest_row_and_pct_to_the_total(self):
        for _ in range(3):
            make_application(country="Nigeria")
        make_application(country="Ghana")
        rows = analytics.breakdown(EmbarkApplication.objects.all(), "country")["rows"]
        self.assertEqual(rows[0]["width"], 100)     # biggest row fills the track
        self.assertEqual(rows[0]["pct"], 75)        # but it is 3 of 4
        self.assertEqual(rows[1]["width"], 33.3)

    def test_internet_readiness_keeps_its_scale_order(self):
        make_application(reliable_internet="yes")
        make_application(reliable_internet="no")
        result = analytics._internet(EmbarkApplication.objects.all())
        self.assertEqual([r["status"] for r in result["rows"]],
                         ["good", "warning", "critical"])
        self.assertEqual(result["answered"], 2)

    def test_an_unknown_range_falls_back_instead_of_erroring(self):
        key, _label, _start, _end = analytics.resolve_range("nonsense")
        self.assertEqual(key, analytics.DEFAULT_RANGE)

    def test_the_window_range_uses_the_real_cohort_dates(self):
        _key, _label, start, end = analytics.resolve_range("cohort")
        self.assertEqual(start, cohort.APPLICATIONS_OPEN)
        self.assertEqual(end, cohort.APPLICATIONS_CLOSE)

    def test_range_filter_excludes_submissions_outside_it(self):
        backdate(make_application(), dt.datetime(2025, 1, 1, 9, 0))
        make_application()                          # today
        applications = analytics.dashboard("30")["tiles"][0]
        self.assertEqual(applications["value"], 1)
        self.assertEqual(applications["total"], 2)  # all-time is still both

    def test_dashboard_runs_with_an_empty_database(self):
        """The dashboard gets opened before the first application of a cohort,
        and every average, axis ceiling and heat level divides by something."""
        data = analytics.dashboard("cohort")
        self.assertEqual(data["tiles"][0]["value"], 0)
        self.assertEqual(data["plot"].peak, 1)      # the axis floor, not real data
        self.assertEqual(data["countries"]["rows"], [])

    def test_every_tile_source_is_counted(self):
        make_application()
        ContactMessage.objects.create(name="Zed", email="z@example.com",
                                      subject="Hi", message="Hello")
        NewsletterSubscriber.objects.create(email="sub@example.com")
        by_key = {t["key"]: t["value"] for t in analytics.dashboard("all")["tiles"]}
        self.assertEqual(by_key["applications"], 1)
        self.assertEqual(by_key["contact"], 1)
        self.assertEqual(by_key["newsletter"], 1)
        self.assertEqual(by_key["volunteers"], 0)


class PlotGeometryTests(TestCase):
    def test_axis_ceiling_is_a_round_number_at_or_above_the_peak(self):
        self.assertEqual(analytics.Plot._nice_ceiling(1), 4)
        self.assertEqual(analytics.Plot._nice_ceiling(7), 10)
        self.assertEqual(analytics.Plot._nice_ceiling(23), 25)
        self.assertEqual(analytics.Plot._nice_ceiling(100), 100)

    def test_a_single_day_still_draws(self):
        """A window one day long divides by (n - 1) if nobody guards it."""
        plot = analytics.Plot([{"date": dt.date(2026, 8, 1), "value": 3}])
        self.assertTrue(plot.line())
        self.assertEqual(len(plot.hotspots()), 1)
        self.assertEqual(len(plot.xticks()), 1)

    def test_rolling_mean_is_trailing_so_it_reaches_the_last_day(self):
        series = [{"date": None, "value": v} for v in [0, 0, 3, 3]]
        self.assertEqual(len(analytics.rolling_mean(series, window=2)), 4)
        self.assertEqual(analytics.rolling_mean(series, window=2)[-1], 3)

    def test_heat_levels_span_the_ramp_without_exceeding_it(self):
        series = [{"date": dt.date(2026, 8, 1) + dt.timedelta(days=i),
                   "value": v} for i, v in enumerate([0, 1, 5, 10])]
        grid = analytics.heat_grid(series)
        levels = [c["level"] for week in grid["weeks"] for c in week if c]
        self.assertEqual(levels[0], 0)              # no applications
        self.assertEqual(max(levels), 4)            # the busiest day
        self.assertTrue(all(0 <= n <= 4 for n in levels))

    def test_sparkline_survives_a_flat_series(self):
        flat = analytics.sparkline([2, 2, 2])
        self.assertTrue(flat["line"])
        self.assertEqual(analytics.sparkline([])["line"], "")


class CohortWindowTests(TestCase):
    def test_day_one_is_day_one_not_day_zero(self):
        progress = cohort.window_progress(cohort.APPLICATIONS_OPEN)
        self.assertEqual(progress["state"], "open")
        self.assertEqual(progress["elapsed"], 1)

    def test_before_and_after_the_window_are_distinguishable(self):
        before = cohort.window_progress(cohort.APPLICATIONS_OPEN - dt.timedelta(days=3))
        after = cohort.window_progress(cohort.APPLICATIONS_CLOSE + dt.timedelta(days=2))
        self.assertEqual(before["state"], "upcoming")
        self.assertEqual(before["days_until_open"], 3)
        self.assertEqual(after["state"], "closed")
        self.assertEqual(after["days_since_close"], 2)

    def test_the_public_key_dates_still_read_the_way_they_shipped(self):
        """These strings are on /embark/ and /embark/apply/ — deriving them from
        dates must not change what an applicant sees."""
        self.assertEqual(cohort.key_dates(), [
            ("Applications open", "1 August – 11 September 2026"),
            ("Admission notifications", "14 – 25 September 2026"),
        ])
