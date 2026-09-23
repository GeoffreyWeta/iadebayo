"""What the staff area lets the team change, described once.

Everything in `/staff/` that lists, edits, creates or deletes a row is driven by
this file. The views in core.staff_views are generic — they take a `Collection`
and know nothing about team members or blog posts — so adding a new editable
thing to the dashboard is a `Collection(...)` here and nothing else.

Why a registry rather than a view per model
-------------------------------------------
There are eighteen editable things on this site and they differ in about six
ways: which columns matter in a list, which fields group together on a form,
what can be searched, what can be filtered, whether the rows have a hand-set
order. Written as eighteen views that is eighteen places for the "mark reviewed"
button to drift out of step. Written as data it is one list-and-form pair that
every collection inherits, which is the same bet Django's own ModelAdmin makes.

Two kinds of collection
-----------------------
`kind="content"` is something the team publishes: it is created, edited, ordered
and deleted here, and it changes the public site.

`kind="inbox"` is something the public sent us: an application, a message, a
subscription. These are records of what a real person submitted, so the staff
area shows them and lets the team mark them reviewed and export them — it does
not let anyone edit the answers, because a record you can quietly rewrite is not
a record. Deleting one needs a superuser (see core.staff_views.can_delete).

`where` is not decoration. Someone editing "Impact stats" needs to know the
numbers show on two pages before they change them, and the list header links
straight through to the live page so the change can be checked.
"""
from dataclasses import dataclass

from blog.models import Post
from submissions import models as sub

from . import models as content


# --------------------------------------------------------------------- columns
@dataclass(frozen=True)
class Col:
    """One column in a collection's list view.

    `kind` picks how core.staff_views.cell renders the value:

      text    plain, truncated by CSS
      strong  the row's identity — becomes the link into the edit form
      long    prose, clamped to two lines
      thumb   an ImageField, shown as a 44px square
      file    a FileField, shown as its basename and size
      bool    a tick or a dash (never colour alone — there is a label too)
      switch  a bool the list can flip in place, one POST per click
      when    a datetime, as "3 Sep 2026, 14:20"
      date    a date with no time — "3 Sep 2026", not "3 Sep 2026, 00:00"
      chip    a small neutral badge, for choice fields
      link    a URL, shown as its domain and opened in a new tab
      count   an integer, right-aligned with tabular figures
    """
    name: str
    label: str = ""
    kind: str = "text"

    @property
    def heading(self):
        return self.label or self.name.replace("_", " ").capitalize()


@dataclass(frozen=True)
class Group:
    """One titled block of fields on the edit form.

    `note` is the sentence above the block. It is where the thing a form field's
    own help text cannot say goes — usually "nothing here shows publicly until
    X", which is a property of the group, not of any one field.
    """
    title: str
    note: str = ""
    fields: tuple = ()


@dataclass(frozen=True)
class Collection:
    slug: str
    model: type
    label: str                      # plural, as it appears in the nav
    singular: str                   # "team member" — used in buttons and flashes
    blurb: str                      # one line: what this controls
    plural: str = ""                # only where adding "s" would be wrong
    section: str = "content"        # nav section: content | people | inbox
    kind: str = "content"           # content | inbox  (see module docstring)
    columns: tuple = ()
    groups: tuple = ()
    search: tuple = ()
    filters: tuple = ()
    ordering: tuple = ()
    order_field: str = ""           # set to enable drag / move-up-down ordering
    where: tuple = ()               # ((url_name, "Home page"), …)
    empty: str = ""                 # empty-state copy
    note: str = ""                  # standing caveat, shown above the list
    per_page: int = 25
    export: bool = False            # offer "Download CSV"
    review_field: str = ""          # inbox only: the boolean the list toggles
    icon: str = "•"

    # ---------------------------------------------------------------- helpers
    @property
    def counted(self):
        """The plural of `singular`, for "0 alumni entries".

        Django's `pluralize` adds an "s" and would give "alumni entrys", so the
        two collections English declines irregularly say so themselves.
        """
        return self.plural or f"{self.singular}s"

    def count_label(self, n):
        return self.singular if n == 1 else self.counted

    @property
    def form_fields(self):
        """Every field on the edit form, flattened out of the groups."""
        return tuple(name for group in self.groups for name in group.fields)

    @property
    def is_inbox(self):
        return self.kind == "inbox"

    @property
    def orderable(self):
        return bool(self.order_field)

    def queryset(self):
        qs = self.model._default_manager.all()
        return qs.order_by(*self.ordering) if self.ordering else qs

    def url(self, name="list", **kwargs):
        from django.urls import reverse
        return reverse(f"staff:{name}", kwargs={"slug": self.slug, **kwargs})


