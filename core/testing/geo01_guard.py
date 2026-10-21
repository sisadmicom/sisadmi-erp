"""GEO-01 connection policy. No environment values or passwords in errors."""
import os

from django.core.exceptions import ImproperlyConfigured

ENGINE = "core.testing.geo01_postgresql"
USER = "sisadmi_erp_test_runner"
BOOTSTRAP = "sisadmi_erp_test_bootstrap"
TEST_DATABASE = "test_sisadmi_geo01"
HOST = "127.0.0.1"
PORT = "5432"


def required_environment(name):
    value = os.environ.get(name)
    if not value or value != value.strip() or any(c in value for c in "\x00\n\r"):
        raise ImproperlyConfigured(f"GEO-01 requires a valid {name}.")
    return value


def validate_database(database, alias="default", *, maintenance=False):
    allowed_names = {BOOTSTRAP} if maintenance else {BOOTSTRAP, TEST_DATABASE}
    auxiliary = False
    allowed_alias = alias == ("__no_db__" if maintenance else "default") or auxiliary
    if (
        not allowed_alias
        or (auxiliary and database.get("NAME") != TEST_DATABASE)
        or database.get("ENGINE") != ENGINE
        or database.get("NAME") not in allowed_names
        or database.get("USER") != USER
        or database.get("HOST") != HOST
        or str(database.get("PORT")) != PORT
        or not database.get("PASSWORD")
        or database.get("CONN_MAX_AGE", 0) != 0
        or database.get("CONN_HEALTH_CHECKS", False)
        or database.get("OPTIONS", {}) != {"connect_timeout": 5, "sslmode": "disable"}
        or database.get("TEST", {}).get("NAME") != TEST_DATABASE
        or database.get("TEST", {}).get("MIRROR")
        or database.get("TEST", {}).get("MIGRATE", True) is not True
    ):
        raise ImproperlyConfigured("GEO-01 rejected the database destination or options.")


def require_admin_verification():
    if any(name.startswith("PG") for name in os.environ):
        raise ImproperlyConfigured("GEO-01 rejects inherited libpq environment options.")
    # Operator acknowledgment, NOT independent proof of server-side privileges.
    if os.environ.get("R01_TEST_ADMIN_VERIFIED") != "1":
        raise ImproperlyConfigured(
            "GEO-01 connection blocked: manual role/database/HBA verification is pending."
        )


def validate_connections(databases, routers):
    if set(databases) != {"default"} or routers:
        raise ImproperlyConfigured("GEO-01 requires one default alias and no routers.")
    validate_database(databases["default"])
