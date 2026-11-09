"""The staff mailbox: receiving, threading, writing, replying, and keeping
received mail from doing anything on a staff page but being read."""
import json
import shutil
import tempfile
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from submissions.models import ContactSender, EmbarkApplication

from . import parsing, services
from .models import Attachment, Conversation, Message
from .rendering import split_quote

FILES = tempfile.mkdtemp(prefix="mailroom-tests-")
SECRET = "test-secret"


def tearDownModule():
    shutil.rmtree(FILES, ignore_errors=True)


SETTINGS = override_settings(
    MAIL_FILES_ROOT=FILES,
    MAIL_INBOUND_SECRET=SECRET,
    STAFF_MAILBOXES=["Embark Academy <embark@iadebayo.foundation>",
                     "IADEBAYO Foundation <hello@iadebayo.foundation>"],
    DEFAULT_FROM_EMAIL="IADEBAYO Foundation <noreply@iadebayo.foundation>",
    EMBARK_FROM_EMAIL="Embark Academy <embark@iadebayo.foundation>",
    EMBARK_REPLY_TO="hello@iadebayo.foundation",
    FOUNDATION_NOTIFY_EMAIL="hello@iadebayo.foundation",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    SECURE_SSL_REDIRECT=False,
)


def an_email(subject="Question about Embark", sender="Ada Obi <ada@example.com>",
             to="embark@iadebayo.foundation", body="Hello team,\n\nA question.",
             html=None, message_id=None, in_reply_to=None, references=None,
             headers=None, attachments=(), date=None):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = date or formatdate(localtime=True)
    msg["Message-ID"] = message_id or make_msgid(domain="example.com")
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references
    for name, value in (headers or {}).items():
        msg[name] = value
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    for filename, data, maintype, subtype in attachments:
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return msg.as_bytes()


class StaffMixin:
    def staff(self):
        self.user = User.objects.create_user("mo", password="x", is_staff=True,
                                             first_name="Mo", last_name="Bello")
        self.client.force_login(self.user)
        return self.user

    def post_raw(self, raw, secret=SECRET, **extra):
        return self.client.post(reverse("mailroom:inbound"), data=raw,
                                content_type="message/rfc822",
                                HTTP_AUTHORIZATION=f"Bearer {secret}", **extra)


# ======================================================================= parsing
@SETTINGS
class ParsingTests(TestCase):
    def test_encoded_headers_and_names_are_decoded(self):
        raw = an_email(subject="Candidature: Ọkafọ́ & co", sender="Chidi Ọkafọ́ <chidi@example.com>")
        parsed = parsing.parse(raw)
        self.assertEqual(parsed.subject, "Candidature: Ọkafọ́ & co")
        self.assertEqual(parsed.from_name, "Chidi Ọkafọ́")
        self.assertEqual(parsed.from_email, "chidi@example.com")

    def test_alternative_bodies_and_attachments(self):
        raw = an_email(html="<p>Hello <b>team</b></p>",
                       attachments=[("cv.pdf", b"%PDF-1.4 fake", "application", "pdf")])
        parsed = parsing.parse(raw)
        self.assertIn("A question.", parsed.text)
        self.assertIn("<b>team</b>", parsed.html)
        self.assertEqual([(a.filename, a.content_type) for a in parsed.attachments],
                         [("cv.pdf", "application/pdf")])
        self.assertEqual(parsed.attachments[0].data, b"%PDF-1.4 fake")

    def test_html_only_mail_still_reads_as_text(self):
        raw = (b"From: a@example.com\r\nTo: embark@iadebayo.foundation\r\nSubject: x\r\n"
               b"Message-ID: <h1@example.com>\r\nContent-Type: text/html; charset=utf-8\r\n\r\n"
               b"<html><head><style>p{color:red}</style></head><body><p>First</p>"
               b"<p>Second &amp; last</p><script>bad()</script></body></html>")
        parsed = parsing.parse(raw)
        self.assertEqual(parsed.text, "")
        self.assertEqual(parsing.html_to_text(parsed.html), "First\n\nSecond & last")

    def test_a_message_without_an_id_gets_a_stable_one(self):
        raw = b"From: a@example.com\r\nSubject: x\r\n\r\nbody\r\n"
        self.assertEqual(parsing.parse(raw).message_id, parsing.parse(raw).message_id)
        self.assertTrue(parsing.parse(raw).message_id.endswith("@received.invalid>"))

    def test_an_unknown_charset_degrades_instead_of_failing(self):
        raw = (b"From: a@example.com\r\nSubject: x\r\nMessage-ID: <c1@example.com>\r\n"
               b"Content-Type: text/plain; charset=x-no-such-charset\r\n\r\nHello \xff there\r\n")
        self.assertIn("Hello", parsing.parse(raw).text)

    def test_a_future_date_is_not_believed(self):
        raw = an_email(date="Tue, 01 Jan 2041 10:00:00 +0000")
        self.assertIsNone(parsing.parse(raw).date)

    def test_receiving_server_verdict_is_read(self):
        raw = an_email(headers={"Authentication-Results":
                                "mx.cloudflare.net; dkim=fail; dkim=pass header.d=example.com; "
                                "spf=pass smtp.mailfrom=example.com; dmarc=fail header.from=example.com"})
        self.assertEqual(parsing.parse(raw).auth, {"dkim": "pass", "spf": "pass", "dmarc": "fail"})

    def test_a_forwarded_email_is_kept_as_an_eml_attachment(self):
        inner = EmailMessage()
        inner["Subject"] = "Original"
        inner["From"] = "x@example.com"
        inner.set_content("inner body")
        outer = EmailMessage()
        outer["From"] = "a@example.com"
        outer["Subject"] = "Fwd: Original"
        outer["Message-ID"] = "<f1@example.com>"
        outer.set_content("see below")
        outer.add_attachment(inner)
        parsed = parsing.parse(outer.as_bytes())
        self.assertEqual(parsed.text.strip(), "see below")
        self.assertEqual(len(parsed.attachments), 1)
        self.assertTrue(parsed.attachments[0].filename.endswith(".eml"))
        self.assertIn(b"inner body", parsed.attachments[0].data)

    def test_quoted_history_is_separated(self):
        fresh, quoted = split_quote("Thanks, that works.\n\nOn Mon 3 Nov 2026 at 14:02, Mo <m@x.org>\nwrote:\n> Hello")
        self.assertEqual(fresh, "Thanks, that works.")
        self.assertTrue(quoted.startswith("On Mon"))
        self.assertEqual(split_quote("> only a quote"), ("> only a quote", ""))


