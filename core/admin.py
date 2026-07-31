from django.contrib import admin
from . import models

admin.site.site_header = "IADEBAYO Foundation"
admin.site.site_title = "IADEBAYO Foundation Admin"
admin.site.index_title = "Manage website content"


@admin.register(models.ImpactStat)
class ImpactStatAdmin(admin.ModelAdmin):
    list_display = ("label", "value", "suffix", "order")
    list_editable = ("value", "suffix", "order")


@admin.register(models.TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "order")
    list_editable = ("order",)


@admin.register(models.FacultyMember)
class FacultyMemberAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "title_company", "is_active", "order")
    list_editable = ("is_active", "order")
    list_filter = ("role", "is_active")
    search_fields = ("name", "expertise")


@admin.register(models.Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "business", "cohort", "media_consent",
                    "on_spotlight", "featured", "order")
    list_editable = ("media_consent", "on_spotlight", "featured", "order")
    list_filter = ("media_consent", "kind", "on_spotlight", "featured", "cohort")
    search_fields = ("name", "business", "story", "quote")
    readonly_fields = ("video_preview",)
    fieldsets = (
        ("Who", {"fields": ("name", "business", "cohort", "photo")}),
        ("Their story", {
            "description": "The write-up shown on the Alumni Spotlight page. "
                           "Leave a blank line between paragraphs.",
            "fields": ("story", "quote", "link", "link_label"),
        }),
        ("Video", {
            "description": "Paste any YouTube link — watch page, youtu.be, or a Short. "
                           "Shorts are detected and framed vertically.",
            "fields": ("kind", "youtube_url", "orientation", "video_preview"),
        }),
        ("Where it appears", {
            "description": "Nothing shows on the public site until media release consent "
                           "is ticked.",
            "fields": ("media_consent", "on_spotlight", "featured", "order"),
        }),
    )

    @admin.display(description="Resolved embed")
    def video_preview(self, obj):
        """Shows what the pasted link actually resolves to.

        Makes a typo or an unsupported link obvious in the admin rather than as
        a blank box on the live page.
        """
        if not obj.youtube_url:
            return "—"
        if not obj.youtube_embed_url:
            return "Could not read a video id from that link — check the URL."
        shape = "vertical (9:16)" if obj.is_portrait else "landscape (16:9)"
        return f"{obj.youtube_embed_url}  ·  {shape}"


@admin.register(models.GalleryImage)
class GalleryImageAdmin(admin.ModelAdmin):
    list_display = ("__str__", "event", "order")
    list_editable = ("order",)


@admin.register(models.SpotlightVideo)
class SpotlightVideoAdmin(admin.ModelAdmin):
    list_display = ("title", "youtube_url", "order")
    list_editable = ("order",)


@admin.register(models.Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ("title", "order")
    list_editable = ("order",)


@admin.register(models.Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display = ("year", "text", "order")
    list_editable = ("order",)


@admin.register(models.PageMeta)
class PageMetaAdmin(admin.ModelAdmin):
    list_display = ("path", "title", "description")
    search_fields = ("path", "title")
