from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from blog.models import Post


class StaticPagesSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.8

    def items(self):
        return ["core:home", "core:about", "core:embark", "core:apply", "core:media",
                "core:partner", "core:get_involved", "core:resources", "core:contact",
                "core:privacy", "core:terms", "blog:list"]

    def location(self, item):
        return reverse(item)


class BlogSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return Post.objects.filter(published=True)

    def lastmod(self, obj):
        return obj.published_at


SITEMAPS = {"static": StaticPagesSitemap, "blog": BlogSitemap}