# ======================================================================= webhook
@SETTINGS
class WebhookTests(StaffMixin, TestCase):
    def test_switched_off_without_a_secret(self):
        with override_settings(MAIL_INBOUND_SECRET=""):
            self.assertEqual(self.post_raw(an_email(), secret="").status_code, 404)

    def test_wrong_secret_is_refused_and_stores_nothing(self):
        response = self.post_raw(an_email(), secret="guess")
        self.assertEqual(response.status_code, 401)
        self.assertFalse(Message.objects.exists())

    def test_only_post(self):
        self.assertEqual(self.client.get(reverse("mailroom:inbound")).status_code, 405)

    def test_a_received_email_lands_in_the_inbox_unread(self):
        raw = an_email(attachments=[("cv.pdf", b"%PDF", "application", "pdf")])
        response = self.post_raw(raw, HTTP_X_ENVELOPE_TO="embark@iadebayo.foundation")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["outcome"], "stored")

        conversation = Conversation.objects.get()
        self.assertEqual(conversation.contact_email, "ada@example.com")
        self.assertEqual(conversation.contact_name, "Ada Obi")
        self.assertEqual(conversation.mailbox, "embark@iadebayo.foundation")
        self.assertTrue(conversation.unread and conversation.has_inbound)
        self.assertFalse(conversation.archived or conversation.junk)
        message = conversation.messages.get()
        with message.raw.open("rb") as handle:
            self.assertEqual(handle.read(), raw)
        self.assertEqual(message.attachments.get().filename, "cv.pdf")

    def test_the_same_message_twice_is_stored_once(self):
        raw = an_email(message_id="<same@example.com>")
        self.post_raw(raw)
        response = self.post_raw(raw)
        self.assertEqual(json.loads(response.content)["outcome"], "duplicate")
        self.assertEqual(Message.objects.count(), 1)

    def test_too_large_is_refused(self):
        with override_settings(MAIL_INBOUND_MAX_BYTES=100):
            self.assertEqual(self.post_raw(an_email(body="x" * 500)).status_code, 413)

    def test_the_sites_own_notifications_are_not_conversations(self):
        raw = an_email(sender="IADEBAYO Foundation <noreply@iadebayo.foundation>",
                       to="hello@iadebayo.foundation")
        response = self.post_raw(raw)
        self.assertEqual(json.loads(response.content)["outcome"], "ignored")
        self.assertFalse(Conversation.objects.exists())

    def test_a_storage_failure_asks_the_worker_to_retry(self):
        with mock.patch("mailroom.services.receive", side_effect=RuntimeError("disk full")):
            with self.assertLogs("mailroom.views", "ERROR"):
                self.assertEqual(self.post_raw(an_email()).status_code, 500)

    def test_the_command_files_an_eml(self):
        from io import StringIO

        from django.core.management import call_command
        path = f"{FILES}/one.eml"
        with open(path, "wb") as handle:
            handle.write(an_email())
        out = StringIO()
        call_command("receive_email", path, stdout=out)
        self.assertIn("stored", out.getvalue())
        self.assertEqual(Conversation.objects.count(), 1)

    def test_imported_mail_keeps_its_date_but_live_mail_uses_arrival(self):
        old = "Mon, 01 Jan 2024 09:30:00 +0000"
        imported = services.receive(an_email(date=old), use_date_header=True).message
        live = services.receive(an_email(date=old, subject="Other")).message
        self.assertEqual(imported.sent_at.year, 2024)
        self.assertEqual(live.sent_at.year, timezone.now().year)


