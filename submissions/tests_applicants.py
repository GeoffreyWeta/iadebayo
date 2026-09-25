import io
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .applicants import unfinished_applicants, unfinished_breakdown
from .forms import EmbarkApplicationForm
from .models import ApplicationEmailIdentity, EmbarkApplication, PartialApplication
from .tests import EMBARK


@override_settings(SECURE_SSL_REDIRECT=False, RECAPTCHA_SECRET_KEY="",
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ApplicantReconciliationTests(TestCase):
    def draft(self, draft_id, email="", **kwargs):
        return PartialApplication.objects.create(draft_id=draft_id, email=email, **kwargs)

    def staff(self):
        user = User.objects.create_superuser("reviewer", "staff@example.com", "test-password")
        self.client.force_login(user)

    def test_completed_and_unstamped_submitted_applicants_are_excluded(self):
        self.draft("finished-draft", "finished@example.com", completed_at=timezone.now())
        self.draft("stale-draft", " Person@Example.com ")
        EmbarkApplication.objects.create(email="person@example.com")
        open_row = self.draft("open-draft", "open@example.com")
        self.assertEqual(list(unfinished_applicants()), [open_row])

    def test_latest_email_draft_wins_but_blank_emails_remain_separate(self):
        old = self.draft("old-device", " PERSON@example.com ")
        latest = self.draft("new-device", "person@example.com")
        # Equal timestamps still have a deterministic winner.
        PartialApplication.objects.filter(pk=old.pk).update(updated_at=latest.updated_at)
        a = self.draft("no-email-one", phone="123456789")
        b = self.draft("no-email-two", phone="123456789")
        self.assertSetEqual(set(unfinished_applicants().values_list("pk", flat=True)),
                            {latest.pk, a.pk, b.pk})

    def test_completed_draft_excludes_its_other_device(self):
        self.draft("completed", "same@example.com", completed_at=timezone.now())
        self.draft("other-device", "SAME@example.com")
        self.assertFalse(unfinished_applicants().exists())

    def test_late_background_save_is_marked_complete(self):
        EmbarkApplication.objects.create(email="person@example.com")
        response = self.client.post(reverse("submissions:apply_progress"), {
            "draft_id": "late-device-123", "email": "PERSON@example.com"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(PartialApplication.objects.get().completed_at)
        self.assertFalse(unfinished_applicants().exists())

    @patch("submissions.views.acknowledge")
    @patch("submissions.views.notify_team")
    def test_submission_closes_legacy_email_with_surrounding_spaces(self, notify, acknowledge):
        row = self.draft("legacy-device", " CHIDI@EXAMPLE.COM ")
        self.client.post(reverse("submissions:apply"), EMBARK)
        row.refresh_from_db()
        self.assertIsNotNone(row.completed_at)

    def test_breakdown_uses_latest_answers_and_includes_missing_data(self):
        self.draft("old-answers", "one@example.com", country="Ghana",
                   answers={"business_sector": "fashion"})
        self.draft("new-answers", "ONE@example.com", country="Nigeria",
                   answers={"business_sector": "technology"})
        self.draft("missing-answers", phone="123456789")
        report = unfinished_breakdown(unfinished_applicants())
        self.assertEqual(report["total"], 2)
        self.assertEqual(report["missing_email"], 1)
        self.assertIn({"label": "Technology", "count": 1, "percent": 50.0}, report["sectors"])
        self.assertIn({"label": "Not provided", "count": 1, "percent": 50.0}, report["sectors"])
        self.assertNotIn("Ghana", [row["label"] for row in report["countries"]])

    def test_staff_and_admin_lists_exports_and_dashboard_share_the_queue(self):
        self.staff()
        self.draft("already-done", "done@example.com", name="Finished Person",
                   completed_at=timezone.now())
        self.draft("open-person", "open@example.com", name="Open Person", country="Ghana",
                   answers={"business_sector": "agriculture"})
        for url in [reverse("staff:list", args=["unfinished"]),
                    reverse("staff:export", args=["unfinished"]),
                    reverse("admin:submissions_partialapplication_changelist")]:
            response = self.client.get(url)
            self.assertContains(response, "Open Person")
            self.assertNotContains(response, "Finished Person")
        listing = self.client.get(reverse("staff:list", args=["unfinished"]))
        self.assertEqual(listing.context["unfinished_breakdown"]["total"], 1)
        exported = self.client.get(reverse("staff:export", args=["unfinished"]))
        self.assertContains(exported, "Agriculture")
        dashboard = self.client.get(reverse("staff:home"))
        queue = next(row for row in dashboard.context["waiting"] if row["c"].slug == "unfinished")
        self.assertEqual(queue["total"], 1)
        self.assertEqual(queue["pending"], 1)

    def test_filtered_report_matches_export(self):
        self.staff()
        self.draft("ghana-person", "ghana@example.com", country="Ghana")
        self.draft("nigeria-person", "nigeria@example.com", country="Nigeria")
        response = self.client.get(reverse("staff:list", args=["unfinished"]), {"country": "Ghana"})
        self.assertEqual(response.context["unfinished_breakdown"]["total"], 1)
        exported = self.client.get(reverse("staff:export", args=["unfinished"]), {"country": "Ghana"})
        self.assertContains(exported, "ghana@example.com")
        self.assertNotContains(exported, "nigeria@example.com")

    def test_follow_up_keeps_unfinished_count_until_submission(self):
        self.staff()
        row = self.draft("followed-up-person", "open@example.com")
        self.client.post(reverse("staff:bulk", args=["unfinished"]),
                         {"pks": [row.pk], "action": "review"})
        page = self.client.get(reverse("staff:home"))
        queue = next(item for item in page.context["waiting"] if item["c"].slug == "unfinished")
        badge = next(item for section in page.context["nav_sections"] for item in section["items"]
                     if item["c"].slug == "unfinished")
        self.assertEqual((queue["total"], queue["pending"], queue["followed_up"]), (1, 0, 1))
        self.assertEqual(badge["badge"], 1)
        self.assertContains(page, "Still unfinished &middot; 1 followed up &middot; 0 not followed up")
        EmbarkApplication.objects.create(email=row.email)
        page = self.client.get(reverse("staff:home"))
        badge = next(item for section in page.context["nav_sections"] for item in section["items"]
                     if item["c"].slug == "unfinished")
        self.assertEqual(badge["badge"], 0)
        self.assertContains(page, '0<span class="visually-hidden"> unfinished applications</span>')

    @patch("submissions.services.send_to_applicant")
    def test_stale_email_link_cannot_nudge_a_completed_applicant(self, send):
        self.staff()
        row = self.draft("completed-person", "done@example.com", completed_at=timezone.now())
        response = self.client.post(reverse("staff:email", args=["unfinished", row.pk]),
                                    {"subject": "Reminder", "body": "Please finish"})
        self.assertEqual(response.status_code, 404)
        send.assert_not_called()

    def test_public_form_rejects_legacy_duplicate_with_case_and_spaces(self):
        EmbarkApplication.objects.create(email=" CHIDI@EXAMPLE.COM ")
        form = EmbarkApplicationForm(EMBARK)
        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_database_reservation_rejects_two_prevalidated_submissions(self):
        first = EmbarkApplicationForm(EMBARK)
        second = EmbarkApplicationForm(EMBARK)
        self.assertTrue(first.is_valid(), first.errors)
        self.assertTrue(second.is_valid(), second.errors)
        first.save()
        with self.assertRaises(ValidationError):
            second.save()
        self.assertEqual(EmbarkApplication.objects.count(), 1)
        self.assertEqual(ApplicationEmailIdentity.objects.count(), 1)

    @patch("submissions.views.acknowledge")
    @patch("submissions.views.notify_team")
    def test_repeated_post_does_not_create_or_notify_twice(self, notify, acknowledge):
        for _ in range(2):
            self.client.post(reverse("submissions:apply"), EMBARK)
        self.assertEqual(EmbarkApplication.objects.count(), 1)
        self.assertEqual(notify.call_count, 1)
        self.assertEqual(acknowledge.call_count, 1)

    def test_audit_is_read_only_and_reports_duplicate_rows(self):
        EmbarkApplication.objects.create(email="same@example.com")
        EmbarkApplication.objects.create(email=" SAME@example.com ")
        output = io.StringIO()
        call_command("audit_applicants", stdout=output)
        report = json.loads(output.getvalue())
        self.assertEqual(report["submitted_unique_emails"], 1)
        self.assertEqual(report["extra_rows_sharing_email"], 1)
        self.assertEqual(EmbarkApplication.objects.count(), 2)
