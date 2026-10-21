"""Opt-in evidence for one CLIENTES-01.3 case; never changes SQL or results."""
import json
import tempfile
import traceback
from pathlib import Path
from threading import Lock
from time import monotonic

from django.contrib.auth import get_user_model
from django.db import connections, transaction
from people.models import Customer, Person, CompanyPersonAccess
from people.services import customer_maintenance
from core.testing.clientes013_guard import DATABASE, USER, HOST, PORT, verify_identity


class CustomerReplacementDiagnostic:
    def __init__(self, case):
        self.case = case
        self.events = []
        self.lock = Lock()
        self.directory = Path(tempfile.mkdtemp(prefix='clientes013-replacement-diagnostic-'))
        self.path = self.directory / 'evidence.json'

    def record(self, event, **data):
        with self.lock:
            self.events.append({'order': len(self.events), 'monotonic': monotonic(),
                                'event': event, **data})

    def identity(self, db, worker):
        with db.cursor() as cursor:
            verify_identity(cursor)
            cursor.execute("SELECT pg_backend_pid(),current_database(),current_user,inet_server_addr()::text,inet_server_port(),current_setting('transaction_isolation')")
            pid, database, user, host, port, isolation = cursor.fetchone()
        if (database, user, host, port) != (DATABASE, USER, HOST+'/32', int(PORT)):
            raise AssertionError('Diagnostic connection identity mismatch')
        self.record('transaction_identity', worker=worker, pid=pid, database=database,
                    user=user, host=host, port=port, isolation=isolation)

    def execute(self, worker, execute, sql, params, many, context):
        # Only the relevant locking SELECT; no user/auth/password statements.
        relevant = ('"people_customer"' in sql.lower() and 'for update' in sql.lower()
                    and sql.lstrip().lower().startswith('select'))
        if not relevant:
            return execute(sql, params, many, context)
        self.record('locking_query_start', worker=worker, sql=sql, params=params)
        try:
            result = execute(sql, params, many, context)
        except BaseException:
            self.record('locking_query_exception', worker=worker, traceback=traceback.format_exc())
            raise
        self.record('locking_query_complete', worker=worker, rowcount=context['cursor'].rowcount)
        return result  # Do not fetch, consume, replace or rerun the original query.

    def __enter__(self):
        self.record('fixture_ids', customer_id=self.case.customer.pk, company_id=self.case.company.pk,
                    original_person_id=self.case.original.pk, replacement_person_id=self.case.replacement.pk)
        self.case.diagnostic = self
        self.identity(connections['default'], 'observer')
        return self

    def final_snapshot(self):
        db = connections['default']
        if db.in_atomic_block:
            raise AssertionError('Diagnostic final snapshot requires a fresh transaction')
        with transaction.atomic():
            with db.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            self.identity(db, 'final_observer')
            fields = ('id', 'company_id', 'person_id', 'category_id', 'is_active')
            direct = Customer.objects.filter(pk=self.case.customer.pk, company_id=self.case.company.pk).values(*fields)
            actor = get_user_model().objects.get(pk=self.case.actor.pk)
            filtered = customer_maintenance._service.available_relations(actor, self.case.company).filter(
                pk=self.case.customer.pk).values(*fields)
            direct_sql, direct_params = direct.query.sql_with_params()
            filtered_sql, filtered_params = filtered.query.sql_with_params()
            data = {'direct': {'sql': direct_sql, 'params': direct_params, 'rows': list(direct)},
                    'availability_filtered': {'sql': filtered_sql, 'params': filtered_params, 'rows': list(filtered)},
                    'persons': list(Person.objects.filter(pk__in=[self.case.original.pk, self.case.replacement.pk])
                                    .order_by('pk').values('id', 'is_active')),
                    # CompanyPersonAccess has no activity flag: record its actual schema.
                    'replacement_accesses': list(CompanyPersonAccess.objects.filter(
                        company_id=self.case.company.pk, person_id=self.case.replacement.pk)
                        .values('id', 'company_id', 'person_id'))}
            self.record('final_snapshot_before_test_cleanup', **data)

    def __exit__(self, kind, error, tb):
        try:
            self.case.release.set()
            for state in self.case.states:
                state['future'].result(timeout=15)
            self.final_snapshot()
        except BaseException:
            self.record('diagnostic_error', traceback=traceback.format_exc())
            raise
        finally:
            self.record('test_outcome', exception_type=kind.__name__ if kind else None,
                        traceback=''.join(traceback.format_exception(kind, error, tb)) if kind else None)
            self.path.write_text(json.dumps(self.events, ensure_ascii=False, indent=2, default=str)+'\n')
            print('CLIENTES013 diagnostic evidence:', self.path)
            del self.case.diagnostic
        return False  # Preserve the original error and all test expectations.
