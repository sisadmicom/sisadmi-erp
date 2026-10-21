"""Run unchanged GEO-01 tests only in the separate precreated database."""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase
from django.test.runner import DiscoverRunner, iter_test_cases
from core.testing.geo01_guard import validate_connections

MODULES = frozenset({
    "people.tests.test_geo01_import", "people.tests.test_geo01_decisions",
    "people.tests.test_geo01_partial", "people.tests.test_geo01_plan_comparison",
})

class Geo01TestRunner(DiscoverRunner):
    def run_tests(self, test_labels, **kwargs):
        validate_connections(settings.DATABASES, settings.DATABASE_ROUTERS)
        if not self.keepdb or self.parallel != 1:
            raise ImproperlyConfigured("GEO-01 requires --keepdb --parallel=1.")
        return super().run_tests(test_labels, **kwargs)

    def build_suite(self, *args, **kwargs):
        suite = super().build_suite(*args, **kwargs)
        for case in iter_test_cases(suite):
            if (type(case).__module__ not in MODULES or
                    not isinstance(case, SimpleTestCase) or
                    (getattr(case, "databases", set()) and not isinstance(case, TestCase)) or
                    getattr(case, "serialized_rollback", False)):
                raise ImproperlyConfigured("Only GEO-01 rollback-safe test cases are permitted.")
        return suite
