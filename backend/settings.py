"""
Django settings for backend project.
"""

import os
from pathlib import Path

import dj_database_url  # pip install dj-database-url

BASE_DIR = Path(__file__).resolve().parent.parent

# =========================
# Security / env
# =========================
# Op Render zet je SECRET_KEY als environment variable.
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-secret")

# Op Render: DEBUG=False
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

# ALLOWED_HOSTS: op Render zet je dit als env var, comma-separated
# Voorbeeld value: "uitjes-backend.onrender.com"
_allowed_hosts = os.environ.get("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts.split(",") if h.strip()]

# Handig voor lokaal als je niks zet:
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["*"]

# Voor proxy/https op platforms zoals Render
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# =========================
# Application definition
# =========================
INSTALLED_APPS = [
    # Django core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",

    # DRF
    "rest_framework",
    "rest_framework.authtoken",

    # Third-party
    "corsheaders",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "dj_rest_auth",
    "dj_rest_auth.registration",

    # Your app
    "events",
]

SITE_ID = 1

MIDDLEWARE = [
    # CORS moet zo hoog mogelijk, vóór CommonMiddleware
    "corsheaders.middleware.CorsMiddleware",

    "django.middleware.security.SecurityMiddleware",

    # WhiteNoise voor static files (admin e.d.) op Render
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "allauth.account.middleware.AccountMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"
WSGI_APPLICATION = "backend.wsgi.application"

# =========================
# Auth / redirects (lokaal vs prod)
# =========================
SOCIALACCOUNT_LOGIN_ON_GET = True

# Voor productie kun je dit sturen via env var:
# RENDER/PROD: zet bijv. https://uitjes-frontend.pages.dev
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")

LOGIN_REDIRECT_URL = FRONTEND_ORIGIN + "/"
LOGOUT_REDIRECT_URL = FRONTEND_ORIGIN + "/"

# =========================
# CORS + CSRF (voor cookie-based auth)
# =========================
# Alleen je API routes CORS-en (aanrader)
CORS_URLS_REGEX = r"^/api/.*$"

# Lokaal + production origin toestaan
# Tip: voeg later preview origins toe als je wilt
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://uitjes-frontend.pages.dev",
]

# Als je cookie-based auth gebruikt tussen frontend en backend:
CORS_ALLOW_CREDENTIALS = True

CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.uitjes-frontend\.pages\.dev$",
]
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "https://uitjes-frontend.pages.dev",
]

# Cookies: voor local dev is Lax ok.
# Als je cross-site cookies (Pages -> Render) echt gaat gebruiken, moet dit naar "None" + Secure.
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")

# Als je later cookies cross-site nodig hebt, zet je op Render:
# SESSION_COOKIE_SAMESITE=None
# CSRF_COOKIE_SAMESITE=None
# SESSION_COOKIE_SECURE=True
# CSRF_COOKIE_SECURE=True

# =========================
# DRF settings
# =========================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
}
REST_USE_JWT = False

# =========================
# Templates
# =========================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# =========================
# Database (Render Postgres via DATABASE_URL)
# =========================
# Lokaal kun je sqlite houden, maar op Render zet je DATABASE_URL env var.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        ssl_require=not DEBUG,
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# =========================
# Password validation
# =========================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# =========================
# Internationalization
# =========================
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Amsterdam"
USE_I18N = True
USE_TZ = True

# =========================
# Static files (WhiteNoise)
# =========================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    }
}