# ===================================================================== threading
@SETTINGS
class ThreadingTests(StaffMixin, TestCase):
    def receive(self, **kwargs):
        return services.receive(an_email(**kwargs)).message

    def test_a_reply_naming_our_message_joins_its_conversation(self):
        first = self.receive(message_id="<one@example.com>")
        first.conversation.archived = True
        first.conversation.unread = False
        first.conversation.save()
        reply = self.receive(subject="Something else entirely", in_reply_to="<one@example.com>",
                             references="<one@example.com>")
        self.assertEqual(reply.conversation_id, first.conversation_id)
        conversation = Conversation.objects.get()
        self.assertFalse(conversation.archived)   # a reply brings it back
        self.assertTrue(conversation.unread)

    def test_without_headers_the_subject_and_address_match(self):
        first = self.receive(subject="Interview time")
        reply = self.receive(subject="RE: Re: Interview time")
        self.assertEqual(reply.conversation_id, first.conversation_id)

    def test_same_subject_from_someone_else_is_a_new_conversation(self):
        first = self.receive(subject="Hello")
        other = self.receive(subject="Re: Hello", sender="b@example.com")
        self.assertNotEqual(other.conversation_id, first.conversation_id)

    def test_an_old_conversation_is_not_reopened_by_subject(self):
        first = self.receive(subject="Hello")
        Conversation.objects.update(last_message_at=timezone.now() - services.THREAD_WINDOW * 2)
        later = self.receive(subject="Hello")
        self.assertNotEqual(later.conversation_id, first.conversation_id)

    def test_dmarc_failure_starts_in_junk(self):
        message = self.receive(headers={"Authentication-Results": "mx.cloudflare.net; dmarc=fail"})
        self.assertTrue(message.suspicious)
        self.assertTrue(message.conversation.junk)

    def test_a_blocked_sender_goes_to_junk(self):
        ContactSender.objects.create(email="ada@example.com", blocked=True)
        self.assertTrue(self.receive().conversation.junk)

    def test_a_copy_of_staff_mail_from_a_mail_app_is_filed_as_sent(self):
        message = self.receive(sender="Embark Academy <embark@iadebayo.foundation>",
                               to="Chidi <chidi@example.com>", headers={"Cc": "hello@iadebayo.foundation"})
        self.assertEqual(message.direction, Message.OUT)
        self.assertTrue(message.sent_elsewhere)
        self.assertEqual(message.conversation.contact_email, "chidi@example.com")
        self.assertFalse(message.conversation.unread)


