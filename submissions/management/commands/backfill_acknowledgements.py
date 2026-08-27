"""`manage.py backfill_acknowledgements` -- mail everyone who never got one.

Every row created before mail worked on the server is owed a confirmation: the
send was attempted, it failed, and the failure was caught and logged so that the
submission itself would still succeed. Nobody was told. This command finds those
rows and writes to them.

Three things it deliberately will not do:

  * **Send anything without `--send`.** The default is a dry run that prints
    exactly who would be written to. A command whose default behaviour is to
    mail hundreds of real people is one that eventually does so by accident,
    off a shell history, at the wrong moment.

  * **Touch PartialApplication.** Those people typed into the form and never
    submitted it. "We have received your submission" is not true of them, and
    saying it to someone who abandoned an application is worse than silence.
    They need a different message, which is a different job.

  * **Mail anyone twice.** `acknowledged_at` records who has already been
    written to, by this command and by the live form views alike, so a re-run
    after a partial failure resumes instead of starting over.

Deliverability matters more here than any of the above. A brand-new sending
domain that suddenly emits hundreds of messages to addresses collected months
ago is the textbook spam signature: stale addresses bounce, the bounce rate
spikes on a domain with no sending history, and the provider suspends the
account -- which takes the working live-form mail down with it. Run this in
batches with `--limit`, oldest first, and read the provider's bounce numbers
between batches.
"""
import time

from django.conf import settings
from django.core.mail import get_connection
from django.core.management.base import BaseCommand, CommandError

from submissions import models
from submissions.services import acknowledge

# name -> (model, the phrase acknowledge() drops into "Thank you for ...").
# Each phrase is copied from the matching views._handle call so that a
# backfilled message is indistinguishable from the one the form would have sent
# at the time.
FORMS = {
    "embark": (models.EmbarkApplication,
               "applying to the Embark Entrepreneurship Academy"),
    "faculty": (models.FacultyApplication,
                "applying to join our faculty"),
    "volunteers": (models.VolunteerApplication,
                   "offering to volunteer with IADEBAYO Foundation"),
    "partners": (models.PartnershipInquiry,
                 "your interest in partnering with IADEBAYO Foundation"),
    "contact": (models.ContactMessage,
                "contacting IADEBAYO Foundation"),
}

# Contact messages are excluded by default. An acknowledgement for an
# application is still welcome months later, because the applicant is waiting on
# an outcome. "We received your message" for a question someone asked in March
# and has long since given up on is just a confusing email. Opt in with
# `--form contact` if you decide otherwise.
DEFAULT_FORMS = ["embark", "faculty", "volunteers", "partners"]


class Command(BaseCommand):
    help = "Send the confirmation email to submissions that never received one."

    def add_arguments(self, parser):
        parser.add_argument(
            "--send", action="store_true",
            help="Actually send. Without this the command only reports.")
        parser.add_argument(
            "--form", action="append", dest="forms", choices=sorted(FORMS),
            help="Repeatable. Default: " + ", ".join(DEFAULT_FORMS) + ".")
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Stop after this many recipients. Use it; see the module docstring.")
        parser.add_argument(
            "--sleep", type=float, default=0.5,
            help="Seconds to pause between sends (default 0.5).")

    def handle(self, *args, **options):
        send = options["send"]
        chosen = options["forms"] or DEFAULT_FORMS
        limit = options["limit"]

        if send and any(k in settings.EMAIL_BACKEND
                        for k in ("console", "locmem", "dummy")):
            raise CommandError(
                "--send with " + settings.EMAIL_BACKEND + " would send nothing "
                "while reporting success, and would stamp every row as "
                "acknowledged -- so the real run would then skip them all. "
                "Configure SMTP first.")

        # Gather before sending, so the plan can be printed and counted whole.
        # Deduped across forms by address: someone who applied to Embark and also
        # offered to volunteer gets one email, not two.
        seen, plan = set(), []
        for key in chosen:
            model, what = FORMS[key]
            qs = (model.objects.filter(acknowledged_at__isnull=True)
                  .exclude(email="").order_by("created_at"))
            for obj in qs:
                email = (obj.email or "").strip()
                if not email or email.lower() in seen:
                    continue
                seen.add(email.lower())
                plan.append((key, obj, email, what))

        eligible = len(plan)
        if limit:
            plan = plan[:limit]
        skipped = eligible - len(plan)

        header = ("SENDING to " if send else "DRY RUN -- ") + str(len(plan)) + " recipient(s)"
        self.stdout.write(self.style.MIGRATE_HEADING(header))
        for key, obj, email, _ in plan:
            name = (getattr(obj, "name", "") or "friend").split()[0]
            self.stdout.write(
                "  {:11} {:%Y-%m-%d}  {:38} {}".format(key, obj.created_at, email, name))

        if skipped:
            self.stdout.write(self.style.WARNING(
                "\n  " + str(skipped) + " more are eligible but were cut by --limit "
                + str(limit) + ". Re-run to continue where this left off."))

        if not plan:
            self.stdout.write("\nNobody is owed an acknowledgement.")
            return

        if not send:
            self.stdout.write(
                "\nDry run -- nothing was sent and nothing was stamped.\n"
                "Re-run with --send once the addresses above look right.")
            return

        # One connection for the whole run rather than one per message.
        connection = get_connection(fail_silently=False)
        sent = failed = 0
        try:
            connection.open()
            for i, (key, obj, email, what) in enumerate(plan):
                name = (getattr(obj, "name", "") or "friend").split()[0]
                if acknowledge(email, name, what, obj=obj, connection=connection):
                    sent += 1
                else:
                    # acknowledge() has already logged the traceback. Keep going:
                    # one dead address must not strand the rest of the batch.
                    failed += 1
                    self.stdout.write(self.style.ERROR("  failed: " + email))
                if options["sleep"] and i < len(plan) - 1:
                    time.sleep(options["sleep"])
        finally:
            connection.close()

        self.stdout.write(self.style.SUCCESS("\nSent " + str(sent) + "."))
        if failed:
            self.stdout.write(self.style.ERROR(
                "Failed " + str(failed) + " -- these were NOT stamped, so a re-run "
                "retries them. Check the log for the reason before re-running."))
        self.stdout.write(
            "Check the provider's bounce and spam-complaint numbers before "
            "sending the next batch.")