# ============================================================ content: the site
IMPACT = Collection(
    slug="impact-stats",
    model=content.ImpactStat,
    label="Impact stats",
    singular="impact stat",
    icon="◆",
    blurb="The counted numbers in the Impact strip.",
    columns=(Col("label", "Stat", "strong"), Col("value", "Number", "count"),
             Col("suffix", "Suffix"), Col("order", "Order", "count")),
    groups=(Group("The number", "Shown as value + suffix, e.g. 80+.",
                  ("label", "value", "suffix", "order")),),
    ordering=("order", "id"),
    order_field="order",
    where=(("core:home", "Home page"), ("core:embark", "Embark page")),
    empty="No impact stats yet. The pages fall back to the built-in numbers.",
    note="`manage.py sync_impact_stats` rewrites every value here from the "
         "canonical list in core/models.py. If a number you set keeps coming "
         "back wrong, that command is why.",
)

COHORT = Collection(
    slug="cohort",
    model=content.Cohort,
    label="Cohort dates",
    singular="cohort",
    icon="◷",
    blurb="When applications open and close, and when people hear back.",
    columns=(Col("name", "Cohort", "strong"),
             Col("applications_open", "Applications open", "date"),
             Col("applications_close", "Close", "date"),
             Col("is_current", "Advertising this one", "switch")),
    groups=(
        Group("Which cohort", "", ("name", "is_current")),
        Group("Application window",
              "These two dates drive the schedule band on the Embark page, the "
              "“This cohort” range on the analytics, and the countdown meter on "
              "the dashboard. Changing them here changes all three.",
              ("applications_open", "applications_close")),
        Group("Admission notifications",
              "The period the Embark page promises applicants will hear back in.",
              ("notify_from", "notify_to")),
    ),
    filters=("is_current",),
    ordering=("-applications_open",),
    where=(("core:embark", "Embark page"), ("core:apply", "Application form")),
    empty="No cohort set — the site is showing the dates built into the code.",
    note="Exactly one cohort is used: the most recent one ticked as current. "
         "Leaving last year's row here unticked is fine, and usually handy.",
)

MILESTONES = Collection(
    slug="milestones",
    model=content.Milestone,
    label="Milestones",
    singular="milestone",
    icon="→",
    blurb="The journey timeline in the home hero.",
    columns=(Col("year", "Year", "strong"), Col("text", "Line", "long"),
             Col("order", "Order", "count")),
    groups=(Group("The entry", "", ("year", "text", "order")),),
    ordering=("order", "id"),
    order_field="order",
    where=(("core:home", "Home page"),),
    empty="No milestones yet.",
)

TEAM = Collection(
    slug="team",
    model=content.TeamMember,
    label="Team",
    singular="team member",
    section="people",
    icon="◉",
    blurb="The Foundation team on the About page.",
    columns=(Col("photo", "", "thumb"), Col("name", "Name", "strong"),
             Col("role", "Role"), Col("order", "Order", "count")),
    groups=(
        Group("Who they are", "", ("name", "role", "photo")),
        Group("More", "The bio is optional — the About page omits an empty one.",
              ("bio", "linkedin_url", "order")),
    ),
    search=("name", "role"),
    ordering=("order", "name"),
    order_field="order",
    where=(("core:about", "About page"),),
    empty="No team members yet.",
)

FACULTY = Collection(
    slug="faculty",
    model=content.FacultyMember,
    label="Faculty",
    singular="faculty member",
    section="people",
    icon="◉",
    blurb="Facilitators and mentors listed on the Embark page.",
    columns=(Col("photo", "", "thumb"), Col("name", "Name", "strong"),
             Col("role", "Kind", "chip"), Col("title_company", "Role & company"),
             Col("is_active", "Showing", "switch"), Col("order", "Order", "count")),
    groups=(
        Group("Who they are", "", ("name", "role", "title_company", "expertise", "photo")),
        Group("Where it appears", "Untick Active to take someone off the page "
                                  "without deleting the record.",
              ("is_active", "order")),
    ),
    search=("name", "expertise", "title_company"),
    filters=("role", "is_active"),
    ordering=("order", "name"),
    order_field="order",
    where=(("core:embark", "Embark page"),),
    empty="No faculty members yet.",
)

