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
    list_display = ("name", "kind", "business", "featured", "order")
    list_editable = ("featured", "order")
    list_filter = ("kind", "featured")


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
