import io
import shutil
import tempfile
import zipfile

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from . import models
from .models import EmbarkApplication

MEDIA_ROOT = tempfile.mkdtemp()
PASSWORD = "pw-for-tests-only"

# The test client speaks plain http. In production DEBUG is off, which turns on
# SECURE_SSL_REDIRECT, and SecurityMiddleware then answers every request with a
# 301 to https. `follow=True` re-issues a redirected POST as a GET, so each
# @require_POST submission view rejects it with 405 and roughly thirty
# assertions fail — but only when the suite happens to run with DEBUG=False.
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
    "entrepreneurship_view": "Impact first — profit is what makes the impact repeatable.",
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
    def test_embark_requires_linkedin(self):
        """LinkedIn is the one profile the panel can check a founder against."""
        response = self.submit("apply", dict(EMBARK, linkedin=""))
        self.assertEqual(models.EmbarkApplication.objects.count(), 0)
        self.assertContains(response, "This field is required")

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
        """A business with no site and an applicant on one platform must still
        be able to apply — only LinkedIn is compulsory."""
        self.submit("apply", dict(EMBARK, social_handle="", social_handle_2="",
                                  business_website="", business_social_handle=""))
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
