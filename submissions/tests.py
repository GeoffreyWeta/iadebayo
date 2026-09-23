import io
from unittest import mock
import shutil
import tempfile
import zipfile

from django.contrib.auth.models import User
from django.core import mail
from django.core.mail.backends.locmem import EmailBackend as LocMemEmailBackend
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from . import models
from .services import acknowledge
from .models import EmbarkApplication

MEDIA_ROOT = tempfile.mkdtemp()
PASSWORD = "pw-for-tests-only"

# The test client speaks plain http. In production DEBUG is off, which turns on
# SECURE_SSL_REDIRECT, and SecurityMiddleware then answers every request with a
# 301 to https. `follow=True` re-issues a redirected POST as a GET, so each
# @require_POST submission view rejects it with 405 and roughly thirty
# assertions fail - but only when the suite happens to run with DEBUG=False.
# Pinning it here keeps the result the same on a developer's machine, in CI, and
# against a production-shaped .env.
SSL_REDIRECT_OFF = override_settings(SECURE_SSL_REDIRECT=False)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
@SSL_REDIRECT_OFF
class ApplicationVideoDownloadTests(TestCase):
    """The video download is the app's only access-controlled endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.application = EmbarkApplication.objects.create(
            name="Jane Doe", email="jane@example.com", phone="8012345678",
            city="Lagos", country="Nigeria", business_name="Acme Crafts",
            business_video=SimpleUploadedFile("IMG_2453.mp4", b"pretend-video-bytes",
                                              content_type="video/mp4"))
        cls.url = reverse("submissions:download_video", args=[cls.application.pk])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def sign_in(self, username, **flags):
        User.objects.create_user(username, password=PASSWORD, **flags)
        self.client.login(username=username, password=PASSWORD)

    def test_anonymous_visitor_is_sent_to_the_staff_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/staff/login/", response["Location"])
        # ?next= carries the file, so signing in lands on the download rather
        # than dumping the staffer on the dashboard.
        self.assertIn(f"next={self.url}", response["Location"])

    def test_signed_in_non_staff_user_cannot_download(self):
        self.sign_in("member")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/staff/login/", response["Location"])

    def test_staff_get_the_file_named_after_the_applicant(self):
        self.sign_in("staffer", is_staff=True)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="jane-doe-acme-crafts-{self.application.pk}.mp4"')
        self.assertEqual(b"".join(response.streaming_content), b"pretend-video-bytes")

    @override_settings(X_ACCEL_REDIRECT=True)
    def test_x_accel_redirect_hands_the_transfer_to_nginx(self):
        self.sign_in("staffer", is_staff=True)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Accel-Redirect"],
                         "/protected-media/applications/videos/IMG_2453.mp4")
        self.assertEqual(response.content, b"")   # nginx supplies the body

    def test_application_without_a_video_is_a_404(self):
        empty = EmbarkApplication.objects.create(
            name="No Video", email="no@example.com", phone="8000000000",
            city="Abuja", country="Nigeria", business_name="Nothing Ltd")
        self.sign_in("staffer", is_staff=True)
        response = self.client.get(
            reverse("submissions:download_video", args=[empty.pk]))
        self.assertEqual(response.status_code, 404)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
@SSL_REDIRECT_OFF
class EmbarkAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.with_video = EmbarkApplication.objects.create(
            name="Jane Doe", email="jane@example.com", phone="8012345678",
            city="Lagos", country="Nigeria", business_name="Acme Crafts",
            business_video=SimpleUploadedFile("IMG_2453.mp4", b"pretend-video-bytes",
                                              content_type="video/mp4"))
        cls.without_video = EmbarkApplication.objects.create(
            name="No Video", email="no@example.com", phone="8000000000",
            city="Abuja", country="Nigeria", business_name="Nothing Ltd")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        User.objects.create_superuser("boss", "boss@example.com", PASSWORD)
        self.client.login(username="boss", password=PASSWORD)

    def test_change_page_offers_a_download_button(self):
        response = self.client.get(reverse(
            "admin:submissions_embarkapplication_change", args=[self.with_video.pk]))
        self.assertContains(response, "Download video")
        self.assertContains(response, reverse(
            "submissions:download_video", args=[self.with_video.pk]))

    def test_bulk_action_zips_the_selected_videos(self):
        response = self.client.post(
            reverse("admin:submissions_embarkapplication_changelist"),
            {"action": "download_videos_zip",
             "_selected_action": [self.with_video.pk, self.without_video.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

        archive = zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content)))
        # The videoless application is skipped, not an empty entry.
        self.assertEqual(archive.namelist(),
                         [f"jane-doe-acme-crafts-{self.with_video.pk}.mp4"])
        self.assertEqual(archive.read(archive.namelist()[0]), b"pretend-video-bytes")

    def test_bulk_action_warns_when_nothing_was_uploaded(self):
        response = self.client.post(
            reverse("admin:submissions_embarkapplication_changelist"),
            {"action": "download_videos_zip",
             "_selected_action": [self.without_video.pk]}, follow=True)
        self.assertContains(response, "None of the selected applications has a video.")


CONTACT ={"name": "Ada Lovelace", "email": "ada@example.com",
           "subject": "Speaking invitation", "message": "Would you speak at our event?"}

EMBARK = {
    "name": "Chidi Okafor", "gender": "male", "applicant_status": "undergraduate",
    "email": "chidi@example.com", "phone_code": "+234", "phone": "8012345678",
    "date_of_birth": "1999-04-12", "institution": "University of Lagos",
    "city": "Lagos", "state": "Lagos", "country": "Nigeria",
    "linkedin": "https://www.linkedin.com/in/chidi-okafor",
    "social_handle": "@chidifarms", "social_handle_2": "@chidi",
    "business_name": "Okafor Farms", "year_established": "2023",
    "business_website": "okaforfarms.ng", "business_social_handle": "@okaforfarms",
    "business_sector": "agriculture",
    "business_video_url": "https://drive.google.com/file/d/1AbCdEf/view?usp=sharing",
    "major_challenge": "Cold-chain logistics; we partnered with a local courier.",
    "growth_limits": ["funding", "customers"],
    "entrepreneurship_view": "Impact first - profit is what makes the impact repeatable.",
    "device": "laptop", "will_participate": "yes", "reliable_internet": "yes",
    "heard_about": "linkedin", "media_consent": "on",
}

FACULTY = {"name": "Ngozi Eze", "phone_code": "+234", "phone": "8022222222",
           "email": "ngozi@example.com", "faculty_option": "mentor",
           "country": "Nigeria", "city": "Abuja",
           "motivation": "I want to give back to young founders.",
           "about": "Fifteen years in consumer goods."}

VOLUNTEER = {"name": "Tunde Bello", "phone_code": "+234", "phone": "8033333333",
             "email": "tunde@example.com", "skills": "Video editing, design",
             "country": "Nigeria", "city": "Ibadan", "area": "content",
             "motivation": "I believe in the mission.",
             "about": "Freelance editor for six years."}

PARTNER = {"name": "Amaka Obi", "phone_code": "+234", "phone": "8044444444",
           "email": "amaka@example.com", "organization": "Lagos Business Hub",
           "website": "https://example.com", "country": "Nigeria", "city": "Lagos",
           "proposal": "We would like to co-host a pitch day."}


@override_settings(MEDIA_ROOT=MEDIA_ROOT, RECAPTCHA_SECRET_KEY="")
@SSL_REDIRECT_OFF
class PublicFormTests(TestCase):
    """All six public forms, end to end: POST → row saved → emails queued."""

    def submit(self, name, data, **extra):
        payload = dict(data, **extra)
        return self.client.post(reverse(f"submissions:{name}"), payload, follow=True)

    # ------------------------------------------------------------- the pages
    def test_every_form_page_renders(self):
        for page in ["contact", "apply", "join_faculty", "volunteer", "partner", "home"]:
            with self.subTest(page=page):
                response = self.client.get(reverse(f"core:{page}"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "csrfmiddlewaretoken")

    # -------------------------------------------------------- happy paths
    def test_contact_form_saves_and_emails(self):
        response = self.submit("contact", CONTACT)
        self.assertEqual(models.ContactMessage.objects.count(), 1)
        self.assertContains(response, "Thank you!")
        self.assertEqual(len(mail.outbox), 2)          # team + acknowledgement
        self.assertIn("hello@iadebayo.foundation", mail.outbox[0].to)
        self.assertIn("ada@example.com", mail.outbox[1].to)

    def test_newsletter_subscribes_once(self):
        self.submit("newsletter", {"email": "reader@example.com"})
        self.assertEqual(models.NewsletterSubscriber.objects.count(), 1)
        response = self.submit("newsletter", {"email": "reader@example.com"})
        self.assertEqual(models.NewsletterSubscriber.objects.count(), 1)
        self.assertContains(response, "already subscribed")

    def test_embark_application_saves_with_its_video_link(self):
        response = self.submit("apply", EMBARK)
        self.assertContains(response, "Thank you!")
        application = models.EmbarkApplication.objects.get()
        self.assertEqual(application.growth_limits, "funding,customers")
        self.assertEqual(application.business_video_url,
                         "https://drive.google.com/file/d/1AbCdEf/view?usp=sharing")
        self.assertEqual(len(mail.outbox), 2)

    def test_faculty_application_saves(self):
        self.assertContains(self.submit("faculty", FACULTY), "Thank you!")
        self.assertEqual(models.FacultyApplication.objects.count(), 1)

    def test_volunteer_application_saves(self):
        self.assertContains(self.submit("volunteer", VOLUNTEER), "Thank you!")
        self.assertEqual(models.VolunteerApplication.objects.count(), 1)

    def test_partnership_inquiry_saves(self):
        self.assertContains(self.submit("partner", PARTNER), "Thank you!")
        self.assertEqual(models.PartnershipInquiry.objects.count(), 1)

    # --------------------------------------------------------- rejections
    def test_honeypot_blocks_the_submission(self):
        self.submit("contact", CONTACT, website_url="http://spam.example")
        self.assertEqual(models.ContactMessage.objects.count(), 0)

    def test_missing_required_field_is_reported_not_saved(self):
        response = self.submit("faculty", dict(FACULTY, email=""))
        self.assertEqual(models.FacultyApplication.objects.count(), 0)
        self.assertContains(response, "This field is required")

    def test_embark_rejects_an_applicant_who_will_not_participate(self):
        response = self.submit("apply", dict(EMBARK, will_participate="no"))
        self.assertEqual(models.EmbarkApplication.objects.count(), 0)
        self.assertContains(response, "commitment-based programme")

    def test_embark_requires_a_video_link(self):
        response = self.submit("apply", dict(EMBARK, business_video_url=""))
        self.assertEqual(models.EmbarkApplication.objects.count(), 0)
        self.assertContains(response, "This field is required")

    def test_embark_rejects_a_link_to_the_drive_rather_than_the_video(self):
        response = self.submit(
            "apply", dict(EMBARK, business_video_url="https://drive.google.com/drive/my-drive"))
        self.assertEqual(models.EmbarkApplication.objects.count(), 0)
        self.assertContains(response, "links to your Drive, not to the video")

    # -------------------------------------------- personal & business links
    def test_embark_does_not_require_linkedin(self):
        """Plenty of real founders run their venture off Instagram and have no
        LinkedIn at all - a required field they cannot fill is a wall."""
        self.submit("apply", dict(EMBARK, linkedin=""))
        application = models.EmbarkApplication.objects.get()
        self.assertEqual(application.linkedin, "")

    def test_embark_rejects_another_platform_in_the_linkedin_field(self):
        response = self.submit(
            "apply", dict(EMBARK, linkedin="https://instagram.com/chidi"))
        self.assertEqual(models.EmbarkApplication.objects.count(), 0)
        self.assertContains(response, "not a LinkedIn address")

    def test_embark_accepts_a_linkedin_url_without_a_scheme(self):
        """Applicants type "linkedin.com/in/me" far more often than the scheme."""
        self.submit("apply", dict(EMBARK, linkedin="linkedin.com/in/chidi-okafor"))
        application = models.EmbarkApplication.objects.get()
        self.assertEqual(application.linkedin, "https://linkedin.com/in/chidi-okafor")

    def test_embark_accepts_regional_linkedin_subdomains(self):
        self.submit("apply", dict(EMBARK, linkedin="https://ng.linkedin.com/in/chidi"))
        self.assertEqual(models.EmbarkApplication.objects.count(), 1)

    def test_the_optional_link_fields_are_genuinely_optional(self):
        """None of the link fields is compulsory: a business with no site, run by
        someone with no LinkedIn, must still be able to apply."""
        self.submit("apply", dict(EMBARK, linkedin="", social_handle="",
                                  social_handle_2="", business_website="",
                                  business_social_handle=""))
        application = models.EmbarkApplication.objects.get()
        self.assertEqual(application.business_website, "")
        self.assertEqual(application.social_handle_2, "")

    def test_both_personal_handles_and_business_links_are_stored(self):
        self.submit("apply", EMBARK)
        application = models.EmbarkApplication.objects.get()
        self.assertEqual(application.social_handle, "@chidifarms")
        self.assertEqual(application.social_handle_2, "@chidi")
        self.assertEqual(application.business_social_handle, "@okaforfarms")
        # Scheme assumed for the bare domain, same as LinkedIn.
        self.assertEqual(application.business_website, "https://okaforfarms.ng")

    # ------------------------------------------------ country → region field
    def test_region_is_still_free_text_on_the_server(self):
        """The picker is a browser convenience. If the server ever started
        validating `state` against the ISO list, a legacy row or a region ISO
        has not caught up with would be rejected - so a value that is on no
        list has to keep saving."""
        self.submit("apply", dict(EMBARK, country="Nigeria",
                                  state="Somewhere Not On Any List"))
        self.assertEqual(models.EmbarkApplication.objects.get().state,
                         "Somewhere Not On Any List")

    def test_a_picked_region_round_trips(self):
        self.submit("apply", dict(EMBARK, country="Kenya", state="Nakuru"))
        application = models.EmbarkApplication.objects.get()
        self.assertEqual(application.country, "Kenya")
        self.assertEqual(application.state, "Nakuru")

    def test_region_data_is_wired_into_the_apply_page(self):
        response = self.client.get(reverse("core:apply"))
        self.assertContains(response, "js/subdivisions.js")
        # Order matters: form-steps.js reads the data at run time, and both
        # scripts are deferred, so the data file has to come first.
        body = response.content.decode()
        self.assertLess(body.index("js/subdivisions.js"), body.index("js/form-steps.js"))

    def test_country_is_asked_before_the_region_it_controls(self):
        response = self.client.get(reverse("core:apply"))
        body = response.content.decode()
        self.assertLess(body.index('id="id_country"'), body.index('id="id_state"'))

    def test_the_video_brief_is_on_the_form(self):
        """The three things the video must cover are the most-missed instruction
        on the form, so they are asserted rather than trusted."""
        response = self.client.get(reverse("core:apply"))
        self.assertContains(response, "Who you are")
        self.assertContains(response, "What your business does")
        self.assertContains(response, "Why you should be chosen")
        # Rendered as markup, not escaped into visible tags.
        self.assertContains(response, "form-help-brief")
        self.assertNotContains(response, "&lt;ol")
        self.assertNotContains(response, "&lt;strong")

    def test_embark_keeps_typed_answers_when_validation_fails(self):
        response = self.submit("apply", dict(EMBARK, institution=""))
        self.assertEqual(models.EmbarkApplication.objects.count(), 0)
        self.assertContains(response, "Okafor Farms")   # re-rendered, not thrown away

    @override_settings(RECAPTCHA_SECRET_KEY="a-key-that-turns-verification-on")
    def test_recaptcha_blocks_a_submission_with_no_token(self):
        response = self.submit("contact", CONTACT)
        self.assertEqual(models.ContactMessage.objects.count(), 0)
        self.assertContains(response, "couldn&#x27;t verify that you&#x27;re human")

    @override_settings(RECAPTCHA_SITE_KEY="a-site-key")
    def test_every_form_page_shows_the_widget_once_keys_are_set(self):
        """Guards the day the keys go into .env: a form whose template forgot
        the widget would start rejecting every real visitor, silently."""
        for page in ["contact", "apply", "join_faculty", "volunteer", "partner"]:
            with self.subTest(page=page):
                response = self.client.get(reverse(f"core:{page}"))
                self.assertContains(response, 'class="g-recaptcha"')
                self.assertContains(response, "recaptcha/api.js")


@override_settings(MEDIA_ROOT=MEDIA_ROOT, RECAPTCHA_SECRET_KEY="")
@SSL_REDIRECT_OFF
class UnfinishedApplicationTests(TestCase):
    """The apply form's background save - see models.PartialApplication.

    What matters here is the boundary: enough typed to reach someone gets kept,
    less than that does not, and nobody is ever chased about an application they
    did in fact send.
    """

    def save(self, data):
        return self.client.post(reverse("submissions:apply_progress"),
                                dict(data, draft_id="draft-abc12345"))

    def test_a_half_filled_form_is_kept_once_there_is_an_email(self):
        self.save({"name": "Chidi Okafor", "email": "chidi@example.com",
                   "business_name": "Okafor Farms", "furthest_step": "2"})
        row = models.PartialApplication.objects.get()
        self.assertEqual(row.name, "Chidi Okafor")
        self.assertEqual(row.email, "chidi@example.com")
        self.assertEqual(row.business_name, "Okafor Farms")
        self.assertEqual(row.furthest_step, 2)
        self.assertIsNone(row.completed_at)

    def test_a_phone_number_alone_is_enough_to_reach_someone(self):
        self.save({"name": "Chidi", "phone_code": "+234", "phone": "8012345678"})
        row = models.PartialApplication.objects.get()
        self.assertEqual(row.phone_display, "+234 8012345678")

    def test_nothing_is_kept_without_a_way_to_make_contact(self):
        """A name and a half-typed email is not something to store: there is
        nothing we could do with it."""
        self.save({"name": "Chidi", "email": "chidi@", "phone": "801"})
        self.assertEqual(models.PartialApplication.objects.count(), 0)

    def test_typing_on_updates_the_same_row(self):
        self.save({"name": "Chidi", "email": "chidi@example.com", "furthest_step": "1"})
        self.save({"name": "Chidi Okafor", "email": "chidi@example.com",
                   "business_name": "Okafor Farms", "furthest_step": "3"})
        row = models.PartialApplication.objects.get()
        self.assertEqual(row.name, "Chidi Okafor")
        self.assertEqual(row.furthest_step, 3)

    def test_going_back_a_section_does_not_lower_the_furthest_step(self):
        self.save({"email": "chidi@example.com", "furthest_step": "3"})
        self.save({"email": "chidi@example.com", "furthest_step": "1"})
        self.assertEqual(models.PartialApplication.objects.get().furthest_step, 3)

    def test_every_answer_typed_is_kept_not_just_the_contact_columns(self):
        self.save({"email": "chidi@example.com", "major_challenge": "Cold-chain",
                   "growth_limits": ["funding", "customers"]})
        row = models.PartialApplication.objects.get()
        self.assertEqual(row.answers["major_challenge"], "Cold-chain")
        self.assertEqual(row.answers["growth_limits"], ["funding", "customers"])
        self.assertIn("Cold-chain", row.answers_display)

    def test_the_honeypot_still_applies(self):
        self.save({"email": "bot@example.com", "website_url": "http://spam.example"})
        self.assertEqual(models.PartialApplication.objects.count(), 0)

    def test_a_missing_draft_id_is_refused(self):
        response = self.client.post(reverse("submissions:apply_progress"),
                                    {"email": "chidi@example.com"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(models.PartialApplication.objects.count(), 0)

    def test_submitting_the_real_application_closes_the_unfinished_row(self):
        self.save({"name": "Chidi", "email": "chidi@example.com"})
        self.client.post(reverse("submissions:apply"),
                         dict(EMBARK, draft_id="draft-abc12345"), follow=True)
        self.assertEqual(models.EmbarkApplication.objects.count(), 1)
        self.assertIsNotNone(models.PartialApplication.objects.get().completed_at)

    def test_a_row_started_on_another_device_is_closed_by_email(self):
        """Started on a phone, finished on a laptop: two draft ids, one person.
        Chasing them about an application already sent is the one outcome this
        must not produce."""
        models.PartialApplication.objects.create(
            draft_id="some-other-device", email="chidi@example.com")
        self.client.post(reverse("submissions:apply"), EMBARK, follow=True)
        self.assertIsNotNone(models.PartialApplication.objects.get().completed_at)

    def test_a_rejected_application_leaves_the_row_open(self):
        self.save({"name": "Chidi", "email": "chidi@example.com"})
        self.client.post(reverse("submissions:apply"),
                         dict(EMBARK, draft_id="draft-abc12345", institution=""),
                         follow=True)
        self.assertEqual(models.EmbarkApplication.objects.count(), 0)
        self.assertIsNone(models.PartialApplication.objects.get().completed_at)

    def test_no_email_is_sent_for_an_unfinished_application(self):
        """They have not applied. An acknowledgement would say they had."""
        mail.outbox.clear()
        self.save({"name": "Chidi", "email": "chidi@example.com"})
        self.assertEqual(mail.outbox, [])

    def test_the_team_can_read_and_export_the_unfinished_rows(self):
        """The admin side of it: a list to work through and a CSV to mail from."""
        row = models.PartialApplication.objects.create(
            draft_id="draft-abc12345", name="Chidi Okafor",
            email="chidi@example.com", phone_code="+234", phone="8012345678",
            business_name="Okafor Farms", furthest_step=2,
            answers={"major_challenge": "Cold-chain logistics"})
        User.objects.create_superuser("boss", "boss@example.com", PASSWORD)
        self.client.login(username="boss", password=PASSWORD)

        page = self.client.get(reverse("admin:submissions_partialapplication_change",
                                       args=[row.pk]))
        self.assertContains(page, "Cold-chain logistics")   # everything they typed

        listing = self.client.get(
            reverse("admin:submissions_partialapplication_changelist"))
        self.assertContains(listing, "Chidi Okafor")
        self.assertContains(listing, "+234 8012345678")     # code and number as one
        self.assertContains(listing, "Unfinished")

        csv_response = self.client.post(
            reverse("admin:submissions_partialapplication_changelist"),
            {"action": "export_csv", "_selected_action": [row.pk]})
        body = csv_response.content.decode()
        self.assertIn("attachment", csv_response["Content-Disposition"])
        self.assertIn("chidi@example.com", body)
        self.assertIn("Okafor Farms", body)

    def test_the_apply_page_asks_the_form_to_save_progress(self):
        response = self.client.get(reverse("core:apply"))
        self.assertContains(response, 'data-progress-url="/forms/apply/progress/"')
        self.assertContains(response, 'name="draft_id"')


# The backfill refuses to --send on a backend whose name contains "locmem",
# because stamping every row as acknowledged while sending nothing is the one
# failure that cannot be undone by re-running. That guard also blocks the test
# backend, so the send path needs a backend that captures like locmem but is not
# named like it. Subclassing is the whole trick.
class CapturingEmailBackend(LocMemEmailBackend):
    pass


CAPTURING = override_settings(EMAIL_BACKEND="submissions.tests.CapturingEmailBackend")


@SSL_REDIRECT_OFF
class AcknowledgementStampTests(TestCase):
    """Who has been written to, and who is still owed a message."""

    def _application(self, **kw):
        fields = {"name": "Ada Obi", "email": "ada@example.com",
                  "phone": "8012345678", "city": "Lagos", "country": "Nigeria",
                  "business_name": "Acme Crafts"}
        fields.update(kw)
        return models.EmbarkApplication.objects.create(**fields)

    def test_a_successful_send_stamps_the_row(self):
        obj = self._application()
        self.assertIsNone(obj.acknowledged_at)
        self.assertTrue(acknowledge(obj.email, "Ada", "applying", obj=obj))
        obj.refresh_from_db()
        self.assertIsNotNone(obj.acknowledged_at)

    def test_a_failed_send_leaves_the_row_unstamped(self):
        """Otherwise a provider outage would mark everyone as done and the
        backfill would never retry them."""
        obj = self._application()
        with mock.patch("submissions.services.send_mail",
                        side_effect=OSError("connection refused")):
            self.assertFalse(acknowledge(obj.email, "Ada", "applying", obj=obj))
        obj.refresh_from_db()
        self.assertIsNone(obj.acknowledged_at)

    def test_a_form_submission_stamps_the_row_it_created(self):
        """So the backfill never re-mails someone the live form already reached."""
        self.client.post(reverse("submissions:contact"), CONTACT, follow=True)
        row = models.ContactMessage.objects.get()
        self.assertIsNotNone(row.acknowledged_at)


@SSL_REDIRECT_OFF
class BackfillCommandTests(TestCase):

    def _application(self, **kw):
        fields = {"name": "Ada Obi", "email": "ada@example.com",
                  "phone": "8012345678", "city": "Lagos", "country": "Nigeria",
                  "business_name": "Acme Crafts"}
        fields.update(kw)
        return models.EmbarkApplication.objects.create(**fields)

    def run_cmd(self, *args):
        out = io.StringIO()
        call_command("backfill_acknowledgements", *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_a_dry_run_sends_nothing_and_stamps_nothing(self):
        obj = self._application()
        output = self.run_cmd()
        self.assertIn("DRY RUN", output)
        self.assertIn("ada@example.com", output)
        self.assertEqual(len(mail.outbox), 0)
        obj.refresh_from_db()
        self.assertIsNone(obj.acknowledged_at)

    @CAPTURING
    def test_send_delivers_once_and_stamps(self):
        obj = self._application()
        self.run_cmd("--send", "--sleep", "0")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("ada@example.com", mail.outbox[0].to)
        obj.refresh_from_db()
        self.assertIsNotNone(obj.acknowledged_at)

    @CAPTURING
    def test_running_it_twice_does_not_mail_anyone_twice(self):
        """The property the whole acknowledged_at column exists for."""
        self._application()
        self.run_cmd("--send", "--sleep", "0")
        self.run_cmd("--send", "--sleep", "0")
        self.assertEqual(len(mail.outbox), 1)

    @CAPTURING
    def test_one_person_on_two_forms_gets_one_email(self):
        self._application(email="both@example.com")
        models.VolunteerApplication.objects.create(
            name="Ada Obi", email="both@example.com", phone="8012345678",
            country="Nigeria")
        self.run_cmd("--send", "--sleep", "0", "--form", "embark",
                     "--form", "volunteers")
        self.assertEqual(len(mail.outbox), 1)

    @CAPTURING
    def test_abandoned_drafts_are_never_mailed(self):
        """PartialApplication rows were never submitted, so "we received your
        submission" would be a false statement to someone who gave up."""
        models.PartialApplication.objects.create(
            name="Chidi Eze", email="chidi@example.com", answers={})
        self.run_cmd("--send", "--sleep", "0")
        self.assertEqual(len(mail.outbox), 0)

    @CAPTURING
    def test_limit_caps_the_batch_and_reports_the_remainder(self):
        for i in range(3):
            self._application(email=f"a{i}@example.com")
        output = self.run_cmd("--send", "--sleep", "0", "--limit", "2")
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("1 more are eligible", output)

    def test_send_is_refused_on_a_backend_that_does_not_send(self):
        """Stamping every row while delivering nothing is unrecoverable: the
        real run afterwards would skip all of them."""
        obj = self._application()
        with self.assertRaises(CommandError):
            self.run_cmd("--send")
        obj.refresh_from_db()
        self.assertIsNone(obj.acknowledged_at)


