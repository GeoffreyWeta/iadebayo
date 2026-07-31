import io
import shutil
import tempfile
import zipfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import EmbarkApplication

MEDIA_ROOT = tempfile.mkdtemp()
PASSWORD = "pw-for-tests-only"


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
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

    def test_anonymous_visitor_is_sent_to_the_admin_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_signed_in_non_staff_user_cannot_download(self):
        self.sign_in("member")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

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
