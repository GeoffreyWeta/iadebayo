# Deploying to a DigitalOcean Droplet (domain at Namecheap)

Ubuntu 24.04 + Nginx + Gunicorn + PostgreSQL + Let's Encrypt.
Cost: ~$6/month droplet (+ $1.20 optional backups). Domain stays at Namecheap.

Everything below assumes the domain `iadebayo.foundation` and the repo
`https://github.com/GeoffreyWeta/iadebayo.git` — substitute your own if different.

**Order matters.** Do Phase 0 → 9 in sequence; each ends with a check you can run.

---

## Phase 0 — Before you start

You need:

- A DigitalOcean account with billing set up.
- Access to the Namecheap account holding `iadebayo.foundation`.
- Push access to the GitHub repo, and your local work committed (see 0.2).
- **Your SMTP details.** A droplet must NOT run its own mail server (DigitalOcean
  blocks port 25 on new accounts, and a fresh IP has no sending reputation).
  Whoever hosts `hello@iadebayo.foundation` today keeps hosting it — you just
  reuse their SMTP host/port/password. Common cases:
  - SmartWeb cPanel: `mail.iadebayo.foundation`, port 465, SSL
  - Namecheap Private Email: `mail.privateemail.com`, port 465, SSL
- **Know where your email DNS lives.** If mail is working today, the MX records
  are somewhere. This guide keeps DNS at Namecheap precisely so you never touch
  those records — you only change the two A records that point at the web server.

### 0.1 Create an SSH key (on your Windows machine)

In PowerShell:

    ssh-keygen -t ed25519 -C "iadebayo-droplet"

Press Enter at each prompt (a passphrase is fine too). Then print the public key:

    Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub

Copy that whole line — you'll paste it into DigitalOcean next.

### 0.2 Get the current code onto GitHub

The droplet installs by cloning GitHub (Phase 5.1) and updates by pulling from it
(*Shipping updates later*). GitHub is the only channel between your machine and the
server — **whatever isn't pushed doesn't deploy.** So push before you build the
droplet, not after.

Confirm the remote is wired:

    git remote -v          # expect origin  https://github.com/GeoffreyWeta/iadebayo.git
    git status --short     # anything listed here is NOT on GitHub yet

Then commit and push:

    git add -A
    git commit -m "Site updates before droplet deploy"
    git push origin master

**Check:** `git status` reports a clean tree, and the newest commit shows on
github.com. If `git push` asks for a password, use a Personal Access Token
(GitHub → Settings → Developer settings → Tokens), not your account password.

Two things that deliberately do **not** travel through git — `.gitignore` excludes
them, and that is correct:

| Path | Why it's ignored | How it reaches the droplet |
|---|---|---|
| `.env` | holds DB and mail passwords | typed by hand in Phase 5.4 |
| `/media/` | admin-uploaded photos and applicant videos | `scp` in Phase 5.6 |
| `/staticfiles/` | build output of `collectstatic` | regenerated in Phase 5.5 |

`static/` itself **is** tracked, so committed artwork (`static/img/*.webp`,
`static/js/islands.js`) ships with a normal `git push` — only *uploads* need scp.

### 0.3 Public or private repo?

Check on github.com — the label sits next to the repo name.

- **Public:** nothing to do. The `https://` clone in Phase 5.1 works as written.
- **Private:** the droplet needs its own read-only key. After Phase 2.6, as `deploy`:

      ssh-keygen -t ed25519 -f ~/.ssh/github -N ""
      cat ~/.ssh/github.pub

  Paste that into the repo's **Settings → Deploy keys → Add deploy key** (leave
  *Allow write access* unticked). Then in Phase 5.1 clone the SSH URL instead:

      sudo git clone git@github.com:GeoffreyWeta/iadebayo.git /srv/iadebayo

  A deploy key is scoped to this one repo, so a compromised droplet can't reach
  the rest of your GitHub account the way a personal token could.

