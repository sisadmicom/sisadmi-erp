"""CAT-02.3 FASE 5.1: actividad documental, sin GREEN.

Entradas reales, sin actor nuevo en DTOs ni política Person documental.
ValidationError es el rechazo de datos comerciales ya usado por los creadores
y PurchaseValidator. ValueError solo verifica condiciones
históricas concretas; errores SQL/import/programación nunca cuentan como éxito.
Snapshots incluyen filas y Sequence ERP, no nextval PostgreSQL ni efectos externos.
Consulta histórica usa ORM empresarial existente: no inventa Views de Compras.
"""
from datetime import date
from decimal import Decimal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.test import tag

from core.models import Company, DocumentType, Sequence
from inventory.models import Stock, StockMovement
from people.models import CompanyPersonAccess, Person
from people.tests.test_customer_company_cat022a_red import require_isolated_postgresql
from sales.tests.sale_manifest_test_support import SaleManifestFixture
from purchases.tests.purchase_manifest_test_support import PurchaseManifestFixture
from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from sales.models import Sale, SaleMovement
from purchases.models import Purchase, PurchaseMovement
from sales.use_cases.create_sale import CreateSale
from sales.use_cases.confirm_sale import ConfirmSale
from sales.use_cases.cancel_sale import CancelSale
from purchases.use_cases.create_purchase import CreatePurchase
from purchases.services.purchase_service import PurchaseService
from purchases.use_cases.confirm_purchase import ConfirmPurchase
from purchases.use_cases.cancel_purchase import CancelPurchase
from sales.dto.sales_return_create_dto import SalesReturnCreateDTO
from sales.dto.sales_return_detail_dto import SalesReturnDetailDTO
from sales.use_cases.create_sales_return import CreateSalesReturn
from sales.use_cases.confirm_sales_return import ConfirmSalesReturn
from sales.use_cases.cancel_sales_return import CancelSalesReturn
from purchases.dto.purchase_return_create_dto import PurchaseReturnCreateDTO
from purchases.dto.purchase_return_detail_dto import PurchaseReturnDetailDTO
from purchases.use_cases.create_purchase_return import CreatePurchaseReturn
from purchases.use_cases.confirm_purchase_return import ConfirmPurchaseReturn
from purchases.use_cases.cancel_purchase_return import CancelPurchaseReturn


def snapshot():
    return {model._meta.label: list(model.objects.order_by('pk').values())
            for model in apps.get_models() if model._meta.app_label in {
                'people', 'core', 'catalog', 'sales', 'purchases', 'inventory', 'sri', 'users', 'auth'}}


