"""CAT-02.2B RED: Supplier empresarial y compatibilidad histórica de Compras.

Solo PostgreSQL TEST con migraciones habilitadas. No se inventan rutas,
selectores, actor en DTO ni servicios de clasificación. Los borradores
históricos se representan mediante ORM, no mediante la entrada de compras
nuevas. Sus movimientos se producen con servicios reales, sin mocks.

La primera expansión nullable posterior a people.0005 se descubre por estado,
no por nombre. Evidencia exclusiva es candidata, no mandato de backfill.
No hay señal aprobada de detención por clasificación: la expansión nullable
debe conservar pendientes; ese cierre posterior queda fuera de este RED.
La reversión protegida acepta solo IrreversibleError de Django, nunca una
excepción genérica de programación, infraestructura o validación.
"""
from datetime import date
from decimal import Decimal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import IntegrityError, connection, models, transaction
from django.db.migrations.exceptions import IrreversibleError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase, TransactionTestCase, tag
from django.test.utils import CaptureQueriesContext

from catalog.models import Product
from core.constants.document_status import DocumentStatus
from core.constants.document_type_codes import DocumentTypeCodes
from core.exceptions.inventory import InventoryException
from core.models import Branch, Company, DocumentType, Sequence
from core.services.context_service import clear_context
from inventory.constants.movement_type import MovementType
from inventory.models import Stock, StockMovement, Warehouse
from inventory.services.stock.increase_stock import IncreaseStock
from inventory.services.stock.decrease_stock import DecreaseStock
from people.models import Person, Supplier
from people.tests.test_customer_company_cat022a_red import require_isolated_postgresql
from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.dto.purchase_return_create_dto import PurchaseReturnCreateDTO
from purchases.dto.purchase_return_detail_dto import PurchaseReturnDetailDTO
from purchases.models import (Purchase, PurchaseDetail, PurchaseMovement,
                              PurchaseReturn, PurchaseReturnDetail, PurchaseReturnMovement)
from purchases.services.purchase_creator import PurchaseCreator
from purchases.use_cases.cancel_purchase import CancelPurchase
from purchases.use_cases.confirm_purchase import ConfirmPurchase
from purchases.use_cases.confirm_purchase_return import ConfirmPurchaseReturn
from purchases.use_cases.create_purchase import CreatePurchase
from purchases.use_cases.create_purchase_return import CreatePurchaseReturn