---

## Phase 1 — Create the droplet

DigitalOcean control panel → **Create** → **Droplets**:

| Field | Value |
|---|---|
| Region | **London** or **Frankfurt** (lowest latency to Nigeria; DO has no African region) |
| Image | **Ubuntu 24.04 (LTS) x64** |
| Droplet type | **Basic** → **Regular (SSD)** → **$6/mo** (1 GB RAM / 1 vCPU / 25 GB) |
| Authentication | **SSH Key** → *New SSH Key* → paste the key from 0.1 |
| Hostname | `iadebayo-web` |
| Backups | Tick **Enable weekly backups** (+$1.20/mo — worth it) |
| Monitoring | Tick it (free) |

Click **Create Droplet**, wait ~45 seconds, and copy the **public IPv4 address**.
Everywhere below, `YOUR_IP` means that address.

### 1.1 First login

    ssh root@YOUR_IP

Type `yes` at the fingerprint prompt.

**Check:** you get a `root@iadebayo-web:~#` prompt.

---

## Phase 2 — Harden the server

Run these as `root`.

### 2.1 Update packages

    apt update && apt upgrade -y

If it asks about restarting services, accept the defaults. If it says a reboot is
required, run `reboot`, wait a minute, and SSH back in.

### 2.2 Create a non-root user

    adduser deploy                 # set a strong password, press Enter through the rest
    usermod -aG sudo deploy
    rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy

### 2.3 Firewall

    ufw allow OpenSSH
    ufw allow 80/tcp               # http
    ufw allow 443/tcp              # https
    ufw enable                     # answer y

Use the raw port numbers, not `ufw allow 'Nginx Full'`. UFW application profiles
live in `/etc/ufw/applications.d/` and are installed *by* the package that defines
them, so the `Nginx Full` profile does not exist until Phase 3 installs nginx —
running it here fails with `ERROR: Could not find a profile matching 'Nginx Full'`.
`Nginx Full` is only a friendly alias for 80,443/tcp, so opening the ports
directly is equivalent and has no ordering dependency.

The OpenSSH rule goes first deliberately: `ufw enable` warns that it may disrupt
existing SSH connections, and that rule is what makes answering `y` safe.

### 2.4 Swap file (important on a 1 GB droplet)

Without swap, `pip install` and `collectstatic` can get OOM-killed.

    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab

### 2.5 Automatic security updates

    apt install -y unattended-upgrades
    dpkg-reconfigure -plow unattended-upgrades      # choose Yes

### 2.6 Switch to the deploy user

    exit
    ssh deploy@YOUR_IP

**Check:** `whoami` prints `deploy`, and `free -h` shows a 2 GB swap line.
**From here on, every command runs as `deploy` unless it starts with `sudo`.**

---

## Phase 3 — Install the system packages

    sudo apt install -y python3-venv python3-dev build-essential \
        nginx postgresql postgresql-contrib git curl

**Check:**

    python3 --version        # 3.12.x — fine, the project needs 3.10+
    systemctl is-active postgresql nginx     # both print "active"

---

## Phase 4 — Create the database

### 4.1 PostgreSQL role and database

Pick a strong password with **letters and digits only** — the settings file parses
`DATABASE_URL` with `urlparse`, so `@ : / # ?` in a password will break it.

    sudo -u postgres psql

At the `postgres=#` prompt, paste these one block at a time (replace the password):

    CREATE DATABASE iadebayo;
    CREATE USER iadebayo WITH PASSWORD 'ReplaceWithLongRandomPassword123';
    ALTER ROLE iadebayo SET client_encoding TO 'utf8';
    ALTER ROLE iadebayo SET default_transaction_isolation TO 'read committed';
    ALTER ROLE iadebayo SET timezone TO 'Africa/Lagos';
    GRANT ALL PRIVILEGES ON DATABASE iadebayo TO iadebayo;

