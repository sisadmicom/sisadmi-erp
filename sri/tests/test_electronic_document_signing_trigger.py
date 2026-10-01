"""C-14C HTTP contract for explicitly signing an electronic document.

The signing service is mocked at the future sri.views import boundary. These
tests exercise authentication, active context, resource scoping, HTTP safety,
and presentation; they never load a certificate or perform cryptography.
"""

from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase, tag
from django.urls import NoReverseMatch, resolve, reverse
from django.utils.html import escape

from core.models import Branch, Company
from people.models import Person
from sri.constants.document_status import SriDocumentStatus
from sri.models import ElectronicDocument, SriCertificate
from sri.tests.electronic_document_signing_test_support import create_generated_document


URL_NAME = "electronic_document_sign"
TEMPLATE = "sri/electronic_document_signing.html"
PRIVATE_ERROR = "/srv/private/certificates/issuer.p12 SECRET_REF=issuer-password"


class SigningTriggerFixture:
    def setUp(self):
        super().setUp()
        self.context_data, self.document = create_generated_document()
        self.company = self.context_data["company"]
        self.branch = self.context_data["branch"]
        self.second_branch = Branch.objects.create(
            company=self.company,
            code="002",
            name="Sucursal secundaria de firma",
        )
        other_person = Person.objects.create(
            identification="1790000002001",
            person_type="LEGAL",
            full_name="Empresa ajena a firma",
        )
        self.other_company = Company.objects.create(
            person=other_person,
            commercial_name="Empresa ajena a firma",
        )
        self.other_branch = Branch.objects.create(
            company=self.other_company,
            code="001",
            name="Sucursal ajena a firma",
        )
        unauthorized_person = Person.objects.create(
            identification="1790000003001",
            person_type="LEGAL",
            full_name="Empresa no autorizada para firma",
        )
        self.unauthorized_company = Company.objects.create(
            person=unauthorized_person,
            commercial_name="Empresa no autorizada para firma",
        )
        self.unauthorized_branch = Branch.objects.create(
            company=self.unauthorized_company,
            code="001",
            name="Sucursal no autorizada",
        )
        self.user = get_user_model().objects.create_user(username="signing-trigger")
        self.user.profile.companies.add(self.company, self.other_company)
        self.user.profile.branches.add(
            self.branch,
            self.second_branch,
            self.other_branch,
        )
        self.client.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk)

        # Match the intended future view import: from the service module import
        # ElectronicDocumentSigningService, then call its .sign method.
        boundary = patch("sri.views.ElectronicDocumentSigningService", create=True)
        self.signing_service = boundary.start()
        self.addCleanup(boundary.stop)
        self.signed_result = ElectronicDocument.objects.get(pk=self.document.pk)
        self.signed_result.status = SriDocumentStatus.SIGNED
        self.signed_result.xml = "<signed-private-xml/>"
        self.signing_service.sign.return_value = self.signed_result

        # The HTTP trigger may delegate to signing only. Keep later workflow
        # stages, the actual crypto service, and external connections guarded.
        for target in (
            "socket.socket.connect",
            "socket.socket.connect_ex",
            "sri.services.electronic_document_signing_service."
            "ElectronicDocumentSigningService.sign",
            "sri.services.electronic_document_reception_service."
            "ElectronicDocumentReceptionService.submit",
            "sri.services.electronic_document_authorization_service."
            "ElectronicDocumentAuthorizationService.authorize",
            "sri.services.electronic_document_authorization_entrypoint."
            "authorize_electronic_document",
            "sri.services.fiscal_document_preparation_service."
            "FiscalDocumentPreparationService.prepare",
        ):
            guard = patch(target, side_effect=AssertionError("Forbidden signing boundary side effect"))
            blocked = guard.start()
            self.addCleanup(guard.stop)
            self.addCleanup(blocked.assert_not_called)

    def set_context(self, company_id, branch_id, client=None):
        session = (client or self.client).session
        session["company_id"] = company_id
        session["branch_id"] = branch_id
        session.save()

    def url(self, document_id=None):
        try:
            return reverse(
                URL_NAME,
                kwargs={
                    "electronic_document_id": (
                        self.document.pk if document_id is None else document_id
                    ),
                },
            )
        except NoReverseMatch:
            self.fail(
                "C-14C boundary absent: production URL "
                "electronic_document_sign is not registered."
            )

    def snapshot(self, document=None):
        target = document or self.document
        return ElectronicDocument.objects.values().get(pk=target.pk)

    def assert_sign_delegated_once(self, document=None):
        expected = document or self.document
        self.signing_service.sign.assert_called_once_with(electronic_document=expected)
        delegated = self.signing_service.sign.call_args.kwargs["electronic_document"]
        self.assertIsInstance(delegated, ElectronicDocument)
        self.assertEqual(delegated.pk, expected.pk)
        self.assertEqual(delegated.company_id, expected.company_id)
        self.assertEqual(delegated.branch_id, expected.branch_id)

    def assert_result(self, response, state):
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/html"))
        self.assertTemplateUsed(response, TEMPLATE)
        self.assertEqual(response.context["electronic_document"].pk, self.document.pk)
        self.assertEqual(response.context["signing_state"], state)
        message = response.context["signing_message"]
        self.assertIsInstance(message, str)
        self.assertTrue(message.strip())
        self.assertContains(response, escape(message), html=False)
        self.assertNotContains(response, PRIVATE_ERROR)
        self.assertNotContains(response, "Traceback (most recent call last)")
        self.assertNotContains(response, self.document.xml)