class SupplierFixture:
    """Contexto determinista compartido por contratos operativos e históricos."""

    def prepare_context(self):
        self.addCleanup(clear_context)
        self.actor = get_user_model().objects.create_user('supplier-red-operator')
        self.person = Person.objects.create(identification='SUP-RED', person_type='LEGAL',
                                            full_name='Proveedor compartido')
        self.a = Company.objects.create(person=Person.objects.create(
            identification='SUP-A', person_type='LEGAL', full_name='Empresa A'))
        self.b = Company.objects.create(person=Person.objects.create(
            identification='SUP-B', person_type='LEGAL', full_name='Empresa B'))
        self.branch = Branch.objects.create(company=self.a, code='001', name='A')
        self.branch_b = Branch.objects.create(company=self.b, code='001', name='B')
        self.warehouse = Warehouse.objects.create(company=self.a, branch=self.branch,
                                                  code='W', name='A', is_main=True)
        self.warehouse_b = Warehouse.objects.create(company=self.b, branch=self.branch_b,
                                                    code='W', name='B', is_main=True)
        self.product = Product.objects.create(company=self.a, code='P', name='A')
        self.product_b = Product.objects.create(company=self.b, code='P', name='B')
        # TransactionTestCase vacía catálogos entre casos: recrear únicamente
        # los tipos existentes con sus capacidades aprobadas, como los fixtures
        # de Compras; no depender de semillas que sobrevivan al flush.
        types = []
        for code, behavior in ((DocumentTypeCodes.PURCHASE_INVOICE, 'IN'),
                               (DocumentTypeCodes.PURCHASE_RETURN, 'OUT')):
            dtype, _ = DocumentType.objects.get_or_create(code=code, defaults={
                'name': code, 'category': 'PURCHASES', 'line_behavior': 'COMMERCIAL',
                'requires_detail': True, 'affects_inventory': True,
                'inventory_behavior': behavior, 'can_issue_electronic': False})
            types.append(dtype)
        self.purchase_type, self.return_type = types
        for company, branch in ((self.a, self.branch), (self.b, self.branch_b)):
            for dtype in (self.purchase_type, self.return_type):
                Sequence.objects.create(company=company, branch=branch, document_type=dtype,
                                        name=dtype.code, prefix='SUP-', next_number=1)

    def company_field(self):
        try:
            field = Supplier._meta.get_field('company')
        except FieldDoesNotExist:
            self.fail('RED esperado: Supplier.company todavía no existe')
        self.assertIsInstance(field, models.ForeignKey)
        self.assertIs(field.related_model, Company)
        return field

    def supplier(self, company):
        self.company_field()
        return Supplier.objects.create(company=company, person=self.person)

    def legacy_supplier(self):
        return Supplier.objects.create(person=self.person, notes='Legado sin clasificación',
                                       created_by=self.actor, updated_by=self.actor)

    def dto(self, supplier, **changes):
        values = dict(company_id=self.a.pk, branch_id=self.branch.pk, supplier_id=supplier.pk,
                      issue_date=date(2026, 10, 11), notes='Supplier RED', details=[
                          PurchaseDetailDTO(product_id=self.product.pk, quantity=Decimal('10'),
                                            unit_price=Decimal('10'), discount=Decimal('0'))])
        values.update(changes)
        return PurchaseCreateDTO(**values)

    def historical_purchase(self, supplier_id, *, company=None, confirmed=False, manifest=True):
        """Historia anterior a expansión: nunca se reclasifica para que pase un test."""
        company = self.a if company is None else company
        branch, product, warehouse = ((self.branch, self.product, self.warehouse)
                                      if company.pk == self.a.pk else
                                      (self.branch_b, self.product_b, self.warehouse_b))
        purchase = Purchase.objects.create(
            company=company, branch=branch, supplier_id=supplier_id,
            document_type=self.purchase_type, issue_date=date(2026, 9, 19),
            status=DocumentStatus.CONFIRMED if confirmed else DocumentStatus.DRAFT,
            number='HIST-SUP' if confirmed else '', notes='Historia inmutable',
            subtotal=Decimal('100'), tax=Decimal('0'), total=Decimal('100'))
        PurchaseDetail.objects.create(purchase=purchase, product=product, line=1,
                                      quantity=Decimal('10'), unit_price=Decimal('10'),
                                      subtotal=Decimal('100'), tax_amount=Decimal('0'),
                                      total=Decimal('100'))
        if confirmed:
            movement = IncreaseStock().execute(
                company=company, branch=branch, warehouse=warehouse, product=product,
                quantity=Decimal('10'), unit_cost=Decimal('10'),
                movement_type=MovementType.PURCHASE, document=purchase,
                return_movement=True)
            if manifest:
                PurchaseMovement.objects.create(purchase=purchase, stock_movement=movement)
        return purchase

    def make_return(self, purchase, quantity='3'):
        return CreatePurchaseReturn.execute(PurchaseReturnCreateDTO(
            purchase_id=purchase.pk, issue_date=date(2026, 10, 11), notes='Histórica', details=[
                PurchaseReturnDetailDTO(purchase_detail_id=purchase.details.get().pk,
                                        quantity=Decimal(quantity))]))

    def snapshot(self):
        # Filas persistidas de estos módulos; no incluye contadores de
        # secuencias PostgreSQL (nextval no se revierte) ni efectos externos.
        return {model._meta.label: list(model.objects.order_by('pk').values())
                for model in apps.get_models() if model._meta.app_label in {
                    'people', 'core', 'catalog', 'purchases', 'inventory', 'sri'}}

    def reject_unchanged(self, operation, exception=ValidationError, message=None):
        before = self.snapshot()
        if message is None:
            with self.assertRaises(exception):
                operation()
        else:
            with self.assertRaisesMessage(exception, message):
                operation()
        self.assertEqual(self.snapshot(), before)


