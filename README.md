# IADEBAYO Foundation — website

Django site with React "islands", designed to run on inexpensive shared hosting
(SmartWeb cPanel) while meeting the technical spec: SEO-ready, mobile-first,
admin-manageable content, six forms with reCAPTCHA + email notifications.

## Quick start (local)

    pip install -r requirements.txt
    python manage.py migrate
    python manage.py seed_demo        # optional sample content
    python manage.py createsuperuser
    python manage.py runserver

Open http://127.0.0.1:8000 — admin at /admin/.

## Project layout

    config/            settings (env-driven), urls, wsgi
    core/              pages, content models (team, faculty, impact stats,
                       testimonials, gallery, spotlight videos, resources)
    blog/              posts with categories + per-post SEO fields
    submissions/       the six forms: models, validation, reCAPTCHA,
                       notification + acknowledgement emails
    templates/         all pages (server-rendered = fully SEO-indexable)
    static/            css design system, js, brand images
    frontend/          React island source (Vite) → builds to static/js/islands.js
    passenger_wsgi.py  cPanel "Setup Python App" entry point

## Editing the React islands

    cd frontend
    npm install
    npm run build      # outputs static/js/islands.js

The islands (hero slider, impact counters) only *enhance* server-rendered
HTML, so SEO and no-JS visitors are unaffected.

## What the team manages in /admin/

Blog posts (with SEO fields), impact numbers, team members, faculty,
alumni testimonials (text or YouTube), Spotlight videos, gallery photos,
downloadable resources — and every form submission arrives there too,
with a "reviewed" checkbox for workflow.

## Images

Every photo is self-hosted WebP — no third-party image hosts. Swap a file in
place (same name, same aspect ratio) and the page picks it up:

    static/img/hero-1.webp  hero-2.webp  hero-3.webp  (home hero slider, 16:9)
    static/img/embark-hero.webp                       (Embark page hero, 16:9)
    static/img/embark-band.webp                       (Embark quote band, 2.5:1)
    static/img/home-what-we-do.webp                   (home, programme photo, 4:3)
    static/img/about-team.webp                        (about page, team photo, 4:3)
    static/img/blog-cover-1.webp  blog-cover-2.webp   (demo post covers, 16:9)
    static/img/gallery/sample-1..6.webp               (demo gallery, 4:3)

The blog covers and gallery samples are demo content: `seed_demo` copies them
into `media/` on a fresh database, and the team replaces them from /admin/.

See DEPLOYMENT.md for putting this live.
