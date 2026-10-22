"""CAT-02.2A FASE 1.2 RED: Customer empresarial directo.

Las pruebas empresariales que necesitan Customer.company fallan explícitamente
antes de crear ese Customer; no ejercitan todavía su contrato posterior.
Se usan únicamente CreateSale y las rutas existentes de Ventas.

Pendientes de integración (no tests aprobados, ni PASS/skip/xfail):
* Creación autorizada y rechazo de Company inexistente/no autorizada: no hay
  entrada de creación ni política pública aprobada; no se inventa una API.
* Señal distinguible de detención por clasificación y representación explícita
  de pendientes: faltan contratos aprobados. approved_classification_stops es
  configuración del harness, vacía hasta acordar esa señal, no una API exigida.
* La evidencia exclusiva de A es candidata de clasificación; nunca se exige
  backfill automático. La ausencia/ambigüedad de evidencia prohíbe asignación.

Las migraciones se limitan al primer estado que satisface el modelo aprobado
más las dependencias necesarias. Sin transición, no se ejecuta ningún migrate.
La ejecución RED actual usa PostgreSQL TEST con MIGRATE=False; cuando exista
la transición, el harness histórico necesita TEST con migraciones habilitadas.
"""
from datetime import date
from decimal import Decimal

from django.apps import apps
from django.contrib.auth.models import Permission
from django.core.exceptions import FieldDoesNotExist, PermissionDenied, ValidationError
from django.db import IntegrityError, connection, models, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, tag
from django.urls import reverse

from catalog.models import Product
from core.constants.document_type_codes import DocumentTypeCodes
from core.models import DocumentType
from core.services.context_service import clear_context
from inventory.models import Warehouse
from people.identification import FINAL_CONSUMER_ID
from people.models import Customer, Person
from people.tests.person_ui_support import PersonUIFixture
from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from sales.models import Sale
from sales.use_cases.create_sale import CreateSale


def require_isolated_postgresql(test):
    test.assertEqual(connection.vendor, 'postgresql')
    name = connection.settings_dict['NAME']
    test.assertTrue(name.startswith('test_'))
    test.assertNotEqual(name, 'sisadmi_erp_dev')
    test.assertFalse(connection.settings_dict['TEST'].get('MIRROR'))
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        test.assertEqual(cursor.fetchone()[0], name)


