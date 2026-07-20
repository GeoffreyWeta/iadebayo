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
    ("Where are the classes held?", "Classes are held online and mostly on weekends."),
    ("Is participation free?", "Yes. The programme is completely free for all selected participants."),
    ("Will I receive a certificate?", "Yes. Participants who complete the programme receive an official Certificate of Completion."),
    ("Can I miss classes?", "Attendance is expected throughout the programme. Where unavoidable, participants must notify the Programme Coordinator at least 48 hours before a scheduled session."),
    ("Can I choose my mentor?", "No. Mentors are assigned based on each participant's business sector and development needs."),
]

CORE_VALUES = ["Resilience", "Conscientiousness", "Innovation", "Excellence", "Integrity", "Possibility Thinking"]


def home(request):
    return render(request, "core/home.html", {
        "stats": ImpactStat.objects.all(),
        "components": PROGRAM_COMPONENTS,
        "testimonials": Testimonial.objects.filter(featured=True)[:6],
        "latest_posts": Post.objects.filter(published=True)[:3],
        "gallery_strip": GalleryImage.objects.all()[:6],
        "milestones": Milestone.objects.all()[:5],
        "newsletter_form": f.NewsletterForm(),
        "meta_title": "Empowering Africa's Next Generation of Entrepreneurs",
        "meta_description": "IADEBAYO Foundation equips young Africans with entrepreneurial education, mentorship, and community to build sustainable businesses.",
    })


def about(request):
    return render(request, "core/about.html", {
        "team": TeamMember.objects.all(),
        "values": CORE_VALUES,
        "meta_title": "About Us",
        "meta_description": "The story, vision, mission, and team behind IADEBAYO Foundation.",
    })


def embark(request):
    return render(request, "core/embark.html", {
        "stats": ImpactStat.objects.all(),
        "components": PROGRAM_COMPONENTS,
        "curriculum": CURRICULUM,
        "faculty": FacultyMember.objects.filter(is_active=True),
        "testimonials": Testimonial.objects.all()[:6],
        "meta_title": "Embark Entrepreneurship Academy",
        "meta_description": "Embark Entrepreneurship Academy — the flagship programme of IADEBAYO Foundation, building entrepreneurs who build Africa.",
    })


def apply(request):
    return render(request, "core/apply.html", {
        "form": f.EmbarkApplicationForm(),
        "faqs": FAQS,
        "meta_title": "Apply to Embark",
        "meta_description": "Apply to the Embark Entrepreneurship Academy — free, online, and open to undergraduates and recent graduates building businesses in Africa.",
    })


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


def get_involved(request):
    return render(request, "core/get_involved.html", {
        "faculty_form": f.FacultyApplicationForm(),
        "volunteer_form": f.VolunteerApplicationForm(),
        "meta_title": "Get Involved",
        "meta_description": "Join our faculty as a facilitator or mentor, or volunteer with IADEBAYO Foundation.",
    })


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
