"""Force the Impact stats table to match the agreed numbers.

Unlike `seed_demo` (which only ever populates an empty database) this runs on
every deploy and overwrites whatever is there, so the figures the team signed
off on are what visitors see.
"""
from django.core.management.base import BaseCommand

from core.models import ImpactStat


class Command(BaseCommand):
    help = "Reset the Impact stats to the agreed figures (idempotent)."

    def handle(self, *args, **options):
        written, removed = ImpactStat.sync_canonical()
        for label in removed:
            self.stdout.write(f"  removed stale stat: {label}")
        for s in ImpactStat.objects.all():
            self.stdout.write(f"  {s.value}{s.suffix}  {s.label}")
        self.stdout.write(self.style.SUCCESS(f"{written} impact stats in sync."))