@tag('cat022a_customer_company_red')
class CustomerCompanyRedTests(PersonUIFixture):
    def setUp(self):
        # Guard before shared fixture writes, independently of the runner.
        require_isolated_postgresql(self)
        super().setUp()
        self.actor.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='sales', codename__in=['view_sale', 'add_sale'],
        ))
        self.addCleanup(clear_context)
        self.grant(self.actor, 'view_customer', 'add_customer', 'change_customer')
        DocumentType.objects.get_or_create(
            code=DocumentTypeCodes.SALES_INVOICE,
            defaults={'name': 'Factura de venta', 'category': 'SALES'},
        )
        self.warehouse = Warehouse.objects.create(company=self.a, branch=self.branch,
                                                  code='RED-W', name='RED')
        self.product = Product.objects.create(company=self.a, code='RED-P', name='RED')

    def company_field(self):
        try:
            field = Customer._meta.get_field('company')
        except FieldDoesNotExist:
            self.fail('RED esperado: Customer todavía no pertenece directamente a Company')
        self.assertIs(field.related_model, type(self.a))
        return field

    def customer(self, company, person=None):
        self.company_field()
        return Customer.objects.create(company=company, person=person or self.visible_person)

    def final_consumer(self, company):
        return Customer.objects.get(
            company=company, person__identification=FINAL_CONSUMER_ID,
        )

    def dto(self, customer, **changes):
        values = dict(company_id=self.a.pk, branch_id=self.branch.pk,
                      warehouse_id=self.warehouse.pk, customer_id=customer.pk,
                      issue_date=date(2026, 10, 10), notes='RED',
                      details=[SaleDetailDTO(product_id=self.product.pk, quantity=Decimal('1'),
                                             unit_price=Decimal('1'), discount=Decimal('0'))])
        values.update(changes)
        return SaleCreateDTO(**values)

    def test_01_same_global_person_can_be_customer_in_two_companies(self):
        count = Person.objects.count()
        first = self.customer(self.a)
        second = self.customer(self.b)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.person_id, second.person_id)
        self.assertEqual(Person.objects.count(), count)
        field = Customer._meta.get_field('person')
        self.assertIsInstance(field, models.ForeignKey)
        self.assertFalse(field.unique)
        self.assertNotIn('companycustomer', apps.all_models['people'])

    def test_02_duplicate_company_person_is_rejected_by_database(self):
        self.customer(self.a)
        constraints = Customer._meta.constraints
        self.assertTrue(any(isinstance(c, models.UniqueConstraint)
                            and set(c.fields) == {'company', 'person'} for c in constraints))
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.customer(self.a)
        self.assertEqual(Customer.objects.filter(company=self.a, person=self.visible_person).count(), 1)

    def test_03_nonexistent_company_is_rejected_by_database(self):
        self.company_field()
        absent_pk = max(self.a.pk, self.b.pk) + 1000
        with self.assertRaises(IntegrityError), transaction.atomic():
            Customer.objects.create(company_id=absent_pk, person=self.visible_person)
            connection.check_constraints()
        self.assertFalse(Customer.objects.filter(company_id=absent_pk).exists())

    def test_04_sales_customer_options_are_scoped_and_switch_with_company(self):
        first = self.customer(self.a)
        second = self.customer(self.b, self.hidden_person)
        for company, branch, expected, excluded in (
                (self.a, self.branch, first, second),
                (self.b, self.branch_b, second, first)):
            with self.subTest(company=company.pk):
                final_consumer = self.final_consumer(company)
                foreign_final_consumer = self.final_consumer(excluded.company)
                self.context(self.client, company, branch)
                response = self.client.get(reverse('sale_create'))
                self.assertEqual(response.status_code, 200)
                choices = response.context['form'].fields['customer_id'].queryset
                choice_ids = set(choices.values_list('pk', flat=True))
                self.assertEqual(choice_ids, {expected.pk, final_consumer.pk})
                self.assertNotIn(excluded.pk, choice_ids)
                self.assertNotIn(foreign_final_consumer.pk, choice_ids)
                self.assertNotContains(response, f'<option value="{excluded.pk}">')
                self.assertNotContains(response, f'<option value="{foreign_final_consumer.pk}">')

    def business_snapshot(self):
        # Compare existing rows too, not only counts of newly created Sales.
        return {model._meta.label: list(model.objects.order_by('pk').values())
                for model in apps.get_models()
                if model._meta.app_label in {'sales', 'core', 'people', 'inventory', 'sri'}}

    def sale_payload(self, customer):
        return {'customer_id': customer.pk, 'warehouse_id': self.warehouse.pk,
                'issue_date': '2026-10-10', 'notes': 'RED POST',
                'details-TOTAL_FORMS': '1', 'details-INITIAL_FORMS': '0',
                'details-MIN_NUM_FORMS': '1', 'details-MAX_NUM_FORMS': '1000',
                'details-0-product_id': self.product.pk, 'details-0-quantity': '1',
                'details-0-unit_price': '1', 'details-0-discount': '0'}

    def test_04_shared_person_selector_uses_company_customer_identity(self):
        first = self.customer(self.a)
        second = self.customer(self.b)
        for company, branch, selected, excluded in (
                (self.a, self.branch, first, second),
                (self.b, self.branch_b, second, first)):
            with self.subTest(company=company.pk):
                final_consumer = self.final_consumer(company)
                foreign_final_consumer = self.final_consumer(excluded.company)
                self.context(self.client, company, branch)
                response = self.client.get(reverse('sale_create'))
                self.assertEqual(response.status_code, 200)
                choices = response.context['form'].fields['customer_id'].queryset
                choice_ids = set(choices.values_list('pk', flat=True))
                self.assertEqual(choice_ids, {selected.pk, final_consumer.pk})
                self.assertNotIn(excluded.pk, choice_ids)
                self.assertNotIn(foreign_final_consumer.pk, choice_ids)
                self.assertNotContains(response, f'<option value="{excluded.pk}">')
                self.assertNotContains(response, f'<option value="{foreign_final_consumer.pk}">')

    def test_04_foreign_customer_information_is_absent_from_rendered_html(self):
        local = self.customer(self.a)
        self.customer(self.b, self.hidden_person)
        response = self.client.get(reverse('sale_create'))
        self.assertContains(response, local.person.full_name)
        for marker in (self.hidden_person.full_name, self.hidden_person.identification,
                       self.hidden_person.email, self.hidden_person.phone,
                       self.hidden_person.address):
            with self.subTest(marker=marker):
                self.assertNotContains(response, marker)

    def test_05_create_sale_rejects_tampered_foreign_customer_atomically(self):
        foreign = self.customer(self.b, self.hidden_person)
        before = self.business_snapshot()
        with self.assertRaises((ValidationError, PermissionDenied, ValueError)):
            CreateSale.execute(self.dto(foreign))
        self.assertEqual(self.business_snapshot(), before)

    def test_05_sale_post_with_local_customer_has_a_valid_control(self):
        local = self.customer(self.a)
        response = self.client.post(reverse('sale_create'), self.sale_payload(local))
        self.assertEqual(response.status_code, 302)
        sale = Sale.objects.get(customer=local)
        self.assertEqual(response['Location'], reverse('sale_detail', args=[sale.pk]))
        self.assertEqual((sale.company_id, sale.branch_id), (self.a.pk, self.branch.pk))
        self.assertEqual(sale.details.count(), 1)

    def test_05_sale_post_rejects_foreign_customer_without_partial_effects(self):
        self.customer(self.a)
        foreign = self.customer(self.b, self.hidden_person)
        before = self.business_snapshot()
        response = self.client.post(reverse('sale_create'), self.sale_payload(foreign))
        self.assertEqual(response.status_code, 200)
        self.assertIn('customer_id', response.context['form'].errors)
        self.assertFalse(any(response.context['formset'].errors))
        self.assertEqual(self.business_snapshot(), before)
        self.assertNotContains(response, self.hidden_person.full_name)

    def test_06_revoked_membership_blocks_customer_selector(self):
        self.actor.profile.companies.remove(self.a)
        response = self.client.get(reverse('sale_create'))
        self.assertRedirects(response, reverse('select_company'), fetch_redirect_response=False)

    def test_06_missing_company_blocks_customer_selector(self):
        self.context(self.client)
        response = self.client.get(reverse('sale_create'))
        self.assertRedirects(response, reverse('select_company'), fetch_redirect_response=False)

    def test_06_valid_membership_and_context_can_open_customer_selector(self):
        response = self.client.get(reverse('sale_create'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('customer_id', response.context['form'].fields)

    def test_06_inactive_company_blocks_customer_selector(self):
        self.a.is_active = False
        self.a.save(update_fields=['is_active'])
        response = self.client.get(reverse('sale_create'))
        self.assertRedirects(response, reverse('select_company'), fetch_redirect_response=False)

    def test_06_missing_branch_blocks_customer_selector(self):
        self.context(self.client, self.a)
        response = self.client.get(reverse('sale_create'))
        self.assertRedirects(response, reverse('select_branch'), fetch_redirect_response=False)

    def test_07_revoked_branch_membership_blocks_customer_selector(self):
        self.actor.profile.branches.remove(self.branch)
        response = self.client.get(reverse('sale_create'))
        self.assertRedirects(response, reverse('select_branch'), fetch_redirect_response=False)

    def test_06_anonymous_actor_cannot_access_customer_selector(self):
        self.client.logout()
        response = self.client.get(reverse('sale_create'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_07_foreign_branch_cannot_bypass_customer_access(self):
        self.context(self.client, self.a, self.branch_b)
        response = self.client.get(reverse('sale_create'))
        self.assertRedirects(response, reverse('select_branch'), fetch_redirect_response=False)

    def test_07_create_sale_rejects_foreign_branch_without_persistence(self):
        customer = self.customer(self.a)
        before = self.business_snapshot()
        with self.assertRaises(ValidationError):
            CreateSale.execute(self.dto(customer, branch_id=self.branch_b.pk))
        self.assertEqual(self.business_snapshot(), before)

    def test_06_inactive_actor_cannot_access_customer_selector(self):
        self.actor.is_active = False
        self.actor.save(update_fields=['is_active'])
        response = self.client.get(reverse('sale_create'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response['Location'])

    def test_06_forged_unauthorized_company_context_is_rejected(self):
        self.actor.profile.companies.remove(self.b)
        self.context(self.client, self.b, self.branch_b)
        response = self.client.get(reverse('sale_create'))
        self.assertRedirects(response, reverse('select_company'), fetch_redirect_response=False)

    def test_07_inactive_branch_cannot_access_customer_selector(self):
        self.branch.is_active = False
        self.branch.save(update_fields=['is_active'])
        response = self.client.get(reverse('sale_create'))
        self.assertRedirects(response, reverse('select_branch'), fetch_redirect_response=False)

    def test_06_revoked_company_access_blocks_sale_post_without_effects(self):
        customer = self.customer(self.a)
        self.actor.profile.companies.remove(self.a)
        before = self.business_snapshot()
        response = self.client.post(reverse('sale_create'), self.sale_payload(customer))
        self.assertRedirects(response, reverse('select_company'), fetch_redirect_response=False)
        self.assertEqual(self.business_snapshot(), before)

    def test_07_foreign_branch_context_blocks_sale_post_without_effects(self):
        customer = self.customer(self.a)
        self.context(self.client, self.a, self.branch_b)
        before = self.business_snapshot()
        response = self.client.post(reverse('sale_create'), self.sale_payload(customer))
        self.assertRedirects(response, reverse('select_branch'), fetch_redirect_response=False)
        self.assertEqual(self.business_snapshot(), before)

    def test_08_sale_customer_fk_still_targets_customer(self):
        field = Sale._meta.get_field('customer')
        self.assertIsInstance(field, models.ForeignKey)
        self.assertIs(field.related_model, Customer)

    def test_08_sale_retains_customer_pk_and_person_reference(self):
        customer = self.customer(self.a)
        sale = CreateSale.execute(self.dto(customer))
        sale.refresh_from_db()
        self.assertEqual(sale.customer_id, customer.pk)
        self.assertEqual(sale.customer.person_id, self.visible_person.pk)


@tag('cat022a_customer_company_red')
class CustomerLegacyMigrationRedTests(TransactionTestCase):
    """Historical preservation, not approval of an automatic backfill.

    No stop signal is approved yet: an empty tuple catches no exceptions.
    Infrastructure/programming errors therefore remain errors, never success.
    Once agreed, register only the approved classification signal here and
    exercise the stop branch, including full schema/data rollback assertions.
    """
    approved_classification_stops = ()
    before = [('people', '0004_backfill_company_person_access'),
              ('sales', '0008_sale_payment_method_saledetailtax_tax_category')]

    def setUp(self):
        require_isolated_postgresql(self)
        loader = MigrationLoader(None)
        leaves = loader.graph.leaf_nodes('people')
        self.assertEqual(len(leaves), 1, 'Integración pendiente: grafo people divergente')
        baseline = set().union(*(set(loader.graph.forwards_plan(key)) for key in self.before))
        self.target = None
        for key in loader.graph.forwards_plan(leaves[0]):
            if key[0] != 'people' or key in baseline:
                continue
            candidate = loader.project_state([key, self.before[1]]).apps.get_model('people', 'Customer')
            fields = {field.name: field for field in candidate._meta.fields}
            if ('company' in fields and isinstance(fields['person'], models.ForeignKey)
                    and not fields['person'].unique and any(
                        isinstance(c, models.UniqueConstraint) and set(c.fields) == {'company', 'person'}
                        for c in candidate._meta.constraints)):
                self.target = [key, self.before[1]]
                break
        self.assertIsNotNone(self.target,
                             'RED esperado: falta transición Customer empresarial con FK y unicidad aprobadas')
        target_nodes = set().union(*(set(loader.graph.forwards_plan(key)) for key in self.target))
        self.transition_nodes = target_nodes - baseline
        executor = MigrationExecutor(connection)
        self.initial_applied = set(executor.loader.applied_migrations)
        relevant = {key for key in self.initial_applied if key[0] in {'people', 'sales'}}
        self.assertTrue(relevant, 'Integración pendiente: harness histórico requiere TEST con migraciones habilitadas')
        self.original_targets = [key for key in relevant if not any(
            child.key in relevant for child in loader.graph.node_map[key].children)]
        # Never roll back unrelated descendants or migrate the whole project.
        for migration, backwards in executor.migration_plan(self.before):
            self.assertIn((migration.app_label, migration.name), self.transition_nodes)
            self.assertTrue(backwards)
        self.old = loader.project_state(self.before).apps
        self.customer_pk = None
        self.sale_ids = []
        # Register restoration BEFORE the first schema mutation or assertion.
        self.addCleanup(self.restore_schema)
        executor.migrate(self.before)
        self.assertNotIn('company', {f.name for f in self.old.get_model('people', 'Customer')._meta.fields})

    def restore_schema(self):
        try:
            if self.sale_ids:
                self.old.get_model('sales', 'Sale').objects.filter(pk__in=self.sale_ids).delete()
            if self.customer_pk is not None:
                self.old.get_model('people', 'Customer').objects.filter(pk=self.customer_pk).delete()
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(self.original_targets)
            self.assertEqual(set(MigrationExecutor(connection).loader.applied_migrations), self.initial_applied)

    def database_snapshot(self, only_sales=False):
        """Raw SQL observes added Company columns too, unlike the old ORM state."""
        snapshot = {}
        with connection.cursor() as cursor:
            tables = connection.introspection.table_names(cursor)
            for table in sorted(tables):
                if only_sales and not table.startswith('sales_'):
                    continue
                description = connection.introspection.get_table_description(cursor, table)
                cursor.execute(f'SELECT * FROM {connection.ops.quote_name(table)}')
                snapshot[table] = (
                    tuple((c.name, c.type_code, c.null_ok) for c in description),
                    connection.introspection.get_constraints(cursor, table),
                    sorted(cursor.fetchall(), key=repr),
                )
        return snapshot

    def legacy(self, companies):
        PersonModel = self.old.get_model('people', 'Person')
        CompanyModel = self.old.get_model('core', 'Company')
        person = PersonModel.objects.create(identification='LEGACY-C', person_type='NATURAL',
                                            full_name='Legacy customer')
        customer = self.old.get_model('people', 'Customer').objects.create(person=person)
        self.customer_pk = customer.pk
        self.original_customer = self.old.get_model('people', 'Customer').objects.values().get(pk=customer.pk)
        document_type, _ = self.old.get_model('core', 'DocumentType').objects.get_or_create(
            code=DocumentTypeCodes.SALES_INVOICE, defaults={'name': 'Venta', 'category': 'SALES'})
        self.company_ids = []
        for index in range(companies):
            legal = PersonModel.objects.create(identification=f'LEGACY-{index}',
                                                person_type='LEGAL', full_name='Company')
            company = CompanyModel.objects.create(person=legal)
            branch = self.old.get_model('core', 'Branch').objects.create(
                company=company, code='001', name='Main')
            warehouse = self.old.get_model('inventory', 'Warehouse').objects.create(
                company=company, branch=branch, code='W', name='Warehouse')
            sale = self.old.get_model('sales', 'Sale').objects.create(
                company=company, branch=branch, warehouse=warehouse,
                customer=customer, document_type=document_type)
            self.company_ids.append(company.pk)
            self.sale_ids.append(sale.pk)
        return customer.pk, person.pk

    def forward_or_approved_stop(self):
        before = self.database_snapshot()
        documents_before = self.database_snapshot(only_sales=True)
        executor = MigrationExecutor(connection)
        for migration, backwards in executor.migration_plan(self.target):
            self.assertIn((migration.app_label, migration.name), self.transition_nodes)
            self.assertFalse(backwards)
        try:
            executor.migrate(self.target)
        except self.approved_classification_stops:
            # Includes raw company_id if introduced, schema and migration records.
            # No generic RuntimeError/ValidationError is accepted as success.
            self.assertEqual(self.database_snapshot(), before)
            return None
        self.assertEqual(self.database_snapshot(only_sales=True), documents_before,
                         'Los documentos históricos no pueden modificarse')
        migrated = executor.loader.project_state(self.target).apps
        customer = migrated.get_model('people', 'Customer').objects.values().get(pk=self.customer_pk)
        for field, value in self.original_customer.items():
            self.assertEqual(customer[field], value, f'Campo histórico alterado: {field}')
        self.assertEqual(migrated.get_model('people', 'Customer').objects.count(), 1)
        return customer

    def test_09_migration_preserves_pk_person_and_existing_sale_references(self):
        pk, person_pk = self.legacy(1)
        evidence = set(self.old.get_model('sales', 'Sale').objects.filter(customer_id=pk)
                       .values_list('company_id', flat=True))
        self.assertEqual(evidence, {self.company_ids[0]})  # Candidate, not an automatic backfill mandate.
        customer = self.forward_or_approved_stop()
        if customer is not None:
            self.assertEqual((customer['id'], customer['person_id']), (pk, person_pk))
            self.assertIn(customer['company_id'], (None, self.company_ids[0]))

    def test_10_unidentified_legacy_customer_remains_pending_or_stops(self):
        legal = self.old.get_model('people', 'Person').objects.create(
            identification='UNRELATED', person_type='LEGAL', full_name='Unrelated')
        self.old.get_model('core', 'Company').objects.create(person=legal)
        pk, _ = self.legacy(0)
        self.assertFalse(self.old.get_model('sales', 'Sale').objects.filter(customer_id=pk).exists())
        customer = self.forward_or_approved_stop()
        if customer is not None:
            self.assertIsNone(customer['company_id'], 'Sin evidencia no hay Company asignable')

    def test_11_multicompany_legacy_customer_requires_explicit_classification(self):
        pk, _ = self.legacy(2)
        evidence = set(self.old.get_model('sales', 'Sale').objects.filter(customer_id=pk)
                       .values_list('company_id', flat=True))
        self.assertEqual(evidence, set(self.company_ids))
        self.assertEqual(len(evidence), 2)
        customer = self.forward_or_approved_stop()
        if customer is not None:
            self.assertIsNone(customer['company_id'], 'Evidencia multiempresa prohíbe elegir una sola Company')
