"""Seed the team roster from the OUR TEAM banner supplied on 2026-07-27.

Names follow the banner, with one correction: it prints "WETTA" but the About
page copy and the repo's own git author both spell it "Weta". If the banner is
right, fix it here and in templates/core/about.html together. Roles are left blank
on purpose — the banner does not state them and inventing a job title for a real
colleague is worse than an empty field. Fill them in under Team members.

Dare Adebayo is the one exception: the About page's own copy says he founded the
Foundation, so that title is on the record rather than a guess.

Idempotent — matched on name, so re-running never duplicates and never
overwrites a role or photo that has been filled in since.
"""
from django.core.management.base import BaseCommand

from core.models import TeamMember

# Order matches left-to-right on the banner, so the grid reads the same way.
TEAM = [
    ("Temitope Olamoyegun", ""),
    ("Geoffrey Weta", ""),
    ("Favour Odedele", ""),
    ("Dare Adebayo", "Founder"),
    ("Mercy Oisewemen", ""),
    ("Feranmi Makinde", ""),
    ("Daniel Makinde", ""),
    ("Abigail Banjo", ""),
]


class Command(BaseCommand):
    help = "Create Team member rows for the eight people on the OUR TEAM banner."

    def handle(self, *args, **options):
        created = skipped = 0
        for index, (name, role) in enumerate(TEAM, start=1):
            _, was_created = TeamMember.objects.get_or_create(
                name=name, defaults={"role": role, "order": index})
            if was_created:
                created += 1
                self.stdout.write(f"  + {name}" + (f" — {role}" if role else ""))
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(f"\n{created} created, {skipped} already present."))

        missing_role = TeamMember.objects.filter(role="").count()
        missing_photo = TeamMember.objects.filter(photo="").count()
        if missing_role or missing_photo:
            self.stdout.write(self.style.WARNING(
                f"\nStill to do in the admin, under Team members:\n"
                f"  · {missing_role} without a role\n"
                f"  · {missing_photo} without a headshot\n"
                "The individual profile grid on /about/ stays hidden until headshots are\n"
                "uploaded, so until then the banner is the whole team section."))
