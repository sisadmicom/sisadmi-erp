"""Deterministic fixtures shared only by new CLIENTES-01.3 tests."""
from datetime import date
from decimal import Decimal
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from catalog.models import Product
from core.models import Branch, Company, DocumentType, Sequence
from inventory.models import Stock, Warehouse
from people.models import Person, Customer, CompanyPersonAccess, CustomerCategory, IdentificationKind
from people.constants.identification_type import IdentificationType
from people.services import customer_maintenance
from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from sales.use_cases.create_sale import CreateSale
from sales.use_cases.confirm_sale import ConfirmSale
from sales.use_cases.cancel_sale import CancelSale
from core.testing.clientes013_guard import verify_identity


def business_snapshot():
    """Full values, not merely counts: no silent changes to historical records."""
    return {model._meta.label: list(model._base_manager.order_by('pk').values())
            for model in apps.get_models() if model._meta.app_label in
            {'people', 'sales', 'inventory', 'core'}}


class CustomerDocumentFixture:
    def setUp(self):
        super().setUp()
        with connection.cursor() as cursor:
            verify_identity(cursor)
        self.prepare_identification_kinds()
        self.actor = get_user_model().objects.create_superuser('cli013-operator', '', None)
        self.company = Company.objects.create(person=self.person('COMPANY', 'LEGAL'))
        self.other = Company.objects.create(person=self.person('OTHER', 'LEGAL'))
        self.actor.profile.companies.add(self.company)
        self.branch = Branch.objects.create(company=self.company, code='001', name='CLI013 branch')
        self.actor.profile.branches.add(self.branch)
        self.warehouse = Warehouse.objects.create(company=self.company, branch=self.branch, code='W', name='CLI013 warehouse')
        self.original = self.person('ORIGINAL')
        self.replacement = self.person('REPLACEMENT')
        self.second = self.person('SECOND')
        for person in [self.original, self.replacement, self.second]:
            CompanyPersonAccess.objects.create(company=self.company, person=person)
        self.category = CustomerCategory.objects.create(company=self.company, code='CLI013', name='CLI013 category')
        self.customer = customer_maintenance.create(actor=self.actor, company=self.company,
            person_id=self.original.pk, data={'category': self.category})
        dtype = DocumentType.objects.get(code='SALES_INVOICE')
        self.sequence = Sequence.objects.create(company=self.company, branch=self.branch,
            document_type=dtype, name='CLI013 sales', prefix='CLI-', next_number=1)
        self.product = Product.objects.create(company=self.company, code='CLI013', name='CLI013 product')
        self.stock = Stock.objects.create(company=self.company, branch=self.branch, warehouse=self.warehouse,
            product=self.product, quantity=Decimal('100'), reserved_quantity=Decimal('0'))

    def prepare_identification_kinds(self):
        # All CLI013-* fixture identities are nonnumeric: the central detector
        # classifies them as OTHER. TransactionTestCase removes migration seeds.
        # Recreate only the required official kind, before any Person INSERT.
        kind, _ = IdentificationKind.objects.get_or_create(
            code=IdentificationType.OTHER,
            defaults={'name': IdentificationType.OTHER.label, 'is_active': True},
        )
        self.assertTrue(kind.is_active, 'The fixture requires an active OTHER kind')

    def person(self, suffix, kind='NATURAL'):
        return Person.objects.create(identification='CLI013-'+suffix, person_type=kind, full_name='CLI013 '+suffix)

    def sale(self):
        return CreateSale.execute(SaleCreateDTO(company_id=self.company.pk, branch_id=self.branch.pk,
            customer_id=self.customer.pk, warehouse_id=self.warehouse.pk, issue_date=date(2026, 10, 1),
            notes='CLI013', details=[SaleDetailDTO(product_id=self.product.pk, quantity=Decimal('2'),
            unit_price=Decimal('10'), discount=Decimal('0'))]))

    def sale_in_state(self, status):
        sale = self.sale()
        if status in {'CONFIRMED', 'CANCELLED'}:
            ConfirmSale.execute(sale.pk, user=self.actor)
        if status == 'CANCELLED':
            CancelSale.execute(sale.pk, user=self.actor)
        sale.refresh_from_db()
        self.assertEqual(sale.status, status)
        return sale