ALUMNI = Collection(
    slug="alumni",
    model=content.Testimonial,
    label="Alumni & testimonials",
    singular="alumni entry",
    plural="alumni entries",
    section="people",
    icon="❝",
    blurb="Quotes, videos and the Alumni Spotlight write-ups.",
    columns=(Col("photo", "", "thumb"), Col("name", "Name", "strong"),
             Col("business", "Venture"), Col("kind", "Kind", "chip"),
             Col("media_consent", "Consent", "switch"),
             Col("on_spotlight", "Spotlight", "switch"),
             Col("featured", "Home", "switch"), Col("order", "Order", "count")),
    groups=(
        Group("Who", "", ("name", "business", "cohort", "photo")),
        Group("Their story",
              "The write-up on the Alumni Spotlight page. Leave a blank line "
              "between paragraphs.",
              ("story", "quote", "link", "link_label")),
        Group("Video",
              "Paste any YouTube link — watch page, youtu.be, or a Short. "
              "Shorts are framed vertically automatically.",
              ("kind", "youtube_url", "orientation")),
        Group("Where it appears",
              "Nothing here reaches the public site until media release consent "
              "is ticked — that is a promise to the person, not a display setting.",
              ("media_consent", "on_spotlight", "featured", "order")),
    ),
    search=("name", "business", "story", "quote", "cohort"),
    filters=("kind", "media_consent", "on_spotlight", "featured"),
    ordering=("order", "id"),
    order_field="order",
    where=(("core:alumni", "Alumni Spotlight"), ("core:home", "Home page")),
    empty="No alumni entries yet.",
)

GALLERY = Collection(
    slug="gallery",
    model=content.GalleryImage,
    label="Gallery",
    singular="gallery image",
    icon="▣",
    blurb="Photographs on the Gallery page.",
    columns=(Col("image", "", "thumb"), Col("caption", "Caption", "strong"),
             Col("event", "Event"), Col("order", "Order", "count")),
    groups=(Group("The photograph",
                  "The caption is what a screen reader announces, so describe "
                  "what is actually in the frame.",
                  ("image", "caption", "event", "order")),),
    search=("caption", "event"),
    ordering=("order", "-id"),
    order_field="order",
    where=(("core:gallery", "Gallery page"),),
    empty="No gallery images yet.",
)

SPOTLIGHT = Collection(
    slug="spotlight-videos",
    model=content.SpotlightVideo,
    label="Spotlight videos",
    singular="spotlight video",
    icon="▶",
    blurb="Spotlight Show extracts on the Media page.",
    columns=(Col("title", "Title", "strong"), Col("youtube_url", "Video", "link"),
             Col("order", "Order", "count")),
    groups=(Group("The video", "Any YouTube link works — watch page, youtu.be, "
                               "or a Short.", ("title", "youtube_url", "order")),),
    search=("title",),
    ordering=("order", "-id"),
    order_field="order",
    where=(("core:gallery", "Gallery page"),),
    empty="No spotlight videos yet.",
)

RESOURCES = Collection(
    slug="resources",
    model=content.Resource,
    label="Resources",
    singular="resource",
    icon="⬇",
    blurb="Downloadable materials on the Resources page.",
    columns=(Col("title", "Title", "strong"), Col("file", "File", "file"),
             Col("description", "Description", "long"), Col("order", "Order", "count")),
    groups=(Group("The download",
                  "Whatever you upload is what the public downloads, under this "
                  "title. Check the file before you save it.",
                  ("title", "description", "file", "order")),),
    search=("title", "description"),
    ordering=("order", "-id"),
    order_field="order",
    where=(("core:resources", "Resources page"),),
    empty="No resources yet.",
)

POSTS = Collection(
    slug="blog",
    model=Post,
    label="Blog posts",
    singular="post",
    icon="✎",
    blurb="Articles on the blog.",
    columns=(Col("cover_image", "", "thumb"), Col("title", "Title", "strong"),
             Col("category", "Category", "chip"),
             Col("published", "Published", "switch"),
             Col("published_at", "Date", "when")),
    groups=(
        Group("The article",
              "In the body, a blank line starts a new paragraph and a line "
              "beginning '## ' becomes a subheading.",
              ("title", "slug", "category", "cover_image", "excerpt", "body",
               "author_name")),
        Group("Publishing",
              "Unpublished posts are invisible to the public and stay out of the "
              "sitemap. The date is what the blog sorts on.",
              ("published", "published_at")),
        Group("Search engines",
              "Both optional. Left blank, the title and excerpt are used.",
              ("seo_title", "seo_description")),
    ),
    search=("title", "excerpt", "body"),
    filters=("category", "published"),
    ordering=("-published_at",),
    where=(("blog:list", "Blog"),),
    empty="No posts yet.",
)

