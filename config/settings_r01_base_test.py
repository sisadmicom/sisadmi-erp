"""Standalone disposable TEST settings. No historical or DEV settings imports."""
from pathlib import Path
import tempfile
import uuid

from core.testing.r01_base_guard import (
    DATABASE, ENGINE, HOST, OPTIONS, PORT, USER, password, validate_connections,
)

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = "r01-base-tests-only-not-a-production-secret"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "core", "people", "users", "catalog", "inventory", "purchases", "sales", "sri",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "core.middleware.ERPContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
LOGIN_URL = "login"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True, "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug", "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages",
        "core.context.erp_context",
    ]}}]
DATABASES = {"default": {
    "ENGINE": ENGINE, "NAME": DATABASE, "USER": USER, "PASSWORD": password(),
    "HOST": HOST, "PORT": PORT, "CONN_MAX_AGE": 0, "CONN_HEALTH_CHECKS": False,
    "OPTIONS": dict(OPTIONS),
    "TEST": {"NAME": DATABASE, "MIRROR": None, "MIGRATE": True},
}}
DATABASE_ROUTERS = []
validate_connections(DATABASES, DATABASE_ROUTERS)
TEST_RUNNER = "core.testing.r01_base_runner.R01BaseTestRunner"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
# Reserve unique auxiliary paths without creating files/directories at import.
# Any future runtime files belong only to this invocation; retain for diagnosis
# until the operator authorizes removal of the specific directory.
_RUNTIME = Path(tempfile.gettempdir()) / ("sisadmi-r01-base-" + uuid.uuid4().hex)
MEDIA_ROOT = _RUNTIME / "media"
STATIC_ROOT = _RUNTIME / "static"
SRI_PRIVATE_STORAGE_ROOT = _RUNTIME / "private" / "sri" / "certificates"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Preserve all six microsecond digits in the isolated Django snapshot.
SERIALIZATION_MODULES = {"json": "core.testing.r01_base_json"}
