from django.core.exceptions import ImproperlyConfigured
from django.db.backends.postgresql.creation import DatabaseCreation as PostgreSQLCreation

from core.testing.geo01_guard import TEST_DATABASE, USER


class DatabaseCreation(PostgreSQLCreation):
    def _execute_create_test_db(self, cursor, parameters, keepdb=False):
        if not keepdb or parameters["dbname"].strip('"') != TEST_DATABASE:
            raise ImproperlyConfigured("GEO-01 requires the precreated TEST database and --keepdb.")
        cursor.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s",
            [TEST_DATABASE],
        )
        row = cursor.fetchone()
        if row != (USER,):
            raise ImproperlyConfigured("GEO-01 TEST database missing or owned by another role.")
        cursor.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
            "FROM pg_roles WHERE rolname = %s", [USER],
        )
        if cursor.fetchone() != (False, False, False, False, False):
            raise ImproperlyConfigured("GEO-01 TEST role has unexpected privileges.")
        cursor.execute(
            "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member "
            "WHERE r.rolname=%s", [USER],
        )
        if cursor.fetchone() is not None:
            raise ImproperlyConfigured("GEO-01 TEST role must not inherit other roles.")
        # Deliberately no CREATE DATABASE, DROP DATABASE, or super() call.

    def _destroy_test_db(self, test_database_name, verbosity):
        raise ImproperlyConfigured("GEO-01 never drops databases; use --keepdb.")

    def _clone_test_db(self, suffix, verbosity, keepdb=False):
        raise ImproperlyConfigured("GEO-01 requires --parallel=1; cloning is disabled.")
