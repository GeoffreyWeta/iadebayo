"""Tests for the staff content admin — the part of /staff/ that changes the site.

Two things are worth pinning down here, and they are different in kind.

The first is **breadth**: the list, form and detail views are generic, so a
mistake in one collection's declaration (a column naming a field that does not
exist, a group listing a field the model dropped) shows up as a 500 on exactly
one page and nowhere else. `test_every_collection_*` walks the registry rather
than naming collections, so a new `Collection(...)` is covered the moment it is
added and a stale one fails loudly.

The second is the **rules that protect data**: submissions cannot be edited,
deleting one needs a superuser, the toggle endpoint cannot be pointed at an
arbitrary column, and `?next=` cannot be pointed off-site. Those are the
assertions that would otherwise only be checked by someone reading the code.
"""
import datetime as dt

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from blog.models import Post
from submissions.models import ContactMessage, EmbarkApplication

from . import staff_content
from .models import Cohort, Milestone, TeamMember, Testimonial

PASSWORD = "pw-for-tests-only"

# Same reason as core.tests: with DEBUG off, SecurityMiddleware answers plain
# http test requests with a 301 to https and every assertion below drifts.
SSL_REDIRECT_OFF = override_settings(SECURE_SSL_REDIRECT=False)


def a_staff_user(client, **flags):
    user = User.objects.create_user("staffer", password=PASSWORD, is_staff=True,
                                    **flags)
    client.login(username="staffer", password=PASSWORD)
    return user


@SSL_REDIRECT_OFF
class RegistryTests(TestCase):
    """Every collection must describe fields that actually exist."""

    def test_columns_and_form_fields_resolve_on_the_model(self):
        for c in staff_content.COLLECTIONS:
            names = {f.name for f in c.model._meta.get_fields()}
            with self.subTest(collection=c.slug):
                for col in c.columns:
                    self.assertIn(col.name, names,
                                  f"{c.slug} lists a column {col.name!r} the model "
                                  f"does not have")
                for field in c.form_fields:
                    self.assertIn(field, names,
                                  f"{c.slug} puts {field!r} on its form, but the "
                                  f"model has no such field")
                for field in (*c.search, *c.filters):
                    self.assertIn(field, names)

    def test_content_collections_are_editable_and_inboxes_are_not(self):
        for c in staff_content.COLLECTIONS:
            with self.subTest(collection=c.slug):
                if c.is_inbox:
                    self.assertEqual(c.form_fields, (),
                                     "a submission must not have an edit form")
                else:
                    self.assertTrue(c.form_fields,
                                    "content with no editable fields cannot be added")

    def test_slugs_are_unique(self):
        slugs = [c.slug for c in staff_content.COLLECTIONS]
        self.assertEqual(len(slugs), len(set(slugs)))


@SSL_REDIRECT_OFF
class EveryCollectionRendersTests(TestCase):
    """Walk the whole registry rather than naming collections one at a time."""

    def setUp(self):
        a_staff_user(self.client)

    def test_every_list_page_renders(self):
        for c in staff_content.COLLECTIONS:
            with self.subTest(collection=c.slug):
                response = self.client.get(c.url())
                self.assertEqual(response.status_code, 200)
                # escaped: "Alumni & testimonials" reaches the page as &amp;
                self.assertContains(response, escape(c.label))

    def test_every_content_collection_offers_a_working_new_form(self):
        for c in staff_content.COLLECTIONS:
            if c.is_inbox:
                continue
            with self.subTest(collection=c.slug):
                response = self.client.get(reverse("staff:new", args=[c.slug]))
                self.assertEqual(response.status_code, 200)
                # Every declared field reaches the page — a group that names a
                # field the form dropped would otherwise fail silently.
                for name in c.form_fields:
                    self.assertContains(response, f'name="{name}"')

    def test_search_and_filters_do_not_break_the_list(self):
        for c in staff_content.COLLECTIONS:
            with self.subTest(collection=c.slug):
                response = self.client.get(c.url(), {"q": "zzz-nothing"})
                self.assertEqual(response.status_code, 200)

    def test_unknown_collection_is_a_404(self):
        response = self.client.get(reverse("staff:list", args=["not-a-thing"]))
        self.assertEqual(response.status_code, 404)


