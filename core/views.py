from django.conf import settings
from django.shortcuts import render

from blog.models import Post
from submissions import forms as f

from .models import (FacultyMember, GalleryImage, ImpactStat, Milestone,
                     Resource, SpotlightVideo, TeamMember, Testimonial)

# Program model cards used on Home + Embark pages
PROGRAM_COMPONENTS = [
    {"name": "Live Classes", "icon": "class",
     "text": "Interactive sessions led by experienced entrepreneurs and professionals deliver a structured entrepreneurship curriculum."},
    {"name": "Spotlight Show", "icon": "spotlight",
     "text": "Conversations with founders and changemakers sharing authentic entrepreneurial experiences and lessons learned."},
    {"name": "Mentorship", "icon": "mentor",
     "text": "Guidance from experienced entrepreneurs and industry professionals, matched to participants by sector and development needs."},
    {"name": "Capstone Project", "icon": "capstone",
     "text": "Participants apply their learning by developing a practical business project that demonstrates strategic thinking and execution."},
    {"name": "Pitch Competition", "icon": "pitch",
     "text": "Participants present their businesses before experienced judges, strengthening their confidence and communication."},
]

CURRICULUM = [
    "Introduction to Entrepreneurship and the Entrepreneurial Mindset", "Developing Business Ideas",
    "Go-to-Market Strategy", "Vision Board Workshop", "Market Research and Data Analysis",
    "Customer Personas", "Product Development", "Marketing and Branding", "Sales Strategy",
    "Financial Management and Revenue Models", "Legal Essentials for Entrepreneurs",
    "Time Management and Productivity", "Teamwork and Collaboration", "Fundraising Fundamentals",
    "AI for Business", "Emotional and Mental Well-being", "Preparing, Pitching, and Presenting Business Ideas",
]

FAQS = [
    ("Is there a registration fee?",
     "No. Embark Entrepreneurship Academy is 100% free. There are no application, "
     "registration, tuition, or certification fees."),
    ("Will I receive a certificate?",
     "Yes. Participants who complete the programme and meet the attendance and "
     "participation requirements will receive a Certificate of Completion at no cost."),
    ("Are there any in-person classes?",
     "No. All classes, mentorship sessions, and programme activities are conducted "
     "entirely online. This allows participants, facilitators, and mentors from across "
     "Africa and around the world to engage conveniently without the need to travel."),
    ("When are classes and mentorship sessions held?",
     "Live classes are held on weekends to accommodate participants' academic and work "
     "schedules: Saturdays (morning) and Sundays (evening). Mentorship sessions are "
     "scheduled separately at mutually convenient times between mentors and mentees."),
    ("Who is eligible to apply?",
     "The programme is open to undergraduates, recent graduates, and early-stage "
     "entrepreneurs across Africa who are currently building or actively working on a "
     "business."),
    ("Do I need to have an existing business?",
     "Yes. The programme is designed for aspiring and early-stage entrepreneurs who "
     "already have a business idea they are validating or an existing business they are "
     "actively growing."),
    ("How long does the programme last?",
     "The duration of each cohort may vary. Successful applicants will receive the "
     "programme calendar and schedule before the cohort begins."),
    ("How much time should I commit each week?",
     "Participants are expected to attend the weekly live classes, actively engage with "
     "mentors, complete assignments where applicable, and participate in programme "
     "activities throughout the cohort."),
    ("What will I learn?",
     "The curriculum covers practical topics including entrepreneurial mindset, business "
     "strategy, customer discovery, product development, marketing, sales, finance, legal "
     "fundamentals, leadership, fundraising, productivity, and leveraging AI for business "
     "growth."),
    ("Will I be assigned a mentor?",
     "Yes. Participants will be matched with experienced entrepreneurs and professionals "
     "who will provide guidance, accountability, and practical support throughout the "
     "mentorship programme."),
    ("Can I participate while studying or working full-time?",
     "Absolutely. The programme is intentionally designed with weekend classes and "
     "flexible mentorship sessions to accommodate students and working professionals."),
    ("How are participants selected?",
     "Applications are reviewed based on eligibility, commitment, the potential of the "
     "business or business idea, and the applicant's willingness to actively participate "
     "throughout the programme."),
    ("What happens after I submit my application?",
     "Our team will review all applications. Shortlisted applicants will be contacted via "
     "email with the next steps and important programme information."),
    ("How can I stay updated about future cohorts?",
     "Follow our social media channels and subscribe to our newsletter to receive updates "
     "on applications, programme announcements, and upcoming events."),
]

CORE_VALUES = ["Resilience", "Conscientiousness", "Innovation", "Excellence", "Integrity", "Possibility Thinking"]


def published_testimonials():
    """Testimonials cleared for the public site.

    The meeting on 2026-07-24 asked for media release consent before any
    alumnus's photo or video is used, so consent is a filter here rather than a
    note in the admin someone has to remember. Untick nothing and a new entry
    simply stays invisible until the paperwork is recorded.
    """
    return Testimonial.objects.filter(media_consent=True)


