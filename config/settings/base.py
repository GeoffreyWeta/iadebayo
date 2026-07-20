"""
IADEBAYO Foundation website — Django settings.

Environment-driven so the same codebase runs on:
  * local development (SQLite, console email)
  * SmartWeb shared cPanel via "Setup Python App" (MySQL, cPanel SMTP)
  * PythonAnywhere / a VPS (MySQL or Postgres)

Set values in a .env file (see .env.example) or real environment variables.
"""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------- .env loader
def _load_dotenv(path):
    """Tiny dependency-free .env loader (shared hosts hate extra deps)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")

def env(key, default=""):
    return os.environ.get(key, default)

def env_bool(key, default=False):
    return env(key, str(default)).lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------- security
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
CSRF_TRUSTED_ORIGINS = [o for o in env("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o]

# Render sets RENDER_EXTERNAL_HOSTNAME automatically — trust it when present.
_render_host = env("RENDER_EXTERNAL_HOSTNAME")
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", True)
    # Behind a TLS-terminating proxy (Render, most PaaS), trust its header:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    X_FRAME_OPTIONS = "DENY"

# ----------------------------------------------------------------------- apps
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "core",
    "blog",
    "submissions",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.site_meta",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ------------------------------------------------------------------- database
# Default: SQLite (dev). Production: set DB_ENGINE=mysql and the DB_* vars —
# cPanel gives you MySQL databases; create one in cPanel > MySQL Databases.
def _db_from_url(url):
    """Tiny DATABASE_URL parser (postgres:// or mysql://) — no extra deps."""
    from urllib.parse import urlparse
    p = urlparse(url)
    engine = {"postgres": "django.db.backends.postgresql",
              "postgresql": "django.db.backends.postgresql",
              "mysql": "django.db.backends.mysql"}[p.scheme]
    return {"ENGINE": engine, "NAME": p.path.lstrip("/"), "USER": p.username or "",
            "PASSWORD": p.password or "", "HOST": p.hostname or "", "PORT": str(p.port or "")}


if env("DATABASE_URL"):
    DATABASES = {"default": _db_from_url(env("DATABASE_URL"))}
elif env("DB_ENGINE") == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": env("DB_NAME"),
            "USER": env("DB_USER"),
            "PASSWORD": env("DB_PASSWORD"),
            "HOST": env("DB_HOST", "localhost"),
            "PORT": env("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
TIME_ZONE = env("DJANGO_TIME_ZONE", "Africa/Lagos")
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------- static/media
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------- email
# Dev: printed to console. Production (cPanel SMTP): set EMAIL_BACKEND=smtp
# and create a mailbox like noreply@iadebayo.foundation in cPanel > Email.
if env("EMAIL_BACKEND", "console") == "smtp":
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST", "mail.iadebayo.foundation")
    EMAIL_PORT = int(env("EMAIL_PORT", "465"))
    EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", True)
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "IADEBAYO Foundation <noreply@iadebayo.foundation>")
FOUNDATION_NOTIFY_EMAIL = env("FOUNDATION_NOTIFY_EMAIL", "hello@iadebayo.foundation")

# ------------------------------------------------------------------ reCAPTCHA
# Leave keys empty in dev to disable. Get keys: https://www.google.com/recaptcha/admin
RECAPTCHA_SITE_KEY = env("RECAPTCHA_SITE_KEY", "")
RECAPTCHA_SECRET_KEY = env("RECAPTCHA_SECRET_KEY", "")

# Google Analytics 4 — set GA_MEASUREMENT_ID (e.g. G-XXXXXXXXXX) to activate
GA_MEASUREMENT_ID = env("GA_MEASUREMENT_ID", "")

# ----------------------------------------------------------------- site meta
SITE_NAME = "IADEBAYO Foundation"
SITE_BASE_URL = env("SITE_BASE_URL", "https://www.iadebayo.foundation")


# --------------------------------------------------- static serving & media
# WhiteNoise: compressed static files in production
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
# Demo hosts (Render free tier) have no separate media server — let Django
# serve /media/ when SERVE_MEDIA=True. Real production should use the host's
# static/media mapping instead.
SERVE_MEDIA = env_bool("SERVE_MEDIA", False)
