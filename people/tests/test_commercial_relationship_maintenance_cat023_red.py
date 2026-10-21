"""CAT-02.3: contratos de mantenimiento empresarial, sin GREEN ni interfaces.

SEAM APROBADO CAT-02.3 FASE 1.2:
people.services.{customer,supplier}_maintenance, operaciones create,
list_relations, get_relation, update y set_active. Solo ServiceAdapter fija esa
convención; una implementación por clases puede conectarse aquí tras revisión.
No se fijan nombres internos, rutas, DTOs ni excepciones nuevas. Company es
contexto resuelto por servidor y se reautoriza; data es entrada no confiable.
La creación reutiliza person_id disponible, nunca crea/resuelve una identidad
global por identificación. Consulta incluye inactivos solo si se pide; detalle
permite administrarlos. Ninguna operación exige Branch.

Los errores por seam ausente son FAIL RED explícitos, no errores de importación.
Importaciones rotas dentro de un servicio existente se propagan como ERROR.
Sin skips/xfails, mocks de servicio ni cambios en documentos o pruebas previas.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from importlib import import_module
from threading import Barrier

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase, tag

from core.models import Company, DocumentType
from people.models import CompanyPersonAccess, Customer, Person, Supplier
from people.services import person_access_policy as policy
from people.tests.person_ui_support import PersonUIFixture
from people.tests.test_customer_company_cat022a_red import require_isolated_postgresql

IdentityUnavailable = policy.IdentityUnavailable


class ServiceAdapter:
    """Único punto de enlace aprobado; no implementación ni fallback GREEN."""
    def __init__(self, test, role):
        path = f'people.services.{role}_maintenance'
        try:
            self.service = import_module(path)
        except ModuleNotFoundError as error:
            if error.name != path:
                raise
            test.fail(f'RED: no existe el contrato de servicio de mantenimiento {role}; seam aprobado: {path}')
        self.test = test

    def operation(self, name):
        function = getattr(self.service, name, None)
        self.test.assertTrue(callable(function), f'RED: falta operación aprobada {name}')
        return function

    def create(self, actor, company, person_id, data=None):
        return self.operation('create')(actor=actor, company=company, person_id=person_id, data=data or {})

    def listing(self, actor, company, query=None, include_inactive=False):
        before=database_snapshot()
        result=list(self.operation('list_relations')(actor=actor, company=company, query=query, include_inactive=include_inactive))
        self.test.assertEqual(database_snapshot(),before,'Consulta con escrituras')
        return result

    def detail(self, actor, company, pk):
        before=database_snapshot()
        result=self.operation('get_relation')(actor=actor, company=company, relation_id=pk)
        self.test.assertEqual(database_snapshot(),before,'Detalle con escrituras')
        return result

    def update(self, actor, company, pk, data):
        return self.operation('update')(actor=actor, company=company, relation_id=pk, data=data)

    def active(self, actor, company, pk, active):
        return self.operation('set_active')(actor=actor, company=company, relation_id=pk, is_active=active)


def database_snapshot():
    """Todas las filas de aplicación, incluida auditoría y documentos; no sequences."""
    return {m._meta.label: list(m.objects.order_by('pk').values())
            for m in apps.get_models(include_auto_created=True) if m._meta.managed and not m._meta.proxy}


class MaintenanceContracts:
    def setUp(self):
        require_isolated_postgresql(self)
        super().setUp()
        self.restrict(self.actor, 'view_person', *(f'{op}_{self.role}' for op in ('view', 'add', 'change')))
        # PersonUIFixture admite ambas empresas; esta operación representa A.
        self.actor.profile.companies.remove(self.b)
        self.actor.profile.branches.clear()
        self.local = self.model.objects.create(company=self.a, person=self.visible_person, notes='Local')
        self.foreign = self.model.objects.create(company=self.b, person=self.hidden_person, notes='Private')
        self.person = self.make_person('AVAILABLE-NEW', email='new@example.invalid')
        CompanyPersonAccess.objects.create(company=self.a, person=self.person)

    def api(self):
        return ServiceAdapter(self, self.role)

    def rejected(self, operation, exceptions=PermissionDenied):
        before = database_snapshot()
        with self.assertRaises(exceptions) as caught:
            operation()
        self.assertEqual(database_snapshot(), before, 'Rechazo con efectos parciales')
        for value in (self.hidden_person.identification, self.hidden_person.full_name,
                      self.hidden_person.email, self.hidden_person.phone, self.hidden_person.address):
            self.assertNotIn(value, str(caught.exception))
        return caught.exception

    def unchanged_except_role_and_appended_audit(self, before, after):
        for label, rows in before.items():
            if label == self.model._meta.label:
                continue
            if label == 'core.AuditLog':
                # Se permite añadir auditoría, nunca alterar registros previos.
                current = {row['id']: row for row in after[label]}
                for row in rows:
                    self.assertEqual(current.get(row['id']), row)
            else:
                self.assertEqual(after[label], rows, label)

    def assert_delta(self, before, pk, allowed=(), created=False):
        after = database_snapshot()
        self.unchanged_except_role_and_appended_audit(before, after)
        label = self.model._meta.label
        old = {r['id']: r for r in before[label]}
        current = {r['id']: r for r in after[label]}
        self.assertEqual(set(current), set(old) | ({pk} if created else set()))
        for key, row in old.items():
            if key != pk or created:
                self.assertEqual(current[key], row)
            else:
                self.assertEqual({k: v for k, v in current[key].items() if k not in allowed},
                                 {k: v for k, v in row.items() if k not in allowed})

    def protected_payloads(self):
        values = {
            'id': self.foreign.pk, 'pk': self.foreign.pk,
            'company': self.b, 'company_id': self.b.pk,
            'person': self.hidden_person, 'person_id': self.hidden_person.pk,
            'created_by': self.other, 'updated_by': self.other,
            'created_by_id': self.other.pk, 'updated_by_id': self.other.pk,
            'created_at': self.local.created_at, 'updated_at': self.local.updated_at,
            'deleted_at': self.local.created_at, 'is_active': False,
            'unknown_commercial_field': 'unsupported',
        }
        for field in Person._meta.concrete_fields:
            if field.name not in {'id', 'created_by', 'updated_by', 'created_at', 'updated_at', 'deleted_at', 'is_active'}:
                values[field.name] = getattr(self.hidden_person, field.name)
        for key, value in values.items():
            yield {key: value}
        for key, value in [('company', self.b.pk), ('person', self.hidden_person.pk),
                           ('created_by', self.other.pk), ('updated_by', self.other.pk)]:
            yield {key: value}

    def all_operations(self, api, actor=None, company=None):
        actor = self.actor if actor is None else actor
        company = self.a if company is None else company
        return [lambda: api.listing(actor, company),
                lambda: api.detail(actor, company, self.local.pk),
                lambda: api.create(actor, company, self.person.pk),
                lambda: api.update(actor, company, self.local.pk, {'notes': 'Attempt'}),
                lambda: api.active(actor, company, self.local.pk, False)]

    def test_01_create_own_role_reuses_identity_and_records_actor(self):
        other=Supplier if self.model is Customer else Customer
        other.objects.create(company=self.a,person=self.person)
        self.model.objects.create(company=self.b,person=self.person)
        api = self.api(); before = database_snapshot(); before_person = list(Person.objects.order_by('pk').values())
        access = list(CompanyPersonAccess.objects.order_by('pk').values())
        obj = api.create(self.actor, self.a, self.person.pk, {'notes': 'Created'})
        obj.refresh_from_db()
        self.assertEqual((obj.company_id, obj.person_id, obj.notes), (self.a.pk, self.person.pk, 'Created'))
        self.assertEqual(obj.created_by_id, self.actor.pk)
        self.assertEqual(obj.updated_by_id, self.actor.pk)
        self.assertTrue(obj.is_active); self.assertIsNone(obj.deleted_at)
        self.assert_delta(before, obj.pk, created=True)
        self.assertEqual(list(Person.objects.order_by('pk').values()), before_person)
        self.assertEqual(list(CompanyPersonAccess.objects.order_by('pk').values()), access)

    def test_02_same_person_can_have_role_in_two_authorized_companies(self):
        api=self.api(); self.actor.profile.companies.add(self.b)
        CompanyPersonAccess.objects.create(company=self.b, person=self.visible_person)
        obj=api.create(self.actor,self.b,self.visible_person.pk)
        self.assertNotEqual(obj.pk,self.local.pk)
        self.assertEqual(set(self.model.objects.filter(person=self.visible_person).values_list('company_id',flat=True)),{self.a.pk,self.b.pk})

    def test_03_duplicate_active_pair_is_rejected_without_writes(self):
        api=self.api()
        self.rejected(lambda:api.create(self.actor,self.a,self.visible_person.pk), ValidationError)

    def test_04_inactive_pair_is_not_implicitly_reactivated_or_duplicated(self):
        self.local.is_active=False; self.local.save(update_fields=['is_active'])
        api=self.api()
        self.rejected(lambda:api.create(self.actor,self.a,self.visible_person.pk),ValidationError)

    def test_05_anonymous_actor_is_rejected_for_every_operation(self):
        api=self.api()
        for op in self.all_operations(api,actor=AnonymousUser()):
            self.rejected(op)

    def test_06_inactive_actor_is_rejected_for_every_operation(self):
        self.actor.is_active=False; self.actor.save(update_fields=['is_active']);api=self.api()
        for op in self.all_operations(api):self.rejected(op)

    def test_07_foreign_company_is_rejected_for_every_operation(self):
        api=self.api()
        for op in self.all_operations(api,company=self.b):self.rejected(op)

    def test_08_revoked_membership_is_rechecked_for_every_operation(self):
        api=self.api();self.actor.profile.companies.remove(self.a)
        for op in self.all_operations(api):self.rejected(op)

    def test_09_inactive_company_is_rejected_for_every_operation(self):
        self.a.is_active=False;self.a.save(update_fields=['is_active']);api=self.api()
        for op in self.all_operations(api):self.rejected(op)

    def test_10_consultation_requires_commercial_view_permission(self):
        self.restrict(self.actor,'view_person',f'add_{self.role}',f'change_{self.role}');api=self.api()
        self.rejected(lambda:api.listing(self.actor,self.a))
        self.rejected(lambda:api.detail(self.actor,self.a,self.local.pk))

    def test_11_creation_requires_commercial_add_permission(self):
        self.restrict(self.actor,'view_person',f'view_{self.role}',f'change_{self.role}');api=self.api()
        self.rejected(lambda:api.create(self.actor,self.a,self.person.pk))

    def test_12_edit_and_activity_require_commercial_change_permission(self):
        self.restrict(self.actor,'view_person',f'view_{self.role}',f'add_{self.role}');api=self.api()
        for op in [lambda:api.update(self.actor,self.a,self.local.pk,{'notes':'x'}),
                   lambda:api.active(self.actor,self.a,self.local.pk,False),
                   lambda:api.active(self.actor,self.a,self.local.pk,True)]:self.rejected(op)

    def test_13_person_add_and_change_do_not_authorize_commercial_operations(self):
        self.restrict(self.actor,'view_person','add_person','change_person');api=self.api()
        for op in self.all_operations(api):self.rejected(op)

    def test_14_role_creation_needs_no_person_add_change_or_branch(self):
        self.restrict(self.actor,'view_person',f'add_{self.role}');api=self.api()
        self.assertFalse(self.actor.profile.branches.exists())
        self.assertFalse(self.actor.has_perm('people.add_person'))
        self.assertFalse(self.actor.has_perm('people.change_person'))
        self.assertEqual(api.create(self.actor,self.a,self.person.pk).person_id,self.person.pk)

    def test_15_unavailable_identity_is_neutral_and_not_associated(self):
        api=self.api();self.rejected(lambda:api.create(self.actor,self.a,self.hidden_person.pk), IdentityUnavailable)
        self.assertFalse(CompanyPersonAccess.objects.filter(company=self.a,person=self.hidden_person).exists())

    def test_16_person_view_permission_is_not_replaced_by_role_permissions(self):
        self.restrict(self.actor,*(f'{op}_{self.role}' for op in ('view','add','change')));api=self.api()
        self.rejected(lambda:api.create(self.actor,self.a,self.person.pk), IdentityUnavailable)
        self.assertEqual(api.listing(self.actor,self.a),[])
        self.rejected(lambda:api.detail(self.actor,self.a,self.local.pk), ObjectDoesNotExist)
        self.rejected(lambda:api.update(self.actor,self.a,self.local.pk,{'notes':'Denied'}), ObjectDoesNotExist)
        self.rejected(lambda:api.active(self.actor,self.a,self.local.pk,False), ObjectDoesNotExist)

    def test_17_inactive_person_is_not_available_for_role_creation(self):
        api=self.api();self.rejected(lambda:api.create(self.actor,self.a,self.inactive_person.pk), IdentityUnavailable)

    def test_18_create_rejects_untrusted_company_person_and_identity_fields(self):
        api=self.api()
        for payload in self.protected_payloads():
            with self.subTest(fields=tuple(payload)):
                self.rejected(lambda:api.create(self.actor,self.a,self.person.pk,payload),ValidationError)

    def test_19_list_and_search_are_company_and_person_scoped(self):
        api=self.api()
        self.model.objects.create(company=self.a,person=self.hidden_person)
        self.model.objects.create(company=None,person=self.person)
        self.assertEqual({r.pk for r in api.listing(self.actor,self.a)},{self.local.pk})
        self.assertEqual({r.pk for r in api.listing(self.actor,self.a,query=self.visible_person.identification)},{self.local.pk})
        for query in (self.hidden_person.identification,self.hidden_person.full_name,self.hidden_person.email):
            self.assertEqual(api.listing(self.actor,self.a,query=query),[])

    def test_20_list_treats_inactive_relations_explicitly(self):
        self.local.is_active=False;self.local.save(update_fields=['is_active']);api=self.api()
        self.assertEqual(api.listing(self.actor,self.a),[])
        self.assertEqual({r.pk for r in api.listing(self.actor,self.a,include_inactive=True)},{self.local.pk})
        self.assertEqual(api.detail(self.actor,self.a,self.local.pk).pk,self.local.pk)

    def test_21_detail_rejects_foreign_unclassified_and_unavailable_identity(self):
        api=self.api();legacy=self.model.objects.create(person=self.person)
        unavailable=self.model.objects.create(company=self.a,person=self.hidden_person)
        for pk in (self.foreign.pk,legacy.pk,unavailable.pk):self.rejected(lambda:api.detail(self.actor,self.a,pk), ObjectDoesNotExist)

    def test_22_revoking_person_access_immediately_hides_existing_role(self):
        api=self.api();CompanyPersonAccess.objects.filter(company=self.a,person=self.visible_person).delete()
        self.assertEqual(api.listing(self.actor,self.a),[])
        self.rejected(lambda:api.detail(self.actor,self.a,self.local.pk), ObjectDoesNotExist)
        self.rejected(lambda:api.update(self.actor,self.a,self.local.pk,{'notes':'Denied'}), ObjectDoesNotExist)
        self.rejected(lambda:api.active(self.actor,self.a,self.local.pk,False), ObjectDoesNotExist)
        self.assertTrue(self.model.objects.filter(pk=self.local.pk).exists())

    def test_23_update_local_notes_records_actor_without_global_changes(self):
        other=Supplier if self.model is Customer else Customer
        other.objects.create(company=self.a,person=self.visible_person)
        self.model.objects.create(company=self.a,person=self.person)
        api=self.api();before=database_snapshot()
        obj=api.update(self.actor,self.a,self.local.pk,{'notes':'Updated'})
        obj.refresh_from_db();self.assertEqual(obj.notes,'Updated');self.assertEqual(obj.updated_by_id,self.actor.pk)
        self.assertEqual(obj.created_by_id,self.local.created_by_id)
        self.assert_delta(before, self.local.pk, {'notes', 'updated_by_id', 'updated_at'})
        foreign=self.model.objects.values().get(pk=self.foreign.pk)
        self.assertEqual(foreign,next(r for r in before[self.model._meta.label] if r['id']==self.foreign.pk))

    def test_24_update_rejects_company_person_global_fields_and_audit_injection(self):
        api=self.api()
        for payload in self.protected_payloads():
            with self.subTest(fields=tuple(payload)):
                self.rejected(lambda:api.update(self.actor,self.a,self.local.pk,{'notes':'Must rollback',**payload}),ValidationError)

    def test_25_foreign_edit_and_activity_are_rejected_even_for_known_pk(self):
        api=self.api()
        self.rejected(lambda:api.update(self.actor,self.a,self.foreign.pk,{'notes':'Foreign'}), ObjectDoesNotExist)
        self.rejected(lambda:api.active(self.actor,self.a,self.foreign.pk,False), ObjectDoesNotExist)
        self.rejected(lambda:api.active(self.actor,self.a,self.foreign.pk,True), ObjectDoesNotExist)

    def test_26_deactivate_reactivate_same_row_preserves_every_other_record(self):
        other_model=Supplier if self.model is Customer else Customer
        other_model.objects.create(company=self.a,person=self.visible_person)
        self.model.objects.create(company=self.b,person=self.visible_person)
        api=self.api();before=database_snapshot();original=self.model.objects.values().get(pk=self.local.pk)
        for active in (False,True):
            obj=api.active(self.actor,self.a,self.local.pk,active);obj.refresh_from_db()
            self.assertEqual(obj.pk,self.local.pk);self.assertIs(obj.is_active,active)
            self.assertEqual(obj.updated_by_id,self.actor.pk);self.assertEqual(obj.deleted_at,original['deleted_at'])
            current=database_snapshot()
            self.unchanged_except_role_and_appended_audit(before,current)
            for row in current[self.model._meta.label]:
                old=next(r for r in before[self.model._meta.label] if r['id']==row['id'])
                if row['id'] != self.local.pk:
                    self.assertEqual(row,old)
                self.assertEqual({k:v for k,v in row.items() if k not in ('is_active','updated_by_id','updated_at')},
                                 {k:v for k,v in old.items() if k not in ('is_active','updated_by_id','updated_at')})
            self.assertEqual(len(current[self.model._meta.label]),len(before[self.model._meta.label]))

    def test_27_activity_preserves_existing_document_rows_and_fk(self):
        from sales.models import Sale
        from purchases.models import Purchase
        from inventory.models import Warehouse
        if self.model is Customer:
            dtype,_=DocumentType.objects.get_or_create(code=Sale.DOCUMENT_TYPE_CODE,defaults={'name':'Sale','category':'SALES'})
            warehouse=Warehouse.objects.create(company=self.a,branch=self.branch,code='H',name='Historical')
            Sale.objects.create(company=self.a,branch=self.branch,warehouse=warehouse,customer=self.local,document_type=dtype)
        else:
            dtype,_=DocumentType.objects.get_or_create(code=Purchase.DOCUMENT_TYPE_CODE,defaults={'name':'Purchase','category':'PURCHASES'})
            Purchase.objects.create(company=self.a,branch=self.branch,supplier=self.local,document_type=dtype)
        other=Supplier if self.model is Customer else Customer
        other.objects.create(company=self.a,person=self.visible_person)
        self.model.objects.create(company=self.b,person=self.visible_person)
        api=self.api();before=database_snapshot()
        obj=api.active(self.actor,self.a,self.local.pk,False)
        obj.refresh_from_db()
        self.assertEqual(obj.pk,self.local.pk)
        self.assertFalse(obj.is_active)
        self.assertEqual(obj.updated_by_id,self.actor.pk)
        self.assert_delta(before,self.local.pk,{'is_active','updated_by_id','updated_at'})

    def test_28_unexpected_database_integrity_errors_are_not_translated(self):
        api=self.api();table=connection.ops.quote_name(self.model._meta.db_table).upper()
        # Fallos PostgreSQL reales en tabla temporal exclusiva. El wrapper no
        # devuelve éxito ni sustituye el servicio: provoca un fallo de escritura.
        with connection.cursor() as c:
            c.execute('CREATE TEMP TABLE cat023_probe (id integer NOT NULL, CONSTRAINT cat023_probe_unique UNIQUE(id))')
            c.execute('INSERT INTO cat023_probe VALUES (1)')
        try:
            for probe,expected in [('INSERT INTO cat023_probe VALUES (NULL)','23502'),
                                   ('INSERT INTO cat023_probe VALUES (1)','23505')]:
                reached=[]
                def fail_at_insert(execute,statement,params,many,context):
                    if statement.lstrip().upper().startswith('INSERT INTO '+table):
                        reached.append(True)
                        with connection.cursor() as c:c.execute(probe)
                    return execute(statement,params,many,context)
                before=database_snapshot()
                with self.assertRaises(IntegrityError) as caught:
                    with transaction.atomic(), connection.execute_wrapper(fail_at_insert):
                        api.create(self.actor,self.a,self.person.pk)
                self.assertTrue(reached,'Debe alcanzar el INSERT real del rol')
                self.assertEqual(caught.exception.__cause__.sqlstate,expected)
                self.assertEqual(database_snapshot(),before)
        finally:
            with connection.cursor() as c:c.execute('DROP TABLE cat023_probe')


    def test_31_hidden_and_nonexistent_person_have_equivalent_public_rejection(self):
        api=self.api()
        missing=Person.objects.order_by('-pk').first().pk + 1
        self.assertFalse(Person.objects.filter(pk=missing).exists())
        hidden=self.rejected(lambda:api.create(self.actor,self.a,self.hidden_person.pk),IdentityUnavailable)
        absent=self.rejected(lambda:api.create(self.actor,self.a,missing),IdentityUnavailable)
        self.assertEqual(type(hidden),type(absent))
        self.assertEqual(getattr(hidden,'code',None),getattr(absent,'code',None))
        self.assertEqual(str(hidden),str(absent))

    def test_32_unclassified_relation_cannot_be_edited_or_activated(self):
        legacy=self.model.objects.create(company=None,person=self.person,is_active=False)
        api=self.api()
        self.rejected(lambda:api.update(self.actor,self.a,legacy.pk,{'notes':'Attempt'}),ObjectDoesNotExist)
        for active in (False,True):
            self.rejected(lambda:api.active(self.actor,self.a,legacy.pk,active),ObjectDoesNotExist)

    def test_33_successful_queries_have_no_writes_and_need_no_branch(self):
        api=self.api();self.assertFalse(self.actor.profile.branches.exists())
        before=database_snapshot()
        self.assertEqual([r.pk for r in api.listing(self.actor,self.a)],[self.local.pk])
        self.assertEqual(database_snapshot(),before)
        self.assertEqual([r.pk for r in api.listing(self.actor,self.a,query=self.visible_person.identification)],[self.local.pk])
        self.assertEqual(database_snapshot(),before)
        self.assertEqual(api.detail(self.actor,self.a,self.local.pk).pk,self.local.pk)
        self.assertEqual(database_snapshot(),before)

    def test_34_edit_and_activity_need_no_branch_and_preserve_other_roles(self):
        other=Supplier if self.model is Customer else Customer
        other.objects.create(company=self.a,person=self.visible_person)
        self.model.objects.create(company=self.b,person=self.visible_person)
        api=self.api();self.assertFalse(self.actor.profile.branches.exists())
        before=database_snapshot()
        obj=api.update(self.actor,self.a,self.local.pk,{'notes':'No branch'})
        obj.refresh_from_db();self.assertEqual(obj.notes,'No branch')
        self.assertEqual(obj.updated_by_id,self.actor.pk)
        self.assert_delta(before,self.local.pk,{'notes','updated_by_id','updated_at'})
        for active in (False,True):
            before=database_snapshot()
            obj=api.active(self.actor,self.a,self.local.pk,active)
            obj.refresh_from_db();self.assertIs(obj.is_active,active)
            self.assertEqual(obj.updated_by_id,self.actor.pk)
            self.assert_delta(before,self.local.pk,{'is_active','updated_by_id','updated_at'})


@tag('cat023_maintenance_red')
class CustomerMaintenanceRedTests(MaintenanceContracts,PersonUIFixture):
    role='customer';model=Customer

    def test_29_credit_limit_accepts_model_precision(self):
        api=self.api();obj=api.update(self.actor,self.a,self.local.pk,{'credit_limit':Decimal('123.45')})
        obj.refresh_from_db();self.assertEqual(obj.credit_limit,Decimal('123.45'))
        maximum=api.create(self.actor,self.a,self.person.pk,{'credit_limit':Decimal('99999999.99')})
        maximum.refresh_from_db();self.assertEqual(maximum.credit_limit,Decimal('99999999.99'))

    def test_30_credit_limit_rejects_negative_fractional_and_overflow_atomically(self):
        api=self.api()
        for value in (Decimal('-0.01'),Decimal('1.001'),Decimal('100000000.00')):
            with self.subTest(value=value):
                self.rejected(lambda:api.update(self.actor,self.a,self.local.pk,{'notes':'Must rollback','credit_limit':value}),ValidationError)
                self.rejected(lambda:api.create(self.actor,self.a,self.person.pk,{'credit_limit':value}),ValidationError)


@tag('cat023_maintenance_red')
class SupplierMaintenanceRedTests(MaintenanceContracts,PersonUIFixture):
    role='supplier';model=Supplier

    def test_29_supplier_rejects_customer_only_fields(self):
        api=self.api()
        self.rejected(lambda:api.update(self.actor,self.a,self.local.pk,{'credit_limit':Decimal('1')}),ValidationError)
        self.rejected(lambda:api.create(self.actor,self.a,self.person.pk,{'credit_limit':Decimal('1')}),ValidationError)


@tag('cat023_maintenance_red')
class ExistingIdentityAndDatabaseContracts(PersonUIFixture):
    def setUp(self):
        require_isolated_postgresql(self);super().setUp()

    def test_existing_policy_has_no_visibility_from_commercial_role_alone(self):
        Customer.objects.create(company=self.a,person=self.hidden_person)
        Supplier.objects.create(company=self.a,person=self.hidden_person)
        self.assertFalse(policy.is_available(actor=self.actor,company=self.a,person=self.hidden_person))

    def test_existing_person_identity_collision_is_neutral_without_association(self):
        from people.services.person_access_policy import IdentityUnavailable
        before=database_snapshot()
        with self.assertRaises(IdentityUnavailable) as caught:
            policy.create_person(actor=self.actor,company=self.a,data={
                'identification':self.hidden_person.identification,'person_type':'LEGAL','full_name':'Attempt'})
        self.assertEqual(str(caught.exception),'identity_unavailable');self.assertEqual(database_snapshot(),before)

    def test_existing_database_allows_same_identity_both_roles_and_two_companies(self):
        for model in (Customer,Supplier):
            for company in (self.a,self.b):model.objects.create(company=company,person=self.visible_person)
            self.assertEqual(model.objects.filter(person=self.visible_person).count(),2)

    def test_existing_unique_pair_includes_inactive_rows(self):
        for model in (Customer,Supplier):
            model.objects.create(company=self.a,person=self.visible_person,is_active=False)
            with self.assertRaises(IntegrityError),transaction.atomic():
                model.objects.create(company=self.a,person=self.visible_person)

    def test_service_composition_can_create_both_roles_for_one_existing_person(self):
        customer=ServiceAdapter(self,'customer');supplier=ServiceAdapter(self,'supplier')
        self.restrict(self.actor,'view_person','add_customer','add_supplier')
        person_before=Person.objects.values().get(pk=self.visible_person.pk)
        c=customer.create(self.actor,self.a,self.visible_person.pk)
        s=supplier.create(self.actor,self.a,self.visible_person.pk)
        self.assertEqual((c.person_id,s.person_id),(self.visible_person.pk,self.visible_person.pk))
        self.assertEqual(Person.objects.values().get(pk=self.visible_person.pk),person_before)


class MaintenanceConcurrencyFixture(TransactionTestCase):
    def setUp(self):
        require_isolated_postgresql(self)
        self.actor=get_user_model().objects.create_user('race-operator')
        legal=Person.objects.create(identification='RACE-LEGAL',person_type='LEGAL',full_name='Legal')
        self.company=Company.objects.create(person=legal)
        self.person=Person.objects.create(identification='RACE-PERSON',person_type='LEGAL',full_name='Shared')
        self.actor.profile.companies.add(self.company)
        CompanyPersonAccess.objects.create(company=self.company,person=self.person)
        self.actor.user_permissions.add(*Permission.objects.filter(content_type__app_label='people',codename__in=['view_person','add_customer','add_supplier']))

    def race(self,operation):
        start=Barrier(2)
        def worker():
            try:
                with connection.cursor() as c:
                    c.execute("SET lock_timeout='5s'");c.execute("SET statement_timeout='15s'")
                    c.execute('SELECT pg_backend_pid()');pid=c.fetchone()[0]
                start.wait(timeout=10)
                try: result=operation()
                except ValidationError:result='duplicate'
                return pid,result
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(worker) for _ in range(2)]
            outcomes=[f.result(timeout=25) for f in futures]
        self.assertEqual(len({pid for pid,_ in outcomes}),2)
        return [outcome for _,outcome in outcomes]


@tag('cat023_maintenance_red')
class MaintenanceConcurrencyRedTests(MaintenanceConcurrencyFixture):
    def test_customer_service_creation_collision_has_one_winner(self):self.service_race('customer',Customer)
    def test_supplier_service_creation_collision_has_one_winner(self):self.service_race('supplier',Supplier)

    def service_race(self,role,model):
        api=ServiceAdapter(self,role)  # Missing seam fails before starting threads.
        actor_id,company_id,person_id=self.actor.pk,self.company.pk,self.person.pk
        before_person=list(Person.objects.order_by('pk').values())
        before_access=list(CompanyPersonAccess.objects.order_by('pk').values())
        inserts=Barrier(2)
        evidence=[]
        def create():
            attempted=False
            def observe_insert(execute,sql,params,many,context):
                nonlocal attempted
                # Django's cursor contract: identify INSERT target only; do not parse columns/parameters.
                normalized=sql.lstrip().upper()
                target=connection.ops.quote_name(model._meta.db_table).upper()
                if not attempted and normalized.startswith('INSERT INTO '+target+' '):
                    attempted=True
                    inserts.wait(timeout=10)
                    try:
                        return execute(sql,params,many,context)
                    except IntegrityError as error:
                        evidence.append((error.__cause__.sqlstate,error.__cause__.diag.constraint_name))
                        raise
                return execute(sql,params,many,context)
            with connection.execute_wrapper(observe_insert):
                obj=api.create(get_user_model().objects.get(pk=actor_id),Company.objects.get(pk=company_id),person_id)
            return obj.pk
        outcomes=self.race(create)
        self.assertEqual(evidence,[('23505',f'people_{role}_company_person_unique')])
        self.assertEqual(outcomes.count('duplicate'),1)
        winners=[v for v in outcomes if v!='duplicate'];self.assertEqual(len(winners),1)
        self.assertEqual(list(model.objects.values_list('pk',flat=True)),winners)
        self.assertEqual(model.objects.get().created_by_id,actor_id)
        self.assertEqual(list(Person.objects.order_by('pk').values()),before_person)
        self.assertEqual(list(CompanyPersonAccess.objects.order_by('pk').values()),before_access)

    def test_database_is_final_authority_for_concurrent_customer_pair(self):self.database_race(Customer)
    def test_database_is_final_authority_for_concurrent_supplier_pair(self):self.database_race(Supplier)

    def database_race(self,model):
        company_id,person_id=self.company.pk,self.person.pk
        def insert():
            try:
                with transaction.atomic():obj=model.objects.create(company_id=company_id,person_id=person_id)
                return obj.pk
            except IntegrityError as error:
                self.assertEqual(error.__cause__.sqlstate,'23505')
                self.assertEqual(error.__cause__.diag.constraint_name,f'people_{model._meta.model_name}_company_person_unique')
                # Solo el harness convierte esta colisión exacta en resultado.
                raise ValidationError('duplicate') from error
        outcomes=self.race(insert)
        self.assertEqual(outcomes.count('duplicate'),1)
        self.assertEqual(model.objects.count(),1)


@tag('cat023_maintenance_red')
class MaintenancePostWriteAtomicityRedTests(MaintenanceConcurrencyFixture):
    """TransactionTestCase: no atomic del llamador que pueda ocultar el defecto."""
    def test_customer_create_rolls_back_after_actual_insert(self):self.post_write_failure('customer',Customer,'create')
    def test_supplier_create_rolls_back_after_actual_insert(self):self.post_write_failure('supplier',Supplier,'create')
    def test_customer_update_rolls_back_after_actual_update(self):self.post_write_failure('customer',Customer,'update')
    def test_supplier_update_rolls_back_after_actual_update(self):self.post_write_failure('supplier',Supplier,'update')
    def test_customer_activity_rolls_back_after_actual_update(self):self.post_write_failure('customer',Customer,'active')
    def test_supplier_activity_rolls_back_after_actual_update(self):self.post_write_failure('supplier',Supplier,'active')

    def post_write_failure(self,role,model,operation):
        api=ServiceAdapter(self,role)
        self.actor.user_permissions.add(Permission.objects.get(content_type__app_label='people',codename=f'change_{role}'))
        self.assertTrue(connection.get_autocommit());self.assertFalse(connection.in_atomic_block)
        obj=None if operation=='create' else model.objects.create(company=self.company,person=self.person,notes='Original')
        table=connection.ops.quote_name(model._meta.db_table).upper()
        with connection.cursor() as cursor:
            cursor.execute('CREATE TEMP TABLE cat023_atomic_probe (id integer NOT NULL)')
        reached=[]
        def after_real_write(execute,statement,params,many,context):
            result=execute(statement,params,many,context)
            verb='INSERT INTO ' if operation=='create' else 'UPDATE '
            if statement.lstrip().upper().startswith(verb+table):
                reached.append(True)
                with connection.cursor() as cursor:
                    cursor.execute('INSERT INTO cat023_atomic_probe VALUES (NULL)')
            return result
        before=database_snapshot()
        try:
            with self.assertRaises(IntegrityError) as caught:
                with connection.execute_wrapper(after_real_write):
                    if operation=='create':api.create(self.actor,self.company,self.person.pk)
                    elif operation=='update':api.update(self.actor,self.company,obj.pk,{'notes':'Attempt'})
                    else:api.active(self.actor,self.company,obj.pk,False)
            self.assertEqual(caught.exception.__cause__.sqlstate,'23502')
            self.assertTrue(reached,'El fallo debe ocurrir después de ejecutar SQL real')
            self.assertFalse(connection.in_atomic_block)
            self.assertTrue(connection.get_autocommit())
            self.assertEqual(database_snapshot(),before)
        finally:
            with connection.cursor() as cursor:cursor.execute('DROP TABLE cat023_atomic_probe')
