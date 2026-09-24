"""Read-only counts to reconcile applicant exports without exposing contacts."""
import json

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.db.models.functions import Lower, Trim

from submissions.applicants import unfinished_applicants, unfinished_breakdown
from submissions.models import EmbarkApplication, PartialApplication


class Command(BaseCommand):
    help = "Report submitted email counts and unfinished sector/country breakdowns (read-only)."

    def handle(self, *args, **options):
        applications = EmbarkApplication.objects.annotate(email_key=Lower(Trim("email")))
        groups = applications.exclude(email_key="").order_by().values("email_key").annotate(n=Count("pk"))
        duplicate_groups = groups.filter(n__gt=1)
        report = {
            "identity_rule": "Trimmed, lowercase email; blank emails cannot establish unique people.",
            "submitted_rows": applications.count(),
            "submitted_unique_emails": groups.count(),
            "submitted_without_email": applications.filter(email_key="").count(),
            "duplicate_email_groups": duplicate_groups.count(),
            "extra_rows_sharing_email": sum(row["n"] - 1 for row in duplicate_groups),
            "stored_drafts": PartialApplication.objects.count(),
            "unfinished": unfinished_breakdown(unfinished_applicants()),
        }
        self.stdout.write(json.dumps(report, indent=2))
