"""Django prepares only a manually precreated disposable DB; never creates/drops it."""
from django.conf import settings
from django.core.management import call_command
from django.db.backends.postgresql.creation import DatabaseCreation as PostgreSQLCreation
from core.testing.clientes013_guard import DATABASE, reject, require_execution, validate_database, verify_identity

class DatabaseCreation(PostgreSQLCreation):
    def create_test_db(self, verbosity=1, autoclobber=False, serialize=None, keepdb=False):
        validate_database(self.connection.settings_dict, self.connection.alias)
        require_execution()
        if not keepdb or settings.DATABASES['default']['NAME'] != DATABASE:
            reject()
        with self.connection.cursor() as cursor:
            verify_identity(cursor)
        call_command('migrate', database=self.connection.alias, verbosity=max(verbosity-1,0),
                     interactive=False, run_syncdb=True)
        return DATABASE

    def _execute_create_test_db(self, *args, **kwargs): reject()
    def _destroy_test_db(self, *args, **kwargs): reject()
    def _clone_test_db(self, *args, **kwargs): reject()

    def destroy_test_db(self, old_database_name=None, verbosity=1, keepdb=False, suffix=None):
        validate_database(self.connection.settings_dict, self.connection.alias)
        if not keepdb or suffix or old_database_name not in (None, DATABASE):
            reject()
        self.connection.close()
