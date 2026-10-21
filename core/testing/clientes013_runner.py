from django.conf import settings
from django.test import SimpleTestCase
from django.test.runner import DiscoverRunner, iter_test_cases
from core.testing.clientes013_guard import validate_connections, require_execution, reject
from core.testing.clientes013_catalog import scoped_identification_catalog

MODULES = frozenset({
    'people.tests.test_customer_document_restrictions_clientes013',
    'people.tests.test_customer_document_concurrency_clientes013',
    'people.tests.test_customer_category_assignment',
    'people.tests.test_customer_ui_actions',
    'people.tests.test_customer_person_replacement',
})

class Clientes013TestRunner(DiscoverRunner):
    def run_tests(self, test_labels, **kwargs):
        validate_connections(settings.DATABASES, settings.DATABASE_ROUTERS)
        require_execution()
        if not self.keepdb or self.parallel != 1:
            reject()
        with scoped_identification_catalog():
            return super().run_tests(test_labels, **kwargs)

    def build_suite(self, test_labels=None, **kwargs):
        if not test_labels or any(not any(label == module or label.startswith(module+'.')
                for module in MODULES) for label in test_labels):
            reject()  # Reject before importing an unauthorized test module.
        suite = super().build_suite(test_labels, **kwargs)
        for case in iter_test_cases(suite):
            if (type(case).__module__ not in MODULES or not isinstance(case, SimpleTestCase)
                    or getattr(case, 'serialized_rollback', False)
                    or getattr(case, 'available_apps', None) is not None
                    or getattr(case, 'databases', set()) not in (set(), {'default'})):
                reject()
        return suite