PROMOS = Collection(
    slug="promos",
    model=content.PromoPopup,
    label="Promo popups",
    singular="promo popup",
    icon="✦",
    blurb="The campaign flier shown once to each visitor.",
    columns=(Col("image", "", "thumb"), Col("title", "Campaign", "strong"),
             Col("is_active", "Active", "switch"), Col("starts_at", "From", "when"),
             Col("ends_at", "Until", "when"), Col("version", "Version", "count")),
    groups=(
        Group("The flier",
              "Portrait or square artwork reads best; it is shown at up to 460px "
              "wide. The alt text must repeat what the artwork says in words.",
              ("title", "image", "image_alt")),
        Group("Button", "Leave the link blank to send people to the Embark "
                        "application.", ("link_label", "link_url")),
        Group("When it shows",
              "Only one popup ever shows: the most recently edited row that is "
              "active and inside its dates. Untick Active to pull it site-wide, "
              "immediately.",
              ("is_active", "starts_at", "ends_at")),
        Group("Showing it again",
              "Someone who closes the popup never sees that version again. Bump "
              "the version to show it to everyone once more.",
              ("version",)),
    ),
    filters=("is_active",),
    ordering=("-updated_at",),
    where=(("core:home", "Every public page"),),
    empty="No promo popups yet — no campaign modal is showing.",
)

SEO = Collection(
    slug="seo",
    model=content.PageMeta,
    label="Page SEO",
    singular="page SEO setting",
    plural="page SEO settings",
    icon="⌕",
    blurb="Search-result title and description, per page.",
    columns=(Col("path", "Path", "strong"), Col("title", "SEO title"),
             Col("description", "Meta description", "long")),
    groups=(Group("The page",
                  "The path must match the URL exactly, leading and trailing "
                  "slash included — '/about/', not 'about'. A path with no row "
                  "here uses the built-in default.",
                  ("path", "title", "description")),),
    search=("path", "title", "description"),
    ordering=("path",),
    empty="No overrides — every page uses its built-in title and description.",
)


# ================================================== inbox: what the public sent
APPLICATIONS = Collection(
    slug="applications",
    model=sub.EmbarkApplication,
    label="Embark applications",
    singular="application",
    section="inbox",
    kind="inbox",
    icon="✉",
    blurb="Completed applications to the Academy.",
    columns=(Col("name", "Applicant", "strong"), Col("business_name", "Business"),
             Col("country", "Country", "chip"), Col("created_at", "Received", "when"),
             Col("reviewed", "Reviewed", "switch")),
    search=("name", "email", "business_name", "country", "institution", "phone"),
    filters=("reviewed", "applicant_status", "gender", "device",
             "reliable_internet", "heard_about", "country"),
    ordering=("-created_at",),
    review_field="reviewed",
    export=True,
    per_page=30,
    empty="No applications yet.",
)

UNFINISHED = Collection(
    slug="unfinished",
    model=sub.PartialApplication,
    label="Unfinished applications",
    singular="unfinished application",
    section="inbox",
    kind="inbox",
    icon="◌",
    blurb="People who started an application and never sent it.",
    columns=(Col("name", "Applicant", "strong"), Col("email", "Email"),
             Col("business_name", "Business"),
             Col("furthest_step", "Reached step", "count"),
             Col("updated_at", "Last typed", "when"),
             Col("reviewed", "Followed up", "switch")),
    search=("name", "email", "phone", "business_name", "institution", "country"),
    filters=("reviewed", "furthest_step", "country"),
    ordering=("-updated_at",),
    review_field="reviewed",
    export=True,
    per_page=30,
    note="Nobody in this list pressed submit, and nobody here consented to "
         "anything. Contact them about finishing the application they started, "
         "and nothing else.",
    empty="Nobody has abandoned an application yet.",
)

