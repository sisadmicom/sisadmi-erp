"""GEO-01 regression only: never uses the populated TEST database."""
from config.settings_test_r01 import *  # Reuse standalone TEST configuration, never DEV.
from core.testing.geo01_guard import ENGINE, TEST_DATABASE, validate_connections

DATABASES = {"default": {**DATABASES["default"], "ENGINE": ENGINE,
    "TEST": {"NAME": TEST_DATABASE, "MIRROR": None, "MIGRATE": True}}}
validate_connections(DATABASES, DATABASE_ROUTERS)
TEST_RUNNER = "core.testing.geo01_runner.Geo01TestRunner"
