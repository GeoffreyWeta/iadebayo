# Deploying the demo to Render (free)

Great for showing the client a live URL. Note the free tier sleeps after
~15 min of inactivity (first visit after that waits ~30-60s), and the demo
database resets on each redeploy — fine for review, not for launch.

## Steps (about 5 minutes)

1. Create an empty repo on GitHub (e.g. `iadebayo-foundation`).
2. Push this project (git is already initialised and committed):

       git remote add origin https://github.com/YOURUSER/iadebayo-foundation.git
       git branch -M main
       git push -u origin main

3. On https://dashboard.render.com : **New → Blueprint**, pick the repo.
   Render reads `render.yaml` and configures everything (Python version,
   build script, gunicorn, secret key, env vars).
4. Click **Apply**. First build takes a few minutes. Your demo goes live at
   `https://iadebayo-foundation.onrender.com` (or similar).
5. Create your admin login in Render's **Shell** tab:

       python manage.py createsuperuser

## What's preconfigured

- `render.yaml` — the blueprint (service, env vars, free plan)
- `render-build.sh` — installs deps, collectstatic, migrate, seeds demo content
- WhiteNoise serves static files; `SERVE_MEDIA=True` lets Django serve
  uploaded media (demo-only pattern)
- `RENDER_EXTERNAL_HOSTNAME` is trusted automatically — no ALLOWED_HOSTS edits

## Upgrading the demo to persistent data (optional)

Add a Render PostgreSQL instance, then in the web service set env var
`DATABASE_URL` to its connection string and add `psycopg2-binary` to
requirements.txt. Uploaded images still need external storage (e.g.
Cloudinary/S3) for true persistence — or move to the cPanel/PythonAnywhere
production setup in DEPLOYMENT.md when ready.
