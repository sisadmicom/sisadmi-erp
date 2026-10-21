"""CAT-02.1: six-place Product targets and existing monetary behavior.

Target tests intentionally fail until Product uses DecimalField(18, 6).
Approved targets: Product prices and stock unit cost (18, 6), commercial money
rounded HALF_UP to cents and headers summed from persisted detail amounts.
Raw arithmetic remains characterized separately from monetary persistence.
No tax rounding, inventory valuation, migrations or fiscal calls are changed.
"""
from datetime import date
from decimal import Decimal, ROUND_DOWN, localcontext

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from catalog.forms import ProductForm
from catalog.models import Product
from catalog.tests import test_product_related_continuation_cat012e_red as contextual
from core.services.commercial.commercial_line_calculator import CommercialLineCalculator
from inventory.models import StockMovement
from purchases.models import PurchaseDetail
from purchases.dto.purchase_create_dto import PurchaseCreateDTO
from purchases.dto.purchase_detail_dto import PurchaseDetailDTO
from purchases.services.purchase_creator import PurchaseCreator
from purchases.tests import test_create_purchase as purchase_fixtures
from sales.models import SaleDetail
from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from sales.tests import test_create_sale as sale_fixtures
from sales.use_cases.create_sale import CreateSale
from django.contrib.contenttypes.models import ContentType
from sri.models import ElectronicDocument
from inventory.constants.movement_type import MovementType


class ProductPrecisionTargetTests(TestCase):
    authorize = contextual.ProductRelatedContinuationRedTests.authorize
    context = contextual.ProductRelatedContinuationRedTests.context
    payload = contextual.ProductRelatedContinuationRedTests.payload

    def setUp(self):
        contextual.ProductRelatedContinuationRedTests.setUp(self)
        self.assertEqual(connection.vendor, 'postgresql')
        self.assertTrue(connection.settings_dict['NAME'].startswith('test_'))
        self.assertNotEqual(connection.settings_dict['NAME'], 'sisadmi_erp_dev')

    def test_target_product_fields_have_eighteen_digits_six_places(self):
        for name in ('cost_price', 'sale_price'):
            with self.subTest(field=name):
                field = Product._meta.get_field(name)
                self.assertEqual((field.max_digits, field.decimal_places), (18, 6))

    def test_target_database_roundtrip_keeps_six_places_exactly(self):
        self.product.cost_price = Decimal('1234.123456')
        self.product.sale_price = Decimal('9876.654321')
        self.product.save(update_fields=['cost_price', 'sale_price'])
        self.product.refresh_from_db()
        self.assertIsInstance(self.product.cost_price, Decimal)
        self.assertIsInstance(self.product.sale_price, Decimal)
        self.assertEqual(self.product.cost_price, Decimal('1234.123456'))
        self.assertEqual(self.product.sale_price, Decimal('9876.654321'))

    def test_target_form_accepts_six_places_as_decimal(self):
        form = ProductForm(data=self.payload(cost_price='0.123456', sale_price='1.987654'),
                           company_id=self.company.pk)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertEqual(form.cleaned_data['cost_price'], Decimal('0.123456'))
        self.assertEqual(form.cleaned_data['sale_price'], Decimal('1.987654'))
        self.assertIsInstance(form.cleaned_data['sale_price'], Decimal)

    def test_target_form_accepts_maximum_without_losing_integer_capacity(self):
        value = '999999999999.999999'
        form = ProductForm(data=self.payload(cost_price=value, sale_price=value),
                           company_id=self.company.pk)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertEqual(form.cleaned_data['cost_price'], Decimal(value))

    def test_form_rejects_overflow_extra_places_and_negative_prices(self):
        for value in ('1000000000000.000000', '0.1234567', '-0.000001'):
            with self.subTest(value=value):
                form = ProductForm(data=self.payload(cost_price=value, sale_price=value),
                                   company_id=self.company.pk)
                self.assertFalse(form.is_valid())
                self.assertIn('cost_price', form.errors)
                self.assertIn('sale_price', form.errors)

    def test_existing_two_place_values_remain_exact_after_unrelated_edit(self):
        self.product.refresh_from_db()
        before = (self.product.cost_price, self.product.sale_price)
        self.product.name = 'Cambio descriptivo'
        self.product.save(update_fields=['name'])
        self.product.refresh_from_db()
        self.assertEqual((self.product.cost_price, self.product.sale_price), before)
        self.assertEqual(before, (Decimal('10.00'), Decimal('20.00')))

    def test_six_place_input_never_bypasses_product_permission(self):
        self.authorize('view_product')
        before = list(Product.objects.values())
        response = self.client.post(reverse('product_create'),
                                    self.payload(cost_price='0.123456', sale_price='1.123456'))
        self.assertIn(response.status_code, (403, 404))
        self.assertEqual(list(Product.objects.values()), before)

    def test_six_place_input_cannot_edit_another_company(self):
        before = list(Product.objects.values())
        response = self.client.post(reverse('product_update', args=[self.foreign_product.pk]),
                                    self.payload(cost_price='0.123456', sale_price='1.123456',
                                                 company_id=self.company.pk))
        self.assertIn(response.status_code, (403, 404))
        self.assertEqual(list(Product.objects.values()), before)


