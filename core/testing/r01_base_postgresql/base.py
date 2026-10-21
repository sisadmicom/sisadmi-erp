"""Validate before connecting, and attest every new physical connection."""
from django.db.backends.postgresql.base import DatabaseWrapper as PostgreSQLWrapper

from core.testing.r01_base_guard import (
    OPTIONS, reject, require_execution, validate_database, verify_identity,
)
from .creation import DatabaseCreation


class DatabaseWrapper(PostgreSQLWrapper):
    creation_class = DatabaseCreation

    def get_connection_params(self):
        validate_database(self.settings_dict, self.alias)
        require_execution()
        return super().get_connection_params()

    def get_new_connection(self, params):
        validate_database(self.settings_dict, self.alias)
        require_execution()
        allowed = {"dbname", "user", "password", "host", "port", "connect_timeout",
                   "sslmode", "client_encoding", "context", "cursor_factory", "prepare_threshold"}
        if (set(params) - allowed
                or any(params.get(k) != self.settings_dict[v] for k, v in (
                    ("dbname", "NAME"), ("user", "USER"), ("password", "PASSWORD"), ("host", "HOST")))
                or str(params.get("port")) != str(self.settings_dict["PORT"])
                or any(params.get(k) != v for k, v in OPTIONS.items())):
            reject()
        raw = super().get_new_connection({**params, "options": ""})
        try:
            with raw.cursor() as cursor:
                verify_identity(cursor)
            # End the read-only identity queries before Django initializes state.
            raw.rollback()
        except BaseException:
            raw.close()
            raise
        return raw

    def _nodb_cursor(self):
        reject()  # No bootstrap, postgres or first-connection fallback.