Then connect to the new database and grant schema rights (**required on
PostgreSQL 15+, which Ubuntu 24.04 ships** — skipping this causes
`permission denied for schema public` during migrate):

    \c iadebayo
    GRANT ALL ON SCHEMA public TO iadebayo;
    \q

> **Simpler alternative:** this is a low-traffic content site, so SQLite would
> genuinely cope. To stay on SQLite, skip Phase 4 entirely and just omit
> `DATABASE_URL` from the `.env` in Phase 5 — `config/settings/base.py` falls back
> to `db.sqlite3` in the project root. You lose concurrent-write safety and easy
> `pg_dump` backups. Postgres is the recommendation.

---

## Phase 5 — Deploy the code

### 5.1 Clone

    sudo mkdir -p /srv
    sudo git clone https://github.com/GeoffreyWeta/iadebayo.git /srv/iadebayo
    sudo chown -R deploy:www-data /srv/iadebayo
    cd /srv/iadebayo

If the repo is private, generate a deploy key instead:
`ssh-keygen -t ed25519 -f ~/.ssh/github -N ""`, add `~/.ssh/github.pub` to the
repo's *Settings → Deploy keys*, then clone the `git@github.com:...` URL.

### 5.2 Virtualenv and dependencies

    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
    .venv/bin/pip install "psycopg2-binary>=2.9"     # skip if you chose SQLite

### 5.3 Generate a secret key

    .venv/bin/python -c "import secrets; print(secrets.token_urlsafe(64))"

Copy the output.

### 5.4 Write the `.env`

    nano /srv/iadebayo/.env

Paste this, filling in the three passwords and the secret key. Note
`DJANGO_SSL_REDIRECT=False` and `YOUR_IP` in ALLOWED_HOSTS — both are
temporary so you can test over plain HTTP before DNS and TLS exist.

    # --- Django core ---
    DJANGO_SECRET_KEY=paste-the-long-random-string-from-5.3
    DJANGO_DEBUG=False
    DJANGO_ALLOWED_HOSTS=iadebayo.foundation,www.iadebayo.foundation,YOUR_IP
    DJANGO_CSRF_TRUSTED_ORIGINS=https://iadebayo.foundation,https://www.iadebayo.foundation
    SITE_BASE_URL=https://www.iadebayo.foundation
    DJANGO_SSL_REDIRECT=False

    # --- Applicant video downloads (nginx serves them; see Phase 7) ---
    X_ACCEL_REDIRECT=True

    # --- Database ---
    DATABASE_URL=postgres://iadebayo:ReplaceWithLongRandomPassword123@127.0.0.1:5432/iadebayo

    # --- Email (reuse your existing mail host — do NOT run a mail server here) ---
    EMAIL_BACKEND=smtp
    EMAIL_HOST=mail.iadebayo.foundation
    EMAIL_PORT=465
    EMAIL_USE_SSL=True
    EMAIL_HOST_USER=noreply@iadebayo.foundation
    EMAIL_HOST_PASSWORD=
    DEFAULT_FROM_EMAIL=IADEBAYO Foundation <noreply@iadebayo.foundation>
    FOUNDATION_NOTIFY_EMAIL=hello@iadebayo.foundation

    # --- reCAPTCHA v2 (forms work without keys; spam protection needs them) ---
    RECAPTCHA_SITE_KEY=
    RECAPTCHA_SECRET_KEY=

    # --- Google Analytics 4 ---
    GA_MEASUREMENT_ID=

    # --- Embark explainer video ---
    EMBARK_INTRO_VIDEO_URL=

Save with `Ctrl+O`, `Enter`, `Ctrl+X`. Then lock it down — it holds your DB and
mail passwords:

    chmod 600 /srv/iadebayo/.env

> Do **not** set `SERVE_MEDIA=True`. Nginx serves `/media/` directly in Phase 7,
> which is faster than routing uploads through Django.

