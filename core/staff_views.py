"""The staff area's content management: one set of views for every collection.

These views are generic. They are handed a `Collection` from core.staff_content
by the URL slug and work entirely off what it declares - there is no per-model
view here, and there should not be one. See that module for why.

What a signed-in staff member can do
------------------------------------
Everything in here is behind `staff_required`, the same `is_active and is_staff`
test the analytics dashboard uses. That is deliberate: `manage.py create_staff`
makes accounts that are `is_staff` with no model permissions at all, which means
they can reach the Django admin and see an index that says they may edit
nothing. The whole point of this area is that those accounts can do their job
without anyone having to understand Django's permission system.

The one thing `is_staff` alone does not buy is deletion of a submission. A
content row is replaceable - re-upload the photo, retype the milestone. An
application is not: it is the only copy of what a person sent us, and it is what
every number on the analytics page is counted from. So `can_delete` requires a
superuser for `kind="inbox"`, and the UI does not offer the button otherwise.

Submissions are never editable here, only markable and exportable. A record that
staff can quietly rewrite is not a record of anything.
"""
import csv
from urllib.parse import urlparse

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import models as dj
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from . import mailmerge, staff_content
from .staff import staff_required
from .staff_forms import form_class_for


# ============================================================ small helpers
def collection_or_404(slug):
    found = staff_content.get(slug)
    if found is None:
        raise Http404(f"No staff collection called {slug!r}")
    return found


def can_delete(user, collection):
    """Who may destroy a row. See the module docstring."""
    return user.is_superuser if collection.is_inbox else True


def back_to(request, fallback):
    """The `next=` the caller asked to return to, if it is safe to use.

    `url_has_allowed_host_and_scheme` rather than a bare redirect: `next` comes
    off the query string, so without the check every toggle button on this page
    is an open redirect someone can point at their own site.
    """
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()},
            require_https=request.is_secure()):
        return HttpResponseRedirect(target)
    return HttpResponseRedirect(fallback)


def _public_links(collection):
    """`where` resolved to real URLs, dropping any route that no longer exists.

    A renamed URL should not take the whole staff page down with a
    NoReverseMatch - the link is a convenience, not the point of the screen.
    """
    links = []
    for name, label in collection.where:
        try:
            links.append({"url": reverse(name), "label": label})
        except NoReverseMatch:
            continue
    return links


def _field(model, name):
    try:
        return model._meta.get_field(name)
    except Exception:          # noqa: BLE001 - a column spec naming a property
        return None


# ============================================================ list cells
def cell(obj, col):
    """One table cell, resolved to what the template needs and nothing more.

    Kept in Python rather than in `{% if %}` branches in the template because
    the branching is on the *field's* type, which the template cannot see.
    """
    value = getattr(obj, col.name, None)
    field = _field(obj.__class__, col.name)
    out = {"kind": col.kind, "name": col.name, "heading": col.heading,
           "value": value, "text": "", "url": "", "on": False}

    if col.kind in ("thumb",):
        out["url"] = value.url if value else ""
        return out

    if col.kind == "file":
        if not value:
            return out
        out["text"] = value.name.rsplit("/", 1)[-1]
        out["url"] = value.url
        try:
            out["size"] = value.size
        except (OSError, ValueError):
            # The row survives its file going missing; say so rather than 500.
            out["size"] = None
            out["missing"] = True
        return out

    if col.kind in ("bool", "switch"):
        out["on"] = bool(value)
        out["text"] = "Yes" if value else "No"
        if field is not None:
            out["label"] = field.verbose_name
        return out

    if col.kind in ("when", "date"):
        out["value"] = value
        return out

    if col.kind == "link":
        out["url"] = value or ""
        out["text"] = urlparse(value).netloc.removeprefix("www.") if value else ""
        return out

    if field is not None and getattr(field, "choices", None):
        out["text"] = getattr(obj, f"get_{col.name}_display")() or ""
        return out

    out["text"] = "" if value in (None, "") else str(value)
    return out