@SSL_REDIRECT_OFF
class ContentEditingTests(TestCase):
    def setUp(self):
        a_staff_user(self.client)

    def test_creating_a_row_puts_it_on_the_public_site(self):
        response = self.client.post(reverse("staff:new", args=["milestones"]),
                                    {"year": "2026", "text": "Cohort 5 opens",
                                     "order": ""})
        self.assertRedirects(response, staff_content.MILESTONES.url())
        self.assertTrue(Milestone.objects.filter(text="Cohort 5 opens").exists())

    def test_a_new_row_goes_to_the_end_of_an_ordered_collection(self):
        """Adding someone to a roster must not put them at the top of it."""
        Milestone.objects.create(year="2024", text="First", order=0)
        Milestone.objects.create(year="2025", text="Second", order=1)
        self.client.post(reverse("staff:new", args=["milestones"]),
                         {"year": "2026", "text": "Third", "order": ""})
        self.assertEqual(
            list(Milestone.objects.values_list("text", flat=True)),
            ["First", "Second", "Third"])

    def test_editing_saves_and_an_invalid_form_saves_nothing(self):
        member = TeamMember.objects.create(name="Ada Obi", role="Director")
        url = reverse("staff:edit", args=["team", member.pk])

        self.client.post(url, {"name": "Ada Obi-Cole", "role": "Director",
                               "bio": "", "linkedin_url": "", "order": 0})
        member.refresh_from_db()
        self.assertEqual(member.name, "Ada Obi-Cole")

        response = self.client.post(url, {"name": "", "role": "Director",
                                          "bio": "", "linkedin_url": "", "order": 0})
        self.assertEqual(response.status_code, 200)       # re-rendered, not saved
        member.refresh_from_db()
        self.assertEqual(member.name, "Ada Obi-Cole")

    def test_delete_asks_first_and_only_a_post_destroys(self):
        member = TeamMember.objects.create(name="Ada Obi")
        url = reverse("staff:delete", args=["team", member.pk])

        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(TeamMember.objects.filter(pk=member.pk).exists())

        self.client.post(url)
        self.assertFalse(TeamMember.objects.filter(pk=member.pk).exists())


