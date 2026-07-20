"""Content the Foundation team manages themselves via Django admin."""
from django.db import models


class ImpactStat(models.Model):
    """Numbers for the 'Impact' sections (Home + Embark pages).

    The spec has XYZ placeholders — the team fills real numbers in admin.
    """
    label = models.CharField(max_length=80, help_text="e.g. 'Entrepreneurs Empowered'")
    value = models.PositiveIntegerField(help_text="The number itself, e.g. 250")
    suffix = models.CharField(max_length=8, blank=True, help_text="Optional, e.g. '+'")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.value}{self.suffix} {self.label}"


class TeamMember(models.Model):
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=120)
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


class Testimonial(models.Model):
    KIND_CHOICES = [("text", "Picture & text"), ("video", "Video (YouTube)")]
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default="text")
    name = models.CharField(max_length=120)
    business = models.CharField(max_length=160, blank=True, help_text="Venture / country, e.g. 'AgroLink, Ghana'")
    quote = models.TextField(blank=True, help_text="For text testimonials")
    photo = models.ImageField(upload_to="alumni/", blank=True)
    youtube_url = models.URLField(blank=True, help_text="For video testimonials: full YouTube link")
    featured = models.BooleanField(default=False, help_text="Show on the home page")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.name} ({self.get_kind_display()})"

    @property
    def youtube_embed_url(self):
        """Turn any pasted YouTube URL into an embeddable one."""
        url = self.youtube_url
        if "watch?v=" in url:
            return url.replace("watch?v=", "embed/").split("&")[0]
        if "youtu.be/" in url:
            return url.replace("youtu.be/", "www.youtube.com/embed/")
        return url


class GalleryImage(models.Model):
    image = models.ImageField(upload_to="gallery/")
    caption = models.CharField(max_length=200, blank=True)
    event = models.CharField(max_length=160, blank=True, help_text="e.g. 'Cohort 4 Pitch Day'")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "-id"]

    def __str__(self):
        return self.caption or f"Image #{self.pk}"


class SpotlightVideo(models.Model):
    """Spotlight Show extracts from the Embark YouTube channel (Media page)."""
    title = models.CharField(max_length=200)
    youtube_url = models.URLField()
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "-id"]

    def __str__(self):
        return self.title

    @property
    def youtube_embed_url(self):
        url = self.youtube_url
        if "watch?v=" in url:
            return url.replace("watch?v=", "embed/").split("&")[0]
        if "youtu.be/" in url:
            return url.replace("youtu.be/", "www.youtube.com/embed/")
        return url


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