@tag("c14c_signing_trigger_red")
class ElectronicDocumentSigningTriggerTests(SigningTriggerFixture, TestCase):
    def test_get_route_view_and_confirmation_are_safe(self):
        url = self.url()
        self.assertEqual(url, f"/sri/electronic-documents/{self.document.pk}/sign/")
        match = resolve(url)
        self.assertEqual(match.url_name, URL_NAME)
        self.assertEqual(match.namespace, "")
        self.assertEqual(match.func.__module__, "sri.views")
        self.assertEqual(match.func.__name__, "electronic_document_sign")
        before = self.snapshot()

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, TEMPLATE)
        self.assertEqual(response.context["electronic_document"].pk, self.document.pk)
        self.assertIsNone(response.context["signing_state"])
        self.assertEqual(response.wsgi_request.active_company, self.company)
        self.assertEqual(response.wsgi_request.active_branch, self.branch)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.signing_service.sign.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_anonymous_get_and_post_redirect_to_core_login(self):
        url = self.url()
        client = Client()

        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(client, method)(url)
                self.assertEqual(response.status_code, 302)
                location = urlsplit(response["Location"])
                self.assertEqual(location.path, reverse("login"))
                self.assertEqual(parse_qs(location.query), {"next": [url]})
                self.signing_service.sign.assert_not_called()

    def test_missing_manipulated_and_revoked_context_redirect_without_signing(self):
        url = self.url()
        cases = (
            (None, None, "select_company", None),
            (self.company.pk, None, "select_branch", None),
            (self.unauthorized_company.pk, self.unauthorized_branch.pk, "select_company", None),
            (self.company.pk, self.other_branch.pk, "select_branch", None),
            (self.company.pk, self.branch.pk, "select_company", "company"),
            (self.company.pk, self.branch.pk, "select_branch", "branch"),
        )
        for company_id, branch_id, destination, revoked in cases:
            for method in ("get", "post"):
                with self.subTest(
                    company=company_id,
                    branch=branch_id,
                    revoked=revoked,
                    method=method,
                ):
                    self.user.profile.companies.add(self.company, self.other_company)
                    self.user.profile.branches.add(
                        self.branch,
                        self.second_branch,
                        self.other_branch,
                    )
                    self.set_context(company_id, branch_id)
                    if revoked == "company":
                        self.user.profile.companies.remove(self.company)
                    elif revoked == "branch":
                        self.user.profile.branches.remove(self.branch)

                    response = getattr(self.client, method)(url)
                    self.assertRedirects(
                        response,
                        reverse(destination),
                        fetch_redirect_response=False,
                    )
                    self.signing_service.sign.assert_not_called()

    def test_cross_company_document_is_scoped_404(self):
        url = self.url()
        self.set_context(self.other_company.pk, self.other_branch.pk)
        before = self.snapshot()

        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 404)
                self.signing_service.sign.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_cross_branch_document_is_404_even_with_membership_in_both_branches(self):
        url = self.url()
        self.set_context(self.company.pk, self.second_branch.pk)
        before = self.snapshot()

        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 404)
                self.signing_service.sign.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_missing_document_does_not_fall_back_to_caller_authorities(self):
        missing_id = (
            ElectronicDocument.objects.order_by("-pk")
            .values_list("pk", flat=True)
            .first()
            + 1
        )
        url = self.url(missing_id)
        supplied = {
            "company": self.company.pk,
            "branch": self.branch.pk,
            "access_key": self.document.access_key,
        }

        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, supplied)
                self.assertEqual(response.status_code, 404)
                self.signing_service.sign.assert_not_called()

    def test_head_is_safe_and_other_methods_are_not_allowed(self):
        url = self.url()
        before = self.snapshot()

        response = self.client.head(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.signing_service.sign.assert_not_called()
        for method in ("put", "patch", "delete", "options"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(
                    set(response["Allow"].split(", ")),
                    {"GET", "HEAD", "POST"},
                )
                self.signing_service.sign.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_valid_post_renders_signed_result_and_delegates_only_document(self):
        url = self.url()
        before = self.snapshot()
        self.signing_service.sign.return_value = self.signed_result

        response = self.client.post(url)

        self.assert_result(response, "SIGNED")
        self.assertEqual(response.context["electronic_document"].status, SriDocumentStatus.SIGNED)
        self.assert_sign_delegated_once()
        self.assertEqual(self.snapshot(), before)

    def test_success_does_not_require_a_certificate_fixture(self):
        url = self.url()
        self.assertFalse(SriCertificate.objects.filter(company=self.company).exists())
        self.signing_service.sign.return_value = self.signed_result

        response = self.client.post(url)

        self.assert_result(response, "SIGNED")
        self.assert_sign_delegated_once()
        self.assertFalse(SriCertificate.objects.filter(company=self.company).exists())

    def test_draft_document_is_delegated_without_view_state_precheck(self):
        url = self.url()
        self.document.status = SriDocumentStatus.DRAFT
        self.document.save(update_fields=["status"])
        self.signing_service.sign.side_effect = ValueError("private wrong-state detail")

        response = self.client.post(url)

        self.assert_result(response, "INVALID")
        self.assert_sign_delegated_once()
        self.assertNotContains(response, "private wrong-state detail")

    def test_already_signed_document_still_delegates_once(self):
        url = self.url()
        self.document.status = SriDocumentStatus.SIGNED
        self.document.save(update_fields=["status"])
        before = self.snapshot()
        self.signing_service.sign.side_effect = ValueError(PRIVATE_ERROR)

        response = self.client.post(url)

        self.assert_result(response, "INVALID")
        self.assert_sign_delegated_once()
        self.assertEqual(self.snapshot(), before)

    def test_valueerror_is_safe_generic_signing_failure(self):
        url = self.url()
        before = self.snapshot()
        self.signing_service.sign.side_effect = ValueError(PRIVATE_ERROR)

        response = self.client.post(url)

        self.assert_result(response, "INVALID")
        self.assert_sign_delegated_once()
        self.assertEqual(self.snapshot(), before)

    def test_unexpected_exception_propagates(self):
        url = self.url()
        error = RuntimeError(PRIVATE_ERROR)
        self.signing_service.sign.side_effect = error
        before = self.snapshot()

        with self.assertRaises(RuntimeError) as caught:
            self.client.post(url)

        self.assertIs(caught.exception, error)
        self.assert_sign_delegated_once()
        self.assertEqual(self.snapshot(), before)

    def test_csrf_is_required_before_signing(self):
        url = self.url()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk, client=client)
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertIn("csrftoken", client.cookies)
        self.signing_service.sign.assert_not_called()

        response = client.post(url)
        self.assertEqual(response.status_code, 403)
        self.signing_service.sign.assert_not_called()

        response = client.post(
            url,
            {"csrfmiddlewaretoken": client.cookies["csrftoken"].value},
        )
        self.assert_result(response, "SIGNED")
        self.assert_sign_delegated_once()

    def test_http_tampering_cannot_supply_certificate_or_document_authorities(self):
        url = self.url()
        supplied = {
            "company": self.other_company.pk,
            "branch": self.other_branch.pk,
            "status": "AUTHORIZED",
            "xml": "<attacker/> ",
            "signed_xml": "<attacker-signed/>",
            "access_key": "9" * 49,
            "environment": "2",
            "certificate": "attacker-certificate",
            "certificate_id": "987654",
            "certificate_file": "attacker.p12",
            "certificate_path": "/etc/passwd",
            "path": "/tmp/attacker.p12",
            "password": "attacker-password",
            "secret_key": "ATTACKER_SECRET",
            "authorization_number": "attacker-authorization",
        }
        before = self.snapshot()
        response = self.client.post(f"{url}?company={self.other_company.pk}&branch={self.other_branch.pk}", supplied)

        self.assert_result(response, "SIGNED")
        self.assert_sign_delegated_once()
        self.assertEqual(self.snapshot(), before)


@tag("c14c_signing_trigger_red")
class ElectronicDocumentSigningTriggerTransactionTests(
    SigningTriggerFixture,
    TransactionTestCase,
):
    def test_sign_is_called_outside_an_external_transaction(self):
        url = self.url()
        observed = []

        def result(*, electronic_document):
            observed.append(connection.in_atomic_block)
            return electronic_document

        self.signing_service.sign.side_effect = result
        response = self.client.post(url)

        self.assert_result(response, "SIGNED")
        self.assert_sign_delegated_once()
        self.assertEqual(observed, [False])
