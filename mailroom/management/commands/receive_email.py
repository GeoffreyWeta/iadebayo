"""File a saved email (.eml) into the staff mailbox, exactly as the webhook would.

    python manage.py receive_email message.eml [more.eml ...]
    python manage.py receive_email - < message.eml

For trying the inbox without the Cloudflare Worker, and for bringing in mail
that arrived while receiving was switched off (Gmail: open the message, ⋮ >
Download message). Running it twice on the same file is harmless - the second
run reports a duplicate.
"""
import sys

from django.core.management.base import BaseCommand, CommandError

from mailroom.services import receive


class Command(BaseCommand):
    help = "File one or more .eml files into the staff mailbox."

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="+", help="Files, or - for standard input.")
        parser.add_argument("--to", default="", help="The address it was delivered to.")

    def handle(self, *args, **options):
        for path in options["paths"]:
            try:
                raw = sys.stdin.buffer.read() if path == "-" else open(path, "rb").read()
            except OSError as exc:
                raise CommandError(f"{path}: {exc}")
            result = receive(raw, envelope_to=options["to"], use_date_header=True)
            message = result.message
            where = f" -> conversation {message.conversation_id}" if message else ""
            self.stdout.write(f"{path}: {result.outcome}{where}")