### 5.5 Migrate, collect static, create the admin login

    cd /srv/iadebayo
    .venv/bin/python manage.py migrate
    .venv/bin/python manage.py collectstatic --noinput
    .venv/bin/python manage.py createsuperuser

### 5.6 Content: seed fresh, or bring your existing data across

**Fresh start** (matches what `render-build.sh` does):

    .venv/bin/python manage.py seed_demo
    .venv/bin/python manage.py sync_impact_stats
    .venv/bin/python manage.py load_team
    .venv/bin/python manage.py load_alumni_videos

**Or migrate real content off your current site.** On your **Windows machine**,
in the project folder:

    python manage.py dumpdata --natural-foreign --natural-primary ^
      -e contenttypes -e auth.Permission -e sessions -e admin.logentry ^
      --indent 2 -o data.json

    scp data.json deploy@YOUR_IP:/srv/iadebayo/
    scp -r media deploy@YOUR_IP:/srv/iadebayo/

The `media` copy is not optional if you have uploaded images — `/media/` is in
`.gitignore`, so uploaded photos are **not** in the repo and will 404 otherwise.

Back on the droplet:

    cd /srv/iadebayo
    .venv/bin/python manage.py loaddata data.json
    .venv/bin/python manage.py sync_impact_stats
    rm data.json

### 5.7 Permissions for media uploads

Nginx reads these; Django (as `deploy`) writes to them.

    mkdir -p /srv/iadebayo/media
    chown -R deploy:www-data /srv/iadebayo/media /srv/iadebayo/staticfiles
    chmod -R 775 /srv/iadebayo/media
    chmod 750 /srv/iadebayo

### 5.8 Smoke test

    .venv/bin/python manage.py check --deploy
    .venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000

In a **second** PowerShell window:

    ssh deploy@YOUR_IP "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/"

**Check:** it prints `200`. Go back to the first window and `Ctrl+C` to stop Gunicorn.

---

## Phase 6 — Run Gunicorn as a service

### 6.1 The systemd unit

    sudo nano /etc/systemd/system/iadebayo.service

Paste:

    [Unit]
    Description=IADEBAYO Foundation — Gunicorn
    After=network.target postgresql.service

    [Service]
    User=deploy
    Group=www-data
    WorkingDirectory=/srv/iadebayo
    ExecStart=/srv/iadebayo/.venv/bin/gunicorn \
        --workers 3 \
        --timeout 60 \
        --access-logfile - \
        --error-logfile - \
        --bind 127.0.0.1:8000 \
        config.wsgi:application
    ExecReload=/bin/kill -s HUP $MAINPID
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=multi-user.target

Gunicorn reads `.env` through `config/settings/base.py` (which resolves it from
`BASE_DIR`), so no `EnvironmentFile` is needed.

### 6.2 Start it

    sudo systemctl daemon-reload
    sudo systemctl enable --now iadebayo
    sudo systemctl status iadebayo

**Check:** status shows `active (running)`. If not:
`journalctl -u iadebayo -n 50 --no-pager`.

---

## Phase 7 — Nginx

### 7.1 Site config

    sudo nano /etc/nginx/sites-available/iadebayo

