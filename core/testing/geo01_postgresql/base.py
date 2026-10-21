from contextlib import contextmanager

from django.db.backends.postgresql.base import DatabaseWrapper as PostgreSQLWrapper
from django.core.exceptions import ImproperlyConfigured

from core.testing.geo01_guard import (
    BOOTSTRAP, HOST, PORT, TEST_DATABASE, USER,
    require_admin_verification, validate_database,
)
from .creation import DatabaseCreation


class DatabaseWrapper(PostgreSQLWrapper):
    creation_class = DatabaseCreation

    def get_connection_params(self):
        validate_database(
            self.settings_dict, self.alias, maintenance=self.alias == "__no_db__"
        )
        return super().get_connection_params()

    def get_new_connection(self, conn_params):
        validate_database(
            self.settings_dict, self.alias, maintenance=self.alias == "__no_db__"
        )
        expected_name = self.settings_dict["NAME"]
        allowed = {
            "dbname", "user", "password", "host", "port", "connect_timeout",
            "sslmode", "client_encoding", "context", "cursor_factory", "prepare_threshold",
        }
        if (
            set(conn_params) - allowed
            or conn_params.get("dbname") != expected_name
            or conn_params.get("user") != USER
            or conn_params.get("host") != HOST
            or str(conn_params.get("port")) != PORT
            or conn_params.get("password") != self.settings_dict["PASSWORD"]
            or conn_params.get("sslmode") != "disable"
            or conn_params.get("connect_timeout") != 5
        ):
            raise ImproperlyConfigured("GEO-01 rejected connection parameter overrides.")
        require_admin_verification()
        # libpq inherits PGOPTIONS unless explicitly overridden. Administrative
        # and bootstrap connections must never write business/schema data.
        params = {**conn_params, "options": ""}
        if expected_name == BOOTSTRAP:
            params["options"] = "-c default_transaction_read_only=on"
        return super().get_new_connection(params)

    @contextmanager
    def _nodb_cursor(self):
        # No fallback to the first configured PostgreSQL connection.
        connection = self.__class__(
            {**self.settings_dict, "NAME": BOOTSTRAP}, alias="__no_db__"
        )
        try:
            with connection.cursor() as cursor:
                yield cursor
        finally:
            connection.close()
