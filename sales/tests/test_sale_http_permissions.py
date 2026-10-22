"""SEG-01A HTTP authorization contracts; requires an authorized isolated PostgreSQL."""

from contextlib import ExitStack
from decimal import Decimal
from html.parser import HTMLParser
from itertools import combinations
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from catalog.models import Product
from core.constants.document_status import DocumentStatus
from core.constants.sri import SriDocumentType
from core.models import PointOfEmission, Sequence
from inventory.models import Stock, StockMovement
from people.models import Customer, Person
from sales.models import Sale, SaleDetail, SaleDetailTax, SaleMovement
from sales.tests.test_sale_fiscal_preparation_trigger import (
    FiscalPreparationTriggerFixtureMixin,
)
from sri.constants.document_status import SriDocumentStatus
from sri.models import (
    ElectronicDocument,
    FiscalSequence,
    SriAuthorizationAttempt,
    SriReceptionAttempt,
)


class SalesActionsHTML(HTMLParser):
    """Inspect the Sales content without conflating it with the shared shell."""

    def __init__(self, content):
        super().__init__()
        self.in_main = False
        self.buttons = {}
        self.forms = []
        self.links = []
        self.current_button = None
        self.feed(content.decode())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "main":
            self.in_main = True
        if not self.in_main:
            return
        if tag == "button":
            self.current_button = (attrs, [])
        elif tag == "form":
            self.forms.append(attrs.get("action"))
        elif tag == "a":
            self.links.append(attrs.get("href"))

    def handle_data(self, data):
        if self.current_button is not None:
            self.current_button[1].append(data)

    def handle_endtag(self, tag):
        if tag == "button" and self.current_button is not None:
            attrs, text = self.current_button
            self.buttons[" ".join("".join(text).split())] = attrs
            self.current_button = None
        elif tag == "main":
            self.in_main = False


