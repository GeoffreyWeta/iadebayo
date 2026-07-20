from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render

from .models import Category, Post


def post_list(request):
    qs = Post.objects.filter(published=True)
    active_category = request.GET.get("category", "")
    if active_category in Category.values:
        qs = qs.filter(category=active_category)
    paginator = Paginator(qs, 9)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "blog/list.html", {
        "page": page,
        "categories": Category.choices,
        "active_category": active_category,
        "meta_title": "Blog",
        "meta_description": "Insights on youth development, entrepreneurship, and AI from IADEBAYO Foundation.",
    })


def post_detail(request, slug):
    post = get_object_or_404(Post, slug=slug, published=True)
    related = Post.objects.filter(published=True, category=post.category).exclude(pk=post.pk)[:3]
    return render(request, "blog/detail.html", {
        "post": post,
        "related": related,
        "meta_title": post.seo_title or post.title,
        "meta_description": post.seo_description or post.excerpt,
    })
