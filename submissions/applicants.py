"""Shared applicant matching and reporting, without deleting source records."""
from collections import Counter

from django.db.models import Exists, OuterRef, Q
from django.db.models.functions import Lower, Trim


def normalized_email(value):
    return (value or "").strip().lower()


def unfinished_applicants(queryset=None):
    """Latest open draft per email; email-less drafts remain separate.

    Check submissions as well as the completion stamp, including historic rows
    and background saves arriving after a successful submission.
    """
    from .models import EmbarkApplication, PartialApplication

    drafts = PartialApplication.objects.annotate(email_key=Lower(Trim("email")))
    submitted = EmbarkApplication.objects.annotate(email_key=Lower(Trim("email")))
    matching_submission = submitted.filter(email_key=OuterRef("email_key")).exclude(email_key="")
    completed_draft = drafts.filter(email_key=OuterRef("email_key"), completed_at__isnull=False).exclude(email_key="")
    newer_draft = drafts.filter(email_key=OuterRef("email_key"), completed_at__isnull=True).exclude(email_key="").filter(
        Q(updated_at__gt=OuterRef("updated_at")) |
        Q(updated_at=OuterRef("updated_at"), pk__gt=OuterRef("pk")))
    qs = queryset if queryset is not None else PartialApplication.objects.all()
    return qs.annotate(email_key=Lower(Trim("email"))).filter(
        completed_at__isnull=True).alias(
        has_submission=Exists(matching_submission),
        has_completed_draft=Exists(completed_draft),
        has_newer_draft=Exists(newer_draft),
    ).filter(has_submission=False, has_completed_draft=False, has_newer_draft=False)


def unfinished_breakdown(queryset):
    from .models import EmbarkApplication

    labels = dict(EmbarkApplication.SECTOR_CHOICES)
    countries, sectors = Counter(), Counter()
    total = missing_email = 0
    for row in queryset.iterator():
        total += 1
        missing_email += not bool(normalized_email(row.email))
        countries[(row.country or "").strip().casefold() or "Not provided"] += 1
        sector = row.answers.get("business_sector", "")
        sector = sector.strip() if isinstance(sector, str) else ""
        sectors[labels.get(sector, sector or "Not provided")] += 1

    def rows(counts, title=False):
        return [{"label": label.title() if title else label, "count": count,
                 "percent": round(count * 100 / total, 1) if total else 0}
                for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]

    return {"total": total, "missing_email": missing_email,
            "countries": rows(countries, True), "sectors": rows(sectors)}