def row_for(obj, collection):
    cells = [cell(obj, c) for c in collection.columns]
    return {"obj": obj, "pk": obj.pk, "cells": cells,
            "title": str(obj)[:120]}


# ============================================================ search + filters
def _distinct_values(collection, name):
    """Filter options for a column with no `choices` - country, step, and such.

    Capped at 40: this is a dropdown, and the day someone applies from the
    fortieth country it should stop growing rather than become unusable. The
    cheaper alternative - no filter at all - costs more.
    """
    qs = collection.model._default_manager.exclude(**{f"{name}__isnull": True})
    if isinstance(_field(collection.model, name), dj.CharField):
        qs = qs.exclude(**{name: ""})
    values = qs.values_list(name, flat=True).distinct().order_by(name)[:40]
    return [(str(v), str(v)) for v in values]


def filter_specs(collection, selected):
    """Every declared filter, as a dropdown the template can render."""
    specs = []
    for name in collection.filters:
        field = _field(collection.model, name)
        if field is None:
            continue
        if getattr(field, "choices", None):
            options = [(str(k), str(v)) for k, v in field.choices]
        elif isinstance(field, dj.BooleanField):
            options = [("1", "Yes"), ("0", "No")]
        else:
            options = _distinct_values(collection, name)
        specs.append({
            "name": name,
            "label": field.verbose_name.capitalize(),
            "options": options,
            "current": selected.get(name, ""),
        })
    return specs


def apply_filters(qs, collection, request):
    """Narrow the queryset by `?q=` and any `?<field>=` the collection allows.

    Only names in `collection.filters` are read out of the query string, so a
    crafted `?password=` cannot become a queryset lookup.
    """
    selected = {}
    for name in collection.filters:
        raw = (request.GET.get(name) or "").strip()
        if not raw:
            continue
        selected[name] = raw
        field = _field(collection.model, name)
        if isinstance(field, dj.BooleanField):
            qs = qs.filter(**{name: raw == "1"})
        else:
            qs = qs.filter(**{name: raw})

    query = (request.GET.get("q") or "").strip()
    if query and collection.search:
        clause = Q()
        for name in collection.search:
            clause |= Q(**{f"{name}__icontains": query})
        qs = qs.filter(clause)
    return qs, query, selected


def querystring(request, **changes):
    """The current query string with some keys replaced or dropped.

    Pagination has to keep the search and the filters; the filter form has to
    drop the page. Doing that by hand in the template is how a filtered list
    ends up on page 7 of an unfiltered one.
    """
    params = request.GET.copy()
    for key, value in changes.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else ""


def page_links(request, page):
    """Pagination that keeps the search and the filters.

    Built here rather than in the template because every link has to carry the
    rest of the query string forward; a template that writes `?page=3` by hand
    is how a filtered list silently becomes an unfiltered one on page 3.
    """
    paginator = page.paginator
    links = []
    if paginator.num_pages > 1:
        for number in paginator.get_elided_page_range(page.number, on_each_side=1,
                                                      on_ends=1):
            if number == paginator.ELLIPSIS:
                links.append({"gap": True})
            else:
                links.append({"n": number, "current": number == page.number,
                              "url": querystring(request, page=number)})
    return {
        "links": links,
        "prev": querystring(request, page=page.previous_page_number())
                if page.has_previous() else "",
        "next": querystring(request, page=page.next_page_number())
                if page.has_next() else "",
    }


# ============================================================ the shell context
def shell(request, **extra):
    """Context every staff page needs: the sidebar, and what is waiting on it.

    The unreviewed counts are one COUNT per inbox collection - seven small
    queries on an indexed boolean. That buys a number beside "Embark
    applications" in the nav, which is the difference between a team that
    notices a new application and a team that remembers to go and look.
    """
    sections = []
    for key, title, note in staff_content.SECTIONS:
        items = []
        for c in staff_content.in_section(key):
            badge = 0
            if c.review_field:
                badge = c.model._default_manager.filter(**{c.review_field: False}).count()
            items.append({"c": c, "badge": badge})
        sections.append({"key": key, "title": title, "note": note, "items": items})

    return {"nav_sections": sections, **extra}


