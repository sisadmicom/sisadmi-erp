from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from core.testing.r01_guard import validate_connections
from core.testing.runner import MigrationIsolationRunner


class R01TestRunner(MigrationIsolationRunner):
    def run_tests(self, test_labels, **kwargs):
        validate_connections(settings.DATABASES, settings.DATABASE_ROUTERS)
        if not self.keepdb or self.parallel != 1:
            raise ImproperlyConfigured("R-01 requires --keepdb --parallel=1.")
        return super().run_tests(test_labels, **kwargs)
