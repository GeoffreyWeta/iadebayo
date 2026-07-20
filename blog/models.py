from django.db import models
from django.urls import reverse
from django.utils import timezone


class Category(models.TextChoices):
    YOUTH = "youth-development", "Youth Development"
    AI = "ai-entrepreneurship", "AI & Entrepreneurship"


class Post(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, help_text="URL part, auto-suggested from title")
    category = models.CharField(max_length=40, choices=Category.choices, default=Category.YOUTH)
    cover_image = models.ImageField(upload_to="blog/", blank=True)
    excerpt = models.TextField(max_length=300, help_text="Short summary shown on cards (max 300 chars)")
    body = models.TextField(help_text="The article. Blank line = new paragraph. Lines starting with '## ' become subheadings.")
    author_name = models.CharField(max_length=120, default="IADEBAYO Foundation")
    published = models.BooleanField(default=False)
    published_at = models.DateTimeField(default=timezone.now)
    # Per-page SEO — required by the technical spec (editable titles + meta descriptions)
    seo_title = models.CharField(max_length=70, blank=True, help_text="Optional. Overrides the browser/search title")
    seo_description = models.CharField(max_length=160, blank=True, help_text="Optional. Meta description for search engines")

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("blog:detail", args=[self.slug])

    @property
    def body_blocks(self):
        """Split plain-text body into paragraphs / headings for the template."""
        blocks = []
        for chunk in self.body.split("\n\n"):
            chunk = chunk.strip()
            if not chunk:
                continue
            if chunk.startswith("## "):
                blocks.append({"type": "h2", "text": chunk[3:]})
            else:
                blocks.append({"type": "p", "text": chunk})
        return blocks
