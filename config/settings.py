from pathlib import Path
from decouple import config
from datetime import timedelta

BASE_DIR  = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost").split(",")

APPEND_SLASH = False

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "drf_spectacular",
    "django_filters",
    "silk"
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.audit"
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "silk.middleware.SilkyMiddleware",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                 "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        }
    }
]

WSGI_APPLICATION = "config.wsgi.application"

# Setting up Redis, Django uses sqlite by default, but I are overriding with Redis as well as for the caching (temporary storage)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB"),
        "USER": config("POSTGRES_USER"),
        "PASSWORD": config("POSTGRES_PASSWORD"),
        "HOST": "postgres",
        "PORT": "5432"
    }
}

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": config("REDIS_URL", default="redis://redis:6379/0"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# setting up celery to save on redis

CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://redis:6379/1")
CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://redis:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# rest framework (for permission, jwt, spectacular(openai), pagination and filter)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
}

# simple JWT config up for token expiration
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# spectacular settings for openai (swagger)
SPECTACULAR_SETTINGS = {
    "TITLE": "TSES Auth Service API",
    "DESCRIPTION": "Email-based OTP authentication service.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
    },
    "COMPONENT_SPLIT_REQUEST": True,
}


# OTP & Rate limiting
OTP_TTL_SECONDS = config("OTP_TTL_SECONDS", default=300, cast=int)

RATE_LIMIT = {
    "EMAIL_MAX": config("OTP_REQUEST_RATE_EMAIL_MAX", default=3, cast=int),
    "EMAIL_WINDOW": config("OTP_REQUEST_RATE_EMAIL_WINDOW", default=600, cast=int),
    "IP_MAX": config("OTP_REQUEST_RATE_IP_MAX", default=10, cast=int),
    "IP_WINDOW": config("OTP_REQUEST_RATE_IP_WINDOW", default=3600, cast=int),
    "FAILED_MAX": config("OTP_REQUEST_RATE_FAILED_MAX", default=5, cast=int),
    "FAILED_WINDOW": config("OTP_REQUEST_RATE_EMAIL_WINDOW", default=900, cast=int),
}



AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "en-US"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
