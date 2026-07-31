"""Load the six alumni testimonial videos supplied on 2026-07-27.

Names, ventures and write-ups are placeholders: the URLs are all we were given,
and inventing an alumnus's name or claiming an impact they did not describe
would be worse than an obvious TODO. Replace them in the admin under
Testimonials.

Idempotent — matched on youtube_url, so re-running never duplicates a row and
never overwrites text that has already been edited.
"""
from django.core.management.base import BaseCommand

from core.models import Testimonial
from core.youtube import is_short, video_id

VIDEOS = [
    "https://youtu.be/m0VLhPOsy5g",
    "https://youtu.be/k_qm2oJjLpE",
    "https://youtu.be/eLHy7FcPYog",
    "https://youtu.be/3lWaS6yjS6M",
    "https://youtube.com/shorts/6ZCUIQMhHkM",
    "https://youtu.be/Xl1QUPYeVN4",
]

PLACEHOLDER_STORY = (
    "TODO — replace with this alumnus's story: what they build, who it serves, and "
    "what changed for the business during and after Embark.\n\n"
    "A second paragraph on impact: customers reached, jobs created, revenue growth, "
    "or whatever they are proudest of. Blank lines start a new paragraph."
)


class Command(BaseCommand):
    help = "Create Testimonial rows for the six alumni videos (placeholder text)."

    def handle(self, *args, **options):
        created = skipped = 0
        for index, url in enumerate(VIDEOS, start=1):
            vid = video_id(url)
            if not vid:
                self.stderr.write(self.style.ERROR(f"Could not parse a video id from {url}"))
                continue
            if Testimonial.objects.filter(youtube_url=url).exists():
                skipped += 1
                continue
            Testimonial.objects.create(
                kind="video",
                name=f"Alumnus {index} — replace with their name",
                business="Venture, Country — replace",
                youtube_url=url,
                story=PLACEHOLDER_STORY,
                order=index,
                on_spotlight=True,
                # Deliberately off: the meeting asked for a signed media release
                # before any alumnus's face is published. Nothing appears on the
                # public site until someone ticks this.
                media_consent=False,
            )
            created += 1
            shape = "vertical Short" if is_short(url) else "landscape"
            self.stdout.write(f"  + {url}  ({shape}, id {vid})")

        self.stdout.write(self.style.SUCCESS(
            f"\n{created} created, {skipped} already present."))
        pending = Testimonial.objects.filter(media_consent=False).count()
        if pending:
            self.stdout.write(self.style.WARNING(
                f"\n{pending} entr{'y is' if pending == 1 else 'ies are'} HIDDEN from the "
                "public site until media release consent is recorded.\n"
                "In the admin: Testimonials -> tick 'Media release consent on file'.\n"
                "Also replace the placeholder names, ventures and stories."))
