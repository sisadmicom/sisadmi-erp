from django.db.backends.postgresql.base import DatabaseWrapper as PostgreSQLWrapper
from core.testing.clientes013_guard import validate_database, require_execution, verify_identity, reject
from .creation import DatabaseCreation

class DatabaseWrapper(PostgreSQLWrapper):
    creation_class = DatabaseCreation

    def get_connection_params(self):
        validate_database(self.settings_dict, self.alias)
        return super().get_connection_params()

    def get_new_connection(self, params):
        validate_database(self.settings_dict, self.alias)
        require_execution()
        allowed = {'dbname','user','password','host','port','connect_timeout','sslmode',
                   'client_encoding','context','cursor_factory','prepare_threshold'}
        if (set(params)-allowed or any(params.get(k) != self.settings_dict[v]
                for k,v in [('dbname','NAME'),('user','USER'),('password','PASSWORD'),('host','HOST')])
                or str(params.get('port')) != '5432' or params.get('sslmode') != 'disable'
                or params.get('connect_timeout') != 5):
            reject()
        raw = super().get_new_connection({**params, 'options': ''})
        try:
            with raw.cursor() as cursor:
                verify_identity(cursor)
            raw.rollback()
        except BaseException:
            raw.close()
            raise
        return raw

    def _nodb_cursor(self):
        reject()  # No administrative/bootstrap connection is permitted.
