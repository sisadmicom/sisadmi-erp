"""C-15A-A: additive DTO input and durable commercial tax snapshots.

No XML, numeric fiscal mappings or fiscal operations belong to this contract.
"""
from dataclasses import fields
from datetime import date
from decimal import Decimal
from importlib import import_module
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import tag

from catalog.models import Tax
from core.constants.document_status import DocumentStatus
from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from sales.models import Sale, SaleDetailTax
from sales.tests.sale_manifest_test_support import SaleManifestFixture
from sales.use_cases.create_sale import CreateSale


@tag("c15aa_domain_red")
class SaleFiscalDataContractTests(SaleManifestFixture):
    def setUp(self):
        super().setUp()
        for target in ("socket.socket.connect", "socket.create_connection"):
            guard = patch(target, side_effect=AssertionError("Network forbidden in domain RED"))
            mock = guard.start()
            self.addCleanup(mock.assert_not_called)
            self.addCleanup(guard.stop)

    def field(self, model, name):
        self.assertIn(name, {f.name for f in model._meta.fields},
                      f"{model.__name__} must persist {name}")
        return model._meta.get_field(name)

    def dto(self, **kwargs):
        values = dict(company_id=self.company.pk, branch_id=self.branch.pk,
                      customer_id=self.customer.pk, warehouse_id=self.warehouse.pk,
                      issue_date=date(2026, 10, 2), notes="Domain contract",
                      details=[SaleDetailDTO(product_id=self.product.pk, quantity=Decimal("2"),
                                             unit_price=Decimal("10"), discount=Decimal("1"))])
        values.update(kwargs)
        return SaleCreateDTO(**values)

    def explicit_dto(self, method):
        self.assertIn("payment_method", {f.name for f in fields(SaleCreateDTO)},
                      "SaleCreateDTO must accept optional explicit payment_method")
        return self.dto(payment_method=method)

    def tax(self, category):
        self.field(Tax, "tax_category")
        tax = Tax.objects.create(company=self.company, code="COMMERCIAL-VAT", name="Nombre comercial",
                                 tax_type="IVA", rate=Decimal("15"), tax_category=category)
        self.product.taxes.add(tax)
        return tax

    def test_payment_enum_is_domain_semantic(self):
        try:
            module = import_module("sales.constants.payment_method")
        except ModuleNotFoundError as error:
            self.fail(f"Missing domain payment enum: {error.name}")
        enum = getattr(module, "PaymentMethod", None)
        self.assertIsNotNone(enum, "PaymentMethod enum is required")
        self.assertEqual(set(enum.values), {"NON_FINANCIAL", "DEBT_OFFSET", "DEBIT_CARD",
            "ELECTRONIC_MONEY", "PREPAID_CARD", "CREDIT_CARD", "FINANCIAL_OTHER", "TITLE_ENDORSEMENT"})
        self.assertEqual(set(dict(self.field(Sale, "payment_method").choices)), set(enum.values))

    def test_payment_and_snapshot_fields_allow_unknown_history_without_defaults(self):
        for model, name in ((Sale, "payment_method"), (SaleDetailTax, "tax_category")):
            with self.subTest(model=model.__name__):
                field = self.field(model, name)
                self.assertTrue(field.null)
                self.assertTrue(field.blank)
                self.assertFalse(field.has_default())

    def test_explicit_payment_methods_reach_persisted_sale(self):
        self.field(Sale, "payment_method")
        for method in ("NON_FINANCIAL", "DEBT_OFFSET", "DEBIT_CARD", "ELECTRONIC_MONEY",
                       "PREPAID_CARD", "CREDIT_CARD", "FINANCIAL_OTHER", "TITLE_ENDORSEMENT"):
            with self.subTest(method=method):
                sale = CreateSale.execute(self.explicit_dto(method))
                sale.refresh_from_db()
                self.assertEqual(sale.payment_method, method)
                self.assertEqual(sale.company_id, self.company.pk)
                self.assertEqual(sale.branch_id, self.branch.pk)
                self.assertEqual(sale.document_type.code, Sale.DOCUMENT_TYPE_CODE)
                self.assertEqual(sale.status, DocumentStatus.DRAFT)
                self.assertEqual(sale.total, Decimal("19.00"))

    def test_omitted_and_none_payment_preserve_transitional_dto_compatibility(self):
        self.field(Sale, "payment_method")
        for explicit_none in (False, True):
            with self.subTest(explicit_none=explicit_none):
                dto = self.explicit_dto(None) if explicit_none else self.dto()
                self.assertIsNone(dto.payment_method)
                sale = CreateSale.execute(dto)
                sale.refresh_from_db()
                self.assertIsNone(sale.payment_method)

    def test_payment_is_not_inferred_from_totals_or_customer_credit(self):
        self.field(Sale, "payment_method")
        for credit in (Decimal("0"), Decimal("1000")):
            with self.subTest(credit=credit):
                self.customer.credit_limit = credit
                self.customer.save(update_fields=["credit_limit"])
                sale = CreateSale.execute(self.dto())
                sale.refresh_from_db()
                self.assertIsNone(sale.payment_method)
                self.assertEqual(sale.total, Decimal("19.00"))

    def test_unknown_payment_is_rejected_before_creating_sale(self):
        dto = self.explicit_dto("UNKNOWN")
        before = Sale.objects.count()
        with self.assertRaises((ValueError, ValidationError)):
            CreateSale.execute(dto)
        self.assertEqual(Sale.objects.count(), before)

    def test_dto_adds_only_payment_and_no_fiscal_or_computed_authority(self):
        self.assertEqual({f.name for f in fields(SaleCreateDTO)},
                         {"company_id", "branch_id", "customer_id", "warehouse_id", "issue_date",
                          "notes", "details", "payment_method"})
        self.assertEqual({f.name for f in fields(SaleDetailDTO)},
                         {"product_id", "quantity", "unit_price", "discount"})

    def test_create_sale_snapshots_category_without_changing_tax_math(self):
        self.field(SaleDetailTax, "tax_category")
        tax = self.tax("VAT_STANDARD")
        sale = CreateSale.execute(self.dto())
        applied = sale.details.get().applied_taxes.get()
        applied.refresh_from_db()
        self.assertEqual(applied.tax_category, "VAT_STANDARD")
        self.assertEqual(applied.tax_id, tax.pk)
        self.assertEqual(applied.tax_code, "COMMERCIAL-VAT")
        self.assertEqual(applied.tax_name, "Nombre comercial")
        self.assertEqual(applied.tax_type, "IVA")
        self.assertEqual(applied.rate, Decimal("15"))
        self.assertEqual(applied.base, Decimal("19.00"))
        self.assertEqual(applied.amount, Decimal("2.85"))
        sale.refresh_from_db()
        self.assertEqual(sale.total, Decimal("21.85"))

    def test_category_snapshot_survives_master_change_and_fresh_reads(self):
        self.field(SaleDetailTax, "tax_category")
        tax = self.tax("VAT_STANDARD")
        sale = CreateSale.execute(self.dto())
        applied = sale.details.get().applied_taxes.get()
        tax.tax_category = "VAT_ZERO_RATED"
        tax.rate = Decimal("0")
        tax.save(update_fields=["tax_category", "rate"])
        first = SaleDetailTax.objects.get(pk=applied.pk)
        self.assertEqual(first.tax_category, "VAT_STANDARD")
        first.save(update_fields=["updated_at"])
        second = SaleDetailTax.objects.get(pk=applied.pk)
        self.assertEqual(second.tax_category, "VAT_STANDARD")
        self.assertEqual(second.rate, Decimal("15"))
        self.assertEqual(second.amount, Decimal("2.85"))

    def test_legacy_sale_and_tax_snapshot_remain_null_on_load(self):
        self.field(Sale, "payment_method")
        self.field(SaleDetailTax, "tax_category")
        self.tax(None)
        sale = CreateSale.execute(self.dto())
        sale.refresh_from_db()
        applied = SaleDetailTax.objects.get(detail__sale=sale)
        self.assertIsNone(sale.payment_method)
        self.assertIsNone(applied.tax_category)
        self.assertEqual(applied.tax_code, "COMMERCIAL-VAT")
