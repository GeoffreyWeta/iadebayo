from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from blog.models import Post


class StaticPagesSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.8

    def items(self):
        # "core:resources" and "core:gallery" are deliberately absent while their
        # links are hidden — no point advertising a page to search engines before
        # it is announced, or while its content is out of date.
        return ["core:home", "core:about", "core:embark", "core:apply",
                "core:partner", "core:get_involved", "core:contact",
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