class DocumentActivityContracts:
    def setUp(self):
        require_isolated_postgresql(self)
        super().setUp()
        self.actor = get_user_model().objects.create_user('document-activity-operator')
        self.other_company = Company.objects.create(person=Person.objects.create(
            identification='DOC-ACTIVITY-OTHER', person_type='LEGAL', full_name='Otra empresa'))
        self.role = self.customer if self.kind == 'sale' else self.supplier
        self.warehouse = self.warehouse if self.kind == 'sale' else self.warehouse_a
        self.second_product = self.product2 if self.kind == 'sale' else self.product_2
        if self.kind == 'purchase':
            for product in (self.product, self.second_product):
                Stock.objects.create(company=self.company, branch=self.branch, warehouse=self.warehouse,
                    product=product, quantity=Decimal('0'), reserved_quantity=Decimal('0'))
        CompanyPersonAccess.objects.create(company=self.company, person=self.role.person)
        self.document_model = Sale if self.kind == 'sale' else Purchase
        self.manifest_model = SaleMovement if self.kind == 'sale' else PurchaseMovement
        for code in ('SALES_RETURN', 'PURCHASE_RETURN'):
            Sequence.objects.create(company=self.company, branch=self.branch,
                document_type=DocumentType.objects.get(code=code), name=code, prefix='DA-', next_number=1)

    def dto(self, multiline=False):
        products = [self.product, self.second_product] if multiline else [self.product]
        common = dict(company_id=self.company.pk, branch_id=self.branch.pk,
                      issue_date=date(2026, 10, 11), notes='Document activity RED')
        if self.kind == 'sale':
            return SaleCreateDTO(**common, customer_id=self.role.pk, warehouse_id=self.warehouse.pk,
                details=[SaleDetailDTO(p.pk, Decimal('5'), Decimal('10'), Decimal('0')) for p in products])
        return PurchaseCreateDTO(**common, supplier_id=self.role.pk,
            details=[PurchaseDetailDTO(p.pk, Decimal('5'), Decimal('10'), Decimal('0')) for p in products])

    def entries(self):
        return [('CreateSale.execute', CreateSale.execute)] if self.kind == 'sale' else [
            ('CreatePurchase.execute -> PurchaseCreator', CreatePurchase.execute),
            ('PurchaseService.create -> CreatePurchase -> PurchaseCreator', PurchaseService.create)]

    def create(self, multiline=False):
        return self.entries()[0][1](self.dto(multiline))

    def confirm_document(self, document):
        if self.kind == 'sale':ConfirmSale.execute(sale_id=document.pk, user=self.actor)
        else:ConfirmPurchase.execute(purchase_id=document.pk, user=self.actor)
        document.refresh_from_db()
        return document

    def cancel_document(self, document):
        if self.kind == 'sale':CancelSale.execute(sale_id=document.pk, user=self.actor)
        else:CancelPurchase.execute(purchase_id=document.pk, user=self.actor)
        document.refresh_from_db()
        return document

    def reject_unchanged(self, operation, exception=ValidationError):
        before = snapshot()
        # Capture the exception manually so snapshot assertions also execute when
        # missing validation unexpectedly accepts the invalid operation.
        rejected = False
        try:operation()
        except exception as error:
            rejected = True
            self.assertTrue(str(error))
        self.assertEqual(snapshot(), before, 'Rechazo debe preservar todas las filas, auditoría y numeración ERP')
        self.assertTrue(rejected, 'RED documental: falta rechazo de relación comercial no operativa')

    def change_role(self, **values):
        for name, value in values.items():setattr(self.role, name, value)
        self.role.save(update_fields=list(values))

    def assert_created(self, document):
        document.refresh_from_db()
        field = 'customer_id' if self.kind == 'sale' else 'supplier_id'
        self.assertEqual(getattr(document, field), self.role.pk)
        self.assertEqual(document.company_id, self.company.pk)
        self.assertEqual(document.status, 'DRAFT')
        self.assertFalse(document.number)
        self.assertEqual(document.details.count(), 1)
        self.assertEqual(document.details.get().quantity, Decimal('5'))
        self.assertFalse(self.manifest_model.objects.filter(**{self.kind: document}).exists())

    def check_creation(self, invalid=False):
        for name, entry in self.entries():
            with self.subTest(entry=name):
                if invalid:self.reject_unchanged(lambda: entry(self.dto()))
                else:self.assert_created(entry(self.dto()))

    def assert_confirmed(self, document):
        self.confirm_document(document)
        self.assertEqual(document.status, 'CONFIRMED')
        self.assertTrue(document.number)
        self.assertEqual(document.confirmed_by_id, self.actor.pk)
        self.assertEqual(self.manifest_model.objects.filter(**{self.kind: document}).count(), document.details.count())

    def test_01_creation_accepts_own_active_role(self):
        self.check_creation()

    def test_02_creation_rejects_inactive_role_without_writes(self):
        self.change_role(is_active=False)
        self.check_creation(invalid=True)

    def test_03_creation_rejects_foreign_role_without_writes(self):
        self.change_role(company=self.other_company)
        self.check_creation(invalid=True)

    def test_04_creation_rejects_unclassified_role_without_writes(self):
        self.change_role(company=None)
        self.check_creation(invalid=True)

    def test_05_creation_does_not_add_person_activity_condition(self):
        self.role.person.is_active = False
        self.role.person.save(update_fields=['is_active'])
        before = list(Person.objects.order_by('pk').values())
        self.check_creation()
        self.assertEqual(list(Person.objects.order_by('pk').values()), before)

    def test_06_creation_does_not_add_person_access_condition_or_grant(self):
        CompanyPersonAccess.objects.filter(company=self.company, person=self.role.person).delete()
        before = list(CompanyPersonAccess.objects.order_by('pk').values())
        self.check_creation()
        self.assertEqual(list(CompanyPersonAccess.objects.order_by('pk').values()), before)

    def test_07_confirmation_accepts_own_active_role(self):
        self.assert_confirmed(self.create())

    def test_08_confirmation_revalidates_deactivated_role(self):
        document = self.create()
        self.change_role(is_active=False)
        self.reject_unchanged(lambda: self.confirm_document(document))

    def test_09_confirmation_rejects_foreign_role(self):
        document = self.create()
        self.change_role(company=self.other_company)
        self.reject_unchanged(lambda: self.confirm_document(document))

    def test_10_confirmation_rejects_unclassified_role(self):
        document = self.create()
        self.change_role(company=None)
        self.reject_unchanged(lambda: self.confirm_document(document))

    def test_11_reactivation_allows_confirmation_of_same_draft(self):
        document = self.create()
        self.change_role(is_active=False)
        self.change_role(is_active=True)
        self.assert_confirmed(document)
        self.assertEqual(self.document_model.objects.count(), 1)

    def test_12_confirmation_does_not_add_person_activity_condition(self):
        document = self.create()
        self.role.person.is_active = False
        self.role.person.save(update_fields=['is_active'])
        before = list(Person.objects.order_by('pk').values())
        self.assert_confirmed(document)
        self.assertEqual(list(Person.objects.order_by('pk').values()), before)

    def test_13_confirmation_does_not_add_person_access_condition_or_grant(self):
        document = self.create()
        CompanyPersonAccess.objects.filter(company=self.company, person=self.role.person).delete()
        before = list(CompanyPersonAccess.objects.order_by('pk').values())
        self.assert_confirmed(document)
        self.assertEqual(list(CompanyPersonAccess.objects.order_by('pk').values()), before)

    def history(self, classification):
        document = self.create()
        self.assert_confirmed(document)
        if classification == 'inactive':self.change_role(is_active=False)
        elif classification == 'foreign':self.change_role(company=self.other_company)
        else:self.change_role(company=None)
        return document

    def historical_query(self, classification):
        document = self.history(classification)
        before = snapshot()
        found = self.document_model.objects.filter(company=self.company).get(pk=document.pk)
        self.assertEqual(found, document)
        self.assertEqual(found.customer_id if self.kind == 'sale' else found.supplier_id, self.role.pk)
        self.assertFalse(self.document_model.objects.filter(company=self.other_company, pk=document.pk).exists())
        self.assertEqual(snapshot(), before)

    def originals(self):
        return list(StockMovement.objects.order_by('pk').values())

    def assert_originals_preserved(self, rows):
        for row in rows:self.assertEqual(StockMovement.objects.values().get(pk=row['id']), row)

    def historical_cancel(self, classification):
        initial = list(Stock.objects.order_by('pk').values_list('product_id', 'quantity'))
        document = self.history(classification)
        originals = self.originals()
        self.cancel_document(document)
        self.assertEqual(document.status, 'CANCELLED')
        self.assertEqual(document.cancelled_by_id, self.actor.pk)
        self.assert_originals_preserved(originals)
        self.assertEqual(list(Stock.objects.order_by('pk').values_list('product_id', 'quantity')), initial)
        self.assertEqual(StockMovement.objects.filter(reverses__isnull=False).count(), len(originals))
        for original in originals:
            compensation = StockMovement.objects.values().get(reverses_id=original['id'])
            for field in ('quantity', 'unit_cost', 'company_id', 'branch_id', 'warehouse_id', 'product_id'):
                self.assertEqual(compensation[field], original[field], field)

    def return_document(self, document, quantity='2'):
        if self.kind == 'sale':
            return CreateSalesReturn.execute(SalesReturnCreateDTO(sale_id=document.pk,
                issue_date=date(2026, 10, 11), notes='Historical return',
                details=[SalesReturnDetailDTO(document.details.get().pk, Decimal(quantity))]))
        return CreatePurchaseReturn.execute(PurchaseReturnCreateDTO(purchase_id=document.pk,
            issue_date=date(2026, 10, 11), notes='Historical return',
            details=[PurchaseReturnDetailDTO(document.details.get().pk, Decimal(quantity))]))

    def historical_return(self, classification):
        document = self.history(classification)
        original_document = self.document_model.objects.values().get(pk=document.pk)
        original_details = list(document.details.values())
        originals = self.originals()
        stock_before = list(Stock.objects.order_by('pk').values_list('product_id', 'quantity'))
        ret = self.return_document(document)
        if self.kind == 'sale':ConfirmSalesReturn.execute(sales_return_id=ret.pk, user=self.actor)
        else:ConfirmPurchaseReturn.execute(purchase_return_id=ret.pk, user=self.actor)
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'CONFIRMED')
        self.assertEqual(ret.confirmed_by_id, self.actor.pk)
        return_movement = StockMovement.objects.exclude(pk__in=[row['id'] for row in originals]).get()
        self.assertEqual(return_movement.quantity, Decimal('2'))
        self.assertEqual(return_movement.unit_cost, originals[0]['unit_cost'])
        quantity = Stock.objects.get(company=self.company, product=self.product, warehouse=self.warehouse).quantity
        old = dict(stock_before)[self.product.pk]
        self.assertEqual(quantity, old + (Decimal('2') if self.kind == 'sale' else Decimal('-2')))
        if self.kind == 'sale':CancelSalesReturn.execute(sales_return_id=ret.pk, user=self.actor)
        else:CancelPurchaseReturn.execute(purchase_return_id=ret.pk, user=self.actor)
        ret.refresh_from_db()
        self.assertEqual(ret.status, 'CANCELLED')
        compensation = StockMovement.objects.get(reverses=return_movement)
        for field in ('quantity', 'unit_cost', 'company_id', 'branch_id', 'warehouse_id', 'product_id'):
            self.assertEqual(getattr(compensation, field), getattr(return_movement, field), field)
        self.assertEqual(list(Stock.objects.order_by('pk').values_list('product_id', 'quantity')), stock_before)
        self.assert_originals_preserved(originals)
        self.assertEqual(self.document_model.objects.values().get(pk=document.pk), original_document)
        self.assertEqual(list(document.details.values()), original_details)

    def test_14_query_after_deactivation(self):self.historical_query('inactive')
    def test_15_query_after_foreign_classification(self):self.historical_query('foreign')
    def test_16_query_after_null_classification(self):self.historical_query('null')
    def test_17_cancellation_after_deactivation(self):self.historical_cancel('inactive')
    def test_18_cancellation_after_foreign_classification(self):self.historical_cancel('foreign')
    def test_19_cancellation_after_null_classification(self):self.historical_cancel('null')
    def test_20_return_and_compensation_after_deactivation(self):self.historical_return('inactive')
    def test_21_return_and_compensation_after_foreign_classification(self):self.historical_return('foreign')
    def test_22_return_and_compensation_after_null_classification(self):self.historical_return('null')

    def test_23_inactive_role_does_not_allow_cancelling_draft(self):
        document = self.create()
        self.change_role(is_active=False)
        self.reject_unchanged(lambda: self.cancel_document(document), exception=ValueError)

    def test_24_inactive_role_does_not_allow_excess_return(self):
        document = self.history('inactive')
        if self.kind == 'sale':
            ret = self.return_document(document, quantity='6')
            operation = lambda: ConfirmSalesReturn.execute(sales_return_id=ret.pk, user=self.actor)
        else:
            # Purchase rejects excess at creation, Sale at confirmation.
            operation = lambda: self.return_document(document, quantity='6')
        self.reject_unchanged(operation)

    def observe_actual_movement_insert(self):
        observed = []
        def inserted(sender, instance, created, **kwargs):
            if created:
                self.assertTrue(StockMovement.objects.filter(pk=instance.pk).exists())
                observed.append(instance.product_id)
        post_save.connect(inserted, sender=StockMovement, weak=False)
        self.addCleanup(post_save.disconnect, inserted, sender=StockMovement)
        return observed