PIXEL_ID = "1221975869207645"


@override_settings(MEDIA_ROOT=MEDIA_ROOT, RECAPTCHA_SECRET_KEY="")
@SSL_REDIRECT_OFF
class MetaPixelTests(TestCase):
    """The Meta Pixel: off unless configured, and honest about what it reports."""

    def test_nothing_facebook_reaches_the_page_without_an_id(self):
        """The default, and what every developer machine runs."""
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "connect.facebook.net")
        self.assertNotContains(response, "fbq(")

    @override_settings(META_PIXEL_ID=PIXEL_ID)
    def test_the_base_code_is_on_every_page(self):
        for page in ["home", "apply", "contact", "embark", "privacy"]:
            with self.subTest(page=page):
                response = self.client.get(reverse(f"core:{page}"))
                self.assertContains(response, "connect.facebook.net")
                self.assertContains(response, f"fbq('init', '{PIXEL_ID}')")
                self.assertContains(response, "fbq('track', 'PageView')")

    @override_settings(META_PIXEL_ID=PIXEL_ID)
    def test_the_pixel_is_never_told_who_the_visitor_is(self):
        """Advanced matching would make `init` carry the applicant's email and
        phone number. It must not: the privacy policy says personal information
        is shared only for the purpose it was given for, and being matched to an
        advertising profile is not that purpose."""
        response = self.client.get(reverse("core:apply"))
        self.assertContains(response, f"fbq('init', '{PIXEL_ID}');")   # id, nothing else

    @override_settings(META_PIXEL_ID=PIXEL_ID)
    def test_a_completed_application_reports_a_conversion(self):
        response = self.client.post(reverse("submissions:apply"), EMBARK, follow=True)
        self.assertEqual(models.EmbarkApplication.objects.count(), 1)
        self.assertContains(response, "fbq('track', 'SubmitApplication')")

    @override_settings(META_PIXEL_ID=PIXEL_ID)
    def test_the_conversion_is_reported_once_not_on_every_page_after(self):
        """Left in the session it would report a fresh application on every page
        the applicant went on to read."""
        self.client.post(reverse("submissions:apply"), EMBARK, follow=True)
        later = self.client.get(reverse("core:home"))
        self.assertNotContains(later, "SubmitApplication")

    @override_settings(META_PIXEL_ID=PIXEL_ID)
    def test_a_rejected_application_reports_nothing(self):
        """No row saved, no conversion - or the cost-per-application figure in
        Ads Manager counts forms that failed validation."""
        response = self.client.post(reverse("submissions:apply"),
                                    dict(EMBARK, institution=""), follow=True)
        self.assertEqual(models.EmbarkApplication.objects.count(), 0)
        self.assertNotContains(response, "SubmitApplication")

    @override_settings(META_PIXEL_ID=PIXEL_ID)
    def test_each_form_reports_its_own_kind_of_conversion(self):
        for name, data, event in [("contact", CONTACT, "Contact"),
                                  ("faculty", FACULTY, "Lead"),
                                  ("volunteer", VOLUNTEER, "Lead"),
                                  ("partner", PARTNER, "Lead"),
                                  ("newsletter", {"email": "new@example.com"},
                                   "Subscribe")]:
            with self.subTest(form=name):
                response = self.client.post(reverse(f"submissions:{name}"), data,
                                            follow=True)
                self.assertContains(response, f"fbq('track', '{event}')")

    def test_a_conversion_is_not_stored_when_no_pixel_is_configured(self):
        """No id, no session write - a visitor to a site running no pixel should
        not be handed a session cookie because of one."""
        self.client.post(reverse("submissions:apply"), EMBARK, follow=True)
        self.assertNotIn("meta_pixel_event", self.client.session)
