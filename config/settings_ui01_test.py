"""Browser review against the existing TEST database; never inherits DEV settings."""
from config.settings_test_r01 import *  # noqa: F403
from core.testing.r01_guard import TEST_DATABASE, validate_connections

DATABASES["default"]["NAME"] = TEST_DATABASE  # noqa: F405
validate_connections(DATABASES, DATABASE_ROUTERS)  # noqa: F405
# Local development server only: enables Django's existing staticfile handling.
DEBUG = True
