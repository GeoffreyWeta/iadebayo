"""Content the Foundation team manages themselves via Django admin."""
from django.db import models

from . import youtube


# The agreed impact numbers, in display order. Single source of truth for the
# seed command, `manage.py sync_impact_stats`, and the template fallbacks.
CANONICAL_IMPACT_STATS = [
    ("Years", 2, ""),
    ("Cohorts", 4, ""),
    ("Entrepreneurs Empowered", 70, ""),
    ("African Countries", 4, ""),
    ("Live Sessions", 80, "+"),
    ("Facilitators & Mentors", 42, "+"),
]


class YouTubeEmbedMixin:
    """Embed/poster URLs derived from whatever YouTube link was pasted in.

    See core.youtube — every shape reduces to a video id first, so Shorts and
    share links carrying ?si=… work the same as a plain watch URL.
    """

    @property
    def youtube_embed_url(self):
        return youtube.embed_url(self.youtube_url)

    @property
    def youtube_thumbnail_url(self):
        return youtube.thumbnail_url(self.youtube_url)

    @property
    def youtube_watch_url(self):
        return youtube.watch_url(self.youtube_url)

    @property
    def is_portrait(self):
        """Vertical video, so the frame must be 9:16 instead of 16:9.

        `orientation` is the manual override for a vertical clip that was
        uploaded as a normal video rather than as a Short.
        """
        setting = getattr(self, "orientation", "auto")
        if setting == "portrait":
            return True
        if setting == "landscape":
            return False
        return youtube.is_short(self.youtube_url)


class ImpactStat(models.Model):
    """Numbers for the 'Impact' sections (Home + Embark pages).

    Defaults come from CANONICAL_IMPACT_STATS; the team edits them in admin.
    """
    label = models.CharField(max_length=80, help_text="e.g. 'Entrepreneurs Empowered'")
    value = models.PositiveIntegerField(help_text="The number itself, e.g. 250")
    suffix = models.CharField(max_length=8, blank=True, help_text="Optional, e.g. '+'")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.value}{self.suffix} {self.label}"

    @classmethod
    def sync_canonical(cls):
        """Make the table match CANONICAL_IMPACT_STATS exactly.

        Matches on label so hand-edits to a value are overwritten but the row
        (and its id) survives. Returns (written, removed_labels).
        """
        keep = []
        for order, (label, value, suffix) in enumerate(CANONICAL_IMPACT_STATS):
            obj, _ = cls.objects.update_or_create(
                label=label, defaults={"value": value, "suffix": suffix, "order": order})
            keep.append(obj.pk)
        stale = cls.objects.exclude(pk__in=keep)
        removed = list(stale.values_list("label", flat=True))
        stale.delete()
        return len(keep), removed


