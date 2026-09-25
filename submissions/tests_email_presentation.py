from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from core.mail_backends import build_payload
from .email_presentation import applicant_email_html
from .models import PartialApplication
from .services import send_to_applicant


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   SITE_BASE_URL="https://iadebayo.foundation")
class BrandedEmailTests(TestCase):
    def setUp(self):
        self.draft = PartialApplication.objects.create(draft_id="private-draft-123", email="ada@example.com")

    def test_personal_link_becomes_button_and_text_fallback_keeps_url(self):
        link = self.draft.resume_url
        body = f"Hi Ada,\n\nRegistration closes on **30 September 2026**.\n\n**{link}**"
        self.assertTrue(send_to_applicant(self.draft.email, "Complete your application", body,
                                         obj=self.draft, stamp_field="nudge_sent_at"))
        message = mail.outbox[0]
        self.assertEqual(message.body, body)
        html = message.alternatives[0].content
        self.assertIn("Complete my application</a>", html)
        self.assertIn(link, html)
        self.assertIn("<strong>30 September 2026</strong>", html)
        payload = build_payload(message)
        self.assertEqual(payload["textbody"], body)
        self.assertEqual(payload["htmlbody"], html)

    def test_untrusted_text_is_escaped(self):
        html = applicant_email_html('Hi <script>alert(1)</script>\n\n**<img src=x onerror=alert(1)>**')
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;", html)

    def test_another_applicants_link_or_external_domain_is_not_a_button(self):
        other = PartialApplication(draft_id="someone-else")
        for link in [other.resume_url, self.draft.resume_url.replace("iadebayo.foundation", "example.com"),
                     "https://iadebayo.foundation/apply/?resume=forged", "https://["]:
            self.assertNotIn("Complete my application</a>", applicant_email_html(link, self.draft))

    @patch("submissions.services.EmailMultiAlternatives.send", return_value=0)
    def test_zero_accepted_messages_does_not_mark_sent(self, send):
        self.assertFalse(send_to_applicant(self.draft.email, "Hello", "Body", self.draft, "nudge_sent_at"))
        self.draft.refresh_from_db()
        self.assertIsNone(self.draft.nudge_sent_at)
