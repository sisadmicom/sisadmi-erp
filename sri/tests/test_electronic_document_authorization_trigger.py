"""C-13D external contract; production routing, middleware and templates.

No app namespace: match core/catalog URL conventions. GET/HEAD are safe;
POST renders HTML immediately (200), including known application failures.
Only sri.views.authorize_electronic_document is the authorization test seam.
create=True permits the missing import during RED, without installing a view.
"""

from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase
from django.urls import NoReverseMatch, resolve, reverse
from django.utils.html import escape
from django.utils import timezone

from core.models import Branch, Company
from people.models import Person
from sri.constants.authorization_attempt_status import SriAuthorizationAttemptStatus
from sri.constants.document_status import SriDocumentStatus
from sri.models import ElectronicDocument, SriAuthorizationAttempt, SriReceptionAttempt
from sri.services.electronic_document_authorization_service import (
    AuthorizationAlreadyInProgress,
    SriAuthorizationProtocolError,
    SriAuthorizationTransportError,
)
from sri.tests.authorization_domain_test_support import create_received_document


URL_NAME = "electronic_document_authorize"
TEMPLATE = "sri/electronic_document_authorization.html"
PRIVATE_ERROR = "internal-transport-detail-must-not-be-rendered"


class AuthorizationTriggerFixture:
    def setUp(self):
        super().setUp()
        # This existing helper explicitly recreates SALES_INVOICE after flush.
        self.context_data, self.document = create_received_document()
        self.company = self.context_data["company"]
        self.branch = self.context_data["branch"]
        person = Person.objects.create(
            identification="1790000002001", person_type="LEGAL",
            full_name="Other trigger company",
        )
        self.other_company = Company.objects.create(
            person=person, commercial_name="Other trigger company",
        )
        self.other_branch = Branch.objects.create(
            company=self.other_company, code="001", name="Other company branch",
        )
        self.second_branch = Branch.objects.create(
            company=self.company, code="002", name="Second active branch",
        )
        self.user = get_user_model().objects.create_user(username="authorization-trigger")
        self.user.profile.companies.add(self.company)
        self.user.profile.branches.add(self.branch, self.second_branch)
        self.client.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk)

        boundary = patch("sri.views.authorize_electronic_document", create=True)
        self.authorize = boundary.start()
        self.addCleanup(boundary.stop)
        self.authorize.return_value = self.document
        # Fail closed even if a future implementation bypasses the C-13C seam.
        for target in (
            "socket.socket.connect",
            "socket.socket.connect_ex",
            "sri.services.electronic_document_reception_service."
            "ElectronicDocumentReceptionService.submit",
        ):
            guard = patch(target, side_effect=AssertionError("Forbidden reception/network"))
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
            return reverse(URL_NAME, kwargs={
                "electronic_document_id": self.document.pk if document_id is None else document_id,
            })
        except NoReverseMatch:
            self.fail("C-13D boundary absent: production URL electronic_document_authorize is not registered.")

    def snapshot(self):
        return {
            "document": ElectronicDocument.objects.values().get(pk=self.document.pk),
            "authorization_attempts": list(SriAuthorizationAttempt.objects.order_by("pk").values()),
            "reception_attempts": list(SriReceptionAttempt.objects.order_by("pk").values()),
        }

    def assert_delegated_once(self):
        self.authorize.assert_called_once_with(electronic_document=self.document)
        delegated = self.authorize.call_args.kwargs["electronic_document"]
        self.assertIsInstance(delegated, ElectronicDocument)
        self.assertEqual(delegated.company_id, self.company.pk)
        self.assertEqual(delegated.branch_id, self.branch.pk)

    def assert_result(self, response, state):
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/html"))
        self.assertTemplateUsed(response, TEMPLATE)
        self.assertEqual(response.context["electronic_document"].pk, self.document.pk)
        self.assertEqual(response.context["authorization_state"], state)
        message = response.context["authorization_message"]
        self.assertIsInstance(message, str)
        self.assertTrue(message.strip())
        # Semantic feedback must reach the user, not only template context.
        self.assertContains(response, escape(message), html=False)
        self.assertNotContains(response, PRIVATE_ERROR)
        self.assertNotContains(response, "Traceback (most recent call last)")

    def authorized_result(self, persist=False):
        result = ElectronicDocument.objects.get(pk=self.document.pk)
        result.status = SriDocumentStatus.AUTHORIZED
        result.authorization_number = result.access_key
        result.authorization_date = timezone.now()
        result.authorized_xml = "<authorized>private evidence</authorized>"
        if persist:
            result.save()
        return result

    def known_error(self, error, state):
        url = self.url()
        before = self.snapshot()
        self.authorize.side_effect = error(PRIVATE_ERROR)
        response = self.client.post(url)
        self.assert_result(response, state)
        self.assert_delegated_once()
        self.assertEqual(self.snapshot(), before)


