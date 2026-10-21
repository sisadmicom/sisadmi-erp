"""Runner Django con bloques históricos explícitos de Customer y Supplier."""
import sys
import unittest

from django.db import connections
from django.test.runner import DiscoverRunner, iter_test_cases

from .migration_isolation import MigrationIsolationError, customer_migration_state, supplier_migration_state

SUPPLIER_CLASS = "people.tests.test_supplier_company_cat022b_red.SupplierMigrationRedTests"

ISOLATED_CLASSES = frozenset({
    "people.tests.test_customer_company_cat022a_red.CustomerLegacyMigrationRedTests",
    "people.tests.test_customer_company_green.CustomerCompanyGreenTests",
    SUPPLIER_CLASS,
})


class MigrationIsolatedSuite(unittest.TestSuite):
    def __init__(self, groups):
        super().__init__()
        self.groups = groups

    def __iter__(self):
        for _, cases in self.groups:
            yield from cases

    def run(self, result, debug=False):
        # Cada suite interna termina teardown de clase/módulo antes de retornar.
        # No sustituimos TestCase, TransactionTestCase, fixtures ni aserciones.
        for isolated, cases in self.groups:
            if result.shouldStop:
                break
            try:
                if isolated:
                    scope = supplier_migration_state if isolated == SUPPLIER_CLASS else customer_migration_state
                    with scope(connections["default"]):
                        unittest.TestSuite(cases).run(result, debug=debug)
                else:
                    unittest.TestSuite(cases).run(result, debug=debug)
            finally:
                result._previousTestClass = None
        return result


class MigrationIsolationRunner(DiscoverRunner):
    def build_suite(self, *args, **kwargs):
        requested_parallel = self.parallel
        suite = super().build_suite(*args, **kwargs)
        cases = list(iter_test_cases(suite))
        selected = [case for case in cases if
                    f"{type(case).__module__}.{type(case).__name__}" in ISOLATED_CLASSES]
        if not selected:
            return suite
        if requested_parallel > 1:
            raise MigrationIsolationError("Las clases históricas Customer requieren --parallel=1; aislamiento paralelo no autorizado.")
        # Dividir suites puede repetir fixtures de módulo. No aceptar esa
        # semántica si se añaden fixtures de módulo a estos contratos congelados.
        for case in selected:
            module = sys.modules[type(case).__module__]
            if getattr(module, "setUpModule", None) or getattr(module, "tearDownModule", None):
                raise MigrationIsolationError("Fixtures de módulo requieren una estrategia de aislamiento explícita.")
        groups = []
        for case in cases:
            name = f"{type(case).__module__}.{type(case).__name__}"
            isolated = name if name in ISOLATED_CLASSES else None
            if groups and groups[-1][0] == isolated:
                groups[-1][1].append(case)
            else:
                groups.append((isolated, [case]))
        return MigrationIsolatedSuite(groups)
