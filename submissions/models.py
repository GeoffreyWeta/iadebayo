"""One model per form in the spec. All reviewable in Django admin."""
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
VIDEO_MAX_BYTES = 64 * 1024 * 1024  # 64 MB — ample for a phone-shot minute


def validate_application_video(f):
    """Guard the applicant video upload: recognised container, sane size.

    Duration can't be checked without ffmpeg on the host, so the one-minute
    limit stays an instruction in the form's help text.
    """
    suffix = Path(f.name).suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        raise ValidationError(
            "Please upload a video file (%(allowed)s).",
            params={"allowed": ", ".join(sorted(VIDEO_EXTENSIONS))})
    if f.size and f.size > VIDEO_MAX_BYTES:
        raise ValidationError(
            "That file is %(got)s MB. Please keep the video under %(cap)s MB.",
            params={"got": round(f.size / 1024 / 1024), "cap": VIDEO_MAX_BYTES // 1024 // 1024})


class TimestampedSubmission(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed = models.BooleanField(default=False, help_text="Tick once the team has handled this")

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class DiallingCodeMixin(models.Model):
    """Splits the international dialling code off the national number.

    Kept as its own column rather than baked into `phone` so the code can be a
    dropdown (see core.countries) while old rows that hold a single free-typed
    number remain readable. `phone_display` is what the admin and the team
    notification emails show.

    Mix this in *after* TimestampedSubmission — Django resolves Meta through the
    MRO, so listing it first makes this Meta win and silently drops the
    `ordering = ["-created_at"]` that every submission list relies on.
    """
    phone_code = models.CharField("Country code", max_length=8, blank=True)

    class Meta:
        abstract = True

    @property
    def phone_display(self):
        return f"{self.phone_code} {self.phone}".strip()


class ContactMessage(TimestampedSubmission):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    subject = models.CharField(max_length=200)
    message = models.TextField()

    def __str__(self):
        return f"{self.name} — {self.subject}"


class NewsletterSubscriber(TimestampedSubmission):
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.email


class EmbarkApplication(TimestampedSubmission, DiallingCodeMixin):
    """Embark Academy application, in three sections.

    Every field is permissive at the database level so historic applications
    (submitted against the shorter 2025 form) stay readable. Which fields an
    applicant *must* answer is decided by EmbarkApplicationForm.REQUIRED.
    """

    SECTOR_CHOICES = [(x.lower().replace(" ", "_"), x) for x in [
        "Agriculture", "Beauty", "Construction", "Creative Arts", "Education",
        "Energy", "Entertainment", "Events", "Fashion", "Finance", "Food",
        "Healthcare", "Hospitality", "Logistics", "Manufacturing", "Media",
        "Professional Services", "Real Estate", "Retail", "Social Enterprise",
        "Sports", "Technology", "Tourism", "Other"]]
    STATUS_CHOICES = [("undergraduate", "Undergraduate"), ("graduate", "Graduate")]
    GENDER_CHOICES = [("male", "Male"), ("female", "Female")]
    DEVICE_CHOICES = [("laptop", "Laptop"), ("smartphone", "Smartphone"),
                      ("tablet", "Tablet"), ("desktop", "Desktop Computer")]
    YES_NO_CHOICES = [("yes", "Yes"), ("no", "No")]
    INTERNET_CHOICES = [("yes", "Yes"), ("no", "No"), ("sometimes", "Sometimes")]
    GROWTH_LIMIT_CHOICES = [
        ("customers", "Lack of customers"),
        ("funding", "Lack of funding"),
        ("knowledge", "Lack of business knowledge"),
        ("systems", "Lack of systems/processes"),
        ("partnerships", "Lack of partnerships"),
        ("confidence", "Lack of confidence"),
        ("other", "Other (please specify)"),
    ]
    REFERRAL_CHOICES = [
        ("linkedin", "LinkedIn"), ("instagram", "Instagram"), ("facebook", "Facebook"),
        ("referral", "Friend/Referral"), ("other", "Other (please specify)"),
    ]

    # ---------------------------------------- Section A: about the applicant
    name = models.CharField("Full name", max_length=120)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    applicant_status = models.CharField("Academic status", max_length=20,
                                        choices=STATUS_CHOICES, blank=True)
    email = models.EmailField("Email address", help_text="A Gmail address is preferred")
    phone = models.CharField("Phone number", max_length=32)
    date_of_birth = models.DateField("Date of birth", null=True, blank=True)
    institution = models.CharField("Name of institution", max_length=160, blank=True,
                                   help_text="Graduated from / currently attending")
    city = models.CharField(max_length=80)
    state = models.CharField("State / region", max_length=80, blank=True)
    country = models.CharField(max_length=80)

    # The applicant's own presence, kept separate from the business's below.
    #
    # LinkedIn is the only one the form requires (see
    # EmbarkApplicationForm.REQUIRED): it is the profile a review panel can
    # actually check a founder against, and it is the one platform where a
    # missing account is a signal rather than a preference. The two free handles
    # take whatever the applicant actually uses — Instagram, X, TikTok — so the
    # form does not have to guess the platform list.
    #
    # `social_handle` predates the split and was labelled "Business or personal",
    # so a handful of pre-2026-08 rows may hold a business handle in it. Nothing
    # reads it as authoritative, so relabelling rather than migrating the values
    # is the honest fix.
    linkedin = models.URLField("LinkedIn profile", max_length=300, blank=True)
    social_handle = models.CharField(
        "Personal social media handle", max_length=160, blank=True)
    social_handle_2 = models.CharField(
        "Another personal handle", max_length=160, blank=True)

    # ------------------------------------- Section B: business information
    business_name = models.CharField(max_length=160)
    # help_text carries markup: form_section.html renders it through |safe, and
    # the three-part brief is the single most-missed instruction on the form, so
    # it is worth a list the applicant can tick off rather than a paragraph they
    # skim. Nothing user-supplied ever reaches here.
    business_video_url = models.URLField(
        "Link to your one-minute video", max_length=500, blank=True,
        help_text=
        "<strong>Your video should answer three things:</strong>"
        "<ol class='form-help-brief'>"
        "<li><b>Who you are</b> — your name, where you are, what you study or studied.</li>"
        "<li><b>What your business does</b> — what you sell, to whom, and how it is going.</li>"
        "<li><b>Why you should be chosen</b> — what Embark would change for your venture.</li>"
        "</ol>"
        "About a minute is plenty, and filmed on a phone is perfectly fine — we are "
        "listening to what you say, not judging the production. "
        "<strong>How to share it:</strong> upload the clip to Google Drive, open it, "
        "choose Share, set it to “Anyone with the link”, then paste that link here. "
        "An unlisted YouTube, Vimeo or Dropbox link works too. A private link cannot "
        "be reviewed, and an application we cannot watch cannot be assessed.")
    business_website = models.URLField("Business website", max_length=300, blank=True)
    business_social_handle = models.CharField(
        "Business social media handle", max_length=160, blank=True)
    year_established = models.PositiveSmallIntegerField(
        "How old is the business?", null=True, blank=True,
        help_text="Year the business was established.")
    revenue_last_year = models.CharField("Approximate revenue generated last year",
                                         max_length=80, blank=True)
    revenue_this_year = models.CharField("Approximate revenue generated this year",
                                         max_length=80, blank=True)
    major_challenge = models.TextField(
        "A major challenge your business has faced, and how you addressed it", blank=True)
    growth_limits = models.CharField(
        "Biggest factors limiting your growth right now", max_length=200, blank=True,
        help_text="Stored as comma-separated codes; set by the application form.")
    growth_limits_other = models.CharField("Other limiting factor", max_length=160, blank=True)
    entrepreneurship_view = models.TextField(
        "What do you think the goal of entrepreneurship is \u2014 impact or profit?",
        blank=True, help_text="Explain briefly.")

    # ------------------------------------------------------ Commitment
    device = models.CharField("Device you will use for the programme", max_length=20,
                              choices=DEVICE_CHOICES, blank=True)
    will_participate = models.CharField(
        "Willing to participate actively throughout", max_length=3,
        choices=YES_NO_CHOICES, blank=True)
    reliable_internet = models.CharField("Reliable internet for live sessions",
                                         max_length=10, choices=INTERNET_CHOICES, blank=True)
    heard_about = models.CharField("How they heard about Embark", max_length=20,
                                   choices=REFERRAL_CHOICES, blank=True)
    heard_about_other = models.CharField("Where else they heard about us",
                                         max_length=160, blank=True)
    media_consent = models.BooleanField(
        "Media release consent", default=False,
        help_text="Agreed that photos and video recorded during the programme may be "
                  "used by the Foundation.")

    # ------------------- Legacy fields from the 2025 form, kept for history
    #
    # `business_video` held the clip itself until 2026-08-01, when the 10 GB
    # droplet made storing 64 MB per applicant untenable — roughly seventy
    # applications would have filled the disk, and a full disk stops SQLite
    # writing at all. Applicants now paste a Drive link into
    # `business_video_url` instead. The column, the staff download view and the
    # ZIP action stay so applications submitted before the switch are still
    # readable; nothing new is ever written here.
    business_video = models.FileField(
        "One-minute business video (uploaded, pre-2026-08)", upload_to="applications/videos/",
        blank=True, validators=[validate_application_video],
        help_text="Legacy — superseded by the video link.")
    business_description = models.TextField(blank=True, help_text="Legacy — superseded by the video")
    business_sector = models.CharField(
        "Which sector does your business operate in?", max_length=120,
        choices=SECTOR_CHOICES, blank=True)
    motivation = models.TextField("Why do you want to join Embark?", blank=True,
                                  help_text="Legacy")

    def __str__(self):
        return f"{self.name} — {self.business_name}"

    @property
    def video_download_name(self):
        """Filename the team gets when they download the video.

        Applicants upload things called `IMG_2453.mp4`, which is useless in a
        folder of eighty of them — name the copy after the person and business
        instead. The pk keeps it unique inside a bulk ZIP when two applicants
        slugify the same.
        """
        stem = slugify(f"{self.name} {self.business_name}") or "embark-application"
        return f"{stem}-{self.pk}{Path(self.business_video.name).suffix.lower()}"

    @property
    def growth_limits_display(self):
        """The stored codes as the labels the applicant actually ticked."""
        labels = dict(self.GROWTH_LIMIT_CHOICES)
        picked = [labels.get(c, c) for c in self.growth_limits.split(",") if c]
        if self.growth_limits_other:
            picked = [p for p in picked if p != labels["other"]]
            picked.append(f"Other: {self.growth_limits_other}")
        return ", ".join(picked)


class FacultyApplication(TimestampedSubmission, DiallingCodeMixin):
    OPTION_CHOICES = [("facilitator", "Facilitator"), ("mentor", "Mentor"), ("both", "Both")]
    name = models.CharField(max_length=120)
    phone = models.CharField("Phone number", max_length=32)
    email = models.EmailField()
    faculty_option = models.CharField(max_length=20, choices=OPTION_CHOICES)
    country = models.CharField(max_length=80)
    city = models.CharField(max_length=80)
    motivation = models.TextField("Your motivation")
    about = models.TextField("Tell us a little about you")
    linkedin = models.URLField("Your LinkedIn", blank=True)
    instagram = models.CharField("Your IG", max_length=120, blank=True)

    def __str__(self):
        return f"{self.name} ({self.get_faculty_option_display()})"


class VolunteerApplication(TimestampedSubmission, DiallingCodeMixin):
    AREA_CHOICES = [
        ("programme", "Programme coordination"),
        ("events", "Event management"),
        ("marketing", "Marketing and communications"),
        ("content", "Content creation"),
        ("technology", "Technology"),
        ("design", "Design"),
        ("admin", "Administration"),
        ("community", "Community engagement"),
        ("other", "Other (tell us in your motivation)"),
    ]
    name = models.CharField(max_length=120)
    phone = models.CharField("Phone number", max_length=32)
    email = models.EmailField()
    skills = models.CharField(max_length=200)
    country = models.CharField(max_length=80)
    city = models.CharField(max_length=80)
    area = models.CharField("Area you want to volunteer in", max_length=20,
                            choices=AREA_CHOICES, blank=True)
    motivation = models.TextField("Your motivation")
    about = models.TextField("About you")
    linkedin = models.URLField("LinkedIn", blank=True)
    instagram = models.CharField("IG", max_length=120, blank=True)

    def __str__(self):
        return self.name


class PartnershipInquiry(TimestampedSubmission, DiallingCodeMixin):
    name = models.CharField(max_length=120)
    phone = models.CharField("Phone number", max_length=32)
    email = models.EmailField()
    organization = models.CharField("Organization name", max_length=160)
    website = models.URLField(blank=True)
    country = models.CharField(max_length=80)
    city = models.CharField(max_length=80)
    proposal = models.TextField("How do you intend to partner with us?")

    def __str__(self):
        return f"{self.organization} ({self.name})"
