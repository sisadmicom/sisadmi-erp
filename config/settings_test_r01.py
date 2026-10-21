"""R-01 settings: standalone, no imports or credential fallback from DEV."""
from pathlib import Path
import tempfile
import atexit
import shutil

from django.core.exceptions import ImproperlyConfigured

from core.testing.r01_guard import (
    BOOTSTRAP, ENGINE, HOST, PORT, TEST_DATABASE, USER,
    required_environment, validate_connections,
)

BASE_DIR = Path(__file__).resolve().parent.parent
if required_environment("R01_TEST_DB_HOST") != HOST:
    raise ImproperlyConfigured("R-01 requires the approved loopback host.")
if required_environment("R01_TEST_DB_PORT") != PORT:
    raise ImproperlyConfigured("R-01 requires the approved PostgreSQL port.")
SECRET_KEY = "r01-test-only-not-a-production-secret"
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
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug", "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages",
        "core.context.erp_context",
    ]},
}]
DATABASES = {"default": {
    "ENGINE": ENGINE, "NAME": BOOTSTRAP, "USER": USER,
    "PASSWORD": required_environment("R01_TEST_DB_PASSWORD"),
    "HOST": HOST, "PORT": PORT, "CONN_MAX_AGE": 0, "CONN_HEALTH_CHECKS": False,
    "OPTIONS": {"connect_timeout": 5, "sslmode": "disable"},
    "TEST": {"NAME": TEST_DATABASE, "MIRROR": None, "MIGRATE": True},
}}
DATABASE_ROUTERS = []
validate_connections(DATABASES, DATABASE_ROUTERS)
TEST_RUNNER = "core.testing.r01_runner.R01TestRunner"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
# A private, per-process location: no shared DEV media, certificate or cache paths.
_RUNTIME = Path(tempfile.mkdtemp(prefix="sisadmi-r01-test-"))
atexit.register(shutil.rmtree, _RUNTIME, ignore_errors=True)
MEDIA_ROOT = _RUNTIME / "media"
STATIC_ROOT = _RUNTIME / "static"
SRI_PRIVATE_STORAGE_ROOT = _RUNTIME / "private" / "sri" / "certificates"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