# ======================================================================= writing
@SETTINGS
class ComposeTests(StaffMixin, TestCase):
    def setUp(self):
        self.staff()

    def compose(self, **data):
        fields = {"from_address": "embark@iadebayo.foundation", "to": "Ada Obi <ada@example.com>",
                  "cc": "", "bcc": "", "subject": "Your interview", "body": "Hello Ada,\n\nSee you **Monday**."}
        fields.update(data)
        return self.client.post(reverse("staff:mail_compose"), fields)

    def test_signed_out_people_are_sent_to_sign_in(self):
        self.client.logout()
        for name in ("staff:mail", "staff:mail_compose"):
            self.assertIn("/staff/login/", self.client.get(reverse(name))["Location"])

    def test_the_pages_render(self):
        services.receive(an_email())
        for url in (reverse("staff:mail"), reverse("staff:mail_folder", args=["sent"]),
                    reverse("staff:mail_folder", args=["junk"]), reverse("staff:mail_compose"),
                    reverse("staff:mail_thread", args=[Conversation.objects.get().pk])):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get(reverse("staff:mail_folder", args=["nope"])).status_code, 404)

    def test_writing_to_anyone_sends_and_files_it(self):
        response = self.compose(cc="team@partner.org", bcc="mo@iadebayo.foundation")
        conversation = Conversation.objects.get()
        self.assertRedirects(response, reverse("staff:mail_thread", args=[conversation.pk]))

        sent = mail.outbox[0]
        self.assertEqual(sent.from_email, "Embark Academy <embark@iadebayo.foundation>")
        self.assertEqual(sent.to, ["Ada Obi <ada@example.com>"])
        self.assertEqual(sent.cc, ["team@partner.org"])
        self.assertEqual(sent.bcc, ["mo@iadebayo.foundation"])
        self.assertIn("<strong>Monday</strong>", sent.alternatives[0][0])

        message = conversation.messages.get()
        self.assertEqual(message.sent_by, self.user)
        self.assertEqual(message.message_id, sent.extra_headers["Message-ID"])
        self.assertEqual(conversation.contact_email, "ada@example.com")
        self.assertTrue(conversation.has_outbound)
        self.assertFalse(conversation.has_inbound)   # in Sent, not the inbox
        self.assertIn(" team@partner.org ", conversation.participants)
        self.assertEqual(conversation.snippet, "Hello Ada, See you Monday.")
        thread = self.client.get(reverse("staff:mail_thread", args=[conversation.pk]))
        self.assertContains(thread, "<strong>Monday</strong>")

    def test_a_bad_address_is_named_and_nothing_is_sent(self):
        response = self.compose(to="ada@example.com, not-an-address")
        self.assertContains(response, "Not an email address: not-an-address")
        self.assertEqual(mail.outbox, [])

    def test_attachments_go_out_and_are_kept(self):
        upload = SimpleUploadedFile("brief.pdf", b"%PDF-1.4 data", content_type="application/pdf")
        self.compose(attachments=[upload])
        self.assertEqual(mail.outbox[0].attachments[0][0], "brief.pdf")
        stored = Attachment.objects.get()
        self.assertEqual(stored.size, len(b"%PDF-1.4 data"))
        response = self.client.get(reverse("staff:mail_attachment", args=[stored.pk]))
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4 data")

    def test_too_much_attached_is_refused(self):
        with override_settings(MAIL_ATTACHMENTS_MAX_BYTES=5):
            response = self.compose(attachments=[SimpleUploadedFile("a.txt", b"0123456789")])
        self.assertContains(response, "Share large files as a link")
        self.assertEqual(mail.outbox, [])

    def test_placeholders_need_a_known_person(self):
        response = self.compose(body="Dear {{ first_name }},")
        self.assertContains(response, "only filled in when")
        self.assertEqual(mail.outbox, [])
        self.assertFalse(Message.objects.exists())

        EmbarkApplication.objects.create(name="Ada Obi", email="ada@example.com")
        self.compose(body="Dear {{ first_name }},")
        self.assertIn("Dear Ada,", mail.outbox[0].body)

    def test_a_refused_send_keeps_the_text_and_records_nothing(self):
        with mock.patch("mailroom.services.EmailMultiAlternatives.send",
                        side_effect=RuntimeError("HTTP 400: sender not verified")):
            with self.assertLogs("mailroom.services", "ERROR"):
                response = self.compose()
        self.assertContains(response, "Not sent.")
        self.assertContains(response, "sender not verified")
        self.assertContains(response, "See you **Monday**.")
        self.assertFalse(Conversation.objects.exists())

    def test_a_template_is_filled_in_for_a_known_person(self):
        from core.models import EmailTemplate
        template = EmailTemplate.objects.create(name="Offer", subject="Welcome {{ first_name }}",
                                                body="Dear {{ first_name }}, welcome.")
        EmbarkApplication.objects.create(name="Ada Obi", email="ada@example.com")
        response = self.client.get(reverse("staff:mail_compose"),
                                   {"to": "ada@example.com", "template": template.pk})
        self.assertContains(response, "Dear Ada, welcome.")
        self.assertContains(response, 'value="Welcome Ada"')