class ElectronicDocumentAuthorizationTriggerTests(AuthorizationTriggerFixture, TestCase):
    def test_get_route_view_and_confirmation_are_safe(self):
        url = self.url()
        self.assertEqual(url, f"/sri/electronic-documents/{self.document.pk}/authorize/")
        match = resolve(url)
        self.assertEqual(match.url_name, URL_NAME)
        self.assertEqual(match.namespace, "")
        self.assertEqual(match.func.__module__, "sri.views")
        self.assertEqual(match.func.__name__, "electronic_document_authorize")
        before = self.snapshot()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, TEMPLATE)
        self.assertEqual(response.context["electronic_document"], self.document)
        self.assertEqual(response.wsgi_request.active_company, self.company)
        self.assertEqual(response.wsgi_request.active_branch, self.branch)
        self.authorize.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_anonymous_get_and_post_redirect_to_real_core_login(self):
        url = self.url()
        client = Client()
        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(client, method)(url)
                self.assertEqual(response.status_code, 302)
                location = urlsplit(response["Location"])
                self.assertEqual(location.path, reverse("login"))
                self.assertEqual(parse_qs(location.query), {"next": [url]})
                self.authorize.assert_not_called()

    def test_missing_manipulated_and_revoked_context_redirects_without_delegation(self):
        url = self.url()
        cases = (
            (None, None, "select_company", False),
            (self.company.pk, None, "select_branch", False),
            (self.other_company.pk, self.other_branch.pk, "select_company", False),
            (self.company.pk, self.other_branch.pk, "select_branch", False),
            (self.company.pk, self.branch.pk, "select_company", True),
        )
        for company_id, branch_id, destination, revoke in cases:
            for method in ("get", "post"):
                with self.subTest(company=company_id, branch=branch_id, revoke=revoke, method=method):
                    self.user.profile.companies.add(self.company)
                    if revoke:
                        self.user.profile.companies.remove(self.company)
                    self.set_context(company_id, branch_id)
                    response = getattr(self.client, method)(url)
                    self.assertRedirects(response, reverse(destination), fetch_redirect_response=False)
                    self.authorize.assert_not_called()

    def test_cross_company_get_and_post_are_scoped_404(self):
        url = self.url()
        self.user.profile.companies.add(self.other_company)
        self.user.profile.branches.add(self.other_branch)
        self.set_context(self.other_company.pk, self.other_branch.pk)
        before = self.snapshot()
        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 404)
                self.authorize.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_cross_branch_is_404_even_with_membership_in_both_branches(self):
        url = self.url()
        self.set_context(self.company.pk, self.second_branch.pk)
        before = self.snapshot()
        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 404)
                self.authorize.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_missing_id_does_not_fall_back_to_caller_access_key(self):
        missing_id = ElectronicDocument.objects.order_by("-pk").values_list("pk", flat=True).first() + 1
        url = self.url(missing_id)
        supplied = {"access_key": self.document.access_key, "company": self.company.pk, "branch": self.branch.pk}
        for method in ("get", "post"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, supplied)
                self.assertEqual(response.status_code, 404)
                self.authorize.assert_not_called()

    def test_post_renders_returned_authorized_document_and_delegates_only_instance(self):
        url = self.url()
        before = self.snapshot()
        self.authorize.return_value = self.authorized_result()
        response = self.client.post(url)
        self.assert_result(response, "AUTHORIZED")
        self.assertEqual(response.context["electronic_document"].status, SriDocumentStatus.AUTHORIZED)
        self.assert_delegated_once()
        self.assertEqual(self.snapshot(), before)
        self.assertNotContains(response, "private evidence")

    def test_initially_authorized_document_still_delegates_and_succeeds(self):
        url = self.url()
        self.authorize.return_value = self.authorized_result(persist=True)
        before = self.snapshot()
        response = self.client.post(url)
        self.assert_result(response, "AUTHORIZED")
        self.assert_delegated_once()
        self.assertEqual(self.snapshot(), before)

    def test_rejected_result_is_fiscal_rejection_without_retry(self):
        url = self.url()
        result = ElectronicDocument.objects.get(pk=self.document.pk)
        result.status = SriDocumentStatus.REJECTED
        self.authorize.return_value = result
        before = self.snapshot()
        response = self.client.post(url)
        self.assert_result(response, "REJECTED")
        self.assert_delegated_once()
        self.assertEqual(self.snapshot(), before)

    def test_pending_uses_latest_attempt_and_does_not_retry(self):
        url = self.url()
        now = timezone.now()
        for status, started_at in (
            (SriAuthorizationAttemptStatus.UNCERTAIN, now - timedelta(minutes=1)),
            (SriAuthorizationAttemptStatus.PENDING, now),
        ):
            SriAuthorizationAttempt.objects.create(
                electronic_document=self.document, status=status,
                access_key=self.document.access_key, environment=self.document.environment,
                started_at=started_at, finished_at=started_at,
            )
        before = self.snapshot()
        response = self.client.post(url)
        self.assert_result(response, "PENDING")
        self.assertEqual(response.context["electronic_document"].status, SriDocumentStatus.RECEIVED)
        self.assert_delegated_once()
        self.assertEqual(self.snapshot(), before)

    def test_transport_error_is_uncertain_without_retry_or_private_details(self):
        self.known_error(SriAuthorizationTransportError, "UNCERTAIN")

    def test_protocol_error_is_not_generic_value_error_or_fiscal_rejection(self):
        self.known_error(SriAuthorizationProtocolError, "PROTOCOL_ERROR")

    def test_in_progress_and_preflight_have_distinct_safe_results(self):
        self.url()  # Report the missing production boundary once during RED.
        for error, state in ((AuthorizationAlreadyInProgress, "IN_PROGRESS"), (ValueError, "INVALID")):
            with self.subTest(state=state):
                self.authorize.reset_mock()
                self.known_error(error, state)

    def test_unexpected_exception_propagates_instead_of_becoming_fiscal_rejection(self):
        url = self.url()
        error = RuntimeError(PRIVATE_ERROR)
        self.authorize.side_effect = error
        before = self.snapshot()
        with self.assertRaises(RuntimeError) as caught:
            self.client.post(url)
        self.assertIs(caught.exception, error)
        self.assert_delegated_once()
        self.assertEqual(self.snapshot(), before)

    def test_csrf_form_token_is_required_and_valid_token_allows_post(self):
        url = self.url()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk, client=client)
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertIn("csrftoken", client.cookies)
        self.authorize.assert_not_called()
        before = self.snapshot()
        response = client.post(url)
        self.assertEqual(response.status_code, 403)
        self.authorize.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.authorize.return_value = self.authorized_result()
        response = client.post(url, {"csrfmiddlewaretoken": client.cookies["csrftoken"].value})
        self.assert_result(response, "AUTHORIZED")
        self.assert_delegated_once()

    def test_head_is_safe_and_other_methods_are_not_allowed(self):
        url = self.url()
        before = self.snapshot()
        response = self.client.head(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        for method in ("put", "patch", "delete", "options"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(set(response["Allow"].split(", ")), {"GET", "HEAD", "POST"})
                self.authorize.assert_not_called()
        self.authorize.assert_not_called()
        self.assertEqual(self.snapshot(), before)

    def test_post_and_querystring_cannot_override_persisted_authorities(self):
        url = self.url()
        supplied = {
            "environment": "2", "access_key": "9" * 49, "status": "AUTHORIZED",
            "authorization_number": "injected", "authorized_xml": "<injected/>",
            "company": self.other_company.pk, "branch": self.other_branch.pk,
        }
        before = self.snapshot()

        def result(*, electronic_document):
            for field in ("environment", "access_key", "status", "authorization_number", "authorized_xml", "company_id", "branch_id"):
                self.assertEqual(getattr(electronic_document, field), before["document"][field])
            return self.authorized_result()

        self.authorize.side_effect = result
        response = self.client.post(f"{url}?{urlencode(supplied)}", supplied)
        self.assert_result(response, "AUTHORIZED")
        self.assert_delegated_once()
        self.assertEqual(self.snapshot(), before)


class ElectronicDocumentAuthorizationTriggerTransactionTests(
    AuthorizationTriggerFixture, TransactionTestCase,
):
    def test_c13c_is_called_outside_an_external_transaction(self):
        url = self.url()
        observed = []

        def result(*, electronic_document):
            observed.append(connection.in_atomic_block)
            return self.authorized_result()

        self.authorize.side_effect = result
        response = self.client.post(url)
        self.assert_result(response, "AUTHORIZED")
        self.assert_delegated_once()
        self.assertEqual(observed, [False])
