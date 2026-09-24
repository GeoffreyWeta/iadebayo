"""Tests for the staff area: who gets in, and whether the numbers are right.

The analytics assertions deliberately go through `analytics.*` rather than
scraping the rendered page - the arithmetic is the part that can be wrong in a
way nobody notices, and it is worth pinning down separately from the markup.
"""
import datetime as dt

from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from submissions.models import (ContactMessage, EmbarkApplication,
                                NewsletterSubscriber)

from . import analytics, cohort, mailmerge
from .models import Cohort, EmailTemplate

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

    def test_staff_root_is_the_dashboard(self):
        """`/staff/` used to redirect to the numbers; it is now a page of its own."""
        self.sign_in("staffer", is_staff=True)
        response = self.client.get(reverse("staff:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Waiting for the team")

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
        # The real password now fails too - that is the point of the throttle.
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

    def test_states_with_the_same_name_in_different_countries_stay_apart(self):
        """The reason this is not just breakdown(qs, "state"): ISO 3166-2 gives
        Ghana, Kenya and Botswana each a region called "Central", and merging
        them would invent a three-country province nobody applied from."""
        make_application(state="Central", country="Ghana")
        make_application(state="Central", country="Kenya")
        make_application(state="Central", country="Kenya")
        result = analytics.region_breakdown(EmbarkApplication.objects.all())
        by_label = {r["label"]: r["value"] for r in result["rows"]}
        self.assertEqual(by_label["Central, Kenya"], 2)
        self.assertEqual(by_label["Central, Ghana"], 1)
        self.assertNotIn("Central", by_label)

    def test_states_left_blank_are_not_counted_as_answers(self):
        """`state` is optional, and the 2025 form never asked for it at all."""
        make_application(state="Lagos")
        make_application(state="")
        result = analytics.region_breakdown(EmbarkApplication.objects.all())
        self.assertEqual(result["answered"], 1)
        self.assertEqual(result["rows"][0]["label"], "Lagos, Nigeria")
        self.assertEqual(result["rows"][0]["pct"], 100)

    def test_a_state_without_a_country_keeps_its_bare_name(self):
        """Legacy rows only - the form requires country - but a label reading
        "Kano, " would look like a truncation bug."""
        make_application(state="Kano", country="")
        rows = analytics.region_breakdown(EmbarkApplication.objects.all())["rows"]
        self.assertEqual(rows[0]["label"], "Kano")

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
        dates = cohort.current()
        self.assertEqual(start, dates.applications_open)
        self.assertEqual(end, dates.applications_close)

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
    """The dates now come from a `Cohort` row, so these read them through
    `current()` - which with an empty table is the shipped fallback."""

    def setUp(self):
        self.dates = cohort.current()

    def test_day_one_is_day_one_not_day_zero(self):
        progress = cohort.window_progress(self.dates.applications_open)
        self.assertEqual(progress["state"], "open")
        self.assertEqual(progress["elapsed"], 1)

    def test_before_and_after_the_window_are_distinguishable(self):
        before = cohort.window_progress(self.dates.applications_open - dt.timedelta(days=3))
        after = cohort.window_progress(self.dates.applications_close + dt.timedelta(days=2))
        self.assertEqual(before["state"], "upcoming")
        self.assertEqual(before["days_until_open"], 3)
        self.assertEqual(after["state"], "closed")
        self.assertEqual(after["days_since_close"], 2)

    def test_the_public_key_dates_still_read_the_way_they_shipped(self):
        """These strings are on /embark/ and /embark/apply/ - deriving them from
        dates must not change what an applicant sees."""
        self.assertEqual(cohort.key_dates(), [
            ("Applications open", "1 August – 30 September 2026"),
            ("Admission notifications", "25 September – 7 October 2026"),
        ])

    def test_a_saved_cohort_replaces_the_built_in_dates(self):
        """The point of the model: the team moves the window without a deploy."""
        Cohort.objects.create(
            name="Cohort 6", applications_open=dt.date(2027, 3, 1),
            applications_close=dt.date(2027, 4, 15),
            notify_from=dt.date(2027, 4, 20), notify_to=dt.date(2027, 5, 1))

        dates = cohort.current()
        self.assertEqual(dates.name, "Cohort 6")
        self.assertEqual(dates.applications_open, dt.date(2027, 3, 1))
        self.assertEqual(
            cohort.key_dates()[0],
            ("Applications open", "1 March – 15 April 2027"))
        self.assertEqual(analytics.resolve_range("cohort")[2], dt.date(2027, 3, 1))

    def test_a_cohort_that_is_not_current_is_ignored(self):
        Cohort.objects.create(
            name="Cohort 4", applications_open=dt.date(2025, 3, 1),
            applications_close=dt.date(2025, 4, 15),
            notify_from=dt.date(2025, 4, 20), notify_to=dt.date(2025, 5, 1),
            is_current=False)
        self.assertEqual(cohort.current().name, cohort.DEFAULT_NAME)

    def test_dates_that_run_backwards_are_refused(self):
        """A close date before the open date makes the window meter divide by a
        negative number, so it must not be savable."""
        backwards = Cohort(name="Wrong", applications_open=dt.date(2027, 4, 1),
                           applications_close=dt.date(2027, 3, 1),
                           notify_from=dt.date(2027, 5, 1),
                           notify_to=dt.date(2027, 5, 2))
        with self.assertRaises(ValidationError):
            backwards.full_clean()


@SSL_REDIRECT_OFF
class StaffPasswordChangeTests(TestCase):
    """Staff can replace the password an administrator handed them."""

    NEW = "sunset-marble-97"

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("dare", password=PASSWORD, is_staff=True)
        self.client.login(username="dare", password=PASSWORD)

    def test_anonymous_is_bounced_to_the_staff_login(self):
        self.client.logout()
        response = self.client.get(reverse("staff:password_change"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("staff:login"), response["Location"])

    def test_a_signed_in_non_staff_user_cannot_reach_it(self):
        """is_staff, not merely is_authenticated -- the page is inside the area
        that reads applicant data."""
        self.client.logout()
        User.objects.create_user("outsider", password=PASSWORD)
        self.client.login(username="outsider", password=PASSWORD)
        response = self.client.get(reverse("staff:password_change"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("staff:login"), response["Location"])

    def test_the_page_renders_for_staff(self):
        response = self.client.get(reverse("staff:password_change"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Change your password")

    def test_changing_it_works_and_keeps_the_session(self):
        response = self.client.post(reverse("staff:password_change"), {
            "old_password": PASSWORD,
            "new_password1": self.NEW,
            "new_password2": self.NEW,
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.NEW))
        # Still signed in: a password change that silently logged everyone out
        # would read as the form having failed.
        self.assertEqual(self.client.get(reverse("staff:analytics")).status_code, 200)

    def test_the_wrong_current_password_is_rejected(self):
        response = self.client.post(reverse("staff:password_change"), {
            "old_password": "not-the-password",
            "new_password1": self.NEW,
            "new_password2": self.NEW,
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_a_weak_new_password_is_refused(self):
        """The validators are the reason this page is worth having: the shared
        starter password cannot be set again through it."""
        for weak in ["yosie", "1234", "password"]:
            with self.subTest(weak=weak):
                self.client.post(reverse("staff:password_change"), {
                    "old_password": PASSWORD,
                    "new_password1": weak,
                    "new_password2": weak,
                })
                self.user.refresh_from_db()
                self.assertTrue(self.user.check_password(PASSWORD))


# ==================================================== decisions and staff email
@SSL_REDIRECT_OFF
class MailMergeTests(TestCase):
    """Placeholder substitution: the part that ends up in a real inbox."""

    def test_a_placeholder_becomes_the_applicants_own_detail(self):
        app = make_application(name="Chidi Okafor", business_name="Okafor Foods")
        out = mailmerge.render(
            "Dear {{ first_name }}, about {{ business_name }}.",
            mailmerge.context_for(app))
        self.assertEqual(out, "Dear Chidi, about Okafor Foods.")

    def test_spacing_inside_the_braces_does_not_matter(self):
        app = make_application(name="Chidi Okafor")
        context = mailmerge.context_for(app)
        self.assertEqual(mailmerge.render("{{first_name}}", context), "Chidi")
        self.assertEqual(mailmerge.render("{{   first_name   }}", context), "Chidi")

    def test_a_nameless_application_does_not_produce_dear_comma(self):
        app = make_application(name="")
        self.assertEqual(
            mailmerge.render("Dear {{ first_name }},", mailmerge.context_for(app)),
            "Dear there,")

    def test_an_unknown_placeholder_is_reported_not_blanked(self):
        """A typo must stop the send. Blanked, it arrives as "Dear ,"."""
        self.assertEqual(mailmerge.unknown("Hi {{ frist_name }}"), ["frist_name"])
        self.assertEqual(mailmerge.unknown("Hi {{ first_name }}"), [])

    def test_template_syntax_is_not_executed(self):
        """The body is prose typed by a person, not a program to be run."""
        app = make_application(name="Chidi Okafor")
        text = "{% if 1 %}x{% endif %} {{ obj.email }}"
        self.assertEqual(mailmerge.render(text, mailmerge.context_for(app)), text)


@SSL_REDIRECT_OFF
class EmailTemplateModelTests(TestCase):
    def test_a_misspelled_placeholder_is_refused_at_save(self):
        template = EmailTemplate(name="Offer", subject="Hello",
                                 body="Dear {{ frist_name }},")
        with self.assertRaises(ValidationError) as caught:
            template.full_clean()
        self.assertIn("frist_name", str(caught.exception))

    def test_the_default_is_preferred_over_an_alphabetically_earlier_one(self):
        EmailTemplate.objects.create(name="A plain one", subject="s", body="b",
                                     purpose=EmailTemplate.APPROVED)
        wanted = EmailTemplate.objects.create(
            name="Z the real one", subject="s", body="b",
            purpose=EmailTemplate.APPROVED, is_default=True)
        self.assertEqual(EmailTemplate.preferred(EmailTemplate.APPROVED), wanted)

    def test_no_template_for_a_purpose_is_none_not_an_error(self):
        self.assertIsNone(EmailTemplate.preferred(EmailTemplate.DECLINED))


@SSL_REDIRECT_OFF
class DecisionTests(TestCase):
    """Recording approve / decline, and who may do it."""

    def setUp(self):
        cache.clear()
        mail.outbox = []
        self.user = User.objects.create_user("dare", password=PASSWORD, is_staff=True)
        self.app = make_application()
        self.url = reverse("staff:decide",
                           kwargs={"slug": "applications", "pk": self.app.pk})

    def test_a_stranger_cannot_decide_anything(self):
        response = self.client.post(self.url, {"decision": "approved"})
        self.assertEqual(response.status_code, 302)
        self.app.refresh_from_db()
        self.assertEqual(self.app.decision, "")

    def test_approving_records_who_and_when(self):
        self.client.login(username="dare", password=PASSWORD)
        self.client.post(self.url, {"decision": "approved"})
        self.app.refresh_from_db()
        self.assertEqual(self.app.decision, "approved")
        self.assertEqual(self.app.decided_by, self.user)
        self.assertIsNotNone(self.app.decided_at)

    def test_approving_does_not_send_anything(self):
        """Deciding and telling someone are two separate actions."""
        self.client.login(username="dare", password=PASSWORD)
        self.client.post(self.url, {"decision": "approved"})
        self.app.refresh_from_db()
        self.assertEqual(len(mail.outbox), 0)
        self.assertIsNone(self.app.decision_email_sent_at)

    def test_clearing_a_decision_clears_the_stamps_with_it(self):
        self.client.login(username="dare", password=PASSWORD)
        self.client.post(self.url, {"decision": "approved"})
        self.client.post(self.url, {"decision": ""})
        self.app.refresh_from_db()
        self.assertEqual(self.app.decision, "")
        self.assertIsNone(self.app.decided_at)
        self.assertIsNone(self.app.decided_by)

    def test_an_invented_decision_is_refused(self):
        self.client.login(username="dare", password=PASSWORD)
        response = self.client.post(self.url, {"decision": "maybe"})
        self.assertEqual(response.status_code, 404)

    def test_a_collection_that_records_no_decisions_has_no_such_page(self):
        self.client.login(username="dare", password=PASSWORD)
        message = ContactMessage.objects.create(
            name="Ada", email="a@example.com", subject="Hi", message="Hello")
        response = self.client.post(
            reverse("staff:decide", kwargs={"slug": "messages", "pk": message.pk}),
            {"decision": "approved"})
        self.assertEqual(response.status_code, 404)


@SSL_REDIRECT_OFF
@override_settings(EMBARK_FROM_EMAIL="Embark <embark@iadebayo.foundation>",
                   EMBARK_REPLY_TO="hello@iadebayo.foundation")
class ApplicantEmailTests(TestCase):
    """Composing and sending one message to one applicant."""

    def setUp(self):
        cache.clear()
        mail.outbox = []
        User.objects.create_user("dare", password=PASSWORD, is_staff=True)
        self.client.login(username="dare", password=PASSWORD)
        self.app = make_application(name="Chidi Okafor", email="chidi@example.com",
                                    decision="approved")
        self.template = EmailTemplate.objects.create(
            name="Cohort offer", purpose=EmailTemplate.APPROVED, is_default=True,
            subject="Welcome to {{ cohort }}, {{ first_name }}",
            body="Dear {{ first_name }},\n\nYou are in.")
        self.url = reverse("staff:email",
                           kwargs={"slug": "applications", "pk": self.app.pk})

    def test_the_box_is_prefilled_with_the_real_message_not_the_template(self):
        """What a staffer reads before sending must be what actually arrives."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        body = response.context["form"].initial["body"]
        self.assertIn("Dear Chidi,", body)
        self.assertNotIn("{{", body)

    def test_the_default_template_for_the_decision_is_the_one_offered(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context["chosen"], self.template)

    def test_sending_delivers_from_the_embark_address_and_stamps_the_row(self):
        response = self.client.post(self.url, {
            "subject": "Welcome to Cohort 5, Chidi",
            "body": "Dear Chidi,\n\nYou are in."})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["chidi@example.com"])
        self.assertEqual(sent.from_email, "Embark <embark@iadebayo.foundation>")
        self.assertEqual(sent.reply_to, ["hello@iadebayo.foundation"])
        self.app.refresh_from_db()
        self.assertIsNotNone(self.app.decision_email_sent_at)

    def test_a_placeholder_typed_by_hand_is_still_filled_in(self):
        self.client.post(self.url, {"subject": "Hello {{ first_name }}",
                                    "body": "Dear {{ first_name }},"})
        self.assertEqual(mail.outbox[0].subject, "Hello Chidi")

    def test_a_misspelled_placeholder_stops_the_send(self):
        response = self.client.post(self.url, {"subject": "Hi",
                                               "body": "Dear {{ frist_name }},"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.app.refresh_from_db()
        self.assertIsNone(self.app.decision_email_sent_at)

    def test_a_failed_send_leaves_the_row_unstamped(self):
        """Otherwise a bounced message reads as a delivered one, forever."""
        with mock.patch("django.core.mail.EmailMessage.send",
                        side_effect=OSError("mail server down")):
            response = self.client.post(self.url, {"subject": "Hi", "body": "Hello"})
        self.assertEqual(response.status_code, 200)
        self.app.refresh_from_db()
        self.assertIsNone(self.app.decision_email_sent_at)

    def test_an_application_with_no_address_cannot_be_mailed(self):
        nowhere = make_application(name="No Address", email="")
        url = reverse("staff:email",
                      kwargs={"slug": "applications", "pk": nowhere.pk})
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {"subject": "Hi", "body": "Hello"})
        self.assertEqual(len(mail.outbox), 0)

    def test_a_stranger_cannot_open_the_compose_page(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/staff/login/", response["Location"])


class ZeptoMailBackendTests(TestCase):
    """The HTTP call is mocked - these pin the payload shape, not delivery."""

    def send(self, message, **backend_kwargs):
        from .mail_backends import ZeptoMailBackend
        backend = ZeptoMailBackend(token="Zoho-enczapikey tok123", **backend_kwargs)
        with mock.patch("urllib.request.urlopen") as urlopen:
            sent = backend.send_messages([message])
        return sent, urlopen

    def test_builds_the_request_zeptomail_expects(self):
        import json
        message = mail.EmailMessage(
            "Hello", "Plain body", "IADEBAYO Foundation <noreply@iadebayo.foundation>",
            ["Jane Doe <jane@example.com>"], reply_to=["hello@iadebayo.foundation"])
        sent, urlopen = self.send(message)

        self.assertEqual(sent, 1)
        request = urlopen.call_args.args[0]
        # Prefix pasted along with the token is stripped, not doubled.
        self.assertEqual(request.get_header("Authorization"), "Zoho-enczapikey tok123")
        payload = json.loads(request.data)
        self.assertEqual(payload["from"], {"address": "noreply@iadebayo.foundation",
                                           "name": "IADEBAYO Foundation"})
        self.assertEqual(payload["to"], [{"email_address": {
            "address": "jane@example.com", "name": "Jane Doe"}}])
        self.assertEqual(payload["reply_to"], [{"address": "hello@iadebayo.foundation"}])
        self.assertEqual(payload["textbody"], "Plain body")
        self.assertNotIn("htmlbody", payload)

    def test_the_endpoint_defaults_to_zeptomails_own_host(self):
        message = mail.EmailMessage("s", "b", "a@iadebayo.foundation", ["x@example.com"])
        _, urlopen = self.send(message)
        self.assertEqual(urlopen.call_args.args[0].full_url,
                         "https://api.zeptomail.com/v1.1/email")

    def test_the_endpoint_can_be_pointed_at_the_accounts_own_host(self):
        """Newer accounts are told to use cpaas.zoho.com, the EU ones their own
        host. Wrong host answers 401, which reads exactly like a bad token."""
        message = mail.EmailMessage("s", "b", "a@iadebayo.foundation", ["x@example.com"])
        with override_settings(ZEPTOMAIL_API_URL="https://cpaas.zoho.com/v1.1/email"):
            _, urlopen = self.send(message)
        self.assertEqual(urlopen.call_args.args[0].full_url,
                         "https://cpaas.zoho.com/v1.1/email")

    def test_a_rejection_raises_with_zeptomail_s_explanation(self):
        import io
        import urllib.error
        from .mail_backends import ZeptoMailBackend, ZeptoMailError
        error = urllib.error.HTTPError(
            "url", 400, "Bad Request", {}, io.BytesIO(b'{"error":"sender not verified"}'))
        backend = ZeptoMailBackend(token="tok")
        message = mail.EmailMessage("s", "b", "a@iadebayo.foundation", ["x@example.com"])
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesMessage(ZeptoMailError, "sender not verified"):
                backend.send_messages([message])


@SSL_REDIRECT_OFF
class DecisionPagesRenderTests(TestCase):
    """The screens themselves, because a template error is invisible to unit tests."""

    def setUp(self):
        cache.clear()
        User.objects.create_user("dare", password=PASSWORD, is_staff=True)
        self.client.login(username="dare", password=PASSWORD)
        self.app = make_application(name="Chidi Okafor", email="chidi@example.com")

    def _detail(self):
        return self.client.get(reverse(
            "staff:detail", kwargs={"slug": "applications", "pk": self.app.pk}))

    def test_an_undecided_application_offers_both_decisions(self):
        page = self._detail().content.decode()
        self.assertIn("Approve", page)
        self.assertIn("Decline", page)
        self.assertIn("No decision yet", page)

    def test_an_approved_application_warns_until_the_person_is_told(self):
        self.app.decision = "approved"
        self.app.decided_at = timezone.now()
        self.app.save()
        page = self._detail().content.decode()
        self.assertIn("has not been told", page)
        self.assertIn("Send email", page)

    def test_the_decision_is_not_listed_as_something_they_submitted(self):
        """Our own decision is not one of the applicant's answers."""
        page = self._detail().content.decode()
        self.assertNotIn("Decision email sent at", page)

    def test_a_submission_without_decisions_shows_no_decision_card(self):
        message = ContactMessage.objects.create(
            name="Ada", email="a@example.com", subject="Hi", message="Hello")
        page = self.client.get(reverse(
            "staff:detail", kwargs={"slug": "messages", "pk": message.pk})
        ).content.decode()
        self.assertNotIn("Send email", page)

    def test_the_templates_collection_is_reachable_and_listed(self):
        EmailTemplate.objects.create(name="Cohort offer", subject="Hi",
                                     body="Dear {{ first_name }},")
        page = self.client.get(
            reverse("staff:list", kwargs={"slug": "email-templates"})).content.decode()
        self.assertIn("Cohort offer", page)

    def test_the_template_form_lists_the_placeholders_that_exist(self):
        page = self.client.get(
            reverse("staff:new", kwargs={"slug": "email-templates"})).content.decode()
        self.assertIn("{{ first_name }}", page)
