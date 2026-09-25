"""Tests for writing to applicants: the resume link, and the two send screens.

These cover the parts that reach a real person's inbox, so the assertions are
mostly about restraint rather than function: that a stale link degrades to an
ordinary form instead of an error, that a failed send leaves no "we told them"
stamp behind, that a resumed draft updates the row it came from instead of
forking a second one, and that nothing sends on a GET.
"""
import datetime as dt
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.signing import TimestampSigner
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from submissions.models import EmbarkApplication, PartialApplication

PASSWORD = "pw-for-tests-only"
SSL_REDIRECT_OFF = override_settings(SECURE_SSL_REDIRECT=False)
LOCMEM = override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")


def a_staff_user(client):
    user = User.objects.create_user("staffer", password=PASSWORD, is_staff=True)
    client.login(username="staffer", password=PASSWORD)
    return user


def a_draft(**kwargs):
    fields = {"draft_id": "draft-abc-123", "name": "Ada Obi",
              "email": "ada@example.com", "business_name": "Acme Crafts",
              "answers": {"name": "Ada Obi", "business_name": "Acme Crafts",
                          "city": "Lagos"},
              "furthest_step": 2}
    fields.update(kwargs)
    return PartialApplication.objects.create(**fields)


@SSL_REDIRECT_OFF
class ResumeLinkTests(TestCase):
    """The link in the nudge email, and what happens when it goes stale."""

    def test_the_link_brings_their_answers_back(self):
        draft = a_draft()
        response = self.client.get(reverse("core:apply"),
                                   {"resume": draft.resume_token})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome back")
        self.assertContains(response, "Acme Crafts")

    def test_the_resumed_form_carries_the_same_draft_id(self):
        """Otherwise finishing the form opens a second row and the first one
        stays on the chase list forever."""
        draft = a_draft()
        response = self.client.get(reverse("core:apply"),
                                   {"resume": draft.resume_token})
        self.assertContains(response, f'data-resume-draft-id="{draft.draft_id}"')

    def test_the_token_is_not_the_raw_draft_id(self):
        draft = a_draft()
        self.assertNotEqual(draft.resume_token, draft.draft_id)
        self.assertIn(draft.draft_id, draft.resume_token)     # signed, not hidden

    def test_a_forged_token_is_ignored(self):
        a_draft()
        response = self.client.get(reverse("core:apply"),
                                   {"resume": "draft-abc-123:forged:signature"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Welcome back")

    def test_an_expired_link_still_renders_an_ordinary_form(self):
        """Six weeks later somebody clicks the old mail. They should get a form,
        not an error page telling them off."""
        draft = a_draft()
        old = TimestampSigner(salt=PartialApplication.RESUME_SALT).sign(draft.draft_id)
        with override_settings(USE_TZ=True):
            PartialApplication.RESUME_MAX_AGE_DAYS = 0        # everything is stale
            try:
                response = self.client.get(reverse("core:apply"), {"resume": old})
            finally:
                PartialApplication.RESUME_MAX_AGE_DAYS = 45
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Welcome back")

    def test_a_deleted_draft_does_not_500(self):
        draft = a_draft()
        token = draft.resume_token
        draft.delete()
        response = self.client.get(reverse("core:apply"), {"resume": token})
        self.assertEqual(response.status_code, 200)

    def test_no_resume_parameter_is_just_the_form(self):
        response = self.client.get(reverse("core:apply"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Welcome back")


@SSL_REDIRECT_OFF
@LOCMEM
class NudgeOneApplicantTests(TestCase):
    def setUp(self):
        a_staff_user(self.client)
        self.draft = a_draft()

    def url(self):
        return reverse("staff:email", args=["unfinished", self.draft.pk])

    def test_the_compose_page_opens_for_an_unfinished_draft(self):
        """Unfinished applications are mailable without being decidable."""
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)

    def test_a_get_sends_nothing(self):
        self.client.get(self.url())
        self.assertEqual(len(mail.outbox), 0)

    def test_sending_stamps_the_nudge_column_not_the_decision_one(self):
        self.client.post(self.url(), {"subject": "You were nearly there",
                                      "body": "Carry on here: {{ resume_link }}"})
        self.draft.refresh_from_db()
        self.assertIsNotNone(self.draft.nudge_sent_at)
        self.assertEqual(len(mail.outbox), 1)

    def test_the_resume_link_is_substituted_into_the_body(self):
        self.client.post(self.url(), {"subject": "Nearly there",
                                      "body": "Continue: {{ resume_link }}"})
        body = mail.outbox[0].body
        self.assertIn(self.draft.resume_token, body)
        self.assertNotIn("{{ resume_link }}", body)

    def test_a_failed_send_leaves_no_stamp(self):
        """A stamp written on a failure would make the person invisible to the
        next person looking for who still needs telling."""
        with override_settings(
                EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                EMAIL_HOST="127.0.0.1", EMAIL_PORT=1):
            self.client.post(self.url(), {"subject": "x", "body": "y"})
        self.draft.refresh_from_db()
        self.assertIsNone(self.draft.nudge_sent_at)

    def test_a_draft_with_no_address_cannot_be_mailed(self):
        nameless = a_draft(draft_id="d2", email="", phone="8012345678")
        response = self.client.post(
            reverse("staff:email", args=["unfinished", nameless.pk]),
            {"subject": "x", "body": "y"})
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(response.status_code, 200)


@SSL_REDIRECT_OFF
@LOCMEM
class MailTheTickedTests(TestCase):
    def setUp(self):
        a_staff_user(self.client)
        self.people = [EmbarkApplication.objects.create(
            name=f"P{i}", email=f"p{i}@example.com", phone="1", city="Lagos",
            country="Nigeria", business_name=f"Biz {i}") for i in range(3)]

    def url(self):
        return reverse("staff:email_many", args=["applications"])

    def test_the_page_lists_who_it_will_reach_before_sending(self):
        response = self.client.post(self.url(),
                                    {"pks": [p.pk for p in self.people]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)          # opening it sends nothing
        for p in self.people:
            self.assertContains(response, p.email)

    def test_sending_needs_the_send_button(self):
        """Choosing a template or reloading must never be a send."""
        self.client.post(self.url(), {"pks": [p.pk for p in self.people],
                                      "subject": "Hi", "body": "There"})
        self.assertEqual(len(mail.outbox), 0)

    def test_each_person_gets_their_own_message(self):
        self.client.post(self.url(), {"pks": [p.pk for p in self.people],
                                      "send": "1", "subject": "Welcome {{ first_name }}",
                                      "body": "Hello {{ first_name }}"})
        self.assertEqual(len(mail.outbox), 3)
        # One recipient each: nobody can see who else was written to.
        for message in mail.outbox:
            self.assertEqual(len(message.to), 1)
        subjects = sorted(m.subject for m in mail.outbox)
        self.assertEqual(subjects, ["Welcome P0", "Welcome P1", "Welcome P2"])

    def test_rows_without_an_address_are_named_rather_than_skipped_quietly(self):
        silent = EmbarkApplication.objects.create(
            name="No Address", email="", phone="1", city="Lagos",
            country="Nigeria", business_name="Biz X")
        response = self.client.post(
            self.url(), {"pks": [p.pk for p in self.people] + [silent.pk]})
        self.assertContains(response, "No Address")

    def test_nothing_ticked_goes_back_to_the_list(self):
        response = self.client.post(self.url(), {"pks": []})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_a_collection_that_is_not_mailable_refuses(self):
        response = self.client.post(reverse("staff:email_many", args=["team"]),
                                    {"pks": [1]})
        self.assertEqual(response.status_code, 404)


@SSL_REDIRECT_OFF
@LOCMEM
class WriteToEveryoneTests(TestCase):
    """"Everyone", as opposed to "the thirty rows currently on screen"."""

    def setUp(self):
        mail.outbox = []
        a_staff_user(self.client)
        self.url = reverse("staff:email_many", kwargs={"slug": "unfinished"})
        self.list_url = reverse("staff:list", kwargs={"slug": "unfinished"})

    def drafts(self, n, **kwargs):
        return [a_draft(draft_id=f"d{i}", email=f"p{i}@example.com",
                        name=f"Person {i}", **kwargs) for i in range(n)]

    # ------------------------------------------------------------- selection
    def test_apply_to_all_reaches_rows_that_were_never_ticked(self):
        self.drafts(5)
        response = self.client.post(self.url, {"all": "1", "next": self.list_url})
        self.assertEqual(len(response.context["rows"]), 5)

    def test_apply_to_all_means_the_list_as_filtered_not_the_whole_table(self):
        """The set someone means by "everyone" is the one in front of them."""
        self.drafts(3)
        a_draft(draft_id="odd", email="zed@example.com", name="Zed Findable")
        response = self.client.post(
            self.url, {"all": "1", "next": self.list_url + "?q=Findable"})
        names = [str(r) for r in response.context["rows"]]
        self.assertEqual(len(names), 1)
        self.assertIn("Zed", names[0])

    def test_without_apply_to_all_only_the_ticked_rows_are_used(self):
        rows = self.drafts(4)
        response = self.client.post(self.url, {"pks": [rows[0].pk, rows[1].pk]})
        self.assertEqual(len(response.context["rows"]), 2)

    def test_a_crafted_filter_name_cannot_become_a_queryset_lookup(self):
        self.drafts(2)
        response = self.client.post(
            self.url, {"all": "1", "next": self.list_url + "?draft_id=d0"})
        # draft_id is not in the collection's declared filters, so it is ignored
        # rather than applied.
        self.assertEqual(len(response.context["rows"]), 2)

    # --------------------------------------------------------- not twice
    def test_people_already_written_to_are_held_back_by_default(self):
        fresh = a_draft(draft_id="new", email="new@example.com", name="New Person")
        done = a_draft(draft_id="old", email="old@example.com", name="Old Person",
                       nudge_sent_at=timezone.now())
        response = self.client.post(self.url, {"all": "1", "next": self.list_url})
        self.assertEqual([r.pk for r in response.context["rows"]], [fresh.pk])
        self.assertEqual([r.pk for r in response.context["repeats"]], [done.pk])

    def test_the_held_back_are_shown_not_hidden(self):
        """Ticking "include them" must not send to names nobody has seen."""
        a_draft(draft_id="old", email="old@example.com", name="Old Person",
                nudge_sent_at=timezone.now())
        a_draft(draft_id="new", email="new@example.com", name="New Person")
        page = self.client.post(self.url, {"all": "1", "next": self.list_url})
        self.assertContains(page, "old@example.com")

    def test_ticking_again_includes_them(self):
        a_draft(draft_id="old", email="old@example.com", name="Old Person",
                nudge_sent_at=timezone.now())
        a_draft(draft_id="new", email="new@example.com", name="New Person")
        response = self.client.post(
            self.url, {"all": "1", "next": self.list_url, "again": "1"})
        self.assertEqual(len(response.context["rows"]), 2)

    def test_a_send_skips_the_already_written_to(self):
        a_draft(draft_id="old", email="old@example.com", name="Old Person",
                nudge_sent_at=timezone.now())
        fresh = a_draft(draft_id="new", email="new@example.com", name="New Person")
        self.client.post(self.url, {
            "pks": [fresh.pk, PartialApplication.objects.get(draft_id="old").pk],
            "send": "1", "subject": "Finish your application", "body": "Hello"})
        self.assertEqual([m.to[0] for m in mail.outbox], ["new@example.com"])

    # ------------------------------------------------------------- marking
    def test_marking_ticks_everyone_the_message_reached(self):
        rows = self.drafts(3)
        self.client.post(self.url, {
            "pks": [r.pk for r in rows], "send": "1", "mark": "1",
            "subject": "Finish your application", "body": "Hello"})
        self.assertEqual(
            PartialApplication.objects.filter(reviewed=True).count(), 3)

    def test_without_the_tick_nothing_is_marked(self):
        rows = self.drafts(2)
        self.client.post(self.url, {
            "pks": [r.pk for r in rows], "send": "1",
            "subject": "Finish your application", "body": "Hello"})
        self.assertEqual(
            PartialApplication.objects.filter(reviewed=True).count(), 0)

    def test_a_failed_send_is_never_marked(self):
        """A "followed up" tick on somebody nothing reached is worse than none:
        it is a person nobody will look at again."""
        rows = self.drafts(2)
        with mock.patch("submissions.services.send_to_applicant", return_value=False):
            self.client.post(self.url, {
                "pks": [r.pk for r in rows], "send": "1", "mark": "1",
                "subject": "Finish your application", "body": "Hello"})
        self.assertEqual(
            PartialApplication.objects.filter(reviewed=True).count(), 0)

    # --------------------------------------------------------- bulk marking
    def test_mark_reviewed_can_cover_the_whole_filtered_list(self):
        self.drafts(4)
        self.client.post(reverse("staff:bulk", kwargs={"slug": "unfinished"}),
                         {"action": "review", "all": "1", "next": self.list_url})
        self.assertEqual(
            PartialApplication.objects.filter(reviewed=True).count(), 4)

    def test_nothing_ticked_and_no_all_is_refused_rather_than_applied(self):
        self.drafts(3)
        self.client.post(reverse("staff:bulk", kwargs={"slug": "unfinished"}),
                         {"action": "review", "next": self.list_url})
        self.assertEqual(
            PartialApplication.objects.filter(reviewed=True).count(), 0)

    def test_all_pages_selection_has_enabled_js_hook_and_pins_every_id(self):
        rows = self.drafts(35)
        listing = self.client.get(self.list_url)
        self.assertContains(listing, 'data-select-matching data-count="35"')
        preview = self.client.post(self.url, {"all": "1", "next": self.list_url})
        self.assertSetEqual(set(preview.context["pks"]), {r.pk for r in rows})
        self.assertEqual(len(mail.outbox), 0)

    def test_all_previously_sent_recipients_still_show_resend_controls(self):
        self.drafts(2, nudge_sent_at=timezone.now())
        response = self.client.post(self.url, {"all": "1", "next": self.list_url})
        self.assertContains(response, 'name="again"')
        self.assertContains(response, 'data-bulk-email')
        self.assertEqual(len(mail.outbox), 0)

    def test_browser_delivery_sends_one_and_marks_only_on_acceptance(self):
        row = self.drafts(1)[0]
        response = self.client.post(self.url, {"pks": [row.pk], "bulk_async": "1",
            "send": "1", "mark": "1", "subject": "Hello", "body": "Continue your application"})
        self.assertEqual(response.json(), {"sent": 1, "failed": 0, "skipped": 0})
        row.refresh_from_db()
        self.assertTrue(row.reviewed)
        self.assertIsNotNone(row.nudge_sent_at)

    def test_browser_delivery_rejects_more_than_one_recipient(self):
        rows = self.drafts(2)
        response = self.client.post(self.url, {"pks": [r.pk for r in rows], "bulk_async": "1",
            "send": "1", "subject": "Hello", "body": "Continue"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_completed_since_preview_is_skipped_at_send_time(self):
        row = self.drafts(1)[0]
        row.completed_at = timezone.now()
        row.save()
        response = self.client.post(self.url, {"pks": [row.pk], "bulk_async": "1",
            "send": "1", "mark": "1", "subject": "Hello", "body": "Continue"})
        self.assertEqual(response.json()["skipped"], 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_without_js_large_send_leaves_remaining_recipients_to_continue(self):
        rows = self.drafts(12)
        response = self.client.post(self.url, {"pks": [r.pk for r in rows],
            "send": "1", "mark": "1", "subject": "Hello", "body": "Continue"})
        self.assertEqual(len(mail.outbox), 10)
        self.assertEqual(len(response.context["pks"]), 2)
        self.assertEqual(PartialApplication.objects.filter(reviewed=True).count(), 10)

    def test_invalid_browser_message_returns_errors_without_sending(self):
        row = self.drafts(1)[0]
        response = self.client.post(self.url, {"pks": [row.pk], "bulk_async": "1", "send": "1"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.json())
        self.assertEqual(len(mail.outbox), 0)
