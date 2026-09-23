"""Tests for writing to applicants: the resume link, and the two send screens.

These cover the parts that reach a real person's inbox, so the assertions are
mostly about restraint rather than function: that a stale link degrades to an
ordinary form instead of an error, that a failed send leaves no "we told them"
stamp behind, that a resumed draft updates the row it came from instead of
forking a second one, and that nothing sends on a GET.
"""
import datetime as dt

from django.contrib.auth.models import User
from django.core import mail
from django.core.signing import TimestampSigner
from django.test import TestCase, override_settings
from django.urls import reverse

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
