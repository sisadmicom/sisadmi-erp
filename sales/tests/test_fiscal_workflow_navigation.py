"""C-14E: persisted workflow visibility and navigation, never domain execution.

Sale detail is the resumable hub. Signing and reception also expose their
immediate next step on a fresh GET. PENDING/UNCERTAIN authorization may still
allow an explicit query; these tests do not demand recovery or polling.
"""
from html.parser import HTMLParser
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase, tag
from django.urls import reverse
from django.utils import timezone

from core.constants.document_status import DocumentStatus
from core.constants.sri import SriDocumentType
from core.models import Branch
from sales.models import Sale
from sales.tests.test_sale_fiscal_preparation_trigger import (
    FiscalPreparationTriggerFixtureMixin,
)
from sri.constants.authorization_attempt_status import SriAuthorizationAttemptStatus as A
from sri.constants.document_status import SriDocumentStatus as D
from sri.constants.reception_attempt_status import SriReceptionAttemptStatus as R
from sri.models import ElectronicDocument, SriAuthorizationAttempt, SriReceptionAttempt


class NavigationHTML(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.links = []
        self.forms = []
        self.visible = []
        self.feed(content.decode())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.links.append(attrs.get("href"))
        if tag == "form":
            self.forms.append((attrs.get("method", "get").lower(), attrs.get("action")))

    def handle_data(self, data):
        self.visible.append(data)


@tag("c14e_navigation_red")
class FiscalWorkflowNavigationTests(FiscalPreparationTriggerFixtureMixin, TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="c14e-operator")
        self.user.profile.companies.add(self.company, self.other_company)
        self.user.profile.branches.add(self.branch, self.other_branch, self.other_company_branch)
        self.client.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk)
        self.guards = []
        targets = (
            "sales.views.CreateSale.execute",
            "sales.views.ConfirmSale.execute",
            "sales.views.FiscalDocumentPreparationService.prepare",
            "sri.views.ElectronicDocumentSigningService.sign",
            "sri.views.submit_electronic_document",
            "sri.views.authorize_electronic_document",
            "sri.services.electronic_document_reception_service.ElectronicDocumentReceptionService.submit",
            "sri.services.electronic_document_authorization_service.ElectronicDocumentAuthorizationService.authorize",
            "sri.services.electronic_document_reception_entrypoint.SriReceptionSoapAdapter",
            "sri.services.electronic_document_authorization_entrypoint.SriAuthorizationSoapAdapter",
            "sri.services.pkcs12_xml_signer.Pkcs12XmlSigner.sign",
            "socket.create_connection",
            "socket.socket.connect",
        )
        for target in targets:
            guard = patch(target, side_effect=AssertionError(f"Forbidden mutation/network: {target}"))
            self.guards.append(guard.start())
            self.addCleanup(guard.stop)
        self.addCleanup(self.assert_guards_unused)

    def assert_guards_unused(self):
        for guard in self.guards:
            guard.assert_not_called()

    def electronic(self, sale=None, status=D.GENERATED, **overrides):
        sale = sale or self.sale()
        sequence = ElectronicDocument.objects.count() + 1
        values = dict(
            company=sale.company, branch=sale.branch,
            content_type=ContentType.objects.get_for_model(sale), object_id=sale.pk,
            document_type=SriDocumentType.INVOICE, establishment=sale.branch.code,
            emission_point="001", sequential=f"{sequence:09d}", numeric_code="12345678",
            access_key=f"{sequence:049d}", status=status,
            xml="<signed>C14E_PRIVATE_XML</signed>",
            error_message="C14E_PRIVATE_TRANSPORT_TRACEBACK_PASSWORD_SOAP",
        )
        values.update(overrides)
        document = ElectronicDocument(**values)
        document.full_clean()
        document.save()
        return document

    def reception(self, document, status):
        attempt = SriReceptionAttempt(
            electronic_document=document, status=status,
            completed_at=None if status == R.IN_PROGRESS else timezone.now(),
            error_message="C14E_PRIVATE_TRANSPORT_TRACEBACK_PASSWORD_SOAP",
        )
        attempt.full_clean()
        attempt.save()
        return attempt

    def authorization(self, document, status):
        attempt = SriAuthorizationAttempt(
            electronic_document=document, status=status, access_key=document.access_key,
            environment=document.environment, started_at=timezone.now(),
            finished_at=None if status == A.IN_PROGRESS else timezone.now(),
            error_message="C14E_PRIVATE_TRANSPORT_TRACEBACK_PASSWORD_SOAP",
        )
        if status == A.AUTHORIZED:
            attempt.authorization_number = document.authorization_number
            attempt.authorization_date = document.authorization_date
            attempt.response_environment = document.environment
        attempt.full_clean()
        attempt.save()
        return attempt

    def url(self, name, document):
        return reverse(name, kwargs={"electronic_document_id": document.pk})

    def get_page(self, name, obj):
        path = self.detail_path(obj.pk) if name == "sale_detail" else self.url(name, obj)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        for secret in ("C14E_PRIVATE_XML", "C14E_PRIVATE_AUTHORIZED_XML",
                       "C14E_PRIVATE_TRANSPORT_TRACEBACK_PASSWORD_SOAP", "Traceback"):
            self.assertNotContains(response, secret)
        if isinstance(obj, ElectronicDocument):
            self.assertNotContains(response, obj.access_key)
        return response, NavigationHTML(response.content)

    def assert_state(self, response, state):
        # Accept machine token or the real enum's human label, not fixed wording.
        visible = " ".join(NavigationHTML(response.content).visible)
        self.assertTrue(str(state) in visible or state.label in visible,
                        f"Persisted workflow state {state} is not visible")

    def assert_no_action(self, html, name, document):
        path = self.url(name, document)
        self.assertNotIn(path, html.links)
        self.assertFalse(any(action == path for _, action in html.forms))

    def assert_no_fiscal_actions(self, html, document):
        for name in ("electronic_document_sign", "electronic_document_receive",
                     "electronic_document_authorize"):
            self.assert_no_action(html, name, document)

    def test_draft_without_electronic_document_preserves_confirmation(self):
        sale = self.sale(status=DocumentStatus.DRAFT, number="")
        response, html = self.get_page("sale_detail", sale)
        self.assertContains(response, self.customer.person.full_name)
        self.assertIn(("post", reverse("sale_confirm", kwargs={"sale_id": sale.pk})), html.forms)
        self.assertFalse(any("/sri/electronic-documents/" in (link or "") for link in html.links))
        self.assertEqual(ElectronicDocument.objects.count(), 0)

    def test_confirmed_without_document_keeps_preparation_as_local_step(self):
        sale = self.sale()
        response, html = self.get_page("sale_detail", sale)
        self.assertContains(response, sale.number)
        self.assertIn(("post", self.prepare_path(sale.pk)), html.forms)
        self.assertFalse(any("/sri/electronic-documents/" in (link or "") for link in html.links))

    def test_generated_is_discovered_and_hands_actual_id_to_signing(self):
        # Different Sale and ElectronicDocument IDs prevent an accidental sale-ID URL.
        self.sale()
        sale = self.sale(number="C14E-SALE-HANDOFF")
        document = self.electronic(sale)
        self.assertNotEqual(sale.pk, document.pk)
        response, html = self.get_page("sale_detail", sale)
        self.assert_state(response, D.GENERATED)
        self.assertIn(self.url("electronic_document_sign", document), html.links)
        self.assert_no_action(html, "electronic_document_receive", document)
        self.assert_no_action(html, "electronic_document_authorize", document)
        self.assertNotContains(response, document.access_key)

    def test_unrelated_documents_do_not_leak_on_sale_detail(self):
        sale = self.sale()
        foreign_sale = self.sale(company=self.other_company, branch=self.other_company_branch,
                                 warehouse=self.other_company_warehouse)
        branch_sale = self.sale(branch=self.other_branch, warehouse=self.other_branch_warehouse)
        unrelated_sale = self.sale(number="C14E-OTHER-ORIGIN")
        documents = [self.electronic(origin, status=D.AUTHORIZED)
                     for origin in (foreign_sale, branch_sale, unrelated_sale)]
        # The real GFK model permits persisted tenant/origin inconsistencies.
        # full_clean is required: no validation/constraint is bypassed here.
        # These rows freeze defensive reads even when origin PK matches exactly.
        scenarios = (
            dict(company=self.other_company, branch=self.other_company_branch),
            dict(branch=self.other_branch),
        )
        for values in scenarios:
            document = self.electronic(sale, status=D.AUTHORIZED, **values)
            documents.append(document)
            with self.subTest(tenant=values):
                response, html = self.get_page("sale_detail", sale)
                for unrelated in documents:
                    self.assert_no_fiscal_actions(html, unrelated)
                    self.assertNotContains(response, str(unrelated))
                    self.assertNotContains(response, unrelated.access_key)
                self.assertNotContains(response, D.AUTHORIZED)
            document.delete()
            documents.pop()
        # A real non-Sale origin with a colliding numeric PK must not match.
        colliding_branch = Branch.objects.create(company=self.company, code="003", name="Collision origin")
        colliding_sale = self.sale(pk=colliding_branch.pk + 10000)
        other_origin = Branch.objects.create(pk=colliding_sale.pk, company=self.company,
                                            code="004", name="Other origin")
        documents.append(self.electronic(
            sale, status=D.AUTHORIZED, content_type=ContentType.objects.get_for_model(Branch),
            object_id=other_origin.pk, document_type=SriDocumentType.DELIVERY_NOTE))
        for origin in (sale, colliding_sale):
            with self.subTest(sale=origin.pk):
                response, html = self.get_page("sale_detail", origin)
                for document in documents:
                    self.assert_no_fiscal_actions(html, document)
                    self.assertNotContains(response, str(document))
                    self.assertNotContains(response, document.access_key)
                self.assertNotContains(response, D.AUTHORIZED)

    def test_wrong_fiscal_type_is_not_presented_as_sale_invoice(self):
        sale = self.sale()
        document = self.electronic(sale, document_type=SriDocumentType.CREDIT_NOTE)
        response, html = self.get_page("sale_detail", sale)
        self.assert_no_fiscal_actions(html, document)
        self.assertNotContains(response, D.GENERATED)
        self.assertNotContains(response, document.access_key)

    def test_signed_sale_hub_exposes_reception_on_fresh_get(self):
        document = self.electronic(status=D.SIGNED)
        response, html = self.get_page("sale_detail", document.document)
        self.assert_state(response, D.SIGNED)
        self.assertIn(self.url("electronic_document_receive", document), html.links)
        self.assert_no_action(html, "electronic_document_sign", document)

    def test_signing_page_signed_exposes_reception_without_signing_again(self):
        document = self.electronic(status=D.SIGNED)
        response, html = self.get_page("electronic_document_sign", document)
        self.assert_state(response, D.SIGNED)
        self.assertIn(self.url("electronic_document_receive", document), html.links)
        self.assert_no_action(html, "electronic_document_sign", document)

    def test_received_sale_hub_exposes_authorization_on_fresh_get(self):
        document = self.electronic(status=D.RECEIVED)
        self.reception(document, R.RECEIVED)
        response, html = self.get_page("sale_detail", document.document)
        self.assert_state(response, D.RECEIVED)
        self.assertIn(self.url("electronic_document_authorize", document), html.links)
        self.assert_no_action(html, "electronic_document_receive", document)

    def test_reception_page_received_exposes_authorization_without_resubmitting(self):
        document = self.electronic(status=D.RECEIVED)
        self.reception(document, R.RECEIVED)
        response, html = self.get_page("electronic_document_receive", document)
        self.assert_state(response, D.RECEIVED)
        self.assertIn(self.url("electronic_document_authorize", document), html.links)
        self.assert_no_action(html, "electronic_document_receive", document)

    def test_reception_rejected_is_durable_and_has_no_next_fiscal_action(self):
        document = self.electronic(status=D.REJECTED)
        self.reception(document, R.REJECTED)
        for page, obj in (("sale_detail", document.document), ("electronic_document_receive", document)):
            with self.subTest(page=page):
                response, html = self.get_page(page, obj)
                self.assert_state(response, D.REJECTED)
                self.assert_no_fiscal_actions(html, document)

    def assert_reception_blocked(self, state):
        document = self.electronic(status=D.SIGNED)
        attempt = self.reception(document, state)
        before = (attempt.status, attempt.completed_at, attempt.error_message)
        for page, obj in (("sale_detail", document.document), ("electronic_document_receive", document)):
            with self.subTest(page=page):
                response, html = self.get_page(page, obj)
                self.assert_state(response, state)
                self.assert_no_fiscal_actions(html, document)
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.completed_at, attempt.error_message), before)
        self.assertEqual(document.reception_attempts.count(), 1)

    def test_reception_uncertain_is_visible_and_blocks_normal_reception(self):
        self.assert_reception_blocked(R.UNCERTAIN)

    def test_reception_in_progress_is_visible_without_recovery(self):
        self.assert_reception_blocked(R.IN_PROGRESS)

    def assert_authorization_attempt_visible(self, state, blocked=False):
        document = self.electronic(status=D.RECEIVED)
        self.reception(document, R.RECEIVED)
        # Earlier evidence must not override the latest persisted authorization.
        self.authorization(document, A.PROTOCOL_ERROR)
        attempt = self.authorization(document, state)
        before = (attempt.status, attempt.finished_at, attempt.error_message)
        for page, obj in (("sale_detail", document.document), ("electronic_document_authorize", document)):
            with self.subTest(page=page):
                response, html = self.get_page(page, obj)
                self.assert_state(response, state)
                self.assert_no_action(html, "electronic_document_sign", document)
                self.assert_no_action(html, "electronic_document_receive", document)
                if blocked:
                    self.assert_no_action(html, "electronic_document_authorize", document)
                self.assertNotContains(response, D.AUTHORIZED)
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.finished_at, attempt.error_message), before)
        self.assertEqual(document.authorization_attempts.count(), 2)
        document.refresh_from_db()
        self.assertEqual(document.status, D.RECEIVED)

    def test_authorization_pending_is_durable_without_automatic_query(self):
        self.assert_authorization_attempt_visible(A.PENDING)

    def test_authorization_uncertain_is_safe_without_automatic_recovery(self):
        self.assert_authorization_attempt_visible(A.UNCERTAIN)

    def test_authorization_in_progress_blocks_duplicate_action(self):
        self.assert_authorization_attempt_visible(A.IN_PROGRESS, blocked=True)

    def test_authorized_terminal_state_is_visible_without_fiscal_actions(self):
        document = self.electronic(status=D.AUTHORIZED,
            authorization_number="C14E-OFFICIAL-AUTHORIZATION", authorization_date=timezone.now(),
            authorized_xml="<authorized>C14E_PRIVATE_AUTHORIZED_XML</authorized>")
        self.reception(document, R.RECEIVED)
        self.authorization(document, A.AUTHORIZED)
        for page, obj in (("sale_detail", document.document), ("electronic_document_authorize", document)):
            with self.subTest(page=page):
                response, html = self.get_page(page, obj)
                self.assert_state(response, D.AUTHORIZED)
                self.assert_no_fiscal_actions(html, document)

    def test_authorization_rejection_uses_real_attempt_semantics(self):
        document = self.electronic(status=D.REJECTED)
        self.reception(document, R.RECEIVED)
        self.authorization(document, A.NOT_AUTHORIZED)
        for page, obj in (("sale_detail", document.document), ("electronic_document_authorize", document)):
            with self.subTest(page=page):
                response, html = self.get_page(page, obj)
                self.assert_state(response, D.REJECTED)
                self.assert_no_fiscal_actions(html, document)

    def test_all_sri_pages_offer_scoped_return_to_sale(self):
        document = self.electronic()
        for page in ("electronic_document_sign", "electronic_document_receive", "electronic_document_authorize"):
            with self.subTest(page=page):
                _, html = self.get_page(page, document)
                self.assertIn(self.detail_path(document.object_id), html.links)

    def test_sri_return_does_not_trust_wrong_missing_or_foreign_origin(self):
        foreign = self.sale(company=self.other_company, branch=self.other_company_branch,
                            warehouse=self.other_company_warehouse)
        other_branch = self.sale(branch=self.other_branch, warehouse=self.other_branch_warehouse)
        own = self.sale()
        cases = ((ContentType.objects.get_for_model(Branch), self.branch.pk),
                 (ContentType.objects.get_for_model(Sale), own.pk + 10000),
                 (ContentType.objects.get_for_model(Sale), foreign.pk),
                 (ContentType.objects.get_for_model(Sale), other_branch.pk))
        for content_type, object_id in cases:
            # GFK has no cross-origin tenant validation; full_clean still applies.
            document = self.electronic(own, content_type=content_type, object_id=object_id)
            for page in ("electronic_document_sign", "electronic_document_receive", "electronic_document_authorize"):
                with self.subTest(origin=object_id, content_type=content_type.pk, page=page):
                    _, html = self.get_page(page, document)
                    self.assertFalse(any((link or "").startswith("/sales/") and link != reverse("sale_create")
                                         for link in html.links))

    def test_foreign_sri_documents_remain_inaccessible_with_real_context(self):
        for origin in (self.sale(company=self.other_company, branch=self.other_company_branch,
                                 warehouse=self.other_company_warehouse),
                       self.sale(branch=self.other_branch, warehouse=self.other_branch_warehouse)):
            document = self.electronic(origin)
            for page in ("electronic_document_sign", "electronic_document_receive", "electronic_document_authorize"):
                with self.subTest(document=document.pk, page=page):
                    self.assertEqual(self.client.get(self.url(page, document)).status_code, 404)

    def test_base_menu_has_existing_sales_entry(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn(reverse("sale_create"), NavigationHTML(response.content).links)

    def test_get_and_head_navigation_never_execute_workflow_mutations(self):
        document = self.electronic()
        paths = [reverse("sale_create"), self.detail_path(document.object_id)]
        paths += [self.url(page, document) for page in
                  ("electronic_document_sign", "electronic_document_receive", "electronic_document_authorize")]
        before = (ElectronicDocument.objects.count(), SriReceptionAttempt.objects.count(),
                  SriAuthorizationAttempt.objects.count(), document.status, document.xml)
        for path in paths:
            for method in ("get", "head"):
                with self.subTest(path=path, method=method):
                    self.assertEqual(getattr(self.client, method)(path).status_code, 200)
        document.refresh_from_db()
        self.assertEqual(before, (ElectronicDocument.objects.count(), SriReceptionAttempt.objects.count(),
                                 SriAuthorizationAttempt.objects.count(), document.status, document.xml))
        self.assert_guards_unused()