Paste:

    server {
        listen 80;
        server_name iadebayo.foundation www.iadebayo.foundation;

        # Embark applicants upload a one-minute video, capped at 64 MB by
        # submissions/models.py. Anything smaller here and nginx rejects the
        # application with a bare 413 before Django ever sees it.
        client_max_body_size 80M;

        location = /favicon.ico { access_log off; log_not_found off; }

        location /static/ {
            alias /srv/iadebayo/staticfiles/;
            expires 1d;                     # filenames aren't hashed — keep it short
            access_log off;
        }

        # The site's press page lives at /media/ AND uploads are served from
        # /media/ — an exact-match location beats the prefix one below, so the
        # page keeps working. Without this, /media/ is a 403 directory listing.
        location = /media/ {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        location /media/ {
            alias /srv/iadebayo/media/;
            expires 30d;
            access_log off;
        }

        # The public gallery is at /gallery/, NOT /media/ — this prefix belongs to
        # MEDIA_URL. Keep any Django page off it: a request for a bare /media/
        # matches the block above, Nginx tries to list the uploads directory,
        # autoindex is off, and the visitor gets 403 without Django ever seeing it.
        # This exact-match redirect rescues old /media/ links (= beats a prefix
        # match in Nginx, so it does not disturb /media/<file> above).
        location = /media/ {
            return 301 /gallery/;
        }

        # Applicant videos are personal data. Longest-prefix wins, so this
        # blocks them from the public /media/ mapping above — staff download
        # them through /forms/applications/<id>/video/, which checks the login.
        location /media/applications/ {
            return 404;
        }

        # ...and that view redirects the actual transfer back here, so nginx
        # sends the file instead of a Gunicorn worker sitting on it for 60 MB.
        # `internal` means only Django can reach it, never a browser directly.
        location /protected-media/ {
            internal;
            alias /srv/iadebayo/media/;
        }

        location / {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;   # required — settings.py
                                                          # trusts this header
            proxy_redirect off;
        }
    }

### 7.2 Enable and reload

    sudo ln -s /etc/nginx/sites-available/iadebayo /etc/nginx/sites-enabled/
    sudo rm /etc/nginx/sites-enabled/default
    sudo nginx -t
    sudo systemctl reload nginx

**Check:** open `http://YOUR_IP/` in a browser. The site loads with CSS and images.
No styling means `collectstatic` didn't run or the `alias` path is wrong —
`sudo tail -20 /var/log/nginx/error.log`.

---

## Phase 8 — Point Namecheap at the droplet

Log in to Namecheap → **Domain List** → **Manage** next to `iadebayo.foundation`.

### 8.1 Confirm the nameservers

On the **Domain** tab, under *Nameservers*, it should read **Namecheap BasicDNS**
(or PremiumDNS). Leave it that way.

> **Why not DigitalOcean's nameservers?** You can move DNS to DO, but then you must
> manually recreate every MX, SPF, DKIM and TXT record or **email stops working**.
> Keeping DNS at Namecheap and changing only the A records is the low-risk path.

### 8.2 Edit the host records

Go to the **Advanced DNS** tab → *Host Records*.

**Delete** Namecheap's parking defaults if present:
- `CNAME  www  →  parkingpage.namecheap.com.`
- `URL Redirect Record  @  →  http://www.iadebayo.foundation/`
- any existing `A Record` for `@` or `www`

**Add** these two:

| Type | Host | Value | TTL |
|---|---|---|---|
| A Record | `@` | `YOUR_IP` | Automatic |
| A Record | `www` | `YOUR_IP` | Automatic |

**Do not touch** any `MX Record`, or the `TXT` records for SPF/DKIM/DMARC — those
keep your email alive.

Click the green checkmark on each row to save.

### 8.3 Wait for propagation

Usually 5–30 minutes on Namecheap. Check from PowerShell:

    nslookup iadebayo.foundation 8.8.8.8
    nslookup www.iadebayo.foundation 8.8.8.8

**Check:** both return `YOUR_IP`. **Do not start Phase 9 until they do** — Let's
Encrypt validates by connecting to the domain, and a failed run burns rate limit.

---

## Phase 9 — HTTPS

### 9.1 Issue the certificate

    sudo apt install -y certbot python3-certbot-nginx

    sudo certbot --nginx \
      -d iadebayo.foundation -d www.iadebayo.foundation \
      -m hello@iadebayo.foundation --agree-tos --no-eff-email --redirect

Certbot rewrites `/etc/nginx/sites-available/iadebayo` to add the 443 server block
and an HTTP→HTTPS redirect, then reloads Nginx.

### 9.2 Turn Django's own SSL redirect back on

Now that TLS terminates at Nginx, drop the temporary line and the bare IP from
`.env`:

    nano /srv/iadebayo/.env

- Delete the `DJANGO_SSL_REDIRECT=False` line (it defaults to `True` when
  `DEBUG=False`).
- Remove `,YOUR_IP` from `DJANGO_ALLOWED_HOSTS`.

Then:

    sudo systemctl restart iadebayo

### 9.3 Confirm auto-renewal

    sudo certbot renew --dry-run
    systemctl list-timers | grep certbot

**Check:**
- `https://iadebayo.foundation` and `https://www.iadebayo.foundation` both load
  with a padlock.
- `http://iadebayo.foundation` redirects to HTTPS.
- `/admin/` logs you in.
- Open an Embark application that has a video → the **⬇ Download video** button
  saves the file. Opening `https://iadebayo.foundation/media/applications/…`
  directly returns 404 — that's the point.
- The **Media** page at `/media/` loads (not a 403 — see the exact-match block
  in 7.1).
- **Submit a real Embark application with a ~50 MB video.** This is the one form
  that can fail purely on infrastructure: too small a `client_max_body_size` and
  nginx returns a bare `413` before Django sees it.
- Submit one form on the live site and confirm the notification email arrives at
  `hello@iadebayo.foundation`. **Test this, don't assume it** — in production
  `send_mail` runs with `fail_silently=True`, so wrong SMTP credentials lose the
  notification without an error anywhere. The submission itself is still saved to
  the admin, so nothing is lost, but nobody gets told about it.
- `https://iadebayo.foundation/sitemap.xml` renders.

---

## Phase 10 — Optional but recommended

### 10.1 Pick one canonical hostname

`SITE_BASE_URL` in your `.env` is the `www` version, so make `www` canonical for
SEO. Edit the Nginx config:

    sudo nano /etc/nginx/sites-available/iadebayo

Find the `server` block certbot created that listens on 443. Change its
`server_name` to just `www.iadebayo.foundation`, and add a new block:

    server {
        listen 443 ssl;
        server_name iadebayo.foundation;
        ssl_certificate     /etc/letsencrypt/live/iadebayo.foundation/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/iadebayo.foundation/privkey.pem;
        include /etc/letsencrypt/options-ssl-nginx.conf;
        return 301 https://www.iadebayo.foundation$request_uri;
    }

Then `sudo nginx -t && sudo systemctl reload nginx`.

### 10.2 Database backups

    sudo mkdir -p /var/backups/iadebayo && sudo chown deploy:deploy /var/backups/iadebayo
    crontab -e

Add (keeps 14 days of dumps, 03:00 daily):

    0 3 * * * pg_dump "postgres://iadebayo:YOURPASSWORD@127.0.0.1:5432/iadebayo" | gzip > /var/backups/iadebayo/db-$(date +\%F).sql.gz && find /var/backups/iadebayo -name '*.sql.gz' -mtime +14 -delete

Media files are covered by DigitalOcean's weekly droplet backups. To pull a copy
down to your machine:

    scp -r deploy@YOUR_IP:/srv/iadebayo/media ./media-backup

### 10.3 fail2ban

    sudo apt install -y fail2ban
    sudo systemctl enable --now fail2ban

### 10.4 Decommission Render

Once the droplet has served the live domain for a few days without issues, delete
the Render service so you stop paying for it and so nothing accidentally serves a
stale copy. Keep `render.yaml` and `render-build.sh` in the repo — they cost
nothing and document the alternative.

---

## Shipping updates later — automatic deploy on push

`.github/workflows/deploy.yml` runs the tests on every push to `master` and, only
if they pass, SSHes into the droplet and runs `deploy/deploy.sh`. Both files are
in the repo, so the pipeline is version-controlled with the code it ships.

Once the four steps below are done, a release is just:

    git push origin master

Watch it in the repo's **Actions** tab. A red test job means nothing was
deployed — the site keeps running the previous commit.

### 11.1 Give the deploy its own SSH key

Do **not** reuse your personal key. On your Windows machine:

    ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\iadebayo_deploy -C "github-actions" -N '""'

Authorise the public half on the droplet:

    # prints the public key — copy it
    type $env:USERPROFILE\.ssh\iadebayo_deploy.pub

    # on the droplet, as the deploy user
    mkdir -p ~/.ssh && chmod 700 ~/.ssh
    nano ~/.ssh/authorized_keys        # paste the key on its own line
    chmod 600 ~/.ssh/authorized_keys

### 11.2 Let the deploy user restart the service without a password

Without this the deploy hangs at a hidden password prompt and times out.
Confirm where `systemctl` lives first — the path must be exact:

    command -v systemctl journalctl      # expect /usr/bin/...

Then:

    sudo visudo -f /etc/sudoers.d/iadebayo-deploy

Paste (adjust the paths if the previous command disagreed):

    deploy ALL=(root) NOPASSWD: /usr/bin/systemctl restart iadebayo
    deploy ALL=(root) NOPASSWD: /usr/bin/journalctl -u iadebayo -n 40 --no-pager

`visudo` refuses to save a file with a syntax error, which is why it is used
here rather than `nano` — a broken sudoers file locks everyone out of `sudo`.

Check it works, with no password prompt:

    sudo -n systemctl restart iadebayo && echo OK

### 11.3 Add the repository secrets

**Settings → Secrets and variables → Actions → New repository secret:**

| Secret | Value | Required |
|---|---|---|
| `DEPLOY_HOST` | the droplet's IP or hostname | yes |
| `DEPLOY_USER` | `deploy` | yes |
| `DEPLOY_SSH_KEY` | the **entire** private key file, `iadebayo_deploy` — including the `BEGIN`/`END` lines | yes |
| `DEPLOY_KNOWN_HOSTS` | output of `ssh-keyscan -H YOUR_IP` | strongly recommended |
| `DEPLOY_HEALTHCHECK_URL` | `https://iadebayo.foundation/` | recommended |
| `DEPLOY_PORT` | only if SSH is not on 22 | no |

Without `DEPLOY_KNOWN_HOSTS` the workflow falls back to `ssh-keyscan` at run
time and logs a warning: it will work, but the first connection trusts whatever
answers, so a machine-in-the-middle would go unnoticed. Set it.

`DEPLOY_HEALTHCHECK_URL` is what turns "the command exited 0" into "the site is
actually serving pages". If it is unset that step is skipped.

### 11.4 If the GitHub repo is private

Phase 5 clones over HTTPS, which is fine for a public repo. If yours is private,
the droplet needs its own read access or `git fetch` will fail during deploy:

    # on the droplet
    ssh-keygen -t ed25519 -f ~/.ssh/github_readonly -N ""
    cat ~/.ssh/github_readonly.pub

Add that key to the repo under **Settings → Deploy keys** (read-only), point git
at SSH, and confirm:

    cd /srv/iadebayo
    git remote set-url origin git@github.com:GeoffreyWeta/iadebayo.git
    ssh -T git@github.com                  # accept the fingerprint once
    git fetch origin

### What the deploy actually does

`deploy/deploy.sh`, in order: `git reset --hard origin/master` (not `pull` — the
server's tree must match origin exactly, and a pull can stop on a conflict from
someone's quick edit on the box), install requirements, `migrate`,
`collectstatic`, `check --deploy`, restart Gunicorn, then poll
`127.0.0.1:8000` until it returns 200.

The config check runs **before** the restart on purpose: a broken `.env` fails
there, leaving the running workers untouched and the site up.

**There is no automatic rollback.** By the time a restart can fail, the
migrations have already been applied, and checking out older code against a
newer schema is how a bad deploy becomes a bad database. On failure the script
prints the last 40 log lines and the exact command to go back, for you to run
once you have read them.

### Deploying by hand

The workflow pipes the script over SSH rather than running the server's copy —
the `reset --hard` rewrites the working tree, and a script edited while bash is
still reading it fails in confusing ways. Do the same by hand:

    ssh deploy@YOUR_IP 'bash -s' < deploy/deploy.sh

Or use **Actions → CI / Deploy → Run workflow** to redeploy `master` untouched.

### The React islands

If you edited anything under `frontend/src/`, run `npm run build` in `frontend/`
and commit the updated `static/js/islands.js` **before** pushing — the droplet
does not run vite. CI rebuilds the bundle and warns if the committed copy has
drifted, but that check is advisory: vite output is not always byte-identical
across machines, so it reports rather than blocks.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| **502 Bad Gateway** | Gunicorn is down. `sudo systemctl status iadebayo`, then `journalctl -u iadebayo -n 50 --no-pager`. |
| **DisallowedHost** in logs | The hostname isn't in `DJANGO_ALLOWED_HOSTS`. Add it, `sudo systemctl restart iadebayo`. |
| **CSRF verification failed** on a form | `DJANGO_CSRF_TRUSTED_ORIGINS` must list the exact `https://…` origins, and Nginx must send `X-Forwarded-Proto` (Phase 7.1). |
| **Infinite redirect loop** | `SECURE_SSL_REDIRECT` is on but Nginx isn't passing `X-Forwarded-Proto $scheme`. Check the proxy headers. |
| **Site loads unstyled** | `collectstatic` not run, or the `/static/` alias path is wrong. `ls /srv/iadebayo/staticfiles/css/`. |
| **A page under `/media/` returns 403** | `MEDIA_URL` owns that prefix, so Nginx answers before Django and refuses to list the uploads directory. Move the page (the gallery lives at `/gallery/`), or add the `location = /media/` block from Phase 7.1. |
| **Uploaded images 404** | The `media/` folder wasn't copied across (it's gitignored), or `/srv/iadebayo` isn't group-readable by `www-data`. Re-run Phase 5.7. |
| **`413 Request Entity Too Large`** when applying | The applicant's video is bigger than `client_max_body_size`. Raise it in Phase 7.1 and reload nginx. |
| **`/media/` press page is 403 Forbidden** | The exact-match `location = /media/` block is missing, so nginx tried to list the uploads directory. Add it (Phase 7.1). |
| **Forms save but no email arrives** | Wrong SMTP host/password. Production swallows the error — test by hand: `.venv/bin/python manage.py shell -c "from django.core.mail import send_mail; send_mail('t','b',None,['hello@iadebayo.foundation'],fail_silently=False)"` and read the traceback. |
| **Every form says "couldn't verify that you're human"** | `RECAPTCHA_SECRET_KEY` is set but `RECAPTCHA_SITE_KEY` isn't (so no widget renders), or the keys are from different reCAPTCHA sites. Set both, or clear both to disable. |
| **Video download saves a 0-byte file** | `X_ACCEL_REDIRECT=True` but the `internal` `/protected-media/` location is missing from the Nginx config. Add it (Phase 7.1), or set `X_ACCEL_REDIRECT=False` to let Django stream instead. |
| **`permission denied for schema public`** | You skipped the `GRANT ALL ON SCHEMA public` in Phase 4.1. |
| **Certbot: "challenge failed"** | DNS hasn't propagated, or port 80 is closed. Re-check Phase 8.3 and `sudo ufw status`. |
| **Forms send nothing** | `EMAIL_BACKEND=smtp` must be set (it defaults to `console`). Test with `.venv/bin/python manage.py shell -c "from django.core.mail import send_mail; send_mail('test','body',None,['hello@iadebayo.foundation'])"`. |
| **Out of memory during pip/collectstatic** | Swap isn't on. Re-run Phase 2.4, confirm with `free -h`. |

Useful logs:

    journalctl -u iadebayo -f              # application
    sudo tail -f /var/log/nginx/error.log  # web server
