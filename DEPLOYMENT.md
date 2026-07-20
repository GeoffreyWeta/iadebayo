# Deployment guide

The same codebase deploys three ways. Start with Option A — it uses
hosting you have already paid for.

---

## Option A — SmartWeb shared cPanel (₦0 extra)

Requires the "Setup Python App" icon in cPanel (Passenger). If you don't
see it, open a SmartWeb support ticket and ask whether they can enable
Python applications on your plan — then use Option B or C if not.

1. **Create the database.** cPanel → MySQL Databases → create a database
   and a user, grant ALL privileges. Note the names (they get your cPanel
   username as a prefix, e.g. `youruser_iadebayo`).
2. **Create email accounts.** cPanel → Email Accounts →
   `noreply@iadebayo.foundation` (for sending) — `hello@` should already exist.
3. **Upload the code.** cPanel → File Manager (or SFTP) → upload the
   project zip to something like `/home/youruser/iadebayo` and extract.
   Do NOT put it inside `public_html`.
4. **Create the Python app.** cPanel → Setup Python App → Create:
   - Python version: newest available (3.10+ required; 3.11/3.12 ideal)
   - Application root: `iadebayo`
   - Application URL: your domain
   - Application startup file: `passenger_wsgi.py`
   - Application entry point: `application`
5. **Install dependencies.** Copy the "enter virtual environment" command
   cPanel shows, run it in cPanel → Terminal, then:

       pip install -r requirements.txt
       pip install mysqlclient   # or PyMySQL if this fails

   If you end up on PyMySQL, add these two lines at the top of
   `config/__init__.py`:

       import pymysql
       pymysql.install_as_MySQLdb()

6. **Configure.** Copy `.env.example` to `.env` in the project root and
   fill in: a long random `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`,
   your domain in `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`,
   the MySQL credentials, and the email settings from step 2.
7. **Migrate + static files.** In the same terminal:

       python manage.py migrate
       python manage.py createsuperuser
       python manage.py collectstatic --noinput

8. **Serve static & media through Apache** (faster than Django):
   in cPanel File Manager create symlinks inside `public_html` — or in
   the Python App screen add static file mappings:
   `/static/ → /home/youruser/iadebayo/staticfiles/` and
   `/media/  → /home/youruser/iadebayo/media/`.
9. **SSL.** cPanel → SSL/TLS Status → run AutoSSL for the domain.
10. **Restart the app** (button in Setup Python App). Done.

## Option B — PythonAnywhere (~$10/month) + SmartWeb for domain/email

1. Create a paid PythonAnywhere account (custom domains need a paid plan).
2. Upload the project (or `git clone`), create a virtualenv,
   `pip install -r requirements.txt` and `pip install mysqlclient`.
3. Web tab → Add a new web app → Manual configuration → point the WSGI
   file at `config.wsgi:application`, set the virtualenv path.
4. Create a MySQL database on the Databases tab; put credentials in `.env`
   (DB_HOST is shown there, not localhost).
5. Static files: map `/static/` to the `staticfiles` folder after running
   `collectstatic`; map `/media/` to the `media` folder.
6. In SmartWeb cPanel → Zone Editor: point `www` CNAME at the domain
   PythonAnywhere gives you. Keep MX records at SmartWeb so
   `hello@iadebayo.foundation` mailboxes stay there; use those SMTP
   details in `.env`.

## Option C — Small VPS (~$4–6/month, most headroom)

Ubuntu server + Nginx + Gunicorn is the classic setup:

    apt install python3-venv nginx
    git clone <repo> /srv/iadebayo && cd /srv/iadebayo
    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt gunicorn
    # .env as in Option A; migrate; collectstatic
    # systemd service running: gunicorn config.wsgi -b 127.0.0.1:8000
    # nginx: proxy_pass to it; serve /static/ and /media/ directly
    # certbot --nginx for free SSL

## After any deployment

- Add real content in `/admin/` (impact stats, team, faculty, posts).
- Add hero/programme photos (paths listed in README.md).
- Set up Google Analytics 4: paste the GA tag into `templates/base.html`
  head block once you have the measurement ID.
- Register reCAPTCHA v2 keys and add them to `.env` — forms work without
  them, but the spam protection only activates when keys are present.
- Verify the site in Google Search Console and submit `/sitemap.xml`.
