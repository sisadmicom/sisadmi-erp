"""Expansion evidence and safe rollback; frozen CAT-02.2A remains unchanged."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse

from catalog.models import Product
from core.models import DocumentType
from inventory.models import Warehouse
from people.models import Customer
from people.services.customer_company_evidence import inspect_customer_company_evidence
from people.tests.person_ui_support import PersonUIFixture
from people.tests.test_customer_company_cat022a_red import require_isolated_postgresql
from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from sales.models import Sale, SaleDetail
from sales.use_cases.create_sale import CreateSale


class CustomerCompanyGreenTests(PersonUIFixture):
    def setUp(self):
        require_isolated_postgresql(self)
        super().setUp()
        self.customer = Customer.objects.create(person=self.visible_person)
        self.document_type = DocumentType.objects.get(code=Sale.DOCUMENT_TYPE_CODE)
        self.warehouse = Warehouse.objects.create(company=self.a, branch=self.branch, code='W', name='W')

    def historical_sale(self, company, branch):
        warehouse = Warehouse.objects.create(company=company, branch=branch, code='H', name='H')
        return Sale.objects.create(company=company, branch=branch, warehouse=warehouse,
                                   customer=self.customer, document_type=self.document_type)

    def records(self):
        return (list(Customer.objects.order_by('pk').values()), list(Sale.objects.order_by('pk').values()))

    def test_no_evidence_does_not_infer_from_membership_or_existing_companies(self):
        before = self.records()
        evidence = inspect_customer_company_evidence(self.customer)
        self.assertEqual(evidence.document_company_ids, frozenset())
        self.assertIsNone(evidence.candidate_company_id)
        self.assertIsNone(evidence.assigned_company_id)
        self.assertEqual(self.records(), before)

    def test_exclusive_evidence_is_only_a_candidate_without_assignment(self):
        self.historical_sale(self.a, self.branch)
        before = self.records()
        evidence = inspect_customer_company_evidence(self.customer)
        self.assertEqual(evidence.candidate_company_id, self.a.pk)
        self.assertFalse(evidence.is_ambiguous)
        self.assertIsNone(evidence.assigned_company_id)
        self.assertEqual(self.records(), before)

    def test_multicompany_evidence_preserves_customer_and_all_documents(self):
        self.historical_sale(self.a, self.branch)
        self.historical_sale(self.b, self.branch_b)
        before = self.records()
        evidence = inspect_customer_company_evidence(self.customer)
        self.assertEqual(evidence.document_company_ids, frozenset((self.a.pk, self.b.pk)))
        self.assertTrue(evidence.is_ambiguous)
        self.assertIsNone(evidence.candidate_company_id)
        self.assertIsNone(evidence.assigned_company_id)
        self.assertEqual(self.records(), before)

    def test_unclassified_customer_is_not_an_operational_sales_choice(self):
        response = self.client.get(reverse('sale_create'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.customer.pk, response.context['form'].fields['customer_id'].queryset
                         .values_list('pk', flat=True))

    def test_unclassified_customer_cannot_create_new_sales(self):
        product = Product.objects.create(company=self.a, code='P', name='P')
        before = self.records()
        dto = SaleCreateDTO(company_id=self.a.pk, branch_id=self.branch.pk,
                            warehouse_id=self.warehouse.pk, customer_id=self.customer.pk,
                            issue_date=date(2026, 10, 10), notes='', details=[
                                SaleDetailDTO(product_id=product.pk, quantity=Decimal('1'),
                                              unit_price=Decimal('1'), discount=Decimal('0'))])
        with self.assertRaises(ValidationError):
            CreateSale.execute(dto)
        self.assertEqual(self.records(), before)
        self.assertFalse(SaleDetail.objects.exists())

    def assert_reverse_rejected_without_changes(self):
        executor = MigrationExecutor(connection)
        applied = set(executor.loader.applied_migrations)
        before = self.records()
        with self.assertRaises(IrreversibleError):
            executor.migrate([('people', '0004_backfill_company_person_access'),
                              ('sales', '0008_sale_payment_method_saledetailtax_tax_category')])
        self.assertEqual(self.records(), before)
        self.assertEqual(set(MigrationExecutor(connection).loader.applied_migrations), applied)
        with connection.cursor() as cursor:
            columns = connection.introspection.get_table_description(cursor, Customer._meta.db_table)
        self.assertIn('company_id', {column.name for column in columns})

    def test_reverse_preserves_explicit_company_assignments_by_rejecting_data_loss(self):
        self.customer.company = self.a
        self.customer.save(update_fields=['company'])
        self.historical_sale(self.a, self.branch)
        self.assert_reverse_rejected_without_changes()

    def test_reverse_rejects_multiple_legacy_customers_for_the_same_person(self):
        Customer.objects.create(person=self.visible_person)
        self.assert_reverse_rejected_without_changes()