# ============================================================ dashboard
@never_cache
@staff_required
def dashboard(request):
    """`/staff/` - what changed, what is waiting, and what is live right now.

    Deliberately not a link farm. The three things a staffer opening this page
    needs are: is anything waiting for me, is the site currently saying what we
    think it is saying, and where do I go to change it.
    """
    waiting = []
    for c in staff_content.in_section("inbox"):
        total = c.model._default_manager.count()
        pending = (c.model._default_manager.filter(**{c.review_field: False}).count()
                   if c.review_field else 0)
        waiting.append({"c": c, "total": total, "pending": pending})
    waiting.sort(key=lambda r: (-r["pending"], r["c"].label))

    content_rows = [{"c": c, "total": c.model._default_manager.count()}
                    for c in staff_content.COLLECTIONS if not c.is_inbox]

    # ---------------------------------------------------- what is live, and what isn't
    promo = staff_content.PROMOS.model.current()
    drafts = staff_content.POSTS.model._default_manager.filter(published=False).count()
    no_consent = staff_content.ALUMNI.model._default_manager.filter(
        media_consent=False).count()
    hidden_faculty = staff_content.FACULTY.model._default_manager.filter(
        is_active=False).count()

    flags = []
    if drafts:
        flags.append({
            "tone": "note", "label": f"{drafts} unpublished blog "
                                     f"{'post' if drafts == 1 else 'posts'}",
            "detail": "Drafts are invisible to the public and stay out of the sitemap.",
            "url": staff_content.POSTS.url() + "?published=0"})
    if no_consent:
        flags.append({
            "tone": "warn", "label": f"{no_consent} alumni "
                                     f"{'entry' if no_consent == 1 else 'entries'} "
                                     f"without media consent",
            "detail": "These are hidden from the public site until consent is ticked.",
            "url": staff_content.ALUMNI.url() + "?media_consent=0"})
    if hidden_faculty:
        flags.append({
            "tone": "note",
            "label": f"{hidden_faculty} faculty "
                     f"{'member' if hidden_faculty == 1 else 'members'} switched off",
            "detail": "Not shown on the Embark page.",
            "url": staff_content.FACULTY.url() + "?is_active=0"})

    # No Cohort row means the public schedule band and the countdown below are
    # running on the dates compiled into core/cohort.py, which is worth saying
    # out loud - it is the one piece of site content that silently has a
    # developer-set value rather than an empty one.
    if staff_content.COHORT.model.current() is None:
        flags.append({
            "tone": "warn",
            "label": "No cohort dates are set",
            "detail": "The Embark page and the dashboard countdown are using the "
                      "dates built into the code. Add a cohort to take them over.",
            "url": reverse("staff:new", kwargs={"slug": staff_content.COHORT.slug})})

    recent = (staff_content.APPLICATIONS.model._default_manager
              .order_by("-created_at")[:6])

    return render(request, "staff/dashboard.html", shell(
        request,
        page_title="Dashboard", nav="dashboard",
        waiting=waiting, content_rows=content_rows,
        promo=promo, flags=flags, recent=recent, today=timezone.localdate(),
    ))