@SSL_REDIRECT_OFF
class SubmissionsAreRecordsTests(TestCase):
    """A submission can be read, marked and exported — never rewritten."""

    def setUp(self):
        self.user = a_staff_user(self.client)
        self.application = EmbarkApplication.objects.create(
            name="Ada Obi", email="ada@example.com", phone="8012345678",
            city="Lagos", country="Nigeria", business_name="Acme Crafts")

    def test_there_is_no_edit_form_for_a_submission(self):
        response = self.client.get(
            reverse("staff:edit", args=["applications", self.application.pk]))
        self.assertEqual(response.status_code, 404)

    def test_the_detail_page_shows_what_they_sent(self):
        response = self.client.get(
            reverse("staff:detail", args=["applications", self.application.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acme Crafts")
        self.assertContains(response, "ada@example.com")

    def test_ordinary_staff_cannot_delete_a_submission(self):
        response = self.client.post(
            reverse("staff:delete", args=["applications", self.application.pk]))
        self.assertTrue(EmbarkApplication.objects.filter(pk=self.application.pk).exists())
        self.assertRedirects(response, staff_content.APPLICATIONS.url())

    def test_a_superuser_can(self):
        self.user.is_superuser = True
        self.user.save()
        self.client.post(
            reverse("staff:delete", args=["applications", self.application.pk]))
        self.assertFalse(EmbarkApplication.objects.filter(pk=self.application.pk).exists())

    def test_export_is_csv_of_the_filtered_list(self):
        EmbarkApplication.objects.create(
            name="Bola Ade", email="bola@example.com", phone="1", city="Accra",
            country="Ghana", business_name="Beta Foods")

        response = self.client.get(reverse("staff:export", args=["applications"]),
                                   {"country": "Ghana"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        body = response.content.decode("utf-8-sig")
        self.assertIn("Beta Foods", body)
        self.assertNotIn("Acme Crafts", body)

    def test_a_collection_that_does_not_export_refuses(self):
        response = self.client.get(reverse("staff:export", args=["team"]))
        self.assertEqual(response.status_code, 404)


@SSL_REDIRECT_OFF
class TogglingTests(TestCase):
    def setUp(self):
        a_staff_user(self.client)
        self.post = Post.objects.create(title="Hello", slug="hello",
                                        excerpt="x", body="y", published=False)

    def url(self):
        return reverse("staff:toggle", args=["blog", self.post.pk])

    def test_a_switch_flips_the_field(self):
        self.client.post(self.url(), {"field": "published"})
        self.post.refresh_from_db()
        self.assertTrue(self.post.published)

    def test_a_field_that_is_not_a_switch_cannot_be_flipped(self):
        """The endpoint must not be a general-purpose setter."""
        response = self.client.post(self.url(), {"field": "seo_title"})
        self.assertEqual(response.status_code, 404)

    def test_a_toggle_needs_a_post(self):
        self.assertEqual(self.client.get(self.url()).status_code, 405)

    def test_next_cannot_be_pointed_off_site(self):
        response = self.client.post(self.url(),
                                    {"field": "published",
                                     "next": "https://evil.example/steal"})
        self.assertEqual(response["Location"], staff_content.POSTS.url())


@SSL_REDIRECT_OFF
class ReorderTests(TestCase):
    def setUp(self):
        a_staff_user(self.client)
        self.rows = [Milestone.objects.create(year=str(2020 + i), text=f"M{i}", order=i)
                     for i in range(3)]

    def order(self):
        return list(Milestone.objects.values_list("text", flat=True))

    def test_move_up_swaps_with_the_row_above(self):
        self.client.post(reverse("staff:reorder", args=["milestones"]),
                         {"pk": self.rows[2].pk, "direction": "up"})
        self.assertEqual(self.order(), ["M0", "M2", "M1"])

    def test_move_up_from_the_top_changes_nothing(self):
        self.client.post(reverse("staff:reorder", args=["milestones"]),
                         {"pk": self.rows[0].pk, "direction": "up"})
        self.assertEqual(self.order(), ["M0", "M1", "M2"])

    def test_a_posted_order_is_applied_and_renumbered_from_zero(self):
        self.client.post(reverse("staff:reorder", args=["milestones"]),
                         {"ids": [self.rows[2].pk, self.rows[0].pk, self.rows[1].pk]})
        self.assertEqual(self.order(), ["M2", "M0", "M1"])
        self.assertEqual(sorted(Milestone.objects.values_list("order", flat=True)),
                         [0, 1, 2])

    def test_a_row_the_client_did_not_know_about_is_kept(self):
        """A row created in another tab must not fall out of the ordering."""
        self.client.post(reverse("staff:reorder", args=["milestones"]),
                         {"ids": [self.rows[1].pk, self.rows[0].pk]})
        self.assertEqual(self.order(), ["M1", "M0", "M2"])

    def test_an_unordered_collection_refuses(self):
        response = self.client.post(reverse("staff:reorder", args=["blog"]),
                                    {"pk": 1, "direction": "up"})
        self.assertEqual(response.status_code, 404)


@SSL_REDIRECT_OFF
class BulkActionTests(TestCase):
    def setUp(self):
        self.user = a_staff_user(self.client)
        self.messages = [ContactMessage.objects.create(
            name=f"P{i}", email=f"p{i}@example.com", subject="Hi", message="…")
            for i in range(3)]

    def test_marking_several_reviewed(self):
        self.client.post(reverse("staff:bulk", args=["messages"]),
                         {"action": "review",
                          "pks": [m.pk for m in self.messages[:2]]})
        self.assertEqual(ContactMessage.objects.filter(reviewed=True).count(), 2)

    def test_bulk_delete_of_submissions_needs_a_superuser(self):
        self.client.post(reverse("staff:bulk", args=["messages"]),
                         {"action": "delete", "pks": [m.pk for m in self.messages]})
        self.assertEqual(ContactMessage.objects.count(), 3)

        self.user.is_superuser = True
        self.user.save()
        self.client.post(reverse("staff:bulk", args=["messages"]),
                         {"action": "delete", "pks": [m.pk for m in self.messages]})
        self.assertEqual(ContactMessage.objects.count(), 0)


@SSL_REDIRECT_OFF
class AccessTests(TestCase):
    """The content admin is behind the same door as the rest of /staff/."""

    def test_anonymous_is_sent_to_the_staff_sign_in(self):
        for url in (reverse("staff:home"),
                    staff_content.TEAM.url(),
                    reverse("staff:new", args=["team"])):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("staff:login"), response["Location"])

    def test_a_signed_in_non_staff_user_gets_nowhere(self):
        User.objects.create_user("member", password=PASSWORD)
        self.client.login(username="member", password=PASSWORD)
        response = self.client.get(staff_content.TEAM.url())
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("staff:login"), response["Location"])

    def test_pages_are_never_indexed_or_cached(self):
        a_staff_user(self.client)
        response = self.client.get(staff_content.ALUMNI.url())
        self.assertContains(response, "noindex")
        self.assertIn("no-store", response["Cache-Control"])


@SSL_REDIRECT_OFF
class DashboardTests(TestCase):
    def setUp(self):
        a_staff_user(self.client)

    def test_it_flags_what_the_public_cannot_see(self):
        Post.objects.create(title="Draft", slug="draft", excerpt="x", body="y",
                            published=False)
        Testimonial.objects.create(name="Ada", media_consent=False)

        response = self.client.get(reverse("staff:home"))
        self.assertContains(response, "unpublished blog post")
        self.assertContains(response, "without media consent")

    def test_it_says_when_the_cohort_dates_are_still_the_built_in_ones(self):
        response = self.client.get(reverse("staff:home"))
        self.assertContains(response, "No cohort dates are set")

    def test_it_says_so_when_there_is_nothing_to_flag(self):
        Cohort.objects.create(
            name="Cohort 6", applications_open=dt.date(2027, 3, 1),
            applications_close=dt.date(2027, 4, 15),
            notify_from=dt.date(2027, 4, 20), notify_to=dt.date(2027, 5, 1))
        response = self.client.get(reverse("staff:home"))
        self.assertContains(response, "Nothing is hidden or half-finished")
