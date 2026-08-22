from decimal import Decimal

from django.test import TestCase

from catalog.models import (
    Product,
    ProductGroup,
    ProductSubGroup,
    Tax,
    TaxConfiguration,
)

from catalog.services import TaxResolver

from core.models import Company
from people.models import Person


class TaxResolverTest(TestCase):

    def setUp(self):

        self.person = Person.objects.create(
            identification="0999999999991",
            person_type="LEGAL",
            full_name="Empresa Impuestos Test",
        )

        self.company = Company.objects.create(
            person=self.person,
            commercial_name="Empresa Impuestos Test",
        )

        self.iva = Tax.objects.create(
            company=self.company,
            name="IVA 15%",
            code="IVA15",
            tax_type="IVA",
            rate=Decimal("15.0000"),
        )

        self.ice = Tax.objects.create(
            company=self.company,
            name="ICE 10%",
            code="ICE10",
            tax_type="ICE",
            rate=Decimal("10.0000"),
        )

        self.group = ProductGroup.objects.create(
            company=self.company,
            name="Grupo Test",
        )

        self.subgroup = ProductSubGroup.objects.create(
            company=self.company,
            group=self.group,
            name="Subgrupo Test",
        )

        self.product = Product.objects.create(
            company=self.company,
            code="P-TAX-001",
            name="Producto Impuestos",
            group=self.group,
            subgroup=self.subgroup,
            cost_price=Decimal("10.00"),
            sale_price=Decimal("20.00"),
        )

        self.configuration = TaxConfiguration.objects.create(
            company=self.company,
        )

    def test_product_tax_has_priority(self):

        self.configuration.taxes.add(self.iva)
        self.group.taxes.add(self.iva)
        self.subgroup.taxes.add(self.iva)

        self.product.taxes.add(self.ice)

        taxes = TaxResolver.resolve(self.product)

        self.assertEqual(
            list(taxes),
            [self.ice],
        )

    def test_subgroup_tax_has_priority_over_group(self):

        self.configuration.taxes.add(self.iva)
        self.group.taxes.add(self.iva)

        self.subgroup.taxes.add(self.ice)

        taxes = TaxResolver.resolve(self.product)

        self.assertEqual(
            list(taxes),
            [self.ice],
        )

    def test_group_tax_has_priority_over_global(self):

        self.configuration.taxes.add(self.iva)

        self.group.taxes.add(self.ice)

        taxes = TaxResolver.resolve(self.product)

        self.assertEqual(
            list(taxes),
            [self.ice],
        )

    def test_global_tax_is_used_when_no_higher_level_exists(self):

        self.configuration.taxes.add(self.iva)

        taxes = TaxResolver.resolve(self.product)

        self.assertEqual(
            list(taxes),
            [self.iva],
        )

    def test_no_tax_returns_empty_queryset(self):

        taxes = TaxResolver.resolve(self.product)

        self.assertEqual(
            taxes.count(),
            0,
        )