@tag('cat022b_supplier_company_red')
class SupplierCompanyRedTests(SupplierFixture, TestCase):
    def setUp(self):
        require_isolated_postgresql(self)
        super().setUp()
        self.prepare_context()

    def test_01_global_person_can_supply_two_companies_without_bridge(self):
        count = Person.objects.count()
        a, b = self.supplier(self.a), self.supplier(self.b)
        self.assertNotEqual(a.pk, b.pk)
        self.assertEqual(a.person_id, b.person_id)
        self.assertEqual(Person.objects.count(), count)
        field = Supplier._meta.get_field('person')
        self.assertIsInstance(field, models.ForeignKey)
        self.assertFalse(field.unique)
        self.assertFalse(any(m.__name__.lower() == 'companysupplier' for m in apps.get_models()))

    def test_02_duplicate_company_person_is_rejected_by_database(self):
        self.supplier(self.a)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.supplier(self.a)
        self.assertEqual(Supplier.objects.filter(company=self.a, person=self.person).count(), 1)

    def test_03_nonexistent_company_is_rejected_by_database(self):
        self.company_field()
        absent = max(self.a.pk, self.b.pk) + 1000
        with self.assertRaises(IntegrityError), transaction.atomic():
            Supplier.objects.create(company_id=absent, person=self.person)
            connection.check_constraints()
        self.assertFalse(Supplier.objects.filter(company_id=absent).exists())

    def test_04_existing_fields_and_audit_remain_available(self):
        supplier = self.legacy_supplier()
        supplier.refresh_from_db()
        self.assertEqual((supplier.person_id, supplier.notes, supplier.created_by_id,
                          supplier.updated_by_id),
                         (self.person.pk, 'Legado sin clasificación', self.actor.pk, self.actor.pk))
        self.assertTrue(supplier.is_active)
        self.assertIsNone(supplier.deleted_at)
        self.assertIsNotNone(supplier.created_at)
        self.assertIsNotNone(supplier.updated_at)
        self.assertEqual(str(supplier), self.person.full_name)

    def test_05_purchase_supplier_fk_and_existing_detail_reference_are_preserved(self):
        supplier = self.legacy_supplier()
        purchase = self.historical_purchase(supplier.pk)
        self.assertIs(Purchase._meta.get_field('supplier').related_model, Supplier)
        purchase.refresh_from_db()
        self.assertEqual(purchase.supplier_id, supplier.pk)
        self.assertEqual(purchase.details.get().purchase_id, purchase.pk)

    def test_06_create_purchase_accepts_own_supplier(self):
        supplier = self.supplier(self.a)
        purchase = CreatePurchase.execute(self.dto(supplier))
        self.assertEqual((purchase.company_id, purchase.supplier_id), (self.a.pk, supplier.pk))
        self.assertEqual(purchase.details.count(), 1)

    def test_07_purchase_creator_accepts_own_supplier(self):
        supplier = self.supplier(self.a)
        purchase = PurchaseCreator.create(self.dto(supplier))
        self.assertEqual((purchase.company_id, purchase.supplier_id), (self.a.pk, supplier.pk))
        self.assertEqual(purchase.details.count(), 1)

    def test_08_create_purchase_rejects_foreign_supplier_without_effects(self):
        supplier = self.supplier(self.b)
        self.reject_unchanged(lambda: CreatePurchase.execute(self.dto(supplier)))

    def test_09_purchase_creator_rejects_foreign_supplier_without_effects(self):
        supplier = self.supplier(self.b)
        self.reject_unchanged(lambda: PurchaseCreator.create(self.dto(supplier)))

    def test_10_create_purchase_rejects_unclassified_supplier_without_effects(self):
        supplier = self.legacy_supplier()
        self.reject_unchanged(lambda: CreatePurchase.execute(self.dto(supplier)))

    def test_11_purchase_creator_rejects_unclassified_supplier_without_effects(self):
        supplier = self.legacy_supplier()
        self.reject_unchanged(lambda: PurchaseCreator.create(self.dto(supplier)))

    def test_12_purchase_creation_still_rejects_foreign_branch(self):
        supplier = self.supplier(self.a)
        self.reject_unchanged(lambda: CreatePurchase.execute(
            self.dto(supplier, branch_id=self.branch_b.pk)))

    def test_13_purchase_creation_still_rejects_foreign_product(self):
        supplier = self.supplier(self.a)
        self.reject_unchanged(lambda: CreatePurchase.execute(self.dto(supplier, details=[
            PurchaseDetailDTO(product_id=self.product_b.pk, quantity=Decimal('1'),
                              unit_price=Decimal('10'))])))

    def test_14_confirmation_accepts_classified_own_supplier(self):
        supplier = self.supplier(self.a)
        purchase = self.historical_purchase(supplier.pk)
        ConfirmPurchase.execute(purchase_id=purchase.pk, user=self.actor)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, DocumentStatus.CONFIRMED)
        self.assertEqual(purchase.movement_manifest.count(), 1)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal('10'))

    def test_15_confirmation_rejects_foreign_supplier_without_effects(self):
        supplier = self.supplier(self.b)
        purchase = self.historical_purchase(supplier.pk)
        self.reject_unchanged(lambda: ConfirmPurchase.execute(purchase_id=purchase.pk, user=self.actor))

    def test_16_confirmation_blocks_unclassified_draft_without_effects(self):
        purchase = self.historical_purchase(self.legacy_supplier().pk)
        self.reject_unchanged(lambda: ConfirmPurchase.execute(purchase_id=purchase.pk, user=self.actor))


