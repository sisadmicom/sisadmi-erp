"""C-14B HTML contract for preparing a fiscal document from a Sale."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import SUCCESS
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase
from django.urls import NoReverseMatch, resolve, reverse

from core.constants.document_category import DocumentCategory
from core.constants.document_status import DocumentStatus
from core.constants.document_type_codes import DocumentTypeCodes
from core.constants.inventory_behavior import InventoryBehavior
from core.constants.line_behavior import LineBehavior
from core.models import Branch, Company, DocumentType, PointOfEmission
from inventory.models import Warehouse
from people.models import Customer, Person
from sales.models import Sale
from sri.constants.document_status import SriDocumentStatus
from sri.models import ElectronicDocument


class FiscalPreparationTriggerFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.invoice_type, _ = DocumentType.objects.get_or_create(
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
        cls.point = PointOfEmission.objects.create(
            branch=cls.branch, code="001", name="Caja principal", is_active=True
        )
        cls.inactive_point = PointOfEmission.objects.create(
            branch=cls.branch, code="002", name="Caja inactiva", is_active=False
        )
        cls.other_branch_point = PointOfEmission.objects.create(
            branch=cls.other_branch, code="001", name="Caja otra sucursal", is_active=True
        )
        cls.other_company_point = PointOfEmission.objects.create(
            branch=cls.other_company_branch,
            code="001",
            name="Caja otra empresa",
            is_active=True,
        )
        cls.warehouse = Warehouse.objects.create(
            company=cls.company, branch=cls.branch, code="W1", name="Principal"
        )
        cls.other_branch_warehouse = Warehouse.objects.create(
            company=cls.company, branch=cls.other_branch, code="W2", name="Otra"
        )
        cls.other_company_warehouse = Warehouse.objects.create(
            company=cls.other_company,
            branch=cls.other_company_branch,
            code="W3",
            name="Otra empresa",
        )
        cls.customer = cls.make_customer("main")

    @classmethod
    def make_company(cls, suffix):
        person = Person.objects.create(
            identification=f"C14B-C-{suffix}",
            person_type="LEGAL",
            full_name=f"Empresa {suffix}",
        )
        return Company.objects.create(person=person, commercial_name=f"Empresa {suffix}")

    @classmethod
    def make_customer(cls, suffix):
        person = Person.objects.create(
            identification=f"C14B-P-{suffix}",
            person_type="NATURAL",
            full_name=f"Cliente {suffix}",
        )
        return Customer.objects.create(person=person)

    def setUp(self):
        if not hasattr(self, "company"):
            # TransactionTestCase does not retain class-level fixtures the
            # same way TestCase does; seed its complete dataset explicitly.
            self.__class__.setUpTestData()
        self.user = get_user_model().objects.create_user(
            username=f"fiscal-trigger-{self.__class__.__name__}",
            password="test-password",
        )
        self.user.profile.companies.add(self.company, self.other_company)
        self.user.profile.branches.add(
            self.branch, self.other_branch, self.other_company_branch
        )
        self.client = Client()
        self.client.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk)

        self.prepare_patcher = patch(
            "sales.views.FiscalDocumentPreparationService", create=True
        )
        self.prepare_boundary = self.prepare_patcher.start()
        self.addCleanup(self.prepare_patcher.stop)
        self.prepare = self.prepare_boundary.prepare
        self.prepare.return_value = ElectronicDocument(
            status=SriDocumentStatus.GENERATED,
            sequential="000000001",
            emission_point=self.point.code,
            environment="1",
        )
        socket_patcher = patch(
            "socket.create_connection",
            side_effect=AssertionError("network access is disabled in C-14B tests"),
        )
        socket_patcher.start()
        self.addCleanup(socket_patcher.stop)
        self.forbidden_calls = []
        forbidden_targets = (
            "sri.models.electronic_document.ElectronicDocument.objects.create",
            "sri.models.electronic_document.ElectronicDocument.save",
            "sri.models.fiscal_sequence.FiscalSequence.objects.create",
            "sri.models.fiscal_sequence.FiscalSequence.save",
            "sri.services.electronic_document_service.ElectronicDocumentService.create",
            "sri.services.fiscal_sequence_service.FiscalSequenceService.next_number",
            "sri.services.access_key_service.AccessKeyService.generate",
            "sri.services.access_key_service.AccessKeyService.generate_numeric_code",
            "sri.services.electronic_invoice_service.ElectronicInvoiceService.generate",
            "sri.services.xml_generation_service.XmlGenerationService.generate",
            "sri.services.xml_generator_service.XmlGeneratorService.generate_invoice",
            "sri.services.xml_signing_service.XmlSigningService.sign",
            "sri.services.electronic_document_signing_service.ElectronicDocumentSigningService.sign",
            "sri.services.electronic_document_reception_service.ElectronicDocumentReceptionService.submit",
            "sri.services.electronic_document_authorization_service.ElectronicDocumentAuthorizationService.authorize",
            "sri.services.electronic_document_authorization_entrypoint.authorize_electronic_document",
        )
        for target in forbidden_targets:
            guard = patch(
                target,
                side_effect=AssertionError(f"C-14B boundary bypassed preparation: {target}"),
            )
            self.forbidden_calls.append(guard.start())
            self.addCleanup(guard.stop)

    def set_context(self, company_id, branch_id, *, client=None):
        session = (client or self.client).session
        session["company_id"] = company_id
        session["branch_id"] = branch_id
        session.save()

    def route(self, name, **kwargs):
        try:
            return reverse(name, kwargs=kwargs or None)
        except NoReverseMatch:
            self.fail(f"C-14B boundary absent: missing route {name!r}.")

    def prepare_path(self, sale_id):
        return self.route("sale_prepare_fiscal", sale_id=sale_id)

    def detail_path(self, sale_id):
        return reverse("sale_detail", kwargs={"sale_id": sale_id})

    def sale(self, **overrides):
        values = {
            "document_type": self.invoice_type,
            "company": self.company,
            "branch": self.branch,
            "customer": self.customer,
            "warehouse": self.warehouse,
            "status": DocumentStatus.CONFIRMED,
            "number": "SAL-001-000000001",
        }
        values.update(overrides)
        return Sale.objects.create(**values)

    def assert_prepare_not_called(self):
        self.prepare.assert_not_called()

    def assert_no_success_feedback(self, response):
        message_storage = response.context.get("messages", ())
        self.assertFalse(
            any(message.level == SUCCESS for message in message_storage)
        )


class SaleFiscalPreparationTriggerTests(FiscalPreparationTriggerFixtureMixin, TestCase):
    def test_route_exists_without_namespace_and_is_post_action_on_sale(self):
        sale = self.sale()
        path = self.prepare_path(sale.pk)
        self.assertEqual(path, f"/sales/{sale.pk}/prepare-fiscal/")
        match = resolve(path)
        self.assertEqual(match.url_name, "sale_prepare_fiscal")
        self.assertEqual(match.namespace, "")

    def test_anonymous_post_redirects_to_core_login_without_preparing(self):
        sale = self.sale()
        anonymous = Client()
        response = anonymous.post(
            self.prepare_path(sale.pk), {"point_of_emission": self.point.pk}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"/core/login/?next={self.prepare_path(sale.pk)}")
        self.assert_prepare_not_called()

    def test_missing_or_revoked_context_redirects_without_preparing(self):
        sale = self.sale()
        cases = (
            (None, None, "select_company"),
            (self.company.pk, None, "select_branch"),
            (self.company.pk, self.other_company_branch.pk, "select_branch"),
        )
        for company_id, branch_id, destination in cases:
            with self.subTest(company_id=company_id, branch_id=branch_id):
                self.set_context(company_id, branch_id)
                response = self.client.post(
                    self.prepare_path(sale.pk),
                    {"point_of_emission": self.point.pk},
                )
                self.assertRedirects(
                    response, reverse(destination), fetch_redirect_response=False
                )

        self.set_context(self.other_company.pk, self.other_company_branch.pk)
        self.user.profile.companies.remove(self.other_company)
        response = self.client.post(
            self.prepare_path(sale.pk),
            {"point_of_emission": self.point.pk},
        )
        self.assertRedirects(
            response, reverse("select_company"), fetch_redirect_response=False
        )

        self.set_context(self.company.pk, self.branch.pk)
        self.user.profile.branches.remove(self.branch)
        response = self.client.post(
            self.prepare_path(sale.pk),
            {"point_of_emission": self.point.pk},
        )
        self.assertRedirects(
            response, reverse("select_branch"), fetch_redirect_response=False
        )
        self.assert_prepare_not_called()

    def test_missing_cross_company_and_cross_branch_sales_are_404(self):
        own = self.sale()
        other_company_sale = self.sale(
            company=self.other_company,
            branch=self.other_company_branch,
            warehouse=self.other_company_warehouse,
        )
        other_branch_sale = self.sale(
            branch=self.other_branch,
            warehouse=self.other_branch_warehouse,
        )
        for sale_id in (other_company_sale.pk, other_branch_sale.pk, own.pk + 1000):
            with self.subTest(sale_id=sale_id):
                response = self.client.post(
                    self.prepare_path(sale_id),
                    {"point_of_emission": self.point.pk},
                )
                self.assertEqual(response.status_code, 404)
        self.assert_prepare_not_called()

    def test_sale_detail_get_is_safe_and_has_no_fiscal_side_effects(self):
        sale = self.sale()
        response = self.client.get(self.detail_path(sale.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["sale"].pk, sale.pk)
        self.assert_prepare_not_called()
        for guard in self.forbidden_calls:
            guard.assert_not_called()

    def test_prepare_endpoint_get_head_and_unsupported_methods_never_prepare(self):
        sale = self.sale()
        path = self.prepare_path(sale.pk)
        for method, expected in (
            ("get", 405), ("head", 405), ("put", 405), ("patch", 405),
            ("delete", 405), ("options", 405),
        ):
            with self.subTest(method=method):
                response = getattr(self.client, method)(path)
                self.assertEqual(response.status_code, expected)
        self.assert_prepare_not_called()

    def test_csrf_failure_from_sale_detail_form_blocks_preparation(self):
        sale = self.sale()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk, client=csrf_client)
        detail_response = csrf_client.get(self.detail_path(sale.pk))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'name="csrfmiddlewaretoken"')
        token = detail_response.cookies.get("csrftoken")
        self.assertIsNotNone(token)
        token_value = token.value
        response = csrf_client.post(
            self.prepare_path(sale.pk), {"point_of_emission": self.point.pk}
        )
        self.assertEqual(response.status_code, 403)
        self.assert_prepare_not_called()

        self.prepare.return_value = ElectronicDocument(status=SriDocumentStatus.GENERATED)
        response = csrf_client.post(
            self.prepare_path(sale.pk),
            {"point_of_emission": self.point.pk},
            HTTP_X_CSRFTOKEN=token_value,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.detail_path(sale.pk))
        self.prepare.assert_called_once_with(sale=sale, point_of_emission=self.point)

    def test_missing_inactive_and_other_branch_points_are_form_errors(self):
        sale = self.sale()
        payloads = (
            {},
            {"point_of_emission": self.inactive_point.pk},
            {"point_of_emission": self.other_branch_point.pk},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post(self.prepare_path(sale.pk), payload)
                self.assertEqual(response.status_code, 200)
                self.assertIn("sale", response.context)
                self.assert_prepare_not_called()

    def test_other_company_point_is_rejected_before_service(self):
        sale = self.sale()
        response = self.client.post(
            f"{self.prepare_path(sale.pk)}?company={self.other_company.pk}&branch={self.other_branch.pk}",
            {"point_of_emission": self.other_company_point.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("sale", response.context)
        self.assert_prepare_not_called()

    def test_valid_post_delegates_exact_objects_and_ignores_authority_tampering(self):
        sale = self.sale()
        self.prepare.return_value = ElectronicDocument(status=SriDocumentStatus.GENERATED)
        response = self.client.post(
            f"{self.prepare_path(sale.pk)}?company={self.other_company.pk}&branch={self.other_branch.pk}",
            {
                "point_of_emission": str(self.point.pk),
                "company": str(self.other_company.pk),
                "branch": str(self.other_branch.pk),
                "document_type": "PURCHASE_INVOICE",
                "environment": "2",
                "emission_type": "9",
                "access_key": "tampered-key",
                "sequential": "999999999",
                "authorization_number": "tampered-number",
                "status": "AUTHORIZED",
                "subtotal": "999999.99",
                "tax": "999999.99",
                "total": "999999.99",
                "ruc": "0000000000000",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.detail_path(sale.pk))
        self.prepare.assert_called_once_with(sale=sale, point_of_emission=self.point)

    def test_draft_sale_is_delegated_and_known_value_error_is_safe(self):
        sale = self.sale(status=DocumentStatus.DRAFT)
        self.prepare.side_effect = ValueError("internal status detail")
        response = self.client.post(
            self.prepare_path(sale.pk), {"point_of_emission": self.point.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["sale"].pk, sale.pk)
        self.assertNotContains(response, "internal status detail")
        self.assertNotContains(response, "Traceback")
        self.assert_no_success_feedback(response)
        self.prepare.assert_called_once_with(sale=sale, point_of_emission=self.point)

    def test_non_electronic_sale_eligibility_remains_owned_by_service(self):
        non_electronic_type = DocumentType.objects.create(
            code="SALES_INTERNAL_C14B",
            name="Venta interna",
            category=DocumentCategory.SALES,
            can_issue_electronic=False,
        )
        sale = self.sale(document_type=non_electronic_type)
        self.prepare.side_effect = ValueError("internal document type detail")
        response = self.client.post(
            self.prepare_path(sale.pk), {"point_of_emission": self.point.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "internal document type detail")
        self.prepare.assert_called_once_with(sale=sale, point_of_emission=self.point)

    def test_duplicate_preparation_is_delegated_and_not_reported_as_idempotent(self):
        sale = self.sale()
        self.prepare.side_effect = ValueError(
            "El documento ya tiene un documento electrónico generado."
        )
        response = self.client.post(
            self.prepare_path(sale.pk), {"point_of_emission": self.point.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.prepare.assert_called_once_with(sale=sale, point_of_emission=self.point)
        self.assertNotContains(response, "Traceback")
        self.assertNotContains(response, "El documento ya tiene un documento electrónico generado.")
        self.assert_no_success_feedback(response)

    def test_unexpected_exception_propagates(self):
        sale = self.sale()
        self.prepare.side_effect = RuntimeError("unexpected preparation failure")
        with self.assertRaisesMessage(RuntimeError, "unexpected preparation failure"):
            self.client.post(
                self.prepare_path(sale.pk),
                {"point_of_emission": self.point.pk},
            )

    def test_success_uses_prg_and_exposes_semantic_feedback(self):
        sale = self.sale()
        self.prepare.return_value = ElectronicDocument(
            status=SriDocumentStatus.GENERATED,
            sequential="000000001",
            emission_point=self.point.code,
            environment="1",
        )
        response = self.client.post(
            self.prepare_path(sale.pk), {"point_of_emission": self.point.pk}, follow=True
        )
        self.assertEqual(response.redirect_chain, [(self.detail_path(sale.pk), 302)])
        messages = list(response.context["messages"])
        success_messages = [message for message in messages if message.level == SUCCESS]
        self.assertTrue(success_messages)
        for message in success_messages:
            self.assertContains(response, str(message))
        self.prepare.assert_called_once_with(sale=sale, point_of_emission=self.point)


class SaleFiscalPreparationTransactionBoundaryTests(
    FiscalPreparationTriggerFixtureMixin, TransactionTestCase
):
    reset_sequences = True

    def test_prepare_is_called_outside_an_external_atomic_block(self):
        sale = self.sale()
        observed_atomic = []

        def observe(*, sale, point_of_emission):
            observed_atomic.append(connection.in_atomic_block)
            return ElectronicDocument(status=SriDocumentStatus.GENERATED)

        self.prepare.side_effect = observe
        response = self.client.post(
            self.prepare_path(sale.pk), {"point_of_emission": self.point.pk}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(observed_atomic, [False])
        self.prepare.assert_called_once_with(sale=sale, point_of_emission=self.point)
