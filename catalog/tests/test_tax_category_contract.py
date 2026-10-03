"""C-15A-A: category authority is distinct from commercial tax attributes."""
from decimal import Decimal
from importlib import import_module

from django.core.exceptions import ValidationError
from django.test import TestCase, tag

from catalog.models import Tax
from core.models import Company
from people.models import Person


@tag("c15aa_domain_red")
class TaxCategoryContractTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(person=Person.objects.create(
            identification="1790000001001", person_type="LEGAL", full_name="Tax company"))

    def field(self):
        self.assertIn("tax_category", {f.name for f in Tax._meta.fields},
                      "Tax must persist a semantic tax_category")
        return Tax._meta.get_field("tax_category")

    def tax(self, **kwargs):
        values = dict(company=self.company, code="COMMERCIAL-VAT", name="Nombre comercial",
                      tax_type="IVA", rate=Decimal("0"))
        values.update(kwargs)
        return Tax(**values)

    def test_enum_has_distinct_semantic_categories(self):
        try:
            module = import_module("catalog.constants.tax_category")
        except ModuleNotFoundError as error:
            self.fail(f"Missing domain tax category enum: {error.name}")
        enum = getattr(module, "TaxCategory", None)
        self.assertIsNotNone(enum, "TaxCategory enum is required")
        self.assertEqual(set(enum.values),
                         {"VAT_STANDARD", "VAT_ZERO_RATED", "VAT_EXEMPT", "VAT_NOT_SUBJECT"})
        self.assertEqual(set(dict(self.field().choices)), set(enum.values))

    def test_field_is_nullable_blank_without_fiscal_default(self):
        field = self.field()
        self.assertTrue(field.null)
        self.assertTrue(field.blank)
        self.assertFalse(field.has_default())

    def test_explicit_categories_persist_without_changing_commercial_code(self):
        self.field()
        for category in ("VAT_STANDARD", "VAT_ZERO_RATED", "VAT_EXEMPT", "VAT_NOT_SUBJECT"):
            with self.subTest(category=category):
                tax = self.tax(code=f"COMMERCIAL-{category}", tax_category=category,
                               rate=Decimal("15") if category == "VAT_STANDARD" else Decimal("0"))
                tax.full_clean()
                tax.save()
                tax.refresh_from_db()
                self.assertEqual(tax.tax_category, category)
                self.assertEqual(tax.code, f"COMMERCIAL-{category}")

    def test_category_is_not_inferred_from_code_name_or_rate(self):
        self.field()
        for code, name, rate in (("IVA15", "IVA ordinario", "15"),
                                 ("ZERO", "Exento", "0"), ("NOT-SUBJECT", "No objeto", "0")):
            with self.subTest(code=code):
                tax = self.tax(code=code, name=name, rate=Decimal(rate))
                tax.full_clean()
                tax.save()
                tax.refresh_from_db()
                self.assertIsNone(tax.tax_category)
                self.assertEqual(tax.code, code)
                self.assertEqual(tax.rate, Decimal(rate))

    def test_invalid_category_fails_model_validation(self):
        self.field()
        with self.assertRaises(ValidationError) as caught:
            self.tax(tax_category="UNKNOWN").full_clean()
        self.assertIn("tax_category", caught.exception.message_dict)
