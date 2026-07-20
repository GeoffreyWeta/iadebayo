"""Optional: `python manage.py seed_demo` fills the site with sample content
so the team can see every section populated before adding real data."""
from django.core.management.base import BaseCommand
from django.utils import timezone

import shutil
from pathlib import Path

from django.conf import settings

from blog.models import Post
from core.models import (FacultyMember, GalleryImage, ImpactStat, Milestone,
                         SpotlightVideo, TeamMember, Testimonial)


class Command(BaseCommand):
    help = "Seed demonstration content (safe to run once on a fresh database)."

    def handle(self, *args, **options):
        if ImpactStat.objects.exists():
            self.stdout.write("Content already exists — skipping.")
            return

        for i, (label, value, suffix) in enumerate([
            ("Cohorts", 4, ""), ("Applications", 1200, "+"),
            ("Entrepreneurs Empowered", 250, "+"), ("African Countries", 12, ""), ("Live Sessions", 60, "+"),
            ("Facilitators", 30, "+"), ("Mentors", 45, "+"),
        ]):
            ImpactStat.objects.create(label=label, value=value, suffix=suffix, order=i)

        TeamMember.objects.create(name="Dare Adebayo", role="Founder", order=0)
        for i, (year, text) in enumerate([
            ("2024", "IADEBAYO Foundation is born"),
            ("Cohort 1", "Embark Entrepreneurship Academy launches"),
            ("2025", "Alumni ventures span 12 African countries"),
            ("Cohort 4", "Applications pass 1,200"),
            ("2026", "Celebrating two years of impact"),
        ]):
            Milestone.objects.create(year=year, text=text, order=i)
        FacultyMember.objects.create(
            name="Sample Mentor", role="mentor",
            title_company="CEO, Example Ventures", expertise="Fundraising · Go-to-market", order=0)
        Testimonial.objects.create(
            kind="text", name="Amina O.", business="AgroLink, Nigeria", featured=True,
            quote="Embark gave me the structure and mentorship I didn't know my business was missing. We doubled revenue during the programme.")
        SpotlightVideo.objects.create(title="Spotlight Show — Sample episode",
                                      youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        Post.objects.create(
            title="Why every African undergraduate should learn entrepreneurship",
            slug="why-learn-entrepreneurship",
            category="youth-development",
            excerpt="Entrepreneurial skills pay off whether or not you ever register a company — here's why.",
            body="Africa's youth population is its greatest asset.\n\n## The case for starting early\nStudents who learn business fundamentals early make better decisions when opportunity arrives.\n\nMentorship compounds these gains dramatically.",
            published=True, published_at=timezone.now())
        Post.objects.create(
            title="Five ways founders are using AI in 2026",
            slug="ai-for-founders-2026",
            category="ai-entrepreneurship",
            excerpt="From customer research to bookkeeping, AI tools are levelling the field for small teams.",
            body="AI is no longer optional for lean startups.\n\n## Start with customer research\nModern language models turn interview transcripts into insight in minutes.\n\n## Automate the boring parts\nInvoicing, follow-ups, and reporting are the easiest wins.",
            published=True, published_at=timezone.now())
        # Sample gallery images (replace with real event photos in the admin)
        for i in range(1, 7):
            if (Path(settings.MEDIA_ROOT) / "gallery" / f"sample-{i}.webp").exists():
                GalleryImage.objects.create(image=f"gallery/sample-{i}.webp",
                                            caption=f"Sample event photo {i}", order=i)
        # Cover images for the demo posts
        blog_dir = Path(settings.MEDIA_ROOT) / "blog"
        blog_dir.mkdir(parents=True, exist_ok=True)
        for slug, cover in [("why-learn-entrepreneurship", "blog-cover-1.webp"),
                            ("ai-for-founders-2026", "blog-cover-2.webp")]:
            src = Path(settings.BASE_DIR) / "static" / "img" / cover
            if src.exists():
                shutil.copy(src, blog_dir / cover)
                Post.objects.filter(slug=slug).update(cover_image=f"blog/{cover}")
        self.stdout.write(self.style.SUCCESS("Demo content created."))