@tag('cat022b_supplier_company_red')
class SupplierHistoricalPurchaseRedTests(SupplierFixture, TestCase):
    def setUp(self):
        require_isolated_postgresql(self)
        super().setUp()
        self.prepare_context()

    def test_17_historical_cancellation_allows_unclassified_supplier(self):
        supplier = self.legacy_supplier()
        purchase = self.historical_purchase(supplier.pk, confirmed=True)
        original = purchase.movement_manifest.get().stock_movement
        original_row = StockMovement.objects.values().get(pk=original.pk)
        details_before = list(purchase.details.order_by('pk').values())
        self.assertEqual((original.quantity, original.unit_cost), (Decimal('10'), Decimal('10')))
        CancelPurchase.execute(purchase_id=purchase.pk, user=self.actor)
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, DocumentStatus.CANCELLED)
        self.assertEqual(purchase.supplier_id, supplier.pk)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal('0'))
        self.assertEqual(purchase.movement_manifest.get().stock_movement_id, original.pk)
        self.assertEqual(original.reversal_movements.count(), 1)
        reversal = original.reversal_movements.get()
        self.assertEqual((reversal.quantity, reversal.unit_cost), (Decimal('10'), Decimal('10')))
        self.assertEqual(reversal.movement_type, MovementType.RETURN_OUT)
        self.assertEqual((reversal.company_id, reversal.branch_id, reversal.warehouse_id,
                          reversal.product_id, reversal.content_type_id, reversal.object_id),
                         (original.company_id, original.branch_id, original.warehouse_id,
                          original.product_id, original.content_type_id, original.object_id))
        self.assertEqual(StockMovement.objects.values().get(pk=original.pk), original_row)
        self.assertEqual(list(purchase.details.order_by('pk').values()), details_before)
        self.assertEqual(StockMovement.objects.count(), 2)

    def test_18_historical_return_allows_unclassified_supplier(self):
        purchase = self.historical_purchase(self.legacy_supplier().pk, confirmed=True)
        before = Purchase.objects.values().get(pk=purchase.pk)
        originals = list(StockMovement.objects.order_by('pk').values())
        manifests = list(purchase.movement_manifest.values())
        details_before = list(purchase.details.order_by('pk').values())
        document = self.make_return(purchase)
        ConfirmPurchaseReturn.execute(purchase_return_id=document.pk, user=self.actor)
        document.refresh_from_db()
        self.assertEqual(document.status, DocumentStatus.CONFIRMED)
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal('7'))
        self.assertEqual(Purchase.objects.values().get(pk=purchase.pk), before)
        movement = document.movement_manifest.get().stock_movement
        self.assertEqual((movement.quantity, movement.unit_cost), (Decimal('3'), Decimal('10')))
        self.assertEqual(movement.movement_type, MovementType.RETURN_OUT)
        self.assertIsNone(movement.reverses_id)
        self.assertEqual((movement.company_id, movement.branch_id, movement.warehouse_id,
                          movement.product_id, movement.object_id),
                         (self.a.pk, self.branch.pk, self.warehouse.pk, self.product.pk, document.pk))
        self.assertEqual(list(StockMovement.objects.filter(pk__in=[r['id'] for r in originals])
                              .order_by('pk').values()), originals)
        self.assertEqual(list(purchase.movement_manifest.values()), manifests)
        self.assertEqual(list(purchase.details.order_by('pk').values()), details_before)
        self.assertEqual(StockMovement.objects.count(), len(originals) + 1)

    def test_19_historical_return_details_manifests_and_generic_references_survive(self):
        purchase = self.historical_purchase(self.legacy_supplier().pk, confirmed=True)
        document = self.make_return(purchase)
        ConfirmPurchaseReturn.execute(purchase_return_id=document.pk, user=self.actor)
        self.assertEqual(document.purchase_id, purchase.pk)
        line = document.details.get()
        self.assertEqual(line.purchase_detail_id, purchase.details.get().pk)
        self.assertEqual(line.purchase_return_id, document.pk)
        for model, source in ((PurchaseMovement, purchase), (PurchaseReturnMovement, document)):
            manifest = model.objects.get(**{'purchase' if model is PurchaseMovement else 'purchase_return': source})
            movement = manifest.stock_movement
            self.assertEqual((movement.content_type_id, movement.object_id),
                             (ContentType.objects.get_for_model(source).pk, source.pk))
            self.assertEqual(movement.document, source)
            self.assertTrue(StockMovement.objects.filter(pk=movement.pk).exists())

    def test_20_historical_query_scopes_by_purchase_company_with_unclassified_supplier(self):
        supplier = self.legacy_supplier()
        a = self.historical_purchase(supplier.pk)
        b = self.historical_purchase(supplier.pk, company=self.b)
        self.assertEqual(list(Purchase.objects.filter(company=self.a).values_list('pk', flat=True)), [a.pk])
        self.assertEqual(list(Purchase.objects.filter(company=self.b).values_list('pk', flat=True)), [b.pk])

    def test_21_supplier_classification_does_not_hide_other_company_history(self):
        supplier = self.supplier(self.a)
        purchase = self.historical_purchase(supplier.pk, company=self.b)
        found = Purchase.objects.filter(company=self.b).select_related('supplier').get(pk=purchase.pk)
        self.assertEqual((found.company_id, found.supplier_id), (self.b.pk, supplier.pk))

    def test_22_confirmed_return_still_blocks_historical_purchase_cancellation(self):
        purchase = self.historical_purchase(self.legacy_supplier().pk, confirmed=True)
        document = self.make_return(purchase)
        ConfirmPurchaseReturn.execute(purchase_return_id=document.pk, user=self.actor)
        self.reject_unchanged(lambda: CancelPurchase.execute(purchase_id=purchase.pk, user=self.actor),
                              InventoryException, 'La compra tiene devoluciones confirmadas.')

    def test_23_insufficient_stock_still_rejects_return_without_partial_effects(self):
        purchase = self.historical_purchase(self.legacy_supplier().pk, confirmed=True)
        document = self.make_return(purchase, quantity='3')
        DecreaseStock().execute(
            company=self.a, branch=self.branch, warehouse=self.warehouse,
            product=self.product, quantity=Decimal('9'), unit_cost=Decimal('10'),
            movement_type=MovementType.ADJUSTMENT_OUT, user=self.actor)
        self.reject_unchanged(lambda: ConfirmPurchaseReturn.execute(
            purchase_return_id=document.pk, user=self.actor),
            ValidationError, 'No existe stock suficiente.')

    def test_24_cancelled_purchase_cannot_be_cancelled_again(self):
        purchase = self.historical_purchase(self.legacy_supplier().pk, confirmed=True)
        CancelPurchase.execute(purchase_id=purchase.pk, user=self.actor)
        self.reject_unchanged(lambda: CancelPurchase.execute(purchase_id=purchase.pk, user=self.actor),
                              ValueError, 'El documento ya fue anulado.')

    def test_25_missing_historical_manifest_still_blocks_cancellation(self):
        purchase = self.historical_purchase(self.legacy_supplier().pk, confirmed=True, manifest=False)
        self.reject_unchanged(lambda: CancelPurchase.execute(purchase_id=purchase.pk, user=self.actor),
                              InventoryException, 'La compra no tiene manifiesto de inventario.')

    def test_32_return_quantity_cannot_exceed_historical_purchase_balance(self):
        purchase = self.historical_purchase(self.legacy_supplier().pk, confirmed=True)
        self.reject_unchanged(lambda: self.make_return(purchase, quantity='11'),
                              ValidationError, 'La cantidad excede el saldo disponible para devolución.')

    def test_33_multiline_return_rolls_back_after_first_stock_and_manifest_write(self):
        """Primera línea válida; segunda sin stock, con servicios y SQL reales."""
        supplier = self.legacy_supplier()
        second = Product.objects.create(company=self.a, code='P2', name='Segunda línea')
        self.assertLess(self.product.pk, second.pk)  # Orden real de confirmación.
        purchase = Purchase.objects.create(
            company=self.a, branch=self.branch, supplier=supplier,
            document_type=self.purchase_type, issue_date=date(2026, 9, 19),
            status=DocumentStatus.CONFIRMED, number='HIST-MULTI',
            subtotal=Decimal('225'), tax=Decimal('0'), total=Decimal('225'))
        lines = []
        for line, (product, quantity, cost) in enumerate((
                (self.product, Decimal('10'), Decimal('10')),
                (second, Decimal('5'), Decimal('25'))), start=1):
            lines.append(PurchaseDetail.objects.create(
                purchase=purchase, product=product, line=line, quantity=quantity,
                unit_price=cost, subtotal=quantity * cost, tax_amount=Decimal('0'),
                total=quantity * cost))
            movement = IncreaseStock().execute(
                company=self.a, branch=self.branch, warehouse=self.warehouse,
                product=product, quantity=quantity, unit_cost=cost,
                movement_type=MovementType.PURCHASE, document=purchase, return_movement=True)
            PurchaseMovement.objects.create(purchase=purchase, stock_movement=movement)
        DecreaseStock().execute(
            company=self.a, branch=self.branch, warehouse=self.warehouse,
            product=second, quantity=Decimal('4'), unit_cost=Decimal('25'),
            movement_type=MovementType.ADJUSTMENT_OUT, user=self.actor)
        document = CreatePurchaseReturn.execute(PurchaseReturnCreateDTO(
            purchase_id=purchase.pk, issue_date=date(2026, 10, 11), notes='Rollback real',
            details=[PurchaseReturnDetailDTO(purchase_detail_id=line.pk, quantity=Decimal('3'))
                     for line in lines]))
        sequence = Sequence.objects.get(company=self.a, branch=self.branch,
                                        document_type=self.return_type)
        persisted_numbering = (document.number, sequence.next_number)
        before = self.snapshot()
        with CaptureQueriesContext(connection) as queries:
            with self.assertRaisesMessage(ValidationError, 'No existe stock suficiente.'):
                ConfirmPurchaseReturn.execute(purchase_return_id=document.pk, user=self.actor)
        sql = [q['sql'].lstrip().upper() for q in queries.captured_queries]
        # La primera línea alcanzó escrituras reales antes del error de stock
        # de la segunda: stock, movimiento y manifiesto. Sin mocks ni señales.
        for model in (StockMovement, PurchaseReturnMovement):
            prefix = 'INSERT INTO ' + connection.ops.quote_name(model._meta.db_table).upper()
            self.assertEqual(sum(q.startswith(prefix) for q in sql), 1, prefix)
        prefix = 'UPDATE ' + connection.ops.quote_name(Stock._meta.db_table).upper()
        self.assertEqual(sum(q.startswith(prefix) for q in sql), 1)
        self.assertTrue(any(q.startswith('ROLLBACK TO SAVEPOINT') for q in sql))
        self.assertEqual(self.snapshot(), before)
        document.refresh_from_db()
        sequence.refresh_from_db()
        self.assertEqual(document.status, DocumentStatus.DRAFT)
        self.assertEqual((document.number, sequence.next_number), persisted_numbering)
        self.assertFalse(document.movement_manifest.exists())
        self.assertEqual(Stock.objects.get(product=self.product).quantity, Decimal('10'))
        self.assertEqual(Stock.objects.get(product=second).quantity, Decimal('1'))
        # No se compara last_value: las secuencias PostgreSQL no son transaccionales.


