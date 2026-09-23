"""`manage.py send_test_email` — prove the mail transport works, loudly.

This exists because every other way of testing mail on this project lies to you.
The form views swallow send failures on purpose (a dead SMTP host must not 500 a
form that already saved), and `send_mail`'s own `fail_silently` swallows them a
second time. So "I submitted a form and no email came" gives you nothing to go
on: no traceback, no log line, no exit code.

This command inverts all of that. It prints what the settings actually resolved
to, sends with `fail_silently=False`, and lets the exception reach you.
"""
from django.conf import settings
from django.core.mail import get_connection, send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send one test email and report exactly why it failed if it did."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to", default=None,
            help="Recipient. Defaults to FOUNDATION_NOTIFY_EMAIL.")

    def handle(self, *args, **options):
        to = options["to"] or settings.FOUNDATION_NOTIFY_EMAIL
        backend = settings.EMAIL_BACKEND

        self.stdout.write(self.style.MIGRATE_HEADING("Resolved mail settings"))
        for label, value in [
            ("EMAIL_BACKEND", backend),
            ("EMAIL_HOST", getattr(settings, "EMAIL_HOST", "(unset)")),
            ("EMAIL_PORT", getattr(settings, "EMAIL_PORT", "(unset)")),
            ("EMAIL_USE_SSL", getattr(settings, "EMAIL_USE_SSL", "(unset)")),
            ("EMAIL_USE_TLS", getattr(settings, "EMAIL_USE_TLS", "(unset)")),
            ("EMAIL_HOST_USER", getattr(settings, "EMAIL_HOST_USER", "") or "(empty)"),
            # Never the password itself — only whether one is present. This
            # command gets run over SSH and pasted into chats when it fails.
            ("EMAIL_HOST_PASSWORD", "set" if getattr(settings, "EMAIL_HOST_PASSWORD", "") else "(empty)"),
            ("ZEPTOMAIL_TOKEN", "set" if getattr(settings, "ZEPTOMAIL_TOKEN", "") else "(unset)"),
            ("DEFAULT_FROM_EMAIL", settings.DEFAULT_FROM_EMAIL),
            ("recipient", to),
        ]:
            self.stdout.write(f"  {label:22} {value}")

        # The console backend is the default, so this is the state a droplet
        # lands in when .env is missing or EMAIL_BACKEND was never set. It looks
        # like success — the message renders and the command exits 0 — which is
        # exactly the confusion this command exists to end.
        if "console" in backend or "locmem" in backend or "dummy" in backend:
            self.stdout.write("")
            raise CommandError(
                f"{backend} does not send anything.\n"
                "Nothing left this machine. Set EMAIL_BACKEND=zeptomail (or smtp) in .env "
                "(and restart gunicorn) before trusting this test.")

        # Open the connection separately from the send so a refused TCP/TLS
        # handshake is distinguishable from an auth or sender-verification
        # rejection. They are different problems with different fixes, and the
        # combined traceback makes them look alike.
        self.stdout.write("")
        try:
            connection = get_connection(fail_silently=False)
            connection.open()
        except Exception as exc:
            raise CommandError(
                f"Could not open a connection to "
                f"{getattr(settings, 'EMAIL_HOST', '?')}:{getattr(settings, 'EMAIL_PORT', '?')}\n"
                f"  {type(exc).__name__}: {exc}\n\n"
                "Usually: wrong host/port, the SSL/TLS flags disagreeing with "
                "the port, or the host firewalling outbound SMTP.") from exc
        self.stdout.write(self.style.SUCCESS("  Connection opened."))

        try:
            sent = send_mail(
                subject="IADEBAYO Foundation — mail transport test",
                message=(
                    "If you are reading this, the site can send email.\n\n"
                    f"Sent by manage.py send_test_email via {getattr(settings, 'EMAIL_HOST', backend)}."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to],
                connection=connection,
                fail_silently=False,      # the entire point of this command
            )
        except Exception as exc:
            raise CommandError(
                f"Connected, but the send was rejected.\n"
                f"  {type(exc).__name__}: {exc}\n\n"
                f"Usually: the API key/token is wrong or lacks Mail Send permission, or "
                f"{settings.DEFAULT_FROM_EMAIL} is not a verified sender on the "
                "provider. Providers accept the login and then refuse the "
                "From address, which is why this failed here and not above.") from exc
        finally:
            connection.close()

        if not sent:
            raise CommandError("The backend reported 0 messages sent, without raising.")

        self.stdout.write(self.style.SUCCESS(f"  Accepted for delivery to {to}."))
        self.stdout.write(
            "\nAccepted is not the same as delivered — check the inbox, the spam\n"
            "folder, and the provider's activity feed before calling this done.")