def home(request):
    return render(request, "core/home.html", {
        "stats": ImpactStat.objects.all(),
        "components": PROGRAM_COMPONENTS,
        "testimonials": published_testimonials().filter(featured=True)[:3],
        "latest_posts": Post.objects.filter(published=True)[:3],
        "gallery_strip": GalleryImage.objects.all()[:6],
        "milestones": Milestone.objects.all()[:5],
        "newsletter_form": f.NewsletterForm(),
        "meta_title": "Empowering Africa's Next Generation of Entrepreneurs",
        "meta_description": "IADEBAYO Foundation equips young Africans with entrepreneurial education, mentorship, and community to build sustainable businesses.",
    })


def about(request):
    return render(request, "core/about.html", {
        # Only members with a headshot: the group banner above the grid already
        # names everyone, so a grid of empty circles would just repeat it.
        "team": TeamMember.objects.exclude(photo=""),
        "team_size": TeamMember.objects.count(),
        "values": CORE_VALUES,
        "stats": ImpactStat.objects.all(),
        "meta_title": "About Us",
        "meta_description": "The story, vision, mission, and team behind IADEBAYO Foundation.",
    })


def embark(request):
    # No faculty grid here — faculty now live on their own Join Faculty page,
    # and this slot carries the FAQ instead.
    return render(request, "core/embark.html", {
        "stats": ImpactStat.objects.all(),
        "components": PROGRAM_COMPONENTS,
        "curriculum": CURRICULUM,
        "faqs": FAQS,
        "testimonials": published_testimonials().filter(on_spotlight=True)[:3],
        "meta_title": "Embark Entrepreneurship Academy",
        "meta_description": "Embark Entrepreneurship Academy — the flagship programme of IADEBAYO Foundation, building entrepreneurs who build Africa.",
    })


def apply_context(form=None):
    """Context for the apply page. Shared with submissions.views so a form with
    validation errors can be re-rendered instead of throwing the answers away."""
    return {
        "form": form if form is not None else f.EmbarkApplicationForm(),
        "faqs": FAQS,
        # Optional: the "what Embark does" explainer shown above the form.
        # Set EMBARK_INTRO_VIDEO_URL once the clip is live on YouTube.
        "embark_intro_video": settings.EMBARK_INTRO_VIDEO_URL,
        "meta_title": "Apply to Embark",
        "meta_description": "Apply to the Embark Entrepreneurship Academy — free, online, and open to undergraduates and recent graduates building businesses in Africa.",
    }


def apply(request):
    return render(request, "core/apply.html", apply_context())


def media_page(request):
    return render(request, "core/media.html", {
        "videos": SpotlightVideo.objects.all(),
        "gallery": GalleryImage.objects.all(),
        "meta_title": "Media",
        "meta_description": "Spotlight Show videos and photos from IADEBAYO Foundation events.",
    })


def partner(request):
    return render(request, "core/partner.html", {
        "form": f.PartnershipInquiryForm(),
        "meta_title": "Partner With Us",
        "meta_description": "Partner with IADEBAYO Foundation — universities, corporations, hubs, foundations, NGOs, and ecosystem partners.",
    })


def alumni(request):
    """The alumni spotlight: one entry per graduate, video plus their story."""
    return render(request, "core/alumni.html", {
        "alumni": published_testimonials().filter(on_spotlight=True),
        "meta_title": "Embark Alumni",
        "meta_description": "Meet Embark Entrepreneurship Academy alumni — the ventures "
                            "they are building across Africa, in their own words.",
    })


def get_involved(request):
    """Hub page. The two ways in each have their own page; this keeps the nav
    parent and every existing /get-involved/ link pointing somewhere useful."""
    return render(request, "core/get_involved.html", {
        "meta_title": "Get Involved",
        "meta_description": "Join our faculty as a facilitator or mentor, or volunteer with IADEBAYO Foundation.",
    })


def join_faculty_context(form=None):
    return {
        "form": form if form is not None else f.FacultyApplicationForm(),
        "faculty": FacultyMember.objects.filter(is_active=True),
        "meta_title": "Join Our Faculty",
        "meta_description": "Share your expertise as an Embark facilitator or mentor and help "
                            "early-stage African entrepreneurs build resilient businesses.",
    }


def join_faculty(request):
    return render(request, "core/join_faculty.html", join_faculty_context())


def volunteer_context(form=None):
    return {
        "form": form if form is not None else f.VolunteerApplicationForm(),
        "meta_title": "Volunteer With Us",
        "meta_description": "Lend your skills to IADEBAYO Foundation — flexible, mostly remote "
                            "volunteer roles supporting young African entrepreneurs.",
    }


def volunteer(request):
    return render(request, "core/volunteer.html", volunteer_context())


def resources(request):
    return render(request, "core/resources.html", {
        "resources": Resource.objects.all(),
        "meta_title": "Resources",
        "meta_description": "Downloadable materials from IADEBAYO Foundation.",
    })


def contact(request):
    return render(request, "core/contact.html", {
        "form": f.ContactForm(),
        "meta_title": "Contact Us",
        "meta_description": "Get in touch with IADEBAYO Foundation.",
    })


def privacy(request):
    return render(request, "core/privacy.html", {"meta_title": "Privacy Policy"})


def terms(request):
    return render(request, "core/terms.html", {"meta_title": "Terms of Use"})


def page_not_found(request, exception=None):
    return render(request, "404.html", {"meta_title": "Page not found"}, status=404)
