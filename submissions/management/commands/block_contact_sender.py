from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from submissions.applicants import normalized_email
from submissions.contact_protection import set_sender_blocked


class Command(BaseCommand):
    help = "Block a contact email and mark its messages reviewed, without deleting them."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--unblock", action="store_true")

    def handle(self, *args, **options):
        email = normalized_email(options["email"])
        try:
            validate_email(email)
        except ValidationError as error:
            raise CommandError("Enter a valid email address.") from error
        count = set_sender_blocked(email, not options["unblock"])
        self.stdout.write("Sender unblocked." if options["unblock"] else
                          f"Sender blocked. {count} messages marked reviewed; none deleted.")