class DecimalCapacityCharacterizationTests(TestCase):
    def test_purchase_and_sale_unit_prices_already_accept_full_target_range(self):
        for model in (PurchaseDetail, SaleDetail):
            with self.subTest(model=model._meta.label):
                field = model._meta.get_field('unit_price')
                self.assertEqual((field.max_digits, field.decimal_places), (18, 6))
                self.assertEqual(field.clean(Decimal('999999999999.999999'), None),
                                 Decimal('999999999999.999999'))
                with self.assertRaises(ValidationError):
                    field.clean(Decimal('1000000000000.000000'), None)

    def test_target_stock_cost_accepts_full_commercial_capacity(self):
        field = StockMovement._meta.get_field('unit_cost')
        self.assertEqual((field.max_digits, field.decimal_places), (18, 6))
        value = Decimal('999999999999.999999')
        self.assertEqual(field.clean(value, None), value)
        with self.assertRaises(ValidationError):
            field.clean(Decimal('1000000000000.000000'), None)
        with self.assertRaises(ValidationError):
            field.clean(Decimal('0.1234567'), None)

    def test_quantity_times_price_preserves_decimal_without_premature_rounding(self):
        result = CommercialLineCalculator.calculate_subtotal(
            Decimal('2.542563'), Decimal('25.542365'), Decimal('0.00'))
        self.assertIsInstance(result, Decimal)
        self.assertEqual(result, Decimal('64.943072181495'))

    def test_half_cent_is_not_rounded_by_line_calculator(self):
        self.assertEqual(CommercialLineCalculator.calculate_subtotal(
            Decimal('1'), Decimal('0.005000'), Decimal('0')), Decimal('0.005000'))


class CommercialPersistenceCharacterizationTests(TestCase):
    def setUp(self):
        sale_fixtures.CreateSaleTest.setUp(self)
        self.tax_configuration.taxes.clear()

    def sale(self, price, count=1):
        return CreateSale.execute(SaleCreateDTO(
            company_id=self.company.pk, branch_id=self.branch.pk,
            customer_id=self.customer.pk, warehouse_id=self.warehouse.pk,
            issue_date=date(2026, 1, 1), notes='Caracterización decimal',
            details=[SaleDetailDTO(product_id=self.product.pk, quantity=Decimal('1'),
                                   unit_price=price, discount=Decimal('0'))
                     for _ in range(count)]))

    def test_sale_database_keeps_six_place_unit_price(self):
        sale = self.sale(Decimal('0.123456'))
        detail = sale.details.get()
        self.assertIsInstance(detail.unit_price, Decimal)
        self.assertEqual(detail.unit_price, Decimal('0.123456'))

    def test_target_sale_header_sums_persisted_half_cent_lines(self):
        sale = self.sale(Decimal('0.005000'), count=2)
        sale.refresh_from_db()
        subtotals = list(sale.details.values_list('subtotal', flat=True))
        self.assertEqual(subtotals, [Decimal('0.01'), Decimal('0.01')])
        self.assertEqual(sale.subtotal, sum(subtotals, Decimal('0')))
        self.assertEqual(sale.subtotal, Decimal('0.02'))
        self.assertEqual(sale.total, sum(sale.details.values_list('total', flat=True), Decimal('0')))

    def test_target_sale_returned_money_is_explicit_half_up_not_ambient_context(self):
        with localcontext() as ctx:
            ctx.rounding = ROUND_DOWN
            sale = self.sale(Decimal('0.005000'))
        # Test the service boundary as well as storage: DB rounding alone does
        # not make the in-memory document a consistent commercial result.
        self.assertEqual(sale.subtotal, Decimal('0.01'))
        self.assertEqual(sale.total, Decimal('0.01'))
        sale.refresh_from_db()
        self.assertEqual(sale.subtotal, Decimal('0.01'))

    def test_stock_roundtrip_preserves_six_places(self):
        movement = StockMovement.objects.create(company=self.company, branch=self.branch,
            warehouse=self.warehouse, product=self.product, movement_type=MovementType.PURCHASE,
            quantity=Decimal('1.000001'), unit_cost=Decimal('1234.123456'))
        movement.refresh_from_db()
        self.assertIsInstance(movement.unit_cost, Decimal)
        self.assertEqual(movement.unit_cost, Decimal('1234.123456'))

    def test_target_stock_roundtrip_preserves_expanded_maximum(self):
        field = StockMovement._meta.get_field('unit_cost')
        # Fail cleanly on the current range before attempting a DB overflow.
        self.assertEqual((field.max_digits, field.decimal_places), (18, 6))
        movement = StockMovement.objects.create(company=self.company, branch=self.branch,
            warehouse=self.warehouse, product=self.product, movement_type=MovementType.PURCHASE,
            quantity=Decimal('1'), unit_cost=Decimal('999999999999.999999'))
        movement.refresh_from_db()
        self.assertEqual(movement.unit_cost, Decimal('999999999999.999999'))

    def test_product_price_edit_does_not_recalculate_sale_or_tax_snapshots(self):
        self.tax_configuration.taxes.add(self.iva)
        sale = self.sale(Decimal('12.345678'))
        before = (list(type(sale).objects.filter(pk=sale.pk).values()),
                  list(sale.details.values()),
                  list(sale.details.get().applied_taxes.values()))
        self.product.cost_price = Decimal('9.00')
        self.product.sale_price = Decimal('99.00')
        self.product.save(update_fields=['cost_price', 'sale_price'])
        self.assertEqual((list(type(sale).objects.filter(pk=sale.pk).values()),
                          list(sale.details.values()),
                          list(sale.details.get().applied_taxes.values())), before)

    def test_product_update_keeps_existing_signed_xml_byte_for_byte(self):
        sale = self.sale(Decimal('12.345678'))
        # Opaque signed payload fixture: preservation, not cryptographic or XSD
        # validation. No signing, regeneration or remote SRI request occurs.
        xml = '<factura><precioUnitario>12.345678</precioUnitario><firma>ñ&amp;</firma></factura>'
        document = ElectronicDocument.objects.create(company=self.company, branch=self.branch,
            content_type=ContentType.objects.get_for_model(sale), object_id=sale.pk,
            document_type='01', establishment='001', emission_point='001',
            sequential='000000001', numeric_code='12345678', status='SIGNED', xml=xml)
        before = ElectronicDocument.objects.filter(pk=document.pk).values().get()
        self.product.sale_price = Decimal('99.00')
        self.product.save(update_fields=['sale_price'])
        self.assertEqual(ElectronicDocument.objects.filter(pk=document.pk).values().get(), before)