class SaleHTTPPermissionsTests(FiscalPreparationTriggerFixtureMixin, TestCase):
    ALL_PERMISSIONS = (
        "sales.view_sale", "sales.add_sale", "sales.change_sale",
        "sri.view_electronicdocument", "sri.add_electronicdocument",
        "sri.change_electronicdocument",
    )
    BUSINESS_MODELS = (
        Sale, SaleDetail, SaleDetailTax, SaleMovement, Sequence, Stock,
        StockMovement, ElectronicDocument, FiscalSequence,
        SriReceptionAttempt, SriAuthorizationAttempt,
    )

    def setUp(self):
        # Do not inherit C-14B's authorized actor or its domain mutation patches.
        self.user = get_user_model().objects.create_user(username="seg01a-operator")
        self.user.profile.companies.add(self.company)
        self.user.profile.branches.add(self.branch)
        self.client.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk)
        self.product = Product.objects.create(company=self.company, code="SEG01A", name="Prueba")
        self.draft = self.sale(status=DocumentStatus.DRAFT, number="")
        self.confirmed = self.sale()
        Sequence.objects.create(
            company=self.company, branch=self.branch, document_type=self.invoice_type,
            name="SEG-01A", prefix="VEN-", series="001",
        )
        Stock.objects.create(
            company=self.company, branch=self.branch, warehouse=self.warehouse,
            product=self.product, quantity=Decimal("10"),
        )
        self.boundaries = []
        for target, result in (
            ("sales.views.CreateSale.execute", self.draft),
            ("sales.views.ConfirmSale.execute", self.draft),
            ("sales.views.FiscalDocumentPreparationService.prepare", None),
        ):
            patcher = patch(target, return_value=result)
            self.boundaries.append(patcher.start())
            self.addCleanup(patcher.stop)
        self.create, self.confirm, self.prepare = self.boundaries
        network = patch("socket.create_connection", side_effect=AssertionError("No network in SEG-01A"))
        network.start()
        self.addCleanup(network.stop)

    def grant(self, *permissions):
        records = []
        for permission in permissions:
            app, codename = permission.split(".", 1)
            records.append(Permission.objects.get(content_type__app_label=app, codename=codename))
        self.user.user_permissions.set(records)

    def create_payload(self):
        return {
            "customer_id": self.customer.pk, "warehouse_id": self.warehouse.pk,
            "issue_date": "2026-10-15", "notes": "SEG-01A",
            "details-TOTAL_FORMS": "1", "details-INITIAL_FORMS": "0",
            "details-MIN_NUM_FORMS": "1", "details-MAX_NUM_FORMS": "1000",
            "details-0-product_id": self.product.pk, "details-0-quantity": "1",
            "details-0-unit_price": "10", "details-0-discount": "0",
        }

    def operations(self):
        return (
            ("create", reverse("sale_create"), ("get", "head", "post"),
             ("sales.view_sale", "sales.add_sale"), self.create_payload()),
            ("detail", self.detail_path(self.draft.pk), ("get", "head"),
             ("sales.view_sale",), {}),
            ("confirm", reverse("sale_confirm", args=[self.draft.pk]), ("post",),
             ("sales.view_sale", "sales.change_sale"), {}),
            ("prepare", self.prepare_path(self.confirmed.pk), ("post",),
             ("sales.view_sale", "sri.view_electronicdocument", "sri.add_electronicdocument"),
             {"point_of_emission": self.point.pk}),
        )

    def snapshot(self):
        return {
            model._meta.label_lower: list(model.objects.order_by("pk").values())
            for model in self.BUSINESS_MODELS
        }

    def assert_no_services(self):
        for boundary in self.boundaries:
            boundary.assert_not_called()

    def electronic(self):
        return ElectronicDocument.objects.create(
            company=self.company, branch=self.branch,
            content_type=ContentType.objects.get_for_model(Sale), object_id=self.confirmed.pk,
            document_type=SriDocumentType.INVOICE, establishment=self.branch.code,
            emission_point=self.point.code, sequential="000000001", numeric_code="12345678",
            access_key="1" * 49, status=SriDocumentStatus.GENERATED,
            xml="<invoice>SEG01A_PRIVATE_FISCAL_DATA</invoice>",
        )

    def test_authenticated_without_permissions_is_denied_before_protected_reads(self):
        before = self.snapshot()
        with ExitStack() as stack:
            for target in (
                "sales.views.get_object_or_404", "sales.views.SaleCreateForm",
                "sales.views.SaleDetailFormSet", "sales.views.FiscalPreparationForm",
            ):
                stack.enter_context(patch(target, side_effect=AssertionError("Protected read before permission")))
            for name, url, methods, _, data in self.operations():
                for method in methods:
                    with self.subTest(operation=name, method=method):
                        self.assertEqual(getattr(self.client, method)(url, data).status_code, 403)
        self.assert_no_services()
        self.assertEqual(self.snapshot(), before)

    def test_partial_permissions_never_substitute_for_a_required_permission(self):
        extras = {
            "create": ("sales.change_sale",),
            "detail": ("sales.add_sale", "sales.change_sale"),
            "confirm": ("sales.add_sale",),
            "prepare": ("sales.add_sale", "sales.change_sale", "sri.change_electronicdocument"),
        }
        before = self.snapshot()
        for name, url, methods, required, data in self.operations():
            for count in range(len(required)):
                for partial in combinations(required, count):
                    self.grant(*partial, *extras[name])
                    with patch("sales.views.get_object_or_404", side_effect=AssertionError("Unauthorized lookup")):
                        for method in methods:
                            with self.subTest(operation=name, permissions=partial, method=method):
                                self.assertEqual(getattr(self.client, method)(url, data).status_code, 403)
        self.assert_no_services()
        self.assertEqual(self.snapshot(), before)

    def test_each_operation_accepts_exactly_its_minimum_permissions(self):
        for name, url, methods, required, data in self.operations():
            self.grant(*required)
            for boundary in self.boundaries:
                boundary.reset_mock()
            for method in methods:
                with self.subTest(operation=name, method=method):
                    response = getattr(self.client, method)(url, data)
                    self.assertEqual(response.status_code, 302 if method == "post" else 200)
            expected = {"create": self.create, "confirm": self.confirm, "prepare": self.prepare}.get(name)
            for boundary in self.boundaries:
                if boundary is expected:
                    boundary.assert_called_once()
                else:
                    boundary.assert_not_called()

    def test_anonymous_requests_still_redirect_to_login(self):
        anonymous = Client()
        for name, url, methods, _, data in self.operations():
            for method in methods:
                with self.subTest(operation=name, method=method):
                    response = getattr(anonymous, method)(url, data)
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response["Location"], f"{reverse('login')}?next={url}")
        self.assert_no_services()

    def test_permissions_do_not_bypass_missing_or_unauthorized_context(self):
        self.grant(*self.ALL_PERMISSIONS)
        before = self.snapshot()
        for company, branch, destination in (
            (None, None, "select_company"),
            (self.company.pk, None, "select_branch"),
            (self.other_company.pk, self.other_company_branch.pk, "select_company"),
            (self.company.pk, self.other_branch.pk, "select_branch"),
        ):
            for name, url, methods, _, data in self.operations():
                for method in methods:
                    self.set_context(company, branch)
                    with self.subTest(operation=name, method=method, context=(company, branch)):
                        response = getattr(self.client, method)(url, data)
                        self.assertRedirects(response, reverse(destination), fetch_redirect_response=False)
        self.assert_no_services()
        self.assertEqual(self.snapshot(), before)

    def test_revoked_memberships_invalidate_saved_context_for_every_operation(self):
        self.grant(*self.ALL_PERMISSIONS)
        before = self.snapshot()
        for relation, destination in (
            (self.user.profile.branches, "select_branch"),
            (self.user.profile.companies, "select_company"),
        ):
            relation.clear()
            for _, url, methods, _, data in self.operations():
                for method in methods:
                    self.set_context(self.company.pk, self.branch.pk)
                    response = getattr(self.client, method)(url, data)
                    self.assertRedirects(response, reverse(destination), fetch_redirect_response=False)
            self.user.profile.branches.add(self.branch)
        self.assert_no_services()
        self.assertEqual(self.snapshot(), before)

    def test_foreign_documents_remain_404_even_with_membership_in_both_contexts(self):
        self.grant(*self.ALL_PERMISSIONS)
        self.user.profile.companies.add(self.other_company)
        self.user.profile.branches.add(self.other_branch, self.other_company_branch)
        foreign_person = Person.objects.create(
            identification="SEG01A-FOREIGN", person_type="NATURAL", full_name="Cliente de prueba",
        )
        foreign_customer = Customer.objects.create(company=self.other_company, person=foreign_person)
        foreign = self.sale(
            company=self.other_company, branch=self.other_company_branch,
            warehouse=self.other_company_warehouse, customer=foreign_customer,
        )
        other_branch = self.sale(branch=self.other_branch, warehouse=self.other_branch_warehouse)
        before = self.snapshot()
        for sale_id in (foreign.pk, other_branch.pk, max(foreign.pk, other_branch.pk) + 1):
            for method, url in (
                ("get", self.detail_path(sale_id)), ("head", self.detail_path(sale_id)),
                ("post", reverse("sale_confirm", args=[sale_id])),
                ("post", self.prepare_path(sale_id)),
            ):
                with self.subTest(method=method, sale_id=sale_id, url=url):
                    response = getattr(self.client, method)(url, {"point_of_emission": self.point.pk})
                    self.assertEqual(response.status_code, 404)
        self.assert_no_services()
        self.assertEqual(self.snapshot(), before)

    def test_get_and_head_never_mutate_business_data_or_call_services(self):
        self.grant(*self.ALL_PERMISSIONS)
        before = self.snapshot()
        for method in ("get", "head"):
            for url, expected in (
                (reverse("sale_create"), 200), (self.detail_path(self.draft.pk), 200),
                (reverse("sale_confirm", args=[self.draft.pk]), 405),
                (self.prepare_path(self.confirmed.pk), 405),
            ):
                self.assertEqual(getattr(self.client, method)(url).status_code, expected)
        self.assert_no_services()
        self.assertEqual(self.snapshot(), before)

    def test_forged_permissions_actor_and_context_cannot_authorize_a_post(self):
        before = self.snapshot()
        payload = self.create_payload() | {
            "permissions": self.ALL_PERMISSIONS, "user_permissions": self.ALL_PERMISSIONS,
            "user_id": self.user.pk, "is_superuser": "1",
            "company": self.other_company.pk, "branch": self.other_company_branch.pk,
            "point_of_emission": self.other_company_point.pk,
        }
        for name, url, methods, _, _ in self.operations():
            if "post" in methods:
                with self.subTest(operation=name):
                    self.assertEqual(self.client.post(url, payload).status_code, 403)
        self.assertFalse(self.user.user_permissions.exists())
        self.assert_no_services()
        self.assertEqual(self.snapshot(), before)

    def test_staff_supervisor_and_developer_flags_do_not_grant_permissions(self):
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.user.profile.is_supervisor = self.user.profile.is_developer = True
        self.user.profile.save(update_fields=["is_supervisor", "is_developer"])
        before = self.snapshot()
        for _, url, methods, _, data in self.operations():
            for method in methods:
                self.assertEqual(getattr(self.client, method)(url, data).status_code, 403)
        self.assert_no_services()
        self.assertEqual(self.snapshot(), before)

    def test_no_sri_view_means_no_fiscal_queries_state_or_data(self):
        self.grant(
            "sales.view_sale", "sales.add_sale", "sales.change_sale",
            "sri.add_electronicdocument", "sri.change_electronicdocument",
        )
        self.electronic()
        self.confirm.side_effect = ValueError("Cannot confirm")
        before = self.snapshot()
        with ExitStack() as stack:
            guards = [stack.enter_context(patch(target, side_effect=AssertionError("Unauthorized fiscal read")))
                      for target in (
                          "sales.views.ElectronicDocument.objects.filter",
                          "sales.views.ContentType.objects.get_for_model",
                          "sales.views._workflow_presentation", "sales.views.FiscalPreparationForm",
                      )]
            with CaptureQueriesContext(connection) as queries:
                for method, url in (
                    ("get", self.detail_path(self.confirmed.pk)),
                    ("head", self.detail_path(self.confirmed.pk)),
                    ("post", reverse("sale_confirm", args=[self.confirmed.pk])),
                ):
                    response = getattr(self.client, method)(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertIsNone(response.context["electronic_document"])
                    self.assertIsNone(response.context.get("workflow_state"))
                    self.assertIsNone(response.context["fiscal_preparation_form"])
                    for value in ("SEG01A_PRIVATE_FISCAL_DATA", "Estado fiscal:", "Documento electrónico:"):
                        self.assertNotContains(response, value)
            for guard in guards:
                guard.assert_not_called()
        for query in queries.captured_queries:
            for model in (ElectronicDocument, FiscalSequence, SriReceptionAttempt, SriAuthorizationAttempt, PointOfEmission):
                self.assertNotIn(f'"{model._meta.db_table}"', query["sql"])
        self.assertEqual(self.snapshot(), before)

    def test_read_only_sales_actions_remain_visible_and_disabled(self):
        self.grant("sales.view_sale")
        response = self.client.get(self.detail_path(self.draft.pk))
        self.assertEqual(response.status_code, 200)
        html = SalesActionsHTML(response.content)
        for label in ("Confirmar venta", "Preparar documento fiscal", "Nueva venta"):
            self.assertIn(label, html.buttons)
            self.assertIn("disabled", html.buttons[label])
        self.assertNotIn(reverse("sale_confirm", args=[self.draft.pk]), html.forms)
        self.assertNotIn(self.prepare_path(self.draft.pk), html.forms)
        self.assertNotIn(reverse("sale_create"), html.links)
        self.assert_no_services()

    def test_sri_read_only_displays_state_but_disables_fiscal_actions(self):
        self.grant("sales.view_sale", "sri.view_electronicdocument")
        document = self.electronic()
        with patch("sales.views.FiscalPreparationForm", side_effect=AssertionError("Preparation not authorized")):
            response = self.client.get(self.detail_path(self.confirmed.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["electronic_document"], document)
        self.assertContains(response, "Estado fiscal:")
        html = SalesActionsHTML(response.content)
        for label in ("Preparar documento fiscal", "Firmar documento"):
            self.assertIn("disabled", html.buttons[label])
        self.assertNotIn(reverse("electronic_document_sign", args=[document.pk]), html.links)
        self.assert_no_services()

    def test_csrf_remains_required_for_authorized_posts(self):
        self.grant(*self.ALL_PERMISSIONS)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk, client=strict)
        self.assertEqual(strict.get(reverse("sale_create")).status_code, 200)
        token = strict.cookies["csrftoken"].value
        before = self.snapshot()
        for _, url, methods, _, data in self.operations():
            if "post" in methods:
                self.assertEqual(strict.post(url, data).status_code, 403)
        self.assert_no_services()
        self.assertEqual(self.snapshot(), before)
        for _, url, methods, _, data in self.operations():
            if "post" in methods:
                self.assertEqual(strict.post(url, data, HTTP_X_CSRFTOKEN=token).status_code, 302)
