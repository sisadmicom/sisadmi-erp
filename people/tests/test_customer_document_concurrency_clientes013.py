"""Real committed fixtures, independent thread-local connections, observed waits."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import connections, transaction, OperationalError
from django.test import TransactionTestCase
from core.models import Company
from people.models import Customer, Person
from people.services import customer_maintenance
from sales.models import Sale
from people.tests.clientes013_support import CustomerDocumentFixture, business_snapshot


class RollbackFirst(Exception):
    pass


class CustomerDocumentConcurrencyTests(CustomerDocumentFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.release = Event()
        self.locked = Event()
        self.states = []
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='clientes013')
        self.addCleanup(self.cleanup_workers)
        self.lock_evidence = []

    def cleanup_workers(self):
        self.release.set()
        try:
            for state in self.states:
                state['future'].result(timeout=15)
        finally:
            self.pool.shutdown(wait=True)
        for state in self.states:
            self.assertTrue(state['closed'])
            self.assertFalse(state['atomic_after'])
            if state.get('error') is not None and not state.get('checked'):
                raise state['error']

    def action(self, name):
        actor = get_user_model().objects.get(pk=self.actor.pk)
        company = Company.objects.get(pk=self.company.pk)
        if name == 'sale': return self.sale().pk
        if name == 'delete':
            customer_maintenance.delete(actor=actor, company=company, relation_id=self.customer.pk)
            return self.customer.pk
        person_id = self.replacement.pk if name == 'replace' else self.second.pk
        return customer_maintenance.update(actor=actor, company=company,
            relation_id=self.customer.pk, data={'person': person_id}).pk

    def worker(self, name, *, first=False, rollback=False, timeout=False):
        state = {'ready': Event(), 'done': Event(), 'pid': None, 'error': None,
                 'result': None, 'closed': False, 'atomic_after': None, 'checked': False}
        def run():
            db = connections['default']  # unique wrapper for this thread
            try:
                with db.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid(),current_database()')
                    state['pid'], database = cursor.fetchone()
                    self.assertEqual(database, 'test_sisadmi_clientes013')
                    cursor.execute("SELECT set_config('lock_timeout',%s,false)", ['1000ms' if timeout else '5s'])
                    cursor.execute("SELECT set_config('statement_timeout','8s',false)")
                state['ready'].set()
                gated = False
                def observe(execute, sql, params, many, context):
                    nonlocal gated
                    diagnostic = getattr(self, 'diagnostic', None)
                    result = (diagnostic.execute(name, execute, sql, params, many, context)
                              if diagnostic else execute(sql, params, many, context))
                    normalized = sql.lower()
                    if first and not gated and 'select' in normalized and 'for update' in normalized and '"people_customer"' in normalized:
                        gated = True
                        self.locked.set()
                        if not self.release.wait(10): raise RuntimeError('Holder release deadline expired')
                    return result
                try:
                    with db.execute_wrapper(observe), transaction.atomic():
                        diagnostic = getattr(self, 'diagnostic', None)
                        if diagnostic: diagnostic.identity(db, name)
                        state['result'] = self.action(name)
                        if first:
                            self.assertTrue(gated, 'Service did not acquire the Customer lock')
                        if rollback: raise RollbackFirst()
                    diagnostic = getattr(self, 'diagnostic', None)
                    if diagnostic: diagnostic.record('transaction_commit_returned', worker=name, result_id=state['result'])
                except RollbackFirst:
                    if not rollback: raise
            except BaseException as error:
                state['error'] = error
                diagnostic = getattr(self, 'diagnostic', None)
                if diagnostic:
                    import traceback
                    diagnostic.record('worker_error', worker=name, exception_type=type(error).__name__, traceback=traceback.format_exc())
            finally:
                state['ready'].set()
                state['atomic_after'] = db.in_atomic_block
                db.close(); state['closed'] = db.connection is None
                state['done'].set()
        state['future'] = self.pool.submit(run)
        self.states.append(state)
        self.assertTrue(state['ready'].wait(10))
        if state['pid'] is None:
            state['checked'] = True
            raise state['error'] or RuntimeError('Worker did not establish identity')
        return state

    def race(self, first_action, second_action, *, rollback=False, timeout=False):
        first = self.worker(first_action, first=True, rollback=rollback)
        deadline = monotonic()+8
        while not self.locked.is_set():
            if first['done'].is_set():
                first['checked'] = True
                raise first['error'] or AssertionError('Missing holder lock')
            self.assertLess(monotonic(), deadline)
            self.locked.wait(.01)  # bounded event wait, never an assumed lock delay
        second = self.worker(second_action, timeout=timeout)
        try:
            self.assertNotEqual(first['pid'], second['pid'])
            observed = False
            deadline = monotonic()+6
            while monotonic() < deadline:
                with connections['default'].cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid(), pg_blocking_pids(%s)', [second['pid']])
                    observer, blockers = cursor.fetchone()
                self.assertNotIn(observer, [first['pid'], second['pid']])
                if first['pid'] in blockers:
                    self.lock_evidence.append((second['pid'], first['pid']))
                    diagnostic = getattr(self, 'diagnostic', None)
                    if diagnostic: diagnostic.record('blocking_edge', observer_pid=observer, waiter_pid=second['pid'], holder_pid=first['pid'], blockers=blockers)
                    observed = True; break
                if second['done'].wait(.01): break
            self.assertTrue(observed, 'Expected blocking edge was not observed')
            if timeout:self.assertTrue(second['done'].wait(5))
            # The gate is after the Customer SELECT FOR UPDATE but before its
            # service performs business writes. The waiter must not insert early.
            self.assertFalse(Sale.objects.exists())
            self.assertEqual(Customer.objects.get(pk=self.customer.pk).person_id, self.original.pk)
        finally:
            diagnostic = getattr(self, 'diagnostic', None)
            if diagnostic: diagnostic.record('holder_release_requested')
            self.release.set()
        for state in [first, second]:
            self.assertTrue(state['done'].wait(12))
            state['future'].result(timeout=1)
            self.assertTrue(state['closed']); self.assertFalse(state['atomic_after'])
        first['checked'] = True
        if first['error'] is not None: raise first['error']
        return second

    def success(self, state):
        state['checked'] = True
        if state['error'] is not None: raise state['error']

    def domain_error(self, state, *, code=None, field=None, missing=False):
        state['checked'] = True
        if missing:
            self.assertIsInstance(state['error'], ObjectDoesNotExist)
        else:
            self.assertIsInstance(state['error'], ValidationError)
            actual = state['error'].error_dict[field][0].code if field else state['error'].code
            self.assertEqual(actual, code)

    def test_sale_first_replacement_waits_then_rejects(self):
        state = self.race('sale', 'replace')
        self.domain_error(state, code='person_has_documents', field='person')
        self.customer.refresh_from_db(); self.assertEqual(self.customer.person_id, self.original.pk)
        self.assertEqual(Sale.objects.get().customer_id, self.customer.pk)

    def test_replacement_first_sale_waits_then_uses_committed_person(self):
        self.success(self.race('replace', 'sale'))
        self.customer.refresh_from_db(); self.assertEqual(self.customer.person_id, self.replacement.pk)
        self.assertEqual(Sale.objects.get().customer.person_id, self.replacement.pk)

    def test_sale_first_delete_waits_then_rejects(self):
        self.domain_error(self.race('sale', 'delete'), code='customer_in_use')
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())
        self.assertEqual(Sale.objects.count(), 1)

    def test_delete_first_sale_waits_then_fails_without_partial_writes(self):
        before = business_snapshot()
        self.domain_error(self.race('delete', 'sale'), missing=True)
        self.assertFalse(Customer.objects.filter(pk=self.customer.pk).exists())
        after = business_snapshot()
        for label in before:
            if label != 'people.Customer': self.assertEqual(after[label], before[label], label)
        self.assertEqual(len(after['people.Customer']), len(before['people.Customer'])-1)

    def test_sale_rollback_allows_waiting_replacement(self):
        before = business_snapshot()
        self.success(self.race('sale', 'replace', rollback=True))
        self.assertFalse(Sale.objects.exists())
        self.customer.refresh_from_db(); self.assertEqual(self.customer.person_id, self.replacement.pk)
        self.stock.refresh_from_db(); self.assertEqual(self.stock.quantity, 100)
        after = business_snapshot()
        for label in before:
            if label != 'people.Customer': self.assertEqual(after[label], before[label], label)

    def test_replacement_rollback_sale_uses_original_person(self):
        self.success(self.race('replace', 'sale', rollback=True))
        self.assertEqual(Sale.objects.get().customer.person_id, self.original.pk)

    def test_delete_rollback_allows_waiting_sale(self):
        self.success(self.race('delete', 'sale', rollback=True))
        self.assertEqual(Sale.objects.get().customer_id, self.customer.pk)

    def test_two_replacements_serialize_last_commit_wins(self):
        self.success(self.race('replace', 'second'))
        self.customer.refresh_from_db(); self.assertEqual(self.customer.person_id, self.second.pk)
        self.assertFalse(Sale.objects.exists())

    def test_delete_first_replacement_reports_missing_customer(self):
        self.domain_error(self.race('delete', 'replace'), missing=True)
        self.assertFalse(Customer.objects.filter(pk=self.customer.pk).exists())
        self.assertTrue(Person.objects.filter(pk=self.original.pk).exists())

    def test_replacement_first_delete_removes_only_customer(self):
        from people.tests.clientes013_diagnostic import CustomerReplacementDiagnostic
        with CustomerReplacementDiagnostic(self):
            self.success(self.race('replace', 'delete'))
            self.assertFalse(Customer.objects.filter(pk=self.customer.pk).exists())
            self.assertTrue(Person.objects.filter(pk=self.original.pk).exists())
            self.assertTrue(Person.objects.filter(pk=self.replacement.pk).exists())

    def test_controlled_timeout_and_holder_rollback_leave_no_changes(self):
        before = business_snapshot()
        state = self.race('sale', 'replace', rollback=True, timeout=True)
        state['checked'] = True
        self.assertIsInstance(state['error'], OperationalError)
        self.assertEqual(state['error'].__cause__.sqlstate, '55P03')
        self.assertEqual(business_snapshot(), before)
        deadline = monotonic()+5
        closed = Event()
        while True:
            with connections['default'].cursor() as cursor:
                cursor.execute('SELECT pg_stat_clear_snapshot()')
                cursor.execute('SELECT count(*) FROM pg_stat_activity WHERE pid=ANY(%s)', [[s['pid'] for s in self.states]])
                if cursor.fetchone()[0] == 0: break
            self.assertLess(monotonic(), deadline, 'Worker backends did not close')
            closed.wait(.01)

    def test_replacement_commit_with_revoked_access_blocks_waiting_delete(self):
        from people.models import CompanyPersonAccess
        original_action = self.action
        def replace_then_revoke(name):
            result = original_action(name)
            if name == 'replace':
                CompanyPersonAccess.objects.filter(company=self.company, person=self.replacement).delete()
            return result
        # Real services still run. Only this test's holder also revokes access
        # before its commit; the waiting deletion must revalidate current identity.
        self.action = replace_then_revoke
        try:
            self.domain_error(self.race('replace', 'delete'), missing=True)
        finally:
            self.action = original_action
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.person_id, self.replacement.pk)
        self.assertTrue(self.customer.is_active)
        self.assertFalse(CompanyPersonAccess.objects.filter(
            company=self.company, person=self.replacement).exists())
        self.assertTrue(Person.objects.filter(pk=self.original.pk, is_active=True).exists())
        self.assertTrue(Person.objects.filter(pk=self.replacement.pk, is_active=True).exists())
        self.assertFalse(Sale.objects.exists())
