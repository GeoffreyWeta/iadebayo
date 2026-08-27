"""`manage.py create_staff` -- make or reset the team's dashboard accounts.

`createsuperuser` prompts, which is no use over `ssh host "..."`, and the
alternative -- piping a block of Python into `manage.py shell -c` -- has to
survive cmd.exe, then ssh, then bash, then Python, each with its own idea of
what a quote means. It reliably arrives mangled. A management command takes
plain arguments and ends that problem for good.

Accounts are made `is_staff`, never `is_superuser` unless asked. That is the
flag the dashboard checks (see core.staff.staff_required), and it is the
smallest thing that works: a superuser can also delete applicants and edit other
people's accounts, which is not what "give Mercy the dashboard" should mean.

Note what `is_staff` alone does *not* buy. It admits someone to the Django admin
but grants no model permissions, so the admin index reads "You don't have
permission to view or edit anything" until the account is given some -- most
tidily by putting everyone in one group. The command says so when it finishes,
because the alternative is six people concluding the site is broken.
"""
import secrets
import string

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

# Ambiguous characters left out: these get read aloud, written on paper and
# retyped by hand, and "was that l or 1" wastes more time than the extra bit of
# entropy is worth.
ALPHABET = (string.ascii_lowercase.replace("l", "").replace("o", "")
            + string.ascii_uppercase.replace("I", "").replace("O", "")
            + "23456789")


class Command(BaseCommand):
    help = "Create or update staff accounts for the analytics dashboard."

    def add_arguments(self, parser):
        parser.add_argument("usernames", nargs="+", help="One or more usernames.")
        parser.add_argument(
            "--password", default=None,
            help="Set this password for all of them. Omitted, a strong random "
                 "one is generated per account and printed once.")
        parser.add_argument(
            "--superuser", action="store_true",
            help="Also grant full admin rights. Rarely what you want.")

    def handle(self, *args, **options):
        User = get_user_model()
        shared = options["password"]
        weak = []

        self.stdout.write(self.style.MIGRATE_HEADING(
            "{:12} {:9} {}".format("username", "status", "password")))

        for username in options["usernames"]:
            username = username.strip().lower()
            if not username:
                continue
            password = shared or "".join(secrets.choice(ALPHABET) for _ in range(14))

            user, created = User.objects.get_or_create(
                username=username, defaults={"is_staff": True})
            user.is_staff = True
            user.is_active = True
            if options["superuser"]:
                user.is_superuser = True
            # set_password deliberately skips AUTH_PASSWORD_VALIDATORS -- an
            # administrator handing out a starter password is a different act
            # from a person choosing their own, and blocking it here would just
            # push people to do it in the shell where nothing is recorded. The
            # weakness is reported instead, and /staff/password/ still enforces
            # the validators when they change it themselves.
            user.set_password(password)
            user.save()

            try:
                validate_password(password, user)
            except ValidationError:
                weak.append(username)

            self.stdout.write("{:12} {:9} {}".format(
                username, "created" if created else "updated", password))

        self.stdout.write("")
        if weak:
            self.stdout.write(self.style.WARNING(
                "That password would be rejected if these people tried to set it\n"
                "themselves -- it is too short, too common, or all digits. This\n"
                "login opens applicants' names, emails, phone numbers and dates of\n"
                "birth, so treat it as a starter only and have everyone replace it\n"
                "at /staff/password/ on first sign-in."))
        self.stdout.write(
            "These accounts reach /staff/analytics/ now. The Django admin will\n"
            "look empty to them until they are given model permissions -- put\n"
            "them in a group with the submissions permissions if they need to\n"
            "open individual applications.")
