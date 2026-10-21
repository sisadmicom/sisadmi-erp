"""Standard Django runner, independent of historical migration runners."""
from django.conf import settings
from django.test.runner import DiscoverRunner

from .r01_base_guard import reject, require_execution, validate_connections


class R01BaseTestRunner(DiscoverRunner):
    def run_tests(self, test_labels, **kwargs):
        validate_connections(settings.DATABASES, settings.DATABASE_ROUTERS)
        require_execution()
        if not self.keepdb or self.parallel != 1:
            reject()
        return super().run_tests(test_labels, **kwargs)
