from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .contact_protection import set_sender_blocked
from .models import ContactMessage, ContactSender


@override_settings(SECURE_SSL_REDIRECT=False, RECAPTCHA_SECRET_KEY="",
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ContactProtectionTests(TestCase):
    def post(self, **changes):
        values = dict(name="Visitor", email="visitor@example.com", subject="Question",
                      message="Please tell me about the next programme.")
        return self.client.post(reverse("submissions:contact"), values | changes)

    @patch("submissions.views.acknowledge")
    @patch("submissions.views.notify_team")
    def test_repeat_message_does_not_save_or_notify_twice(self, notify, acknowledge):
        self.post()
        self.post(email="VISITOR@example.com", subject="Another subject",
                  message="  PLEASE tell me about the next programme.  ")
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertEqual(notify.call_count, 1)
        self.assertEqual(acknowledge.call_count, 1)

    def test_fourth_different_message_in_hour_is_rejected(self):
        for i in range(4):
            self.post(message=f"Question number {i}")
        self.assertEqual(ContactMessage.objects.count(), 3)

    def test_limit_expires_and_different_senders_are_independent(self):
        for i in range(3):
            self.post(message=f"Question number {i}")
        ContactMessage.objects.update(created_at=timezone.now() - timedelta(hours=2))
        self.post(message="A new question")
        self.post(email="another@example.com")
        self.assertEqual(ContactMessage.objects.count(), 5)

    def test_duplicate_window_expires(self):
        self.post()
        ContactMessage.objects.update(created_at=timezone.now() - timedelta(days=2))
        self.post()
        self.assertEqual(ContactMessage.objects.count(), 2)

    @patch("submissions.views.acknowledge")
    @patch("submissions.views.notify_team")
    def test_blocked_sender_neither_saves_nor_notifies(self, notify, acknowledge):
        set_sender_blocked(" VISITOR@example.com ")
        self.post()
        self.assertFalse(ContactMessage.objects.exists())
        notify.assert_not_called()
        acknowledge.assert_not_called()

    def test_block_reviews_existing_messages_without_deleting_and_can_be_reversed(self):
        self.post()
        row = ContactMessage.objects.get()
        user = User.objects.create_user("staff", is_staff=True)
        self.client.force_login(user)
        url = reverse("staff:contact_sender", args=[row.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {"action": "block"}).status_code, 302)
        row.refresh_from_db()
        self.assertTrue(row.reviewed)
        self.assertTrue(ContactSender.objects.get().blocked)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.client.post(url, {"action": "unblock"})
        self.assertFalse(ContactSender.objects.get().blocked)

    def test_non_staff_cannot_block(self):
        row = ContactMessage.objects.create(email="someone@example.com")
        response = self.client.post(reverse("staff:contact_sender", args=[row.pk]), {"action": "block"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ContactSender.objects.exists())

    def test_other_languages_are_not_treated_as_spam(self):
        self.post(message="გამარჯობა, მინდა მეტი ინფორმაცია პროგრამის შესახებ.")
        self.assertEqual(ContactMessage.objects.count(), 1)
