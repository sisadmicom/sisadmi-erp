from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Product
from core.models import Branch, Company
from inventory.models import Warehouse
from people.models import Customer, Person
from sales.constants.payment_method import PaymentMethod
from sales.models import Sale


class SalePaymentMethodHTTPTests(TestCase):
    def setUp(self):
        person = Person.objects.create(identification="R04-issuer", person_type="LEGAL", full_name="R04 issuer")
        self.company = Company.objects.create(person=person)
        self.branch = Branch.objects.create(company=self.company, code="001", name="Main")
        self.warehouse = Warehouse.objects.create(company=self.company, branch=self.branch, code="MAIN", name="Main")
        buyer = Person.objects.create(identification="R04-buyer", full_name="R04 buyer")
        self.customer = Customer.objects.create(company=self.company, person=buyer)
        self.product = Product.objects.create(company=self.company, code="R04", name="Product")
        user = get_user_model().objects.create_user("r04-sales")
        user.profile.companies.add(self.company)
        user.profile.branches.add(self.branch)
        self.client.force_login(user)
        session = self.client.session
        session.update({"company_id": self.company.pk, "branch_id": self.branch.pk})
        session.save()

    def payload(self, **changes):
        result = dict(customer_id=self.customer.pk, warehouse_id=self.warehouse.pk,
            issue_date="2026-10-15", notes="R04", payment_method=PaymentMethod.CREDIT_CARD,
            **{"details-TOTAL_FORMS": "1", "details-INITIAL_FORMS": "0", "details-MIN_NUM_FORMS": "1", "details-MAX_NUM_FORMS": "1000",
               "details-0-product_id": self.product.pk, "details-0-quantity": "2", "details-0-unit_price": "10.25", "details-0-discount": "0"})
        result.update(changes)
        return result

    def test_form_shows_existing_payment_choices(self):
        response = self.client.get(reverse("sale_create"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["form"].fields["payment_method"].choices)[1:], list(PaymentMethod.choices))

    def test_http_payment_survives_validation_dto_service_and_persistence(self):
        for value in PaymentMethod.values:
            with self.subTest(payment=value):
                response = self.client.post(reverse("sale_create"), self.payload(payment_method=value))
                self.assertEqual(response.status_code, 302)
                sale = Sale.objects.latest("pk")
                self.assertEqual(sale.payment_method, value)
                self.assertEqual(sale.issue_date, date(2026, 10, 15))
                self.assertEqual(sale.total, Decimal("20.50"))
                self.assertEqual(sale.company_id, self.company.pk)
                self.assertEqual(sale.branch_id, self.branch.pk)

    def test_unrecognized_payment_never_creates_a_sale(self):
        response = self.client.post(reverse("sale_create"), self.payload(payment_method="99"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("payment_method", response.context["form"].errors)
        self.assertFalse(Sale.objects.exists())

    def test_omission_is_preserved_as_missing_for_commercial_drafts(self):
        payload = self.payload()
        payload.pop("payment_method")
        response = self.client.post(reverse("sale_create"), payload)
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(Sale.objects.get().payment_method)
