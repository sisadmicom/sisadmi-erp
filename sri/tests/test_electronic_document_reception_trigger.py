from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from django.contrib.auth import get_user_model
from django.db import connection
from django.shortcuts import get_object_or_404 as django_get_object_or_404
from django.test import Client, TestCase, TransactionTestCase
from django.urls import NoReverseMatch, resolve, reverse
from django.utils.html import escape

from core.models import Branch, Company
from people.models import Person
from sri.constants.document_status import SriDocumentStatus
from sri.constants.reception_attempt_status import SriReceptionAttemptStatus
from sri.models import (
    ElectronicDocument,
    SriAuthorizationAttempt,
    SriReceptionAttempt,
    SriReceptionMessage,
)
from sri.clients.sri_reception_soap_adapter import (
    SriReceptionProtocolError,
    SriReceptionTransportError,
)
from sri.tests.authorization_domain_test_support import create_received_document


URL_NAME = "electronic_document_receive"
TEMPLATE = "sri/electronic_document_reception.html"
PRIVATE_ERROR = "private-reception-transport-detail"
PRIVATE_XML = "<signed>private-reception-xml</signed>"


class ReceptionTriggerFixture:
    def setUp(self):
        super().setUp()
        # This helper recreates SALES_INVOICE after TransactionTestCase flush.
        self.context_data, self.document = create_received_document()
        self.company = self.context_data["company"]
        self.branch = self.context_data["branch"]
        person = Person.objects.create(
            identification="1790000002001",
            person_type="LEGAL",
            full_name="Other reception company",
        )
        self.other_company = Company.objects.create(
            person=person,
            commercial_name="Other reception company",
        )
        self.other_branch = Branch.objects.create(
            company=self.other_company,
            code="001",
            name="Other company branch",
        )
        self.second_branch = Branch.objects.create(
            company=self.company,
            code="002",
            name="Second reception branch",
        )
        self.user = get_user_model().objects.create_user(
            username="reception-trigger",
        )
        self.user.profile.companies.add(self.company)
        self.user.profile.branches.add(self.branch, self.second_branch)
        self.client.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk)

        boundary = patch("sri.views.submit_electronic_document", create=True)
        self.submit = boundary.start()
        self.addCleanup(boundary.stop)
        self.submit.return_value = self.document

        # The HTTP boundary must use only the C-14D-A seam and never perform
        # any later/earlier pipeline operation or external connection.
        guarded_calls = (
            ("sri.views.SriReceptionSoapAdapter", True),
            ("sri.clients.sri_reception_soap_adapter.SriReceptionSoapAdapter", False),
            ("sri.services.electronic_document_reception_service.ElectronicDocumentReceptionService.submit", False),
            ("sri.services.electronic_document_authorization_entrypoint.authorize_electronic_document", False),
            ("sri.services.electronic_document_authorization_service.ElectronicDocumentAuthorizationService.authorize", False),
            ("sri.services.electronic_document_signing_service.ElectronicDocumentSigningService.sign", False),
            ("sri.services.fiscal_document_preparation_service.FiscalDocumentPreparationService.prepare", False),
            ("sri.services.sri_submission_service.SriSubmissionService.submit", False),
            ("sri.clients.sri_client.SriClient.send", False),
            ("socket.socket.connect", False),
            ("socket.socket.connect_ex", False),
        )
        for target, create in guarded_calls:
            guard = patch(
                target,
                create=create,
                side_effect=AssertionError(f"Forbidden reception side effect: {target}"),
            )
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
                "C-14D-B boundary absent: production URL "
                "electronic_document_receive is not registered."
            )

    def snapshot(self):
        return {
            "document": ElectronicDocument.objects.values().get(
                pk=self.document.pk,
            ),
            "reception_attempts": list(
                SriReceptionAttempt.objects.order_by("pk").values(),
            ),
            "reception_messages": list(
                SriReceptionMessage.objects.order_by("pk").values(),
            ),
            "authorization_attempts": list(
                SriAuthorizationAttempt.objects.order_by("pk").values(),
            ),
        }

    def assert_result(self, response, state):
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/html"))
        self.assertTemplateUsed(response, TEMPLATE)
        self.assertEqual(response.context["electronic_document"].pk, self.document.pk)
        self.assertEqual(response.context["reception_state"], state)
        message = response.context["reception_message"]
        self.assertIsInstance(message, str)
        self.assertTrue(message.strip())
        self.assertContains(response, escape(message), html=False)
        for private_value in (
            PRIVATE_ERROR,
            PRIVATE_XML,
            self.document.access_key,
            "Traceback (most recent call last)",
        ):
            self.assertNotContains(response, private_value)

    def assert_delegated_once(self):
        self.submit.assert_called_once_with(electronic_document=self.document)
        delegated = self.submit.call_args.kwargs["electronic_document"]
        self.assertIsInstance(delegated, ElectronicDocument)
        self.assertEqual(delegated.company_id, self.company.pk)
        self.assertEqual(delegated.branch_id, self.branch.pk)