CONTACT = Collection(
    slug="messages",
    model=sub.ContactMessage,
    label="Contact messages",
    singular="message",
    section="inbox",
    kind="inbox",
    icon="✉",
    blurb="Everything sent through the contact form.",
    columns=(Col("name", "From", "strong"), Col("subject", "Subject"),
             Col("message", "Message", "long"), Col("created_at", "Received", "when"),
             Col("reviewed", "Handled", "switch")),
    search=("name", "email", "subject", "message"),
    filters=("reviewed",),
    ordering=("-created_at",),
    review_field="reviewed",
    export=True,
    empty="No messages yet.",
)

FACULTY_APPS = Collection(
    slug="faculty-applications",
    model=sub.FacultyApplication,
    label="Faculty applications",
    singular="faculty application",
    section="inbox",
    kind="inbox",
    icon="✉",
    blurb="People offering to facilitate or mentor.",
    columns=(Col("name", "Name", "strong"), Col("faculty_option", "Wants to", "chip"),
             Col("country", "Country"), Col("created_at", "Received", "when"),
             Col("reviewed", "Reviewed", "switch")),
    search=("name", "email", "country", "about", "motivation"),
    filters=("reviewed", "faculty_option", "country"),
    ordering=("-created_at",),
    review_field="reviewed",
    export=True,
    empty="No faculty applications yet.",
)

VOLUNTEERS = Collection(
    slug="volunteers",
    model=sub.VolunteerApplication,
    label="Volunteer applications",
    singular="volunteer application",
    section="inbox",
    kind="inbox",
    icon="✉",
    blurb="People offering to volunteer.",
    columns=(Col("name", "Name", "strong"), Col("area", "Area", "chip"),
             Col("skills", "Skills"), Col("country", "Country"),
             Col("created_at", "Received", "when"), Col("reviewed", "Reviewed", "switch")),
    search=("name", "email", "skills", "country", "about", "motivation"),
    filters=("reviewed", "area", "country"),
    ordering=("-created_at",),
    review_field="reviewed",
    export=True,
    empty="No volunteer applications yet.",
)

PARTNERSHIPS = Collection(
    slug="partnerships",
    model=sub.PartnershipInquiry,
    label="Partnership enquiries",
    singular="partnership enquiry",
    plural="partnership enquiries",
    section="inbox",
    kind="inbox",
    icon="✉",
    blurb="Organisations proposing to work with the Foundation.",
    columns=(Col("organization", "Organisation", "strong"), Col("name", "Contact"),
             Col("country", "Country"), Col("created_at", "Received", "when"),
             Col("reviewed", "Reviewed", "switch")),
    search=("organization", "name", "email", "country", "proposal"),
    filters=("reviewed", "country"),
    ordering=("-created_at",),
    review_field="reviewed",
    export=True,
    empty="No partnership enquiries yet.",
)

NEWSLETTER = Collection(
    slug="newsletter",
    model=sub.NewsletterSubscriber,
    label="Newsletter",
    singular="subscriber",
    section="inbox",
    kind="inbox",
    icon="◈",
    blurb="Email addresses collected from the site footer.",
    columns=(Col("email", "Email", "strong"), Col("created_at", "Subscribed", "when")),
    search=("email",),
    ordering=("-created_at",),
    export=True,
    per_page=50,
    note="These addresses were given for the newsletter. Exporting them into "
         "anything else is a different purpose, and not one they agreed to.",
    empty="No subscribers yet.",
)


# ------------------------------------------------------------------- the index
COLLECTIONS = (
    COHORT, IMPACT, MILESTONES, GALLERY, SPOTLIGHT, RESOURCES, POSTS, PROMOS, SEO,
    TEAM, FACULTY, ALUMNI,
    APPLICATIONS, UNFINISHED, CONTACT, FACULTY_APPS, VOLUNTEERS, PARTNERSHIPS,
    NEWSLETTER,
)

BY_SLUG = {c.slug: c for c in COLLECTIONS}

# Nav sections, in the order they appear in the sidebar. The labels are what a
# team member would call the thing, not what the model is called.
SECTIONS = (
    ("content", "Site content", "Pages, media and the blog"),
    ("people", "People", "Team, faculty and alumni"),
    ("inbox", "Submissions", "Everything the public sent us"),
)


def get(slug):
    """The collection for a URL slug, or None."""
    return BY_SLUG.get(slug)


def in_section(name):
    return [c for c in COLLECTIONS if c.section == name]