@tag('cat022b_supplier_company_red')
class SupplierMigrationRedTests(SupplierFixture, TransactionTestCase):
    before = [('people', '0005_customer_company_expansion'), ('purchases', '0006_purchase_movement')]

    def setUp(self):
        require_isolated_postgresql(self)
        super().setUp()
        loader = MigrationLoader(None)
        leaves = loader.graph.leaf_nodes('people')
        self.assertEqual(len(leaves), 1, 'Harness: grafo people divergente')
        baseline = set().union(*(set(loader.graph.forwards_plan(k)) for k in self.before))
        self.target = None
        for key in loader.graph.forwards_plan(leaves[0]):
            if key[0] != 'people' or key in baseline:
                continue
            candidate = loader.project_state([key, self.before[1]]).apps.get_model('people', 'Supplier')
            fields = {f.name: f for f in candidate._meta.fields}
            if ('company' in fields and fields['company'].null
                    and isinstance(fields['company'], models.ForeignKey)
                    and isinstance(fields['person'], models.ForeignKey) and not fields['person'].unique
                    and any(isinstance(c, models.UniqueConstraint)
                            and set(c.fields) == {'company', 'person'} for c in candidate._meta.constraints)):
                self.target = [key, self.before[1]]
                break
        self.assertIsNotNone(self.target,
                             'RED esperado: falta expansión nullable Supplier posterior a people.0005')
        target_nodes = set().union(*(set(loader.graph.forwards_plan(k)) for k in self.target))
        self.transition = target_nodes - baseline
        executor = MigrationExecutor(connection)
        self.initial_applied = set(executor.loader.applied_migrations)
        self.assertTrue(target_nodes <= self.initial_applied,
                        'Harness: TEST debe habilitar migraciones antes de pruebas históricas')
        relevant = {k for k in self.initial_applied if k[0] in {'people', 'purchases'}}
        self.original_targets = [k for k in relevant if not any(
            child.key in relevant for child in loader.graph.node_map[k].children)]
        self.old = loader.project_state(self.before).apps
        self.addCleanup(self.restore_schema)  # Antes de cualquier mutación de esquema.
        self.check_plan(executor, self.before, backwards=True)
        executor.migrate(self.before)
        self.assertNotIn('company', {f.name for f in self.old.get_model('people', 'Supplier')._meta.fields})
        self.prepare_context()

    def check_plan(self, executor, targets, backwards):
        for migration, reverse in executor.migration_plan(targets):
            self.assertIn((migration.app_label, migration.name), self.transition,
                          'Harness: transición altera migraciones ajenas a Supplier')
            self.assertEqual(reverse, backwards)

    def restore_schema(self):
        require_isolated_postgresql(self)
        executor = MigrationExecutor(connection)
        try:
            executor.migrate(self.original_targets)
        except Exception as error:
            # Propagar el error original con contexto; jamás convertirlo en PASS.
            error.add_note('HARNESS: falló restauración de PostgreSQL TEST a '
                           f'{self.original_targets!r}; requiere revisión, no recuperación DEV.')
            raise
        self.assertEqual(set(MigrationExecutor(connection).loader.applied_migrations), self.initial_applied,
                         'HARNESS: restauración TEST dejó un registro de migraciones diferente')

    def raw_snapshot(self):
        result = {}
        with connection.cursor() as cursor:
            for table in sorted(connection.introspection.table_names(cursor)):
                columns = connection.introspection.get_table_description(cursor, table)
                cursor.execute(f'SELECT * FROM {connection.ops.quote_name(table)}')
                result[table] = (tuple((c.name, c.type_code, c.null_ok) for c in columns),
                                 connection.introspection.get_constraints(cursor, table),
                                 sorted(cursor.fetchall(), key=repr))
        return result

    def legacy(self):
        return self.old.get_model('people', 'Supplier').objects.create(
            person_id=self.person.pk, notes='Preservar auditoría', created_by_id=self.actor.pk,
            updated_by_id=self.actor.pk)

    def expand(self, supplier):
        originals = list(self.old.get_model('people', 'Supplier').objects.order_by('pk').values())
        before = self.raw_snapshot()
        executor = MigrationExecutor(connection)
        self.check_plan(executor, self.target, backwards=False)
        executor.migrate(self.target)  # Ninguna excepción genérica cuenta como éxito.
        after = self.raw_snapshot()
        self.assertEqual(set(before), set(after))
        for table in before:
            if table not in {'people_supplier', 'django_migrations'}:
                self.assertEqual(after[table], before[table], table)
        self.expanded = executor.loader.project_state(self.target).apps
        rows = list(self.expanded.get_model('people', 'Supplier').objects.order_by('pk').values())
        self.assertEqual(len(rows), len(originals), 'Expansión alteró cantidad de Supplier')
        self.assertEqual({r['id'] for r in rows}, {r['id'] for r in originals},
                         'Expansión insertó o eliminó identidades Supplier')
        by_pk = {r['id']: r for r in rows}
        for original in originals:
            for field, value in original.items():
                self.assertEqual(by_pk[original['id']][field], value, (original['id'], field))
        return by_pk[supplier.pk]

    def assert_reverse_protected(self):
        before = self.raw_snapshot()
        applied = set(MigrationExecutor(connection).loader.applied_migrations)
        executor = MigrationExecutor(connection)
        self.check_plan(executor, self.before, backwards=True)
        with self.assertRaises(IrreversibleError):
            executor.migrate(self.before)
        self.assertEqual(self.raw_snapshot(), before)
        self.assertEqual(set(MigrationExecutor(connection).loader.applied_migrations), applied)

    def test_26_expansion_preserves_supplier_and_all_historical_document_links(self):
        supplier = self.legacy()
        # Otra identidad sin documentos detecta pérdida o alteración de filas
        # distintas del proveedor protagonista; no impone clasificación.
        other_person = Person.objects.create(identification='SUP-OTHER', person_type='LEGAL',
                                            full_name='Otro proveedor legado')
        self.old.get_model('people', 'Supplier').objects.create(
            person_id=other_person.pk, notes='Otra identidad histórica',
            created_by_id=self.actor.pk, updated_by_id=self.actor.pk, is_active=False)
        purchase = self.historical_purchase(supplier.pk, confirmed=True)
        document = self.make_return(purchase)
        ConfirmPurchaseReturn.execute(purchase_return_id=document.pk, user=self.actor)
        current = self.expand(supplier)
        self.assertEqual((current['id'], current['person_id']), (supplier.pk, self.person.pk))
        self.assertIn(current['company_id'], (None, self.a.pk))  # Candidata, no backfill obligatorio.
        self.assertEqual(Purchase.objects.get(pk=purchase.pk).supplier_id, supplier.pk)
        self.assertEqual(PurchaseReturn.objects.get(pk=document.pk).purchase_id, purchase.pk)

    def test_27_legacy_without_evidence_remains_unclassified(self):
        supplier = self.legacy()
        self.assertFalse(Purchase.objects.filter(supplier_id=supplier.pk).exists())
        self.assertIsNone(self.expand(supplier)['company_id'])

    def test_28_multicompany_history_is_not_automatically_classified(self):
        supplier = self.legacy()
        self.historical_purchase(supplier.pk)
        self.historical_purchase(supplier.pk, company=self.b)
        self.assertEqual(set(Purchase.objects.filter(supplier_id=supplier.pk)
                             .values_list('company_id', flat=True)), {self.a.pk, self.b.pk})
        self.assertIsNone(self.expand(supplier)['company_id'])

    def test_29_reverse_rejects_loss_of_explicit_company_assignment(self):
        supplier = self.legacy()
        self.expand(supplier)
        self.expanded.get_model('people', 'Supplier').objects.filter(pk=supplier.pk).update(company_id=self.a.pk)
        self.assert_reverse_protected()

    def test_30_reverse_rejects_multiple_suppliers_for_one_person(self):
        supplier = self.legacy()
        self.expand(supplier)
        model = self.expanded.get_model('people', 'Supplier')
        # Aislar multiplicidad de pérdida de clasificación (cubierta en 29).
        self.assertIsNone(model.objects.get(pk=supplier.pk).company_id)
        model.objects.create(person_id=self.person.pk, company_id=None)
        self.assertEqual(model.objects.filter(person_id=self.person.pk).count(), 2)
        self.assert_reverse_protected()

    def test_31_safe_reverse_preserves_unclassified_supplier_identity(self):
        supplier = self.legacy()
        self.expand(supplier)
        model = self.expanded.get_model('people', 'Supplier')
        self.assertIsNone(model.objects.get(pk=supplier.pk).company_id)
        executor = MigrationExecutor(connection)
        self.check_plan(executor, self.before, backwards=True)
        executor.migrate(self.before)
        old = executor.loader.project_state(self.before).apps.get_model('people', 'Supplier')
        row = old.objects.get(pk=supplier.pk)
        self.assertEqual((row.pk, row.person_id), (supplier.pk, self.person.pk))
