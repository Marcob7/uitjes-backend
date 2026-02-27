"""
Django settings for backend project.
"""

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# =========================
# Security / env
# =========================
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-secret")

DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

# ALLOWED_HOSTS (Render: "uitjes-backend.onrender.com" of "uitjes-backend.onrender.com,localhost,127.0.0.1")
_allowed_hosts = os.environ.get("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts.split(",") if h.strip()]
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["*"]

# Default primary key warnings fix
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

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
    # CORS moet helemaal bovenaan, vóór CommonMiddleware
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
# Render / proxy / https
# =========================
# Render draait achter een proxy (Cloudflare/Render). Hiermee snapt Django dat requests "https" zijn.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
# Allauth gebruikt dit om de juiste https callback/redirect urls te bouwen
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"

# (optioneel, maar vaak handig)
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "False").lower() == "true"

# =========================
# Frontend origin + redirects
# =========================
# Render/PROD: FRONTEND_ORIGIN="https://uitjes-frontend.pages.dev"
# Lokaal: default = http://localhost:3000
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000").rstrip("/")

LOGIN_REDIRECT_URL = f"{FRONTEND_ORIGIN}/"
LOGOUT_REDIRECT_URL = f"{FRONTEND_ORIGIN}/"

SOCIALACCOUNT_LOGIN_ON_GET = True

# =========================
# CORS + CSRF
# =========================
# Alleen API endpoints CORS geven (netter)
CORS_URLS_REGEX = r"^/api/.*$"

# Beste aanpak: neem FRONTEND_ORIGIN als bron van waarheid.
# Je mag localhost er hard bij zetten zodat lokaal altijd werkt.
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
]
if FRONTEND_ORIGIN.startswith("http"):
    # voorkom dubbele entry
    if FRONTEND_ORIGIN not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(FRONTEND_ORIGIN)

CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
]
if FRONTEND_ORIGIN.startswith("http"):
    if FRONTEND_ORIGIN not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(FRONTEND_ORIGIN)

# =========================
# Cookies (Pages ↔ Render)
# =========================
# Lokaal is Lax prima.
# Voor cross-site cookies (frontend.pages.dev -> backend.onrender.com) moet SameSite=None + Secure=True.
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")

SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "False").lower() == "true"
CSRF_COOKIE_SECURE = os.environ.get("CSRF_COOKIE_SECURE", "False").lower() == "true"

# Aanrader op Render als je auth via cookies wil:
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
    # Events wil je public: AllowAny is prima, en voor protected endpoints zet je per-view permissions.
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
# Database
# =========================
# Render: DATABASE_URL env var (postgres)
# Lokaal: sqlite fallback
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        ssl_require=not DEBUG,
    )
}

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