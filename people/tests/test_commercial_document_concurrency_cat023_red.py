"""CAT-02.3 5.3A: row serialization RED on committed PostgreSQL TEST fixtures.

execute_wrapper observes completed SQL without replacing results or validation.
A separate PostgreSQL probe proves ownership of a compatible lock on the exact
commercial row; preliminary reads do not trigger synchronization. pg_blocking_pids proves waiting; post_save distinguishes
an early role lock from a deferred FK wait at COMMIT after document writes.
No sleeps, mocks, shared Django connections, new production APIs or global PostgreSQL settings.
Timeout SQLSTATE 55P03 is expected only in its deliberately blocked scenario.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from threading import Event, Lock, Thread
from time import monotonic
import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import connections, transaction, OperationalError
from django.db.models.signals import post_save
from django.test import TransactionTestCase, tag

from django.apps import apps

from catalog.models import Product
from core.models import Branch, Company, DocumentType, Sequence
from inventory.models import Stock, StockMovement, Warehouse
from people.models import Customer, Supplier, Person, CompanyPersonAccess
from people.services import customer_maintenance, supplier_maintenance
from people.tests.test_customer_company_cat022a_red import require_isolated_postgresql
from people.tests.test_commercial_document_activity_cat023_red import snapshot
from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from sales.models import Sale, SaleMovement
from sales.use_cases.create_sale import CreateSale
from sales.use_cases.confirm_sale import ConfirmSale
from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.models import Purchase, PurchaseMovement
from purchases.services.purchase_service import PurchaseService
from purchases.use_cases.create_purchase import CreatePurchase
from purchases.use_cases.confirm_purchase import ConfirmPurchase


class RollbackActivity(Exception):
    """Test-only request to roll back the holder's real service transaction."""


class ConcurrentDocumentContracts:
    # Every fixture is committed: no TestCase outer transaction hides row locks.
    def setUp(self):
        super().setUp()
        require_isolated_postgresql(self)
        self.assertTrue(connections['default'].get_autocommit())
        self.company = Company.objects.create(person=Person.objects.create(
            identification='CON53-COMPANY', person_type='LEGAL', full_name='Empresa TEST'))
        self.branch = Branch.objects.create(company=self.company, code='001', name='Matriz')
        self.warehouse = Warehouse.objects.create(company=self.company, branch=self.branch,
            code='MAIN', name='Principal', is_main=True)
        self.person = Person.objects.create(identification='CON53-PERSON', person_type='NATURAL', full_name='Comercial')
        self.model = Customer if self.kind == 'sale' else Supplier
        self.service = customer_maintenance if self.kind == 'sale' else supplier_maintenance
        self.role = self.model.objects.create(company=self.company, person=self.person)
        self.actor = get_user_model().objects.create_user('con53-actor')
        self.actor.profile.companies.add(self.company)
        self.actor.user_permissions.add(*Permission.objects.filter(content_type__app_label='people',
            codename__in=['view_person', 'change_' + self.model._meta.model_name]))
        CompanyPersonAccess.objects.create(company=self.company, person=self.person)
        code = 'SALES_INVOICE' if self.kind == 'sale' else 'PURCHASE_INVOICE'
        self.dtype, _ = DocumentType.objects.get_or_create(code=code, defaults=dict(
            name=code, category='SALES' if self.kind == 'sale' else 'PURCHASES',
            line_behavior='COMMERCIAL', requires_detail=True, affects_inventory=True,
            inventory_behavior='OUT' if self.kind == 'sale' else 'IN', can_issue_electronic=self.kind == 'sale'))
        self.sequence = Sequence.objects.create(company=self.company, branch=self.branch,
            document_type=self.dtype, name=code, prefix='CON-', next_number=1)
        self.product = Product.objects.create(company=self.company, code='P', name='Producto')
        self.stock = Stock.objects.create(company=self.company, branch=self.branch, warehouse=self.warehouse,
            product=self.product, quantity=Decimal('100'), reserved_quantity=Decimal('0'))
        self.doc_model = Sale if self.kind == 'sale' else Purchase
        self.manifest_model = SaleMovement if self.kind == 'sale' else PurchaseMovement
        self.document_id = self.create().pk if self.operation == 'confirm' else None
        self.completed = []
        self.completion_lock = Lock()
        self.evidence = []
        self.writes = Event()
        def written(sender, **kwargs):self.writes.set()
        for model in apps.get_models():
            if model is Sequence or model._meta.app_label in {'sales', 'purchases', 'inventory'}:
                post_save.connect(written, sender=model, weak=False)
                self.addCleanup(post_save.disconnect, written, sender=model)
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='con53')
        self.releases = []
        self.workers = []
        self.auxiliary_pids = []
        self.milestones = []
        self.addCleanup(self.cleanup_workers)
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT pg_backend_pid(), current_database()')
            self.observer_pid, self.actual_database = cursor.fetchone()
        self.assertTrue(self.actual_database.startswith('test_'))

    def record(self, phase, **data):
        with self.completion_lock:
            self.milestones.append(dict(phase=phase, utc=datetime.now(timezone.utc).isoformat(),
                                        monotonic=monotonic(), **data))

    def unexpected(self, state):
        error = state['error']
        if error is None:
            return None
        if state.get('domain_error') and isinstance(error, ValidationError):
            return None  # Functional assertions still decide whether this rejection is correct.
        if (state.get('controlled_timeout') and isinstance(error, OperationalError)
                and getattr(error.__cause__, 'sqlstate', None) == '55P03'):
            return None
        return error

    def collect_workers(self):
        errors = []
        for state in self.workers:
            try:
                state['future'].result(timeout=12)
            except BaseException as error:
                errors.append(error)
            if state.get('atomic_after'):
                errors.append(RuntimeError('Worker returned with an open atomic block'))
            error = self.unexpected(state)
            if error is not None and not state.get('reported'):
                state['reported'] = True
                errors.append(error)
            errors.extend(state.pop('close_errors', []))
        with connections['default'].cursor() as cursor:
            pids = [s['pid'] for s in self.workers if s['pid']] + self.auxiliary_pids
            cursor.execute('SELECT pid FROM pg_stat_activity WHERE pid=ANY(%s)', [pids])
            remaining = cursor.fetchall()
        if remaining:
            errors.append(RuntimeError(f'Own TEST connections remain open: {remaining}'))
        if errors:
            raise BaseExceptionGroup('Concurrency workers/cleanup failed', errors)

    def cleanup_workers(self):
        # Registered before launch; always release gates and inspect every future/error.
        for event in self.releases:
            event.set()
        try:
            self.collect_workers()
        finally:
            self.pool.shutdown(wait=True)
            print('CON532 ' + json.dumps(dict(test=self.id(), database=self.actual_database,
                  observer_pid=self.observer_pid, evidence=self.evidence,
                  milestones=self.milestones, worker_completion_order=self.completed,
                  workers=[dict(name=s['name'], pid=s['pid'], atomic_after=s.get('atomic_after'),
                                error=type(s['error']).__name__ if s['error'] else None)
                           for s in self.workers]), default=str), flush=True)

    def resources(self, connection, pids, phase):
        # Catalog evidence, not a claim that uncontended row locks appear in pg_locks.
        with connection.cursor() as cursor:
            cursor.execute("""SELECT pid,state,xact_start,backend_xid::text,wait_event_type,wait_event
                              FROM pg_stat_activity WHERE pid=ANY(%s) ORDER BY pid""", [pids])
            activity = cursor.fetchall()
            cursor.execute("""SELECT pid,locktype,mode,granted,relation::regclass::text,
                                     page,tuple,transactionid::text,virtualxid,virtualtransaction
                              FROM pg_locks WHERE pid=ANY(%s)
                              AND (locktype IN ('transactionid','virtualxid','tuple')
                                   OR relation IN (%s::regclass,%s::regclass,'core_sequence'::regclass,
                                                   'inventory_stock'::regclass))
                              ORDER BY pid,locktype,mode""",
                           [pids, self.model._meta.db_table, self.doc_model._meta.db_table])
            locks = cursor.fetchall()
        self.record(phase, activity=activity, locks=locks)

    def owns_commercial_lock(self, connection):
        # RowShare/RowExclusive alone are table locks, so also probe the exact row.
        # A NO KEY UPDATE probe conflicts with locks that protect an is_active UPDATE,
        # but remains compatible with a FK's KEY SHARE lock.
        with connection.cursor() as cursor:
            cursor.execute("""SELECT pg_backend_pid(), EXISTS(
                SELECT 1 FROM pg_locks WHERE pid=pg_backend_pid() AND granted
                AND relation=%s::regclass AND mode IN
                ('RowShareLock','RowExclusiveLock','ShareRowExclusiveLock','ExclusiveLock','AccessExclusiveLock'))""",
                [self.model._meta.db_table])
            owner_pid, candidate = cursor.fetchone()
        if not candidate:
            return False
        probe = dict(ready=Event(), done=Event(), pid=None, error=None)
        wrapper_class, probe_settings = type(connection), deepcopy(connection.settings_dict)
        def run_probe():
            own = wrapper_class(probe_settings, alias='con532_row_probe')
            own.settings_dict = {**own.settings_dict, 'OPTIONS': {
                **own.settings_dict.get('OPTIONS', {}), 'connect_timeout': 5}}
            try:
                own.ensure_connection()
                with own.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid(),current_database()')
                    probe['pid'], database = cursor.fetchone()
                    if database != self.actual_database:
                        raise RuntimeError('Wrong probe database')
                    with self.completion_lock:
                        self.auxiliary_pids.append(probe['pid'])
                    cursor.execute("SELECT set_config('lock_timeout','300ms',false)")
                    cursor.execute("SELECT set_config('statement_timeout','1s',false)")
                    probe['ready'].set()
                    cursor.execute(f'SELECT id FROM "{self.model._meta.db_table}" WHERE id=%s FOR NO KEY UPDATE',
                                   [self.role.pk])
                    cursor.fetchall()  # autocommit releases a successful observational lock
            except BaseException as error:
                probe['error'] = error
            finally:
                try:
                    own.close()
                except BaseException as error:
                    probe['close_error'] = error
                finally:
                    probe['ready'].set()
                    probe['done'].set()
        thread = Thread(target=run_probe, name='con532-row-probe')
        thread.start()
        acquired = False
        try:
            if not probe['ready'].wait(6):
                raise RuntimeError('Probe connection startup timeout')
            deadline = monotonic() + 2
            while not probe['done'].is_set() and monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_blocking_pids(%s)', [probe['pid']])
                    blockers = cursor.fetchone()[0]
                if owner_pid in blockers:
                    acquired = True
                    self.resources(connection, [owner_pid, probe['pid']], 'commercial_lock_proved')
                    self.record('commercial_row_owner', owner_pid=owner_pid, probe_pid=probe['pid'],
                                table=self.model._meta.db_table, pk=self.role.pk,
                                probe_mode='FOR NO KEY UPDATE', blockers=blockers)
                    break
                probe['done'].wait(.005)
            if not probe['done'].wait(6):
                raise RuntimeError('Probe did not terminate')
        finally:
            thread.join(timeout=6)
            if thread.is_alive():
                raise RuntimeError('Probe thread did not terminate')
        if probe.get('close_error'):
            raise probe['close_error']
        error = probe['error']
        if error is not None and not (isinstance(error, OperationalError)
                and getattr(error.__cause__, 'sqlstate', None) == '55P03'):
            raise error
        return acquired

    @contextmanager
    def after_commercial_lock(self, connection, callback):
        seen = inspecting = False
        def observe(execute, sql, params, many, context):
            nonlocal seen, inspecting
            result = execute(sql, params, many, context)
            if not seen and not inspecting and connection.in_atomic_block:
                inspecting = True
                try:
                    acquired = self.owns_commercial_lock(connection)
                    if acquired:
                        seen = True
                        callback()
                finally:
                    inspecting = False
            return result
        with connection.execute_wrapper(observe):
            yield

    def ready_or_finished(self, state, ready):
        deadline = monotonic() + 10
        while monotonic() < deadline:
            if ready.is_set():
                return True
            if state['done'].wait(.01):
                error = self.unexpected(state)
                if error is not None:
                    state['reported'] = True
                    raise error
                return ready.is_set()
        raise RuntimeError('Worker neither acquired commercial lock nor terminated')

    def dto(self):
        data = dict(company_id=self.company.pk, branch_id=self.branch.pk,
            issue_date=date(2026, 10, 11), notes='Concurrency RED')
        if self.kind == 'sale':
            return SaleCreateDTO(**data, customer_id=self.role.pk, warehouse_id=self.warehouse.pk,
                details=[SaleDetailDTO(self.product.pk, Decimal('5'), Decimal('10'), Decimal('0'))])
        return PurchaseCreateDTO(**data, supplier_id=self.role.pk,
            details=[PurchaseDetailDTO(self.product.pk, Decimal('5'), Decimal('10'), Decimal('0'))])

    def create(self):
        if self.kind == 'sale':return CreateSale.execute(self.dto())
        if self.entry == 'service':return PurchaseService.create(self.dto())
        return CreatePurchase.execute(self.dto())

    def document_operation(self):
        if self.operation == 'create':return self.create().pk
        if self.kind == 'sale':ConfirmSale.execute(sale_id=self.document_id, user=self.actor_for_thread())
        else:ConfirmPurchase.execute(purchase_id=self.document_id, user=self.actor_for_thread())
        return self.document_id

    def actor_for_thread(self):return get_user_model().objects.get(pk=self.actor.pk)

    def activity(self, active):
        acquired = Event()
        with self.after_commercial_lock(connections['default'], acquired.set):
            result = self.service.set_active(actor=self.actor_for_thread(),
                company=Company.objects.get(pk=self.company.pk), relation_id=self.role.pk, is_active=active)
        self.assertTrue(acquired.is_set(), 'RED: actividad sin bloqueo comercial efectivo')
        return result

    def launch(self, name, function, lock_timeout='5s', *, domain_error=False, controlled_timeout=False):
        state = dict(name=name, connected=Event(), done=Event(), pid=None, error=None, result=None,
                     domain_error=domain_error, controlled_timeout=controlled_timeout, close_errors=[])
        self.workers.append(state)
        def work():
            connection = connections['default']  # thread-local wrapper, never borrowed
            connection.settings_dict = {**connection.settings_dict, 'OPTIONS': {
                **connection.settings_dict.get('OPTIONS', {}), 'connect_timeout': 5}}
            try:
                connection.ensure_connection()
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid(), current_database()')
                    state['pid'], database = cursor.fetchone()
                    if database != self.actual_database:
                        raise RuntimeError('Wrong PostgreSQL TEST database')
                    cursor.execute("SELECT set_config('lock_timeout', %s, false)", [lock_timeout])
                    cursor.execute("SELECT set_config('statement_timeout', '8s', false)")
                self.record('worker_connected', name=name, pid=state['pid'])
                state['connected'].set()
                state['result'] = function(connection)
                self.record('operation_returned_after_transaction', name=name, pid=state['pid'])
            except BaseException as error:
                state['error'] = error
                self.record('operation_exception', name=name, pid=state['pid'], error=type(error).__name__,
                            sqlstate=getattr(error.__cause__, 'sqlstate', None))
            finally:
                state['connected'].set()
                state['atomic_after'] = connection.in_atomic_block
                with self.completion_lock:
                    self.completed.append(name)
                try:
                    connection.close()
                except BaseException as error:
                    state['close_errors'].append(error)
                finally:
                    self.record('connection_closed', name=name, pid=state['pid'])
                    state['done'].set()
        state['future'] = self.pool.submit(work)
        if not state['connected'].wait(10):
            raise RuntimeError('Worker connection startup timeout')
        if state['pid'] is None:
            error = state['error'] or RuntimeError('Worker connection has no PID')
            state['reported'] = True
            raise error
        return state

    def waiting(self, waiter, holder):
        self.assertNotEqual(waiter['pid'], holder['pid'])
        self.assertNotIn(self.observer_pid, [waiter['pid'], holder['pid']])
        deadline = monotonic() + 6
        while monotonic() < deadline:
            with connections['default'].cursor() as cursor:
                cursor.execute('SELECT pg_blocking_pids(%s)', [waiter['pid']])
                blockers = cursor.fetchone()[0]
            if holder['pid'] in blockers:
                self.evidence.append((waiter['pid'], holder['pid'], blockers))
                self.resources(connections['default'], [waiter['pid'], holder['pid']], 'wait_edge_observed')
                return True
            if waiter['done'].wait(.01):return False
        raise RuntimeError('Harness: worker neither completed nor waited on the known holder')

    def finish(self, *states):
        self.collect_workers()  # every registered worker, including early-failure paths
        for state in states:
            self.assertTrue(state['done'].is_set())
            self.assertFalse(state['atomic_after'])
        self.resources(connections['default'], [s['pid'] for s in states], 'after_workers_closed')

    def assert_success(self, state):
        if state['error'] is not None:raise state['error']
        doc = self.doc_model.objects.get(pk=state['result'])
        self.assertEqual(doc.status, 'DRAFT' if self.operation == 'create' else 'CONFIRMED')
        self.assertEqual(doc.details.count(), 1)
        self.sequence.refresh_from_db();self.stock.refresh_from_db()
        self.assertEqual(self.sequence.next_number, 1 if self.operation == 'create' else 2)
        self.assertEqual(self.stock.quantity, Decimal('100') if self.operation == 'create' else
            (Decimal('95') if self.kind == 'sale' else Decimal('105')))
        self.assertEqual(StockMovement.objects.count(), 0 if self.operation == 'create' else 1)
        self.assertEqual(self.manifest_model.objects.count(), 0 if self.operation == 'create' else 1)
        self.assertEqual(bool(doc.number), self.operation == 'confirm')
        if self.operation == 'confirm':self.assertEqual(doc.confirmed_by_id, self.actor.pk)

    def role_first(self, *, rollback=False, active=False, timeout=False):
        if active:self.model.objects.filter(pk=self.role.pk).update(is_active=False)
        before = snapshot()
        ready, release = Event(), Event();self.releases.append(release)
        def hold(connection):
            try:
                with transaction.atomic():
                    self.activity(active)
                    ready.set()
                    if not release.wait(10):raise AssertionError('Holder release timeout')
                    if rollback:raise RollbackActivity()
            except RollbackActivity:pass
        holder = self.launch('activity', hold)
        if not self.ready_or_finished(holder, ready):
            raise RuntimeError('Activity ended before its holder milestone')
        doc = self.launch('document', lambda connection:self.document_operation(),
            lock_timeout='1500ms' if timeout else '5s', domain_error=True, controlled_timeout=timeout)
        try:
            blocked = self.waiting(doc, holder)
            early_write = self.writes.is_set()
            if timeout:self.assertTrue(doc['done'].wait(5), 'Expected controlled lock timeout')
        finally:
            self.record('holder_release_requested')
            release.set()
        self.finish(holder, doc)
        if holder['error'] is not None:raise holder['error']
        # Unexpected exceptions are infrastructure/programming errors, never RED successes.
        error = doc['error']
        if isinstance(error, OperationalError):
            if not timeout or getattr(error.__cause__, 'sqlstate', None) != '55P03':raise error
        elif error is not None and not isinstance(error, ValidationError):raise error
        self.assertTrue(blocked, 'RED: documental no espera el lock comercial')
        self.assertFalse(early_write, 'RED: escritura documental antes del lock; posible espera tardía de FK')
        self.role.refresh_from_db()
        self.assertEqual(self.role.is_active, not active if rollback else active)
        if timeout:
            self.assertIsInstance(error, OperationalError)
            self.assertEqual(getattr(error.__cause__, 'sqlstate', None), '55P03')
            self.assertEqual(snapshot(), before)
        elif rollback or active:
            self.assert_success(doc)
            if rollback:
                after = snapshot()
                for label in ('people.Customer', 'people.Supplier', 'people.Person', 'people.CompanyPersonAccess'):
                    self.assertEqual(after[label], before[label])
        else:
            self.assertIsInstance(error, ValidationError)
            after = snapshot()
            # Only committed activity/audit rows may change; no document effects.
            for label in before:
                if label != self.model._meta.label:self.assertEqual(after[label], before[label], label)
            original = {row['id']: row for row in before[self.model._meta.label]}
            current = {row['id']: row for row in after[self.model._meta.label]}
            self.assertEqual(current.keys(), original.keys())
            for pk, row in original.items():
                allowed = {'is_active', 'updated_by_id', 'updated_at'} if pk == self.role.pk else set()
                self.assertEqual({k: v for k, v in current[pk].items() if k not in allowed},
                                 {k: v for k, v in row.items() if k not in allowed})
            self.assertEqual(self.role.updated_by_id, self.actor.pk)

    def test_01_deactivation_first_document_waits_then_rejects(self):self.role_first()
    def test_02_deactivation_rollback_document_waits_then_succeeds(self):self.role_first(rollback=True)
    def test_04_controlled_lock_timeout_rolls_back_without_open_transactions(self):self.role_first(rollback=True, timeout=True)
    def test_05_reactivation_first_document_waits_then_succeeds(self):self.role_first(active=True)

    def test_03_document_first_deactivation_waits_until_document_commit(self):
        ready, release = Event(), Event();self.releases.append(release)
        def document(connection):
            def acquired():
                self.record('document_commercial_lock_gate')
                ready.set()
                if not release.wait(10):
                    raise RuntimeError('Commercial lock release timeout')
            with self.after_commercial_lock(connection, acquired):
                return self.document_operation()
        doc = self.launch('document', document)
        if not self.ready_or_finished(doc, ready):
            self.finish(doc)
            self.assert_success(doc)
            self.fail('RED: documento termina sin adquirir bloqueo comercial compatible sobre su relación')
        observed = {}
        def deactivate(connection):
            result = self.activity(False)
            expected = 'DRAFT' if self.operation == 'create' else 'CONFIRMED'
            observed['document_committed'] = self.doc_model.objects.filter(
                company_id=self.company.pk, status=expected).exists()
            return result.pk
        activity = self.launch('activity', deactivate)
        try:blocked = self.waiting(activity, doc)
        finally:
            self.record('holder_release_requested')
            release.set()
        self.finish(doc, activity)
        if activity['error'] is not None:raise activity['error']
        self.assert_success(doc)
        self.assertTrue(blocked, 'RED: operación documental no retiene lock del rol hasta COMMIT')
        self.assertTrue(observed['document_committed'], 'Document must commit before activity acquires the role')
        self.role.refresh_from_db();self.assertFalse(self.role.is_active)

    def test_06_deactivation_and_reactivation_serialize_on_same_row(self):
        ready, release = Event(), Event();self.releases.append(release)
        def first(connection):
            with transaction.atomic():
                result = self.activity(False)
                ready.set()
                if not release.wait(10):raise RuntimeError('Activity release timeout')
                return result.is_active
        holder = self.launch('deactivate', first)
        if not self.ready_or_finished(holder, ready):
            raise RuntimeError('Activity ended before its holder milestone')
        waiter = self.launch('reactivate', lambda connection:self.activity(True).pk)
        try:blocked = self.waiting(waiter, holder)
        finally:
            self.record('holder_release_requested')
            release.set()
        self.finish(holder, waiter)
        for state in (holder, waiter):
            if state['error'] is not None:raise state['error']
        self.assertTrue(blocked)
        self.assertFalse(holder['result'], 'Deactivation completed and committed before reactivation')
        self.assertEqual(waiter['result'], self.role.pk)
        self.role.refresh_from_db();self.assertTrue(self.role.is_active)


@tag('cat023_concurrency_red')
class CustomerCreationConcurrencyRedTests(ConcurrentDocumentContracts, TransactionTestCase):
    kind='sale';operation='create';entry='use_case'

@tag('cat023_concurrency_red')
class CustomerConfirmationConcurrencyRedTests(ConcurrentDocumentContracts, TransactionTestCase):
    kind='sale';operation='confirm';entry='use_case'

@tag('cat023_concurrency_red')
class SupplierCreationConcurrencyRedTests(ConcurrentDocumentContracts, TransactionTestCase):
    kind='purchase';operation='create';entry='use_case'

@tag('cat023_concurrency_red')
class SupplierServiceCreationConcurrencyRedTests(ConcurrentDocumentContracts, TransactionTestCase):
    kind='purchase';operation='create';entry='service'

@tag('cat023_concurrency_red')
class SupplierConfirmationConcurrencyRedTests(ConcurrentDocumentContracts, TransactionTestCase):
    kind='purchase';operation='confirm';entry='use_case'
