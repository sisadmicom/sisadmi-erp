"""Closed PostgreSQL destination policy for the disposable R-01 Base only."""
import ipaddress
import os

from django.core.exceptions import ImproperlyConfigured

DATABASE = "test_sisadmi_r01"
ENGINE = "core.testing.r01_base_postgresql"
USER = "sisadmi_erp_test_runner"
HOST = "127.0.0.1"
PORT = "5432"
OPTIONS = {"connect_timeout": 5, "sslmode": "disable"}


def reject():
    # Never interpolate connection parameters, credentials or server responses.
    raise ImproperlyConfigured("R-01 Base rejected configuration, identity or execution authorization.")


def password():
    value = os.environ.get("R01_BASE_TEST_DB_PASSWORD")
    if not value or any(c in value for c in "\x00\n\r"):
        reject()
    return value


def require_execution():
    if (os.environ.get("R01_BASE_ALLOW_TEST_EXECUTION") != "1"
            or any(k.startswith("PG") for k in os.environ)):
        reject()


def validate_database(cfg, alias="default"):
    test = cfg.get("TEST", {})
    if (alias != "default" or cfg.get("ENGINE") != ENGINE
            or cfg.get("NAME") != DATABASE or test.get("NAME") != DATABASE
            or cfg.get("USER") != USER or cfg.get("HOST") != HOST
            or str(cfg.get("PORT")) != PORT or not cfg.get("PASSWORD")
            or cfg.get("CONN_MAX_AGE", 0) != 0 or cfg.get("CONN_HEALTH_CHECKS", False)
            or cfg.get("OPTIONS") != OPTIONS or test.get("MIRROR")
            or test.get("MIGRATE", True) is not True or test.get("DEPENDENCIES")
            or test.get("TEMPLATE") or test.get("CHARSET") or test.get("COLLATION")
            or cfg.get("SERVICE") or cfg.get("DISABLE_SERVER_SIDE_CURSORS", False)):
        reject()


def validate_connections(databases, routers):
    if set(databases) != {"default"} or routers:
        reject()
    validate_database(databases["default"])


def verify_identity(cursor):
    cursor.execute("SELECT current_database(), session_user, current_user, inet_server_addr()::text, inet_server_port()")
    row = cursor.fetchone()
    if not row or len(row) != 5 or row[:3] != (DATABASE, USER, USER) or row[4] != int(PORT):
        reject()
    try:
        address = ipaddress.ip_interface(row[3]).ip
    except (ValueError, TypeError):
        reject()
    if str(address) != HOST:
        reject()
    cursor.execute("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()")
    if cursor.fetchone() != (USER,):
        reject()
    cursor.execute("SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname=current_user")
    if cursor.fetchone() != (False,) * 5:
        reject()
    cursor.execute("SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=current_user")
    if cursor.fetchone() is not None:
        reject()
    cursor.execute("SELECT has_database_privilege(current_user,current_database(),'CONNECT'), has_schema_privilege(current_user,'public','CREATE')")
    if cursor.fetchone() != (True, True):
        reject()