class TeamMember(models.Model):
    name = models.CharField(max_length=120)
    # Blank-able so a roster can be seeded from a group photo before job titles
    # are confirmed; the template omits an empty role rather than showing a gap.
    role = models.CharField(max_length=120, blank=True)
    photo = models.ImageField(upload_to="team/", blank=True)
    bio = models.TextField(blank=True)
    linkedin_url = models.URLField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class FacultyMember(models.Model):
    ROLE_CHOICES = [("facilitator", "Facilitator"), ("mentor", "Mentor"), ("both", "Facilitator & Mentor")]
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="mentor")
    title_company = models.CharField("Role & company", max_length=160, blank=True)
    expertise = models.CharField("Areas of expertise", max_length=200, blank=True)
    photo = models.ImageField(upload_to="faculty/", blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "Faculty members"

    def __str__(self):
        return self.name


class Testimonial(YouTubeEmbedMixin, models.Model):
    KIND_CHOICES = [("text", "Picture & text"), ("video", "Video (YouTube)")]
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default="text")
    name = models.CharField(max_length=120)
    business = models.CharField(max_length=160, blank=True, help_text="Venture / country, e.g. 'AgroLink, Ghana'")
    quote = models.TextField(blank=True, help_text="For text testimonials")
    photo = models.ImageField(upload_to="alumni/", blank=True)
    youtube_url = models.URLField(
        blank=True, help_text="Paste any YouTube link — watch page, youtu.be, or a Short")
    ORIENTATION_CHOICES = [
        ("auto", "Detect automatically (Shorts are treated as vertical)"),
        ("landscape", "Landscape — 16:9"),
        ("portrait", "Vertical — 9:16"),
    ]
    orientation = models.CharField(
        max_length=10, choices=ORIENTATION_CHOICES, default="auto",
        help_text="Only change this if a vertical clip was uploaded as a normal video.")

    # ------------------------------------------- Alumni spotlight page fields
    cohort = models.CharField(max_length=60, blank=True, help_text="e.g. 'Cohort 2, 2025'")
    story = models.TextField(
        blank=True,
        help_text="The write-up for the alumni spotlight page: what they build and the "
                  "impact it has had. A few short paragraphs; blank lines start a new one.")
    link = models.URLField(
        blank=True, help_text="Their website or social page — linked from the spotlight page")
    link_label = models.CharField(
        max_length=60, blank=True,
        help_text="What to call that link, e.g. 'Instagram' or 'agrolink.co'. "
                  "Defaults to the domain.")

    featured = models.BooleanField(default=False, help_text="Show on the home page")
    on_spotlight = models.BooleanField(
        "Show on the Alumni Spotlight page", default=True,
        help_text="Untick to keep an entry out of the spotlight page.")
    media_consent = models.BooleanField(
        "Media release consent on file", default=False,
        help_text="Tick only once this alumnus has agreed their photo and video may be "
                  "used. Entries without it are hidden from the public site.")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

    @property
    def story_paragraphs(self):
        """The write-up split on blank lines, so the template can emit <p>s."""
        return [p.strip() for p in self.story.split("\n\n") if p.strip()]

    @property
    def link_text(self):
        """Label for `link`, falling back to the bare domain."""
        if self.link_label:
            return self.link_label
        from urllib.parse import urlparse
        return urlparse(self.link).netloc.removeprefix("www.") or self.link


class GalleryImage(models.Model):
    image = models.ImageField(upload_to="gallery/")
    caption = models.CharField(max_length=200, blank=True)
    event = models.CharField(max_length=160, blank=True, help_text="e.g. 'Cohort 4 Pitch Day'")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "-id"]

    def __str__(self):
        return self.caption or f"Image #{self.pk}"


class SpotlightVideo(YouTubeEmbedMixin, models.Model):
    """Spotlight Show extracts from the Embark YouTube channel (Media page)."""
    title = models.CharField(max_length=200)
    youtube_url = models.URLField()
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "-id"]

    def __str__(self):
        return self.title


class Resource(models.Model):
    """Downloadable materials for the Resources page."""
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="resources/")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "-id"]

    def __str__(self):
        return self.title


class Milestone(models.Model):
    """Journey timeline shown in the home hero (like the client reference)."""
    year = models.CharField(max_length=12, help_text="e.g. '2024' or 'Cohort 1'")
    text = models.CharField(max_length=140, help_text="Short line, e.g. 'Embark Academy launches'")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.year} — {self.text}"


class PageMeta(models.Model):
    """Editable SEO title + meta description for any static page (spec requirement).

    Path must match the URL exactly, e.g. '/', '/about/', '/embark/'.
    Overrides the built-in defaults when present.
    """
    path = models.CharField(max_length=120, unique=True, help_text="Exact URL path, e.g. /about/")
    title = models.CharField("SEO title", max_length=70, blank=True)
    description = models.CharField("Meta description", max_length=160, blank=True)

    class Meta:
        verbose_name = "Page SEO setting"
        verbose_name_plural = "Page SEO settings"

    def __str__(self):
        return self.path