@tag('cat023_document_activity_red')
class SaleDocumentActivityRedTests(DocumentActivityContracts, SaleManifestFixture):
    kind = 'sale'

    def test_25_second_line_stock_failure_rolls_back_real_first_insert(self):
        document = self.create(multiline=True)
        Stock.objects.filter(product=self.second_product, warehouse=self.warehouse).update(quantity=0)
        observed = self.observe_actual_movement_insert()
        self.reject_unchanged(lambda: self.confirm_document(document), exception=ValidationError)
        self.assertIn(self.product.pk, observed)
        self.assertNotIn(self.second_product.pk, observed)


@tag('cat023_document_activity_red')
class PurchaseDocumentActivityRedTests(DocumentActivityContracts, PurchaseManifestFixture):
    kind = 'purchase'

    def test_25_second_line_cancellation_failure_rolls_back_real_first_compensation(self):
        document = self.create(multiline=True)
        self.assert_confirmed(document)
        self.change_role(is_active=False)
        # Existing domain condition: stock of the second product is no longer
        # available for cancellation; history and manifests remain intact.
        Stock.objects.filter(product=self.second_product, warehouse=self.warehouse).update(quantity=0)
        observed = self.observe_actual_movement_insert()
        self.reject_unchanged(lambda: self.cancel_document(document), exception=ValidationError)
        self.assertIn(self.product.pk, observed)
        self.assertNotIn(self.second_product.pk, observed)
