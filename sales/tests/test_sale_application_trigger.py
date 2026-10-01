"""C-14A HTTP contract for creating, reviewing and confirming sales.

The application boundary is intentionally absent during RED. Tests patch only
the existing use cases and exercise Django routing, authentication, context,
forms, ownership and delegation; domain calculations and stock are out of scope.
"""

from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.urls import NoReverseMatch, resolve, reverse

from catalog.models import Product
from core.constants.document_category import DocumentCategory
from core.constants.document_type_codes import DocumentTypeCodes
from core.constants.inventory_behavior import InventoryBehavior
from core.constants.line_behavior import LineBehavior
from core.exceptions import InvalidPrice, InvalidQuantity
from core.models import Branch, Company, DocumentType
from inventory.models import Warehouse
from inventory.models import StockMovement
from people.models import Customer, Person
from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from sales.models import Sale


CREATE_URL_NAME = "sale_create"
DETAIL_URL_NAME = "sale_detail"
CONFIRM_URL_NAME = "sale_confirm"
LOGIN_URL_NAME = "login"


class SaleApplicationTriggerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sale_type, _ = DocumentType.objects.get_or_create(
            code=DocumentTypeCodes.SALES_INVOICE,
            defaults={
                "name": "Factura de venta",
                "category": DocumentCategory.SALES,
                "line_behavior": LineBehavior.COMMERCIAL,
                "requires_detail": True,
                "affects_inventory": True,
                "inventory_behavior": InventoryBehavior.OUT,
                "can_issue_electronic": True,
            },
        )
        cls.company = cls.make_company("main")
        cls.branch = Branch.objects.create(
            company=cls.company, code="001", name="Matriz"
        )
        cls.other_branch = Branch.objects.create(
            company=cls.company, code="002", name="Sucursal 2"
        )
        cls.other_company = cls.make_company("other")
        cls.other_company_branch = Branch.objects.create(
            company=cls.other_company, code="001", name="Otra empresa"
        )
        cls.warehouse = Warehouse.objects.create(
            company=cls.company, branch=cls.branch, code="W1", name="Principal"
        )
        cls.other_branch_warehouse = Warehouse.objects.create(
            company=cls.company,
            branch=cls.other_branch,
            code="W2",
            name="Otra sucursal",
        )
        cls.other_company_warehouse = Warehouse.objects.create(
            company=cls.other_company,
            branch=cls.other_company_branch,
            code="W3",
            name="Otra empresa",
        )
        cls.customer = cls.make_customer("customer-main")
        # Customer has no company relation and is intentionally valid globally.
        cls.global_customer = cls.make_customer("customer-global")
        cls.product = Product.objects.create(
            company=cls.company, code="P1", name="Producto 1"
        )
        cls.inactive_product = Product.objects.create(
            company=cls.company,
            code="P-INACTIVE",
            name="Producto inactivo",
            is_active=False,
        )
        cls.other_product = Product.objects.create(
            company=cls.other_company, code="P2", name="Producto ajeno"
        )
        cls.inactive_customer = cls.make_customer("inactive")
        cls.inactive_customer.is_active = False
        cls.inactive_customer.save(update_fields=["is_active"])
        cls.inactive_warehouse = Warehouse.objects.create(
            company=cls.company,
            branch=cls.branch,
            code="W-INACTIVE",
            name="Bodega inactiva",
            is_active=False,
        )

    @classmethod
    def make_company(cls, suffix):
        person = Person.objects.create(
            identification=f"C14A-{suffix}",
            person_type="LEGAL",
            full_name=f"Empresa {suffix}",
        )
        return Company.objects.create(person=person, commercial_name=f"Empresa {suffix}")

    @classmethod
    def make_customer(cls, suffix):
        person = Person.objects.create(
            identification=f"C14A-{suffix}",
            person_type="NATURAL",
            full_name=f"Cliente {suffix}",
        )
        return Customer.objects.create(person=person)

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="sale-trigger-user", password="test-password"
        )
        self.user.profile.companies.add(self.company)
        self.user.profile.branches.add(self.branch, self.other_branch)
        self.client.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk)

        create_patcher = patch("sales.views.CreateSale", create=True)
        create_boundary = create_patcher.start()
        self.addCleanup(create_patcher.stop)
        self.create_use_case = create_boundary.execute
        confirm_patcher = patch("sales.views.ConfirmSale", create=True)
        confirm_boundary = confirm_patcher.start()
        self.addCleanup(confirm_patcher.stop)
        self.confirm_use_case = confirm_boundary.execute
        self.create_use_case.side_effect = None
        self.create_use_case.return_value = None
        self.confirm_use_case.side_effect = None
        self.confirm_use_case.return_value = None

        # The commercial boundary must stop before any fiscal workflow.
        forbidden = (
            "sri.services.fiscal_document_preparation_service."
            "FiscalDocumentPreparationService.prepare",
            "sri.services.electronic_document_service.ElectronicDocumentService.create",
            "sri.services.xml_generation_service.XmlGenerationService.generate",
            "sri.services.electronic_document_signing_service."
            "ElectronicDocumentSigningService.sign",
            "sri.services.electronic_document_reception_service."
            "ElectronicDocumentReceptionService.submit",
            "sri.services.electronic_document_authorization_entrypoint."
            "authorize_electronic_document",
        )
        self.fiscal_guards = []
        for target in forbidden:
            guard = patch(target, side_effect=AssertionError("SRI outside C-14A"))
            self.fiscal_guards.append(guard.start())
            self.addCleanup(guard.stop)

    def set_context(self, company_id, branch_id, client=None):
        target = client or self.client
        session = target.session
        session["company_id"] = company_id
        session["branch_id"] = branch_id
        session.save()

    def route(self, name, **kwargs):
        try:
            return reverse(name, kwargs=kwargs or None)
        except NoReverseMatch:
            self.fail(f"C-14A boundary absent: missing route {name!r}.")

    def create_path(self):
        return self.route(CREATE_URL_NAME)

    def detail_path(self, sale_id):
        return self.route(DETAIL_URL_NAME, sale_id=sale_id)

    def confirm_path(self, sale_id):
        return self.route(CONFIRM_URL_NAME, sale_id=sale_id)

    def sale(self, **overrides):
        values = {
            "document_type": self.sale_type,
            "company": self.company,
            "branch": self.branch,
            "customer": self.customer,
            "warehouse": self.warehouse,
            "issue_date": date(2026, 9, 30),
            "notes": "Venta de prueba",
        }
        values.update(overrides)
        return Sale.objects.create(**values)

    def create_payload(self, **overrides):
        values = {
            "customer_id": str(self.customer.pk),
            "warehouse_id": str(self.warehouse.pk),
            "issue_date": "2026-09-30",
            "notes": "Venta desde formulario",
            "details-TOTAL_FORMS": "1",
            "details-INITIAL_FORMS": "0",
            "details-MIN_NUM_FORMS": "1",
            "details-MAX_NUM_FORMS": "1000",
            "details-0-product_id": str(self.product.pk),
            "details-0-quantity": "2.000000",
            "details-0-unit_price": "10.00",
            "details-0-discount": "0.00",
        }
        values.update(overrides)
        return values

    def assert_no_fiscal_calls(self):
        for guard in self.fiscal_guards:
            guard.assert_not_called()

    def assert_login_redirect(self, response, path):
        self.assertEqual(response.status_code, 302)
        location = urlsplit(response["Location"])
        self.assertEqual(location.path, reverse(LOGIN_URL_NAME))
        self.assertEqual(parse_qs(location.query), {"next": [path]})

    def test_routes_names_and_view_contract(self):
        create_url = self.route(CREATE_URL_NAME)
        detail_url = self.route(DETAIL_URL_NAME, sale_id=1)
        confirm_url = self.route(CONFIRM_URL_NAME, sale_id=1)
        self.assertEqual(create_url, self.create_path())
        self.assertEqual(detail_url, self.detail_path(1))
        self.assertEqual(confirm_url, self.confirm_path(1))
        for url, name, view_name in (
            (create_url, CREATE_URL_NAME, "sale_create"),
            (detail_url, DETAIL_URL_NAME, "sale_detail"),
            (confirm_url, CONFIRM_URL_NAME, "sale_confirm"),
        ):
            match = resolve(url)
            self.assertEqual(match.url_name, name)
            self.assertEqual(match.namespace, "")
            self.assertEqual(match.func.__module__, "sales.views")
            self.assertEqual(match.func.__name__, view_name)

    def test_anonymous_create_and_confirm_redirect_to_core_login(self):
        sale = self.sale()
        anonymous = Client()
        for path, method in (
            (self.create_path(), "get"),
            (self.create_path(), "post"),
            (self.confirm_path(sale.pk), "post"),
        ):
            with self.subTest(path=path, method=method):
                response = getattr(anonymous, method)(path, self.create_payload())
                self.assert_login_redirect(response, path)
        self.create_use_case.assert_not_called()
        self.confirm_use_case.assert_not_called()

    def test_missing_or_revoked_context_blocks_create_and_confirm(self):
        sale = self.sale()
        cases = (
            (None, None, "select_company"),
            (self.company.pk, None, "select_branch"),
            (self.other_company.pk, self.other_company_branch.pk, "select_company"),
            (self.company.pk, self.other_company_branch.pk, "select_branch"),
        )
        for company_id, branch_id, destination in cases:
            for path, method in (
                (self.create_path(), "get"),
                (self.create_path(), "post"),
                (self.confirm_path(sale.pk), "post"),
            ):
                with self.subTest(context=(company_id, branch_id), path=path):
                    self.set_context(company_id, branch_id)
                    response = getattr(self.client, method)(path, self.create_payload())
                    self.assertRedirects(
                        response, reverse(destination), fetch_redirect_response=False
                    )
        self.user.profile.companies.remove(self.company)
        self.set_context(self.company.pk, self.branch.pk)
        response = self.client.post(self.create_path(), self.create_payload())
        self.assertRedirects(
            response, reverse("select_company"), fetch_redirect_response=False
        )
        self.create_use_case.assert_not_called()
        self.confirm_use_case.assert_not_called()

    def test_create_get_is_safe_and_does_not_call_use_case(self):
        response = self.client.get(self.create_path())
        self.assertEqual(response.status_code, 200)
        for method in ("put", "patch", "delete", "options"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.create_path())
                self.assertEqual(response.status_code, 405)
        head_response = self.client.head(self.create_path())
        self.assertEqual(head_response.status_code, 200)
        self.create_use_case.assert_not_called()
        self.assertEqual(Sale.objects.count(), 0)
        self.assert_no_fiscal_calls()

    def test_valid_create_maps_active_context_and_only_dto_fields_then_prg(self):
        created_sale = self.sale()
        self.create_use_case.return_value = created_sale
        transaction_depth = len(connection.atomic_blocks)
        observed_depths = []
        self.create_use_case.side_effect = lambda dto: (
            observed_depths.append(len(connection.atomic_blocks)), created_sale
        )[1]
        response = self.client.post(
            self.create_path(),
            self.create_payload(
                company=str(self.other_company.pk),
                branch=str(self.other_branch.pk),
                document_type="PURCHASE_INVOICE",
                subtotal="999999.99",
                tax="888888.88",
                total="777777.77",
                created_by="999",
                updated_by="999",
                user_id="999",
                detail_subtotal="666666.66",
                detail_tax="555555.55",
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.detail_path(created_sale.pk))
        created_sale.refresh_from_db()
        self.assertIsNone(created_sale.created_by_id)
        self.assertIsNone(created_sale.updated_by_id)
        self.create_use_case.assert_called_once()
        (dto,), kwargs = self.create_use_case.call_args
        self.assertEqual(kwargs, {})
        self.assertIsInstance(dto, SaleCreateDTO)
        self.assertEqual(dto.company_id, self.company.pk)
        self.assertEqual(dto.branch_id, self.branch.pk)
        self.assertEqual(dto.customer_id, self.customer.pk)
        self.assertEqual(dto.warehouse_id, self.warehouse.pk)
        self.assertEqual(dto.issue_date, date(2026, 9, 30))
        self.assertEqual(dto.notes, "Venta desde formulario")
        self.assertEqual(len(dto.details), 1)
        self.assertEqual(dto.details[0], SaleDetailDTO(
            product_id=self.product.pk,
            quantity=Decimal("2.000000"),
            unit_price=Decimal("10.00"),
            discount=Decimal("0.00"),
        ))
        self.assertFalse(hasattr(dto, "document_type"))
        self.assertFalse(hasattr(dto, "subtotal"))
        self.assertFalse(hasattr(dto, "user_id"))
        self.assertEqual(observed_depths, [transaction_depth])
        self.assert_no_fiscal_calls()

    def test_create_preserves_multiple_detail_lines_and_editable_price(self):
        self.create_use_case.return_value = self.sale()
        payload = self.create_payload(
            **{
                "details-TOTAL_FORMS": "2",
                "details-1-product_id": str(self.product.pk),
                "details-1-quantity": "3.000000",
                "details-1-unit_price": "7.25",
                "details-1-discount": "1.00",
            }
        )
        payload["details-0-unit_price"] = "12.50"
        response = self.client.post(self.create_path(), payload)
        self.assertEqual(response.status_code, 302)
        self.create_use_case.assert_called_once()
        dto = self.create_use_case.call_args.args[0]
        self.assertEqual(len(dto.details), 2)
        self.assertEqual(dto.details[0].unit_price, Decimal("12.50"))
        self.assertEqual(dto.details[1].unit_price, Decimal("7.25"))

    def test_global_customer_without_company_relation_is_accepted(self):
        self.create_use_case.return_value = self.sale()
        response = self.client.post(
            self.create_path(),
            self.create_payload(customer_id=str(self.global_customer.pk)),
        )
        self.assertEqual(response.status_code, 302)
        dto = self.create_use_case.call_args.args[0]
        self.assertEqual(dto.customer_id, self.global_customer.pk)

    def test_product_company_and_active_scope_is_enforced(self):
        for product in (self.other_product, self.inactive_product):
            with self.subTest(product=product.pk):
                response = self.client.post(
                    self.create_path(),
                    self.create_payload(**{"details-0-product_id": str(product.pk)}),
                )
                self.assertEqual(response.status_code, 200)
        self.create_use_case.assert_not_called()

    def test_cross_branch_warehouse_does_not_reach_create_use_case(self):
        for warehouse in (
            self.other_branch_warehouse,
            self.other_company_warehouse,
            self.inactive_warehouse,
        ):
            with self.subTest(warehouse=warehouse.pk):
                response = self.client.post(
                    self.create_path(),
                    self.create_payload(warehouse_id=str(warehouse.pk)),
                )
                self.assertEqual(response.status_code, 200)
        self.create_use_case.assert_not_called()

    def test_missing_customer_or_product_is_a_form_error(self):
        for payload in (
            self.create_payload(customer_id="999999"),
            self.create_payload(customer_id=str(self.inactive_customer.pk)),
            self.create_payload(**{"details-0-product_id": ""}),
        ):
            with self.subTest(payload=payload):
                response = self.client.post(self.create_path(), payload)
                self.assertEqual(response.status_code, 200)
        self.create_use_case.assert_not_called()

    def test_empty_details_are_rejected_without_calling_create(self):
        response = self.client.post(
            self.create_path(),
            self.create_payload(**{"details-TOTAL_FORMS": "0"}),
        )
        self.assertEqual(response.status_code, 200)
        self.create_use_case.assert_not_called()

    def test_known_quantity_and_price_domain_errors_are_safe(self):
        for error in (InvalidQuantity(), InvalidPrice()):
            with self.subTest(error=type(error).__name__):
                self.create_use_case.reset_mock()
                self.create_use_case.side_effect = error
                response = self.client.post(self.create_path(), self.create_payload())
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "Traceback")
                self.create_use_case.assert_called_once()
        self.assert_no_fiscal_calls()

    def test_unexpected_create_exception_propagates(self):
        self.create_use_case.side_effect = RuntimeError("unexpected create failure")
        with self.assertRaisesMessage(RuntimeError, "unexpected create failure"):
            self.client.post(self.create_path(), self.create_payload())

    def test_create_and_confirm_require_csrf_for_mutations(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk, client=csrf_client)
        create_response = csrf_client.get(self.create_path())
        self.assertEqual(create_response.status_code, 200)
        token = csrf_client.cookies["csrftoken"].value
        sale = self.sale()
        for path in (self.create_path(), self.confirm_path(sale.pk)):
            with self.subTest(path=path):
                response = csrf_client.post(path, self.create_payload())
                self.assertEqual(response.status_code, 403)
        self.create_use_case.assert_not_called()
        self.confirm_use_case.assert_not_called()
        self.create_use_case.return_value = self.sale()
        response = csrf_client.post(
            self.create_path(), self.create_payload(), HTTP_X_CSRFTOKEN=token
        )
        self.assertEqual(response.status_code, 302)
        self.create_use_case.assert_called_once()
        self.confirm_use_case.return_value = sale
        response = csrf_client.post(
            self.confirm_path(sale.pk), self.create_payload(), HTTP_X_CSRFTOKEN=token
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.detail_path(sale.pk))
        self.confirm_use_case.assert_called_once_with(sale_id=sale.pk, user=self.user)

    def test_detail_is_scoped_and_read_only(self):
        sale = self.sale()
        response = self.client.get(self.detail_path(sale.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["sale"].pk, sale.pk)
        self.create_use_case.assert_not_called()
        self.confirm_use_case.assert_not_called()

    def test_confirm_is_post_only_and_does_not_mutate_on_get_or_head(self):
        sale = self.sale()
        for method in ("get", "head", "put", "patch", "delete", "options"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.confirm_path(sale.pk))
                self.assertEqual(response.status_code, 405)
        self.confirm_use_case.assert_not_called()
        self.assertEqual(Sale.objects.get(pk=sale.pk).status, "DRAFT")

    def test_confirm_scoped_lookup_hides_foreign_branch_company_and_missing_ids(self):
        own = self.sale()
        foreign_branch_sale = self.sale(branch=self.other_branch, warehouse=self.other_branch_warehouse)
        foreign_company_sale = self.sale(
            company=self.other_company,
            branch=self.other_company_branch,
            warehouse=self.other_company_warehouse,
        )
        missing_id = max(own.pk, foreign_branch_sale.pk, foreign_company_sale.pk) + 100
        self.user.profile.companies.add(self.other_company)
        self.user.profile.branches.add(self.other_company_branch)
        for sale_id in (foreign_branch_sale.pk, foreign_company_sale.pk, missing_id):
            with self.subTest(sale_id=sale_id):
                detail_response = self.client.get(self.detail_path(sale_id))
                self.assertEqual(detail_response.status_code, 404)
                response = self.client.post(self.confirm_path(sale_id))
                self.assertEqual(response.status_code, 404)
        self.confirm_use_case.assert_not_called()

    def test_valid_confirm_delegates_exact_id_and_authenticated_user(self):
        sale = self.sale()
        self.confirm_use_case.return_value = sale
        transaction_depth = len(connection.atomic_blocks)
        observed_depths = []
        movement_count = StockMovement.objects.count()
        self.confirm_use_case.side_effect = lambda **kwargs: (
            observed_depths.append(len(connection.atomic_blocks)), sale
        )[1]
        response = self.client.post(self.confirm_path(sale.pk))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.detail_path(sale.pk))
        self.confirm_use_case.assert_called_once_with(sale_id=sale.pk, user=self.user)
        self.assertEqual(observed_depths, [transaction_depth])
        self.assertEqual(StockMovement.objects.count(), movement_count)
        self.assertEqual(Sale.objects.get(pk=sale.pk).status, "DRAFT")
        self.assert_no_fiscal_calls()

    def test_confirm_does_not_precheck_status_and_never_accepts_post_user(self):
        sale = self.sale(status="CONFIRMED")
        self.confirm_use_case.return_value = sale
        response = self.client.post(
            self.confirm_path(sale.pk),
            {"user_id": "999", "company": self.other_company.pk, "branch": self.other_branch.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.detail_path(sale.pk))
        self.confirm_use_case.assert_called_once_with(sale_id=sale.pk, user=self.user)

    def test_known_confirm_domain_error_is_not_reported_as_success_or_technical_detail(self):
        sale = self.sale()
        self.confirm_use_case.side_effect = ValueError("internal state detail")
        response = self.client.post(self.confirm_path(sale.pk))
        self.assertEqual(response.status_code, 200)
        self.confirm_use_case.assert_called_once_with(sale_id=sale.pk, user=self.user)
        self.assertNotContains(response, "internal state detail")
        self.assertNotContains(response, "Traceback")

    def test_unexpected_confirm_exception_propagates(self):
        sale = self.sale()
        self.confirm_use_case.side_effect = RuntimeError("unexpected confirm failure")
        with self.assertRaisesMessage(RuntimeError, "unexpected confirm failure"):
            self.client.post(self.confirm_path(sale.pk))