# ================================================================ conversations
@SETTINGS
class ConversationTests(StaffMixin, TestCase):
    def setUp(self):
        self.staff()

    def test_a_reply_threads_under_their_message_and_quotes_it(self):
        received = services.receive(an_email(
            subject="Question", message_id="<q1@example.com>",
            headers={"Reply-To": "Ada Personal <ada.home@example.com>", "Cc": "Bayo <bayo@example.com>"},
            body="Can I bring my cofounder?")).message
        url = reverse("staff:mail_thread", args=[received.conversation_id])

        page = self.client.get(url)
        form = page.context["form"]
        self.assertEqual(form.initial["to"], "Ada Personal <ada.home@example.com>")
        self.assertEqual(form.initial["cc"], "Bayo <bayo@example.com>")
        self.assertEqual(form.initial["subject"], "Re: Question")
        self.assertIn("Kind regards,\nMo Bello\nEmbark Academy", form.initial["body"])

        self.client.post(url, {**form.initial, "body": "Yes, please do."})
        sent = mail.outbox[0]
        self.assertEqual(sent.extra_headers["In-Reply-To"], "<q1@example.com>")
        self.assertIn("<q1@example.com>", sent.extra_headers["References"])
        self.assertIn("> Can I bring my cofounder?", sent.body)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Message.objects.filter(direction=Message.OUT).count(), 1)

    def test_opening_marks_read_and_actions_file_it(self):
        conversation = services.receive(an_email()).message.conversation
        url = reverse("staff:mail_thread", args=[conversation.pk])
        action = reverse("staff:mail_action", args=[conversation.pk])
        self.assertEqual(self.client.get(reverse("staff:home")).context["mail_unread"], 1)

        self.client.get(url)
        conversation.refresh_from_db()
        self.assertFalse(conversation.unread)

        self.client.post(action, {"action": "unread"})
        conversation.refresh_from_db()
        self.assertTrue(conversation.unread)

        self.client.post(action, {"action": "archive"})
        self.assertNotIn(conversation, self.client.get(reverse("staff:mail")).context["rows"])
        archived = self.client.get(reverse("staff:mail_folder", args=["archived"])).context["rows"]
        self.assertIn(conversation, archived)

    def test_blocking_a_sender_junks_them_here_and_on_the_contact_form(self):
        conversation = services.receive(an_email()).message.conversation
        self.client.post(reverse("staff:mail_action", args=[conversation.pk]), {"action": "block"})
        conversation.refresh_from_db()
        self.assertTrue(conversation.junk)
        self.assertTrue(ContactSender.objects.get(email="ada@example.com").blocked)
        later = services.receive(an_email(subject="Another thing")).message
        self.assertTrue(later.conversation.junk)

    def test_a_redirect_after_an_action_stays_on_this_site(self):
        conversation = services.receive(an_email()).message.conversation
        response = self.client.post(reverse("staff:mail_action", args=[conversation.pk]),
                                    {"action": "notjunk", "next": "https://evil.example/"})
        self.assertEqual(response["Location"], reverse("staff:mail_thread", args=[conversation.pk]))


# ============================================================= received HTML
@SETTINGS
class ReceivedHtmlTests(StaffMixin, TestCase):
    HOSTILE = ('<p>Hi</p><script>document.title="owned"</script>'
               '<img src="https://tracker.example/p.gif">'
               '<meta http-equiv="refresh" content="0;url=https://phish.example/">'
               '<a href="https://ok.example/">link</a>')

    def setUp(self):
        self.staff()
        self.message = services.receive(an_email(html=self.HOSTILE)).message
        self.url = reverse("staff:mail_thread", args=[self.message.conversation_id])

    def test_the_html_is_only_ever_inside_a_script_free_sandbox(self):
        page = self.client.get(self.url).content.decode()
        self.assertNotIn("<script>document.title", page)
        self.assertIn('sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"', page)
        self.assertNotIn("allow-scripts", page)
        self.assertIn("&lt;script&gt;document.title", page)   # escaped into srcdoc

    def test_remote_images_wait_to_be_asked_for_and_refresh_is_removed(self):
        frame = self.client.get(self.url).context["items"][0]["frame"]
        self.assertIn("img-src data:;", frame)
        self.assertNotIn("http-equiv=\"refresh\"", frame)
        self.assertNotIn("phish.example", frame)
        allowed = self.client.get(self.url, {"images": self.message.pk}).context["items"][0]["frame"]
        self.assertIn("img-src data: https: http:;", allowed)

    def test_inline_images_are_embedded_and_not_listed_twice(self):
        msg = EmailMessage()
        msg["From"] = "a@example.com"
        msg["Subject"] = "Logo"
        msg["Message-ID"] = "<logo@example.com>"
        msg.set_content("logo")
        msg.add_alternative('<img src="cid:logo1">', subtype="html")
        msg.get_payload()[1].add_related(b"\x89PNG fake", maintype="image", subtype="png", cid="<logo1>")
        message = services.receive(msg.as_bytes()).message
        item = self.client.get(reverse("staff:mail_thread", args=[message.conversation_id])).context["items"][0]
        self.assertIn("data:image/png;base64,", item["frame"])
        self.assertEqual(item["attachments"], [])

    def test_a_dangerous_attachment_downloads_rather_than_opens(self):
        message = services.receive(an_email(
            attachments=[("page.html", b"<script>steal()</script>", "text", "html")])).message
        response = self.client.get(reverse("staff:mail_attachment", args=[message.attachments.get().pk]))
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))
        self.assertEqual(response["Content-Type"], "application/octet-stream")
        self.assertIn("sandbox", response["Content-Security-Policy"])

    def test_the_original_downloads_for_staff_only(self):
        url = reverse("staff:mail_source", args=[self.message.pk])
        self.assertEqual(self.client.get(url)["Content-Type"], "message/rfc822")
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)