# ============================================================ list
@never_cache
@staff_required
def collection_list(request, slug):
    collection = collection_or_404(slug)
    qs, query, selected = apply_filters(collection.queryset(), collection, request)

    paginator = Paginator(qs, collection.per_page)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "staff/collection_list.html", shell(
        request,
        page_title=collection.label, nav=collection.slug, c=collection,
        page=page, rows=[row_for(o, collection) for o in page.object_list],
        total=paginator.count, total_label=collection.count_label(paginator.count),
        query=query, pages=page_links(request, page),
        filters=filter_specs(collection, selected),
        has_narrowing=bool(query or selected),
        public_links=_public_links(collection),
        may_delete=can_delete(request.user, collection),
        # The export follows the search and the filters, so it carries the same
        # query string - minus `page`, which would export one screenful.
        export_url=reverse("staff:export", kwargs={"slug": collection.slug})
                   + querystring(request, page=None),
        # Reordering renumbers the whole collection, so it is only offered on an
        # unfiltered, unpaginated view - dragging row 3 above row 1 on page 2 of
        # a search result cannot mean anything coherent.
        may_reorder=collection.orderable and not query and not selected
                    and paginator.num_pages == 1,
        here=request.get_full_path(),
    ))


# ============================================================ create / edit
@never_cache
@staff_required
def collection_edit(request, slug, pk=None):
    collection = collection_or_404(slug)
    if collection.is_inbox:
        raise Http404("Submissions are records, not content - they are not editable.")

    instance = get_object_or_404(collection.model, pk=pk) if pk else None
    form_class = form_class_for(collection)

    if request.method == "POST":
        form = form_class(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            obj = form.save(commit=False)
            _place_new_at_end(obj, collection, creating=instance is None)
            obj.save()
            form.save_m2m()
            messages.success(
                request,
                f"{'Added' if instance is None else 'Saved'} “{obj}”.")
            if "save_and_add" in request.POST:
                return redirect("staff:new", slug=collection.slug)
            return redirect(collection.url())
        messages.error(request, "Nothing was saved - see the highlighted fields.")
    else:
        form = form_class(instance=instance)

    return render(request, "staff/collection_form.html", shell(
        request,
        page_title=f"{'Edit' if instance else 'New'} {collection.singular}",
        nav=collection.slug, c=collection, form=form, obj=instance,
        public_links=_public_links(collection),
        may_delete=instance is not None and can_delete(request.user, collection),
    ))


def _place_new_at_end(obj, collection, creating):
    """A new row in an ordered collection goes last, not first.

    Without this every new team member arrives at `order=0` and lands at the top
    of the page, which is never what adding someone to a roster means.
    """
    if not (creating and collection.orderable):
        return
    if getattr(obj, collection.order_field, 0):
        return
    last = (collection.model._default_manager
            .order_by(f"-{collection.order_field}")
            .values_list(collection.order_field, flat=True).first())
    setattr(obj, collection.order_field, (last or 0) + 1)


# ============================================================ delete
@never_cache
@staff_required
def collection_delete(request, slug, pk):
    """GET asks; POST does it. Never a link - a GET must not destroy anything."""
    collection = collection_or_404(slug)
    obj = get_object_or_404(collection.model, pk=pk)

    if not can_delete(request.user, collection):
        messages.error(
            request,
            f"Deleting a {collection.singular} needs an administrator account. "
            "It is the only copy of what someone sent us, and the analytics are "
            "counted from it.")
        return redirect(collection.url())

    if request.method == "POST":
        label = str(obj)
        obj.delete()
        messages.success(request, f"Deleted “{label}”. That cannot be undone.")
        return redirect(collection.url())

    return render(request, "staff/collection_delete.html", shell(
        request, page_title=f"Delete {collection.singular}", nav=collection.slug,
        c=collection, obj=obj, row=row_for(obj, collection),
    ))


# ============================================================ inbox detail
@never_cache
@staff_required
def submission_detail(request, slug, pk):
    """Everything one person submitted, on one page, read-only."""
    collection = collection_or_404(slug)
    if not collection.is_inbox:
        return redirect("staff:edit", slug=slug, pk=pk)
    obj = get_object_or_404(collection.model, pk=pk)

    return render(request, "staff/submission_detail.html", shell(
        request, page_title=str(obj)[:60], nav=collection.slug, c=collection,
        obj=obj, rows=detail_rows(obj), extras=detail_extras(obj),
        may_delete=can_delete(request.user, collection),
        here=request.get_full_path(),
        reviewed=getattr(obj, collection.review_field, None)
                 if collection.review_field else None,
    ))


# Columns that are plumbing, not answers: they say nothing to someone reading an
# application and their labels ("Draft id") only add noise.
#
# The decision columns are skipped for a different reason than the rest: they
# are not plumbing, they are just not *answers*. The applicant did not tell us
# whether we approved them, and listing our own decision under "What they
# submitted" reads as though they did. They have their own card on the page.
_DETAIL_SKIP = {"id", "draft_id", "acknowledged_at", "answers",
                "decision", "decided_at", "decided_by", "decision_email_sent_at"}


def detail_rows(obj):
    """Every answer on a submission, as label/value pairs in model order."""
    rows = []
    for field in obj._meta.fields:
        if field.name in _DETAIL_SKIP:
            continue
        value = getattr(obj, field.name)
        if field.choices:
            value = getattr(obj, f"get_{field.name}_display")()
        rows.append({
            "label": field.verbose_name.capitalize(),
            "value": value,
            "empty": value in (None, ""),
            "is_bool": isinstance(field, dj.BooleanField),
            "is_url": isinstance(field, dj.URLField),
            "is_file": isinstance(field, dj.FileField),
            "long": isinstance(field, dj.TextField),
        })
    return rows


def detail_extras(obj):
    """Derived read-outs that are not fields - the joined-up phone number, the
    ticked growth limits, the raw draft of an unfinished application."""
    extras = []
    if hasattr(obj, "phone_display"):
        extras.append({"label": "Phone (with code)", "value": obj.phone_display, "pre": False})
    if hasattr(obj, "growth_limits_display"):
        extras.append({"label": "Limiting factors, as ticked",
                       "value": obj.growth_limits_display, "pre": False})
    if hasattr(obj, "answers_display"):
        extras.append({"label": "Everything typed so far",
                       "value": obj.answers_display, "pre": True})
    return [e for e in extras if e["value"]]


# ============================================================ toggles
@require_POST
@staff_required
def collection_toggle(request, slug, pk):
    """Flip one boolean from the list - reviewed, published, active, featured.

    Only fields the collection already declares as a `switch` column (or its
    review field) can be flipped, so this endpoint cannot be pointed at an
    arbitrary column.
    """
    collection = collection_or_404(slug)
    name = request.POST.get("field", "")
    allowed = {c.name for c in collection.columns if c.kind == "switch"}
    if collection.review_field:
        allowed.add(collection.review_field)
    if name not in allowed:
        raise Http404("That field is not switchable here.")

    obj = get_object_or_404(collection.model, pk=pk)
    new = not getattr(obj, name)
    setattr(obj, name, new)
    # `update_fields` limits the UPDATE to the one column, which also silently
    # skips any auto_now column - and PromoPopup.current() picks the campaign to
    # show by `-updated_at`, so a popup switched on from this button would sort
    # behind one edited earlier and never appear. Write those too.
    stamps = [f.name for f in collection.model._meta.fields
              if getattr(f, "auto_now", False)]
    obj.save(update_fields=[name, *stamps])

    field = collection.model._meta.get_field(name)
    messages.success(
        request,
        f"“{str(obj)[:60]}” - {field.verbose_name} {'on' if new else 'off'}.")
    return back_to(request, collection.url())


# ============================================================ reordering
@require_POST
@staff_required
def collection_reorder(request, slug):
    """Set the display order.

    Two callers, one endpoint. The move up/down buttons post a single `pk` and a
    `direction` and work with scripting off; the drag handler posts the whole
    `ids` list it ended up with. Both finish by renumbering the collection from
    zero, which also quietly repairs the duplicate `order` values that hand-typed
    numbers always end up with.
    """
    collection = collection_or_404(slug)
    if not collection.orderable:
        raise Http404("This collection has no manual order.")

    field = collection.order_field
    current = list(collection.queryset().values_list("pk", flat=True))

    posted = request.POST.getlist("ids")
    if posted:
        wanted = [int(i) for i in posted if i.isdigit()]
        known = set(current)
        order = [pk for pk in wanted if pk in known]
        # Anything the client did not mention keeps its place at the end, so a
        # row created in another tab is never dropped out of the ordering.
        order += [pk for pk in current if pk not in set(order)]
    else:
        try:
            pk = int(request.POST.get("pk", ""))
        except ValueError:
            raise Http404("No row named.")
        if pk not in current:
            raise Http404("That row is not in this collection.")
        index = current.index(pk)
        step = -1 if request.POST.get("direction") == "up" else 1
        target = index + step
        order = current[:]
        if 0 <= target < len(order):
            order[index], order[target] = order[target], order[index]

    rows = collection.model._default_manager.in_bulk(order)
    for position, pk in enumerate(order):
        row = rows.get(pk)
        if row is not None and getattr(row, field) != position:
            setattr(row, field, position)
            row.save(update_fields=[field])

    if not request.headers.get("X-Requested-With") == "XMLHttpRequest":
        messages.success(request, "Order updated.")
    return back_to(request, collection.url())


# ============================================================ bulk actions
@require_POST
@staff_required
def collection_bulk(request, slug):
    """Mark, unmark or delete the ticked rows."""
    collection = collection_or_404(slug)
    action = request.POST.get("action", "")
    pks = [int(p) for p in request.POST.getlist("pks") if p.isdigit()]
    if not pks:
        messages.error(request, "Nothing was ticked.")
        return back_to(request, collection.url())

    qs = collection.model._default_manager.filter(pk__in=pks)

    if action in ("review", "unreview") and collection.review_field:
        count = qs.update(**{collection.review_field: action == "review"})
        word = "reviewed" if action == "review" else "not reviewed"
        messages.success(request, f"{count} marked as {word}.")
    elif action == "delete":
        if not can_delete(request.user, collection):
            messages.error(request, "Deleting these needs an administrator account.")
            return back_to(request, collection.url())
        count = qs.count()
        qs.delete()
        messages.success(request, f"Deleted {count} "
                                  f"{collection.count_label(count)}. "
                                  f"That cannot be undone.")
    else:
        messages.error(request, "Unknown action.")
    return back_to(request, collection.url())


# ============================================================ mail the ticked
@never_cache
@staff_required
def collection_email_many(request, slug):
    """Write one message and send it to everybody ticked, personalised per row.

    Two deliberate properties, both of which exist because this is the screen
    that can annoy the most people at once:

      * **The recipients are listed by name and address before anything is
        sent.** A bulk send whose audience you cannot see is how the wrong forty
        people get told they were admitted.
      * **Each message is rendered per recipient**, so `{{ first_name }}` is
        their name and `{{ resume_link }}` is their own link. It is one message
        written once, not one message shared.

    Rows with no email address are dropped and named, rather than silently
    skipped, because "I sent it to everyone" needs to be true or corrected.
    """
    from .models import EmailTemplate
    from .staff_forms import ApplicantEmailForm
    from submissions.services import send_to_applicant

    collection = _mailable(slug)
    pks = [int(p) for p in request.POST.getlist("pks") or request.GET.getlist("pks")
           if p.isdigit()]
    rows = list(collection.model._default_manager.filter(pk__in=pks))
    if not rows:
        messages.error(request, "Nothing was ticked.")
        return redirect(collection.url())

    with_email = [r for r in rows if (getattr(r, "email", "") or "").strip()]
    without = [str(r) for r in rows if not (getattr(r, "email", "") or "").strip()]

    if request.method == "POST" and request.POST.get("send"):
        form = ApplicantEmailForm(request.POST)
        if form.is_valid():
            sent, failed = [], []
            for row in with_email:
                context = mailmerge.context_for(row)
                ok = send_to_applicant(
                    (row.email or "").strip(),
                    mailmerge.render(form.cleaned_data["subject"], context),
                    mailmerge.render(form.cleaned_data["body"], context),
                    obj=row, stamp_field=collection.email_stamp_field)
                (sent if ok else failed).append(str(row))

            if sent:
                messages.success(request, f"Sent to {len(sent)} "
                                          f"{collection.count_label(len(sent))}.")
            if failed:
                # Named, not counted: a failure the team cannot identify is one
                # they cannot retry.
                messages.error(request, "Could not send to: " + "; ".join(failed[:20]))
            if not failed:
                return redirect(collection.url())
    else:
        chosen = None
        if request.POST.get("template") or request.GET.get("template"):
            want = request.POST.get("template") or request.GET.get("template")
            chosen = EmailTemplate.objects.filter(pk=want).first()
        # Unrendered on purpose: the placeholders are the point on this screen,
        # because one body serves many people. The preview below shows what the
        # first recipient will actually get.
        form = ApplicantEmailForm(initial={
            "subject": chosen.subject if chosen else "",
            "body": chosen.body if chosen else "",
        })

    preview = None
    if with_email:
        first = with_email[0]
        preview = {"who": str(first), "context": mailmerge.context_for(first)}

    return render(request, "staff/email_many.html", shell(
        request, page_title=f"Email {len(with_email)} people",
        nav=collection.slug, c=collection, form=form,
        rows=with_email, without=without, preview=preview,
        templates=list(EmailTemplate.objects.all()),
        tokens=mailmerge.catalogue(),
        pks=[r.pk for r in rows],
    ))


# ============================================================ export
@never_cache
@staff_required
def collection_export(request, slug):
    """The current, filtered list as CSV.

    Exports what is on screen, not the whole table - someone who filtered to
    Ghana and pressed Download means Ghana. The filename says so too.
    """
    collection = collection_or_404(slug)
    if not collection.export:
        raise Http404("This collection is not exportable.")

    qs, query, selected = apply_filters(collection.queryset(), collection, request)

    fields = [f for f in collection.model._meta.fields
              if f.name not in ("acknowledged_at",)]
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    stamp = timezone.localdate().isoformat()
    name = slugify(collection.label)
    if query or selected:
        name += "-filtered"
    response["Content-Disposition"] = f'attachment; filename="{name}-{stamp}.csv"'
    # Excel on a Windows machine reads a bare UTF-8 CSV as Latin-1 and turns
    # every accented name into mojibake. The BOM is what makes it read UTF-8.
    response.write("﻿")

    writer = csv.writer(response)
    writer.writerow([f.verbose_name.capitalize() for f in fields])
    for obj in qs.iterator(chunk_size=500):
        row = []
        for field in fields:
            value = getattr(obj, field.name)
            if field.choices:
                value = getattr(obj, f"get_{field.name}_display")()
            elif isinstance(field, dj.FileField):
                value = value.name or ""
            elif isinstance(value, bool):
                value = "yes" if value else "no"
            elif hasattr(value, "tzinfo") and value.tzinfo is not None:
                value = timezone.localtime(value).strftime("%Y-%m-%d %H:%M")
            row.append("" if value is None else str(value))
        writer.writerow(row)
    return response


# ============================================================ decisions and mail
def _mailable(slug):
    """The collection for `slug`, if staff may write to the people in it.

    Separate from `_decidable` because the two are no longer the same set:
    unfinished applications are mailed (one "you were nearly there" nudge) but
    never approved or declined - nobody in that list has applied for anything
    yet.
    """
    collection = collection_or_404(slug)
    if not collection.mailable:
        raise Http404("That collection is not one staff write to.")
    return collection


def _decidable(slug):
    """The collection for `slug`, if it records decisions. 404 otherwise.

    The check is on the collection rather than on the model so that these two
    views stay as generic as every other view in this module: a second inbox
    that starts recording decisions declares `decision_field` and gets both
    screens, with nothing added here.
    """
    collection = collection_or_404(slug)
    if not collection.decides:
        raise Http404("That collection does not record decisions.")
    return collection


@require_POST
@staff_required
def collection_decide(request, slug, pk):
    """Record approve / decline / undo on one submission.

    Deliberately does not send anything. Deciding and telling someone are two
    actions a person should take separately: the second one needs the first to
    be right, and a button that does both means every misclick is an email that
    cannot be recalled. The decision sets up the next screen; it does not fire it.
    """
    collection = _decidable(slug)
    obj = get_object_or_404(collection.model, pk=pk)
    field = collection.decision_field

    value = request.POST.get("decision", "")
    allowed = {c for c, _ in collection.model._meta.get_field(field).choices}
    if value and value not in allowed:
        raise Http404("Not a decision this collection recognises.")

    setattr(obj, field, value)
    obj.decided_at = timezone.now() if value else None
    obj.decided_by = request.user if value else None
    obj.save(update_fields=[field, "decided_at", "decided_by"])

    if value:
        messages.success(
            request,
            f"“{str(obj)[:60]}” marked {obj.get_decision_display().lower()}. "
            f"They have not been told yet - use “Send email” when you are ready.")
    else:
        messages.success(request, f"Decision cleared for “{str(obj)[:60]}”.")
    return back_to(request, collection.url("detail", pk=pk))


@never_cache
@staff_required
def collection_email(request, slug, pk):
    """Compose and send one message to one applicant.

    GET fills the box from a template - the one the URL names, or the one whose
    purpose matches the decision just recorded - with this applicant's details
    already substituted. POST sends exactly what came back in the box.

    Rendering on the way *in* rather than on the way out is the point. A staff
    member who reads the message before pressing send has read the real message,
    not a draft with `{{ first_name }}` in it that will be filled in later by
    code they cannot see.
    """
    from .models import EmailTemplate
    from .staff_forms import ApplicantEmailForm
    from submissions.services import send_to_applicant

    collection = _mailable(slug)
    obj = get_object_or_404(collection.model, pk=pk)
    to_email = (getattr(obj, "email", "") or "").strip()
    already = getattr(obj, collection.email_stamp_field, None)

    templates = list(EmailTemplate.objects.all())
    chosen = None
    if request.GET.get("template"):
        chosen = next((t for t in templates
                       if str(t.pk) == request.GET["template"]), None)
    elif collection.decides and getattr(obj, collection.decision_field, ""):
        chosen = EmailTemplate.preferred(getattr(obj, collection.decision_field))

    context = mailmerge.context_for(obj)

    if request.method == "POST":
        form = ApplicantEmailForm(request.POST)
        if not to_email:
            # Belt and braces: the button is hidden without an address, but a
            # POST is not the button.
            messages.error(request, "That submission has no email address on it.")
        elif form.is_valid():
            subject = mailmerge.render(form.cleaned_data["subject"], context)
            body = mailmerge.render(form.cleaned_data["body"], context)
            sent = send_to_applicant(to_email, subject, body, obj=obj,
                                     stamp_field=collection.email_stamp_field)
            if sent:
                messages.success(request, f"Email sent to {to_email}.")
                return redirect(collection.url("detail", pk=pk))
            # Not a redirect: the text is still in the box, and losing it would
            # mean rewriting the message to try again.
            messages.error(
                request,
                "The message could not be sent - the mail server refused it. "
                "Nothing was recorded against this applicant, so nothing is "
                "lost by trying again.")
    else:
        form = ApplicantEmailForm(initial={
            "subject": mailmerge.render(chosen.subject, context) if chosen else "",
            "body": mailmerge.render(chosen.body, context) if chosen else "",
        })

    return render(request, "staff/email_compose.html", shell(
        request, page_title=f"Email {getattr(obj, 'name', '') or to_email}",
        nav=collection.slug, c=collection, obj=obj, form=form,
        already_sent=already,
        to_email=to_email, templates=templates, chosen=chosen,
        placeholders=mailmerge.catalogue(),
        sent_at=getattr(obj, "decision_email_sent_at", None),
        decision=getattr(obj, collection.decision_field, ""),
    ))