class PurchasePrecisionTests(TestCase):
    def setUp(self):
        purchase_fixtures.CreatePurchaseTest.setUp(self)

    def purchase(self, price, count=1):
        return PurchaseCreator.create(PurchaseCreateDTO(company_id=self.company.pk,
            branch_id=self.branch.pk, supplier_id=self.supplier.pk,
            issue_date=date(2026, 1, 1), notes='Precisión compra',
            details=[PurchaseDetailDTO(product_id=self.product.pk, quantity=Decimal('1'),
                unit_price=price, discount=Decimal('0')) for _ in range(count)]))

    def test_purchase_persists_exact_unit_price_and_keeps_historical_amounts(self):
        purchase = self.purchase(Decimal('12.345678'))
        detail = purchase.details.get()
        self.assertIsInstance(detail.unit_price, Decimal)
        self.assertEqual(detail.unit_price, Decimal('12.345678'))
        before = (list(type(purchase).objects.filter(pk=purchase.pk).values()),
                  list(purchase.details.values()))
        self.product.cost_price = Decimal('90.00')
        self.product.save(update_fields=['cost_price'])
        self.assertEqual((list(type(purchase).objects.filter(pk=purchase.pk).values()),
                          list(purchase.details.values())), before)

    def test_target_purchase_header_sums_persisted_half_cent_lines(self):
        purchase = self.purchase(Decimal('0.005000'), count=2)
        purchase.refresh_from_db()
        self.assertEqual(list(purchase.details.values_list('subtotal', flat=True)),
                         [Decimal('0.01'), Decimal('0.01')])
        self.assertEqual(purchase.subtotal, Decimal('0.02'))
        self.assertEqual(purchase.total,
                         sum(purchase.details.values_list('total', flat=True), Decimal('0')))


class PrecisionContinuationTests(TestCase):
    # Reuse helpers explicitly without inheriting/re-discovering prior tests.
    authorize = contextual.ProductRelatedContinuationRedTests.authorize
    context = contextual.ProductRelatedContinuationRedTests.context
    payload = contextual.ProductRelatedContinuationRedTests.payload
    parent_url = contextual.ProductRelatedContinuationRedTests.parent_url
    isolated_case = contextual.ProductRelatedContinuationRedTests.isolated_case
    snapshot = contextual.ProductRelatedContinuationRedTests.snapshot
    form = contextual.ProductRelatedContinuationRedTests.form
    hidden = contextual.ProductRelatedContinuationRedTests.hidden
    control = contextual.ProductRelatedContinuationRedTests.control
    begin = contextual.ProductRelatedContinuationRedTests.begin
    finish = contextual.ProductRelatedContinuationRedTests.finish
    assert_values = contextual.ProductRelatedContinuationRedTests.assert_values

    def setUp(self):
        contextual.ProductRelatedContinuationRedTests.setUp(self)

    def test_create_and_edit_continuations_preserve_exact_decimal_text_and_tax_lists(self):
        for editing in (False, True):
            for taxes in ([str(self.iva.pk), str(self.ice.pk)], []):
                with self.subTest(editing=editing, taxes=taxes), self.isolated_case():
                    before = self.snapshot()
                    data = self.payload(cost_price='0.123456', sale_price='999.987654', taxes=taxes)
                    target, posted = self.begin(editing=editing, data=data)
                    location, page = self.finish(target, cancel=True)
                    self.assert_values(page, data)
                    self.assertEqual(self.snapshot(), before)