class ElectronicDocumentReceptionTriggerTests(ReceptionTriggerFixture, TestCase):
    def test_get_route_confirmation_is_safe_and_uses_expected_resource(self):
        url = self.url()
        self.assertEqual(
            url,
            f"/sri/electronic-documents/{self.document.pk}/receive/",
        )
        match = resolve(url)
        self.assertEqual(match.url_name, URL_NAME)
        self.assertEqual(match.namespace, "")
        self.assertEqual(match.func.__module__, "sri.views")
        self.assertEqual(match.func.__name__, "electronic_document_receive")
        before = self.snapshot()

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, TEMPLATE)
        self.assertEqual(response.context["electronic_document"], self.document)
        self.assertEqual(response.context["reception_state"], "")
        self.assertEqual(response.wsgi_request.active_company, self.company)
        self.assertEqual(response.wsgi_request.active_branch, self.branch)
        self.assertContains(response, str(self.document.pk))
        self.assertContains(response, self.document.status)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.submit.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_anonymous_get_and_post_redirect_to_core_login_without_delegation(self):
        url = self.url()
        anonymous_client = Client()

        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(anonymous_client, method)(url)
                self.assertEqual(response.status_code, 302)
                location = urlsplit(response["Location"])
                self.assertEqual(location.path, reverse("login"))
                self.assertEqual(parse_qs(location.query), {"next": [url]})
                self.submit.assert_not_called()

    def test_missing_manipulated_and_revoked_context_redirects_without_delegation(self):
        url = self.url()
        cases = (
            (None, None, "select_company", None),
            (self.company.pk, None, "select_branch", None),
            (self.other_company.pk, self.other_branch.pk, "select_company", None),
            (self.company.pk, self.other_branch.pk, "select_branch", None),
            (self.company.pk, self.branch.pk, "select_company", "company"),
            (self.company.pk, self.branch.pk, "select_branch", "branch"),
        )
        for company_id, branch_id, destination, revoke in cases:
            self.user.profile.companies.add(self.company)
            self.user.profile.branches.add(self.branch)
            if revoke == "company":
                self.user.profile.companies.remove(self.company)
            elif revoke == "branch":
                self.user.profile.branches.remove(self.branch)
            self.set_context(company_id, branch_id)
            for method in ("get", "post"):
                with self.subTest(
                    company=company_id,
                    branch=branch_id,
                    revoked=revoke,
                    method=method,
                ):
                    response = getattr(self.client, method)(url)
                    self.assertRedirects(
                        response,
                        reverse(destination),
                        fetch_redirect_response=False,
                    )
                    self.submit.assert_not_called()

    def test_cross_company_document_is_404_with_other_valid_membership(self):
        self.user.profile.companies.add(self.other_company)
        self.user.profile.branches.add(self.other_branch)
        self.document.company = self.other_company
        self.document.branch = self.other_branch
        self.document.save(update_fields=["company", "branch"])
        url = self.url()
        before = self.snapshot()

        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 404)
                self.submit.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_cross_branch_document_is_404_even_with_membership_in_both_branches(self):
        self.document.branch = self.second_branch
        self.document.save(update_fields=["branch"])
        url = self.url()
        before = self.snapshot()

        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 404)
                self.submit.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_missing_document_does_not_fall_back_to_client_supplied_authority(self):
        missing_id = (
            ElectronicDocument.objects.order_by("-pk")
            .values_list("pk", flat=True)
            .first()
            + 1
        )
        url = self.url(missing_id)
        supplied = {"company": self.company.pk, "branch": self.branch.pk}
        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, supplied)
                self.assertEqual(response.status_code, 404)
                self.submit.assert_not_called()

    def test_head_is_safe_and_unsupported_methods_are_not_allowed(self):
        url = self.url()
        before = self.snapshot()
        response = self.client.head(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.submit.assert_not_called()

        for method in ("put", "patch", "delete", "options"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(
                    set(response["Allow"].split(", ")),
                    {"GET", "HEAD", "POST"},
                )
                self.submit.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_csrf_token_is_required_and_valid_token_allows_one_post(self):
        url = self.url()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk, client=client)
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertIn("csrftoken", client.cookies)
        self.submit.assert_not_called()

        before = self.snapshot()
        response = client.post(url)
        self.assertEqual(response.status_code, 403)
        self.submit.assert_not_called()
        self.assertEqual(self.snapshot(), before)

        response = client.post(
            url,
            {"csrfmiddlewaretoken": client.cookies["csrftoken"].value},
        )
        self.assertEqual(response.status_code, 200)
        self.assert_delegated_once()

    def test_valid_post_delegates_exact_scoped_document_once(self):
        url = self.url()
        before = self.snapshot()
        scoped_documents = []

        def capture_scoped_lookup(*args, **kwargs):
            document = django_get_object_or_404(*args, **kwargs)
            scoped_documents.append(document)
            return document

        with patch(
            "sri.views.get_object_or_404",
            side_effect=capture_scoped_lookup,
            create=True,
        ):
            response = self.client.post(url)

        self.assert_result(response, "RECEIVED")
        self.assert_delegated_once()
        self.assertEqual(len(scoped_documents), 1)
        self.assertIs(
            self.submit.call_args.kwargs["electronic_document"],
            scoped_documents[0],
        )
        self.assertEqual(self.snapshot(), before)

    def test_post_and_querystring_tampering_cannot_override_authorities(self):
        url = self.url()
        supplied = {
            "company": self.other_company.pk,
            "branch": self.other_branch.pk,
            "status": "AUTHORIZED",
            "xml": PRIVATE_XML,
            "signed_xml": PRIVATE_XML,
            "environment": "2",
            "access_key": "9" * 49,
            "wsdl": "https://invalid.example/private?wsdl",
            "endpoint": "https://invalid.example/soap",
            "adapter": "forged-adapter",
            "client_factory": "forged-factory",
            "authorization_number": "forged-authorization",
        }
        before = self.snapshot()

        response = self.client.post(f"{url}?{urlencode(supplied)}", supplied)

        self.assert_result(response, "RECEIVED")
        self.assert_delegated_once()
        self.assertEqual(self.snapshot(), before)

    def test_already_received_and_other_document_states_still_delegate(self):
        url = self.url()
        for status in (
            SriDocumentStatus.SIGNED,
            SriDocumentStatus.RECEIVED,
            SriDocumentStatus.REJECTED,
            SriDocumentStatus.AUTHORIZED,
        ):
            with self.subTest(status=status):
                self.submit.reset_mock()
                self.document.status = status
                self.document.save(update_fields=["status"])
                self.submit.return_value = self.document
                response = self.client.post(url)
                self.assertEqual(response.status_code, 200)
                self.assert_delegated_once()

    def test_rejected_reception_is_not_authorization_rejection(self):
        url = self.url()
        rejected = ElectronicDocument.objects.get(pk=self.document.pk)
        rejected.status = SriDocumentStatus.REJECTED
        self.submit.return_value = rejected

        response = self.client.post(url)

        self.assert_result(response, "REJECTED")
        self.assert_delegated_once()
        self.assertNotContains(response, "NOT_AUTHORIZED")

    def test_transport_uncertainty_is_safe_and_does_not_retry(self):
        url = self.url()
        SriReceptionAttempt.objects.create(
            electronic_document=self.document,
            status=SriReceptionAttemptStatus.UNCERTAIN,
            error_type="SriReceptionTransportError",
            error_message=PRIVATE_ERROR,
        )
        self.submit.side_effect = SriReceptionTransportError(PRIVATE_ERROR)

        response = self.client.post(url)

        self.assert_result(response, "UNCERTAIN")
        self.assert_delegated_once()

    def test_protocol_uncertainty_is_safe_and_distinct_from_rejection(self):
        url = self.url()
        SriReceptionAttempt.objects.create(
            electronic_document=self.document,
            status=SriReceptionAttemptStatus.UNCERTAIN,
            error_type="SriReceptionProtocolError",
            error_message=PRIVATE_ERROR,
        )
        self.submit.side_effect = SriReceptionProtocolError(PRIVATE_ERROR)

        response = self.client.post(url)

        self.assert_result(response, "UNCERTAIN")
        self.assert_delegated_once()

    def test_active_attempt_valueerror_is_not_presented_as_rejection(self):
        url = self.url()
        SriReceptionAttempt.objects.create(
            electronic_document=self.document,
            status=SriReceptionAttemptStatus.IN_PROGRESS,
        )
        self.submit.side_effect = ValueError(PRIVATE_ERROR)

        response = self.client.post(url)

        self.assert_result(response, "IN_PROGRESS")
        self.assert_delegated_once()

    def test_preflight_valueerror_is_neutral_and_hides_exception_text(self):
        url = self.url()
        self.submit.side_effect = ValueError(PRIVATE_ERROR)

        response = self.client.post(url)

        self.assert_result(response, "INVALID")
        self.assert_delegated_once()

    def test_unexpected_exception_propagates_unchanged(self):
        url = self.url()
        error = RuntimeError(PRIVATE_ERROR)
        self.submit.side_effect = error
        before = self.snapshot()

        with self.assertRaises(RuntimeError) as caught:
            self.client.post(url)

        self.assertIs(caught.exception, error)
        self.assert_delegated_once()
        self.assertEqual(self.snapshot(), before)


class ElectronicDocumentReceptionTriggerTransactionTests(
    ReceptionTriggerFixture,
    TransactionTestCase,
):
    def test_c14d_a_is_called_outside_an_outer_transaction(self):
        url = self.url()
        observed = []

        def result(*, electronic_document):
            observed.append(connection.in_atomic_block)
            return electronic_document

        self.submit.side_effect = result
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(observed, [False])
        self.assert_delegated_once()