# ========================================================= applicant screens
@SETTINGS
class ApplicantMailTests(StaffMixin, TestCase):
    def test_a_decision_email_starts_a_conversation_their_reply_joins(self):
        self.staff()
        application = EmbarkApplication.objects.create(name="Chidi Okafor", email="chidi@example.com")
        self.client.post(reverse("staff:email", args=["applications", application.pk]),
                         {"subject": "Your Embark application", "body": "Dear Chidi, welcome."})
        conversation = Conversation.objects.get()
        sent = conversation.messages.get()
        self.assertEqual(sent.sent_by, self.user)
        self.assertEqual(sent.reply_to, "hello@iadebayo.foundation")

        # Dated a second *before* our send, as a fast reply from a slightly
        # slow clock is: it must still read below what it answers.
        reply = services.receive(an_email(sender="Chidi <chidi@example.com>",
                                          to="hello@iadebayo.foundation",
                                          subject="Re: Your Embark application",
                                          date="Mon, 01 Jan 2024 00:00:00 +0000")).message
        self.assertEqual(reply.conversation_id, conversation.pk)
        self.assertEqual(list(conversation.messages.all()), [sent, reply])
        conversation.refresh_from_db()
        self.assertEqual(conversation.contact_name, "Chidi")   # learned from the reply
        self.assertEqual(conversation.last_direction, Message.IN)

        detail = self.client.get(reverse("staff:detail", args=["applications", application.pk]))
        self.assertContains(detail, "Email with chidi@example.com")
        self.assertContains(detail, reverse("staff:mail_thread", args=[conversation.pk]))
        thread = self.client.get(reverse("staff:mail_thread", args=[conversation.pk]))
        self.assertEqual(thread.context["records"][0]["title"], str(application))


# ================================================================ the backend
class ZeptoMailThreadingTests(TestCase):
    def payloads(self, responses):
        import io
        import urllib.error

        from core.mail_backends import ZeptoMailBackend
        bodies = []

        def answer(request, timeout=None):
            bodies.append(json.loads(request.data))
            status = responses.pop(0)
            if status != 200:
                raise urllib.error.HTTPError("u", status, "x", {}, io.BytesIO(b'{"error":"bad header"}'))
            return mock.MagicMock()

        message = mail.EmailMessage("Re: hi", "b", "embark@iadebayo.foundation", ["a@example.com"],
                                    headers={"Message-ID": "<ours@iadebayo.foundation>",
                                             "In-Reply-To": "<theirs@example.com>",
                                             "References": "<theirs@example.com>"})
        with mock.patch("urllib.request.urlopen", side_effect=answer):
            sent = ZeptoMailBackend(token="tok").send_messages([message])
        return sent, bodies

    def test_threading_headers_travel_but_message_id_does_not(self):
        sent, bodies = self.payloads([200])
        self.assertEqual(sent, 1)
        self.assertEqual(bodies[0]["mime_headers"], {"In-Reply-To": "<theirs@example.com>",
                                                     "References": "<theirs@example.com>"})

    def test_refused_threading_headers_never_block_the_send(self):
        with self.assertLogs("core.mail_backends", "WARNING"):
            sent, bodies = self.payloads([400, 200])
        self.assertEqual(sent, 1)
        self.assertIn("mime_headers", bodies[0])
        self.assertNotIn("mime_headers", bodies[1])
