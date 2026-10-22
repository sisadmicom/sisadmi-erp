"""D-01: shared operator shell, read-only navigation and global feedback."""
from html.parser import HTMLParser
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages.storage.session import SessionStorage
from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.test import RequestFactory, TestCase, override_settings, tag
from django.urls import NoReverseMatch, reverse
from django.contrib import messages

from core.constants.sri import SriDocumentType
from sales.models import Sale
from sales.tests.test_sale_fiscal_preparation_trigger import FiscalPreparationTriggerFixtureMixin
from sri.constants.document_status import SriDocumentStatus
from sri.models import ElectronicDocument


class ShellHTML(HTMLParser):
    def __init__(self, content):
        super().__init__()
        self.links = []
        self.forms = []
        self.stylesheets = []
        self.error_signals = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        if tag == "form":
            self.forms.append((attrs.get("method", "get").lower(), attrs.get("action", "")))
        if tag == "link" and "stylesheet" in attrs.get("rel", "").split():
            self.stylesheets.append(attrs.get("href", ""))
        if attrs.get("role") == "alert" or "error" in attrs.get("class", "").lower():
            self.error_signals.append(attrs)


class ShellFixture(FiscalPreparationTriggerFixtureMixin):
    """Reuse C-14B model fixtures, but never its mutation mocks or test methods."""
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="d01-operator", password="d01-test-password")
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="sales",
            codename__in=["view_sale", "add_sale"]))
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label="sri",
            codename__in=["view_electronicdocument", "change_electronicdocument"]))
        self.user.user_permissions.add(Permission.objects.get(
            content_type__app_label="catalog", content_type__model="product",
            codename="view_product",
        ))
        self.user.profile.companies.add(self.company, self.other_company)
        self.user.profile.branches.add(self.branch, self.other_branch, self.other_company_branch)
        self.client.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk)
        for target in (
            "sales.views.CreateSale.execute", "sales.views.ConfirmSale.execute",
            "sales.views.FiscalDocumentPreparationService.prepare",
            "sri.views.ElectronicDocumentSigningService.sign",
            "sri.views.submit_electronic_document", "sri.views.authorize_electronic_document",
            "sri.services.electronic_document_reception_entrypoint.SriReceptionSoapAdapter",
            "sri.services.electronic_document_authorization_entrypoint.SriAuthorizationSoapAdapter",
            "socket.create_connection", "socket.socket.connect", "requests.sessions.Session.request",
        ):
            guard = patch(target, side_effect=AssertionError(f"D-01 navigation must not call {target}"))
            mock = guard.start()
            self.addCleanup(guard.stop)
            self.addCleanup(mock.assert_not_called)

    def logout_path(self):
        try:
            path = reverse("logout")
        except NoReverseMatch:
            self.fail("D-01 requires a named CORE logout route")
        self.assertTrue(path.startswith("/core/"), "Logout must be a CORE boundary")
        return path

    def shell(self, response):
        # Render the common template without page content: catalog row actions
        # and contextual fiscal links are deliberately outside this contract.
        return ShellHTML(render_to_string("core/base.html", request=response.wsgi_request))

    def document(self):
        sale = self.sale()
        document = ElectronicDocument(
            company=self.company, branch=self.branch,
            content_type=ContentType.objects.get_for_model(Sale), object_id=sale.pk,
            document_type=SriDocumentType.INVOICE, establishment="001", emission_point="001",
            sequential="000000001", numeric_code="12345678", access_key="8" * 49,
            status=SriDocumentStatus.GENERATED,
            xml="<private>D01_PRIVATE_XML</private>", error_message="D01_PRIVATE_SOAP_TRACEBACK_SECRET",
        )
        document.full_clean()
        document.save()
        return sale, document

    def pages(self, sale, document):
        return [reverse("dashboard"), reverse("product_list"), reverse("sale_create"),
                reverse("sale_detail", kwargs={"sale_id": sale.pk})] + [
                    reverse(name, kwargs={"electronic_document_id": document.pk}) for name in
                    ("electronic_document_sign", "electronic_document_receive", "electronic_document_authorize")]


@tag("d01_application_shell_red")
class ApplicationShellTests(ShellFixture, TestCase):
    def test_private_shell_shows_identity_context_and_operator_actions(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        for value in ("SISADMI", self.user.username, self.company.commercial_name, self.branch.name):
            self.assertContains(response, value)
        html = self.shell(response)
        for name in ("dashboard", "product_list", "sale_create", "select_company", "select_branch"):
            with self.subTest(route=name):
                self.assertIn(reverse(name), html.links)
        self.assertIn(("post", self.logout_path()), html.forms)

    def test_shell_has_no_dead_global_fiscal_admin_or_delete_links(self):
        html = self.shell(self.client.get(reverse("dashboard")))
        self.assertNotIn("#", html.links)
        allowed = {reverse(name) for name in
                   ("dashboard", "product_list", "sale_create", "select_company", "select_branch")}
        self.assertTrue(set(html.links) <= allowed, "Only real D-01 operator entries belong in the shell")
        self.assertFalse(any("/sri/" in link or "/delete/" in link or "/admin/" in link for link in html.links))

    def test_dashboard_provides_real_frequent_actions_and_context_changes(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        html = ShellHTML(response.content.decode())
        for name in ("sale_create", "product_list", "select_company", "select_branch"):
            with self.subTest(route=name):
                self.assertIn(reverse(name), html.links)
        self.assertContains(response, self.company.commercial_name)
        self.assertContains(response, self.branch.name)

    @override_settings(MESSAGE_STORAGE="django.contrib.messages.storage.session.SessionStorage")
    def test_messages_are_global_and_sale_detail_does_not_duplicate_them(self):
        sale = self.sale()
        for index, path in enumerate((reverse("dashboard"), reverse("sale_detail", kwargs={"sale_id": sale.pk}))):
            with self.subTest(page=path):
                request = RequestFactory().get(path)
                request.session = self.client.session
                storage = SessionStorage(request)
                request._messages = storage
                marker = f"D01_ONE_GLOBAL_MESSAGE_{index}"
                messages.success(request, marker)
                storage.update(HttpResponse())
                request.session.save()
                response = self.client.get(path)
                self.assertContains(response, marker, count=1)

    def test_all_critical_pages_render_the_common_operator_shell(self):
        sale, document = self.document()
        for path in self.pages(sale, document):
            with self.subTest(page=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "core/base.html")
                self.assertIn(reverse("select_company"), ShellHTML(response.content.decode()).links)

    def test_get_and_head_operator_navigation_are_read_only(self):
        sale, document = self.document()
        for path in self.pages(sale, document):
            for method in ("get", "head"):
                with self.subTest(page=path, method=method):
                    self.assertEqual(getattr(self.client, method)(path).status_code, 200)
        document.refresh_from_db()
        self.assertEqual(document.status, SriDocumentStatus.GENERATED)
        self.assertEqual(document.reception_attempts.count(), 0)
        self.assertEqual(document.authorization_attempts.count(), 0)

    def test_common_css_is_local_included_and_available_to_staticfiles(self):
        asset = "core/css/erp.css"
        html = self.shell(self.client.get(reverse("dashboard")))
        with self.subTest(contract="included"):
            self.assertIn(static(asset), html.stylesheets)
        with self.subTest(contract="available"):
            self.assertIsNotNone(finders.find(asset), "The shared stylesheet must be an offline local asset")
        self.assertFalse(any(url.startswith(("http://", "https://", "//")) for url in html.stylesheets))

    def test_context_selectors_do_not_invent_an_active_context(self):
        self.set_context(None, None)
        company_page = self.client.get(reverse("select_company"))
        self.assertEqual(company_page.status_code, 200)
        self.assertIsNone(company_page.wsgi_request.active_company)
        self.assertIsNone(company_page.wsgi_request.active_branch)
        self.set_context(self.company.pk, None)
        branch_page = self.client.get(reverse("select_branch"))
        self.assertEqual(branch_page.status_code, 200)
        self.assertEqual(branch_page.wsgi_request.active_company.pk, self.company.pk)
        self.assertIsNone(branch_page.wsgi_request.active_branch)

    def test_shell_escapes_context_and_fiscal_pages_hide_sensitive_evidence(self):
        self.company.commercial_name = '<script>D01_COMPANY</script>'
        self.company.save(update_fields=["commercial_name"])
        self.branch.name = '<script>D01_BRANCH</script>'
        self.branch.save(update_fields=["name"])
        sale, document = self.document()
        for path in self.pages(sale, document):
            with self.subTest(page=path):
                response = self.client.get(path)
                self.assertContains(response, "&lt;script&gt;D01_COMPANY&lt;/script&gt;")
                self.assertNotContains(response, '<script>D01_COMPANY</script>')
                self.assertNotContains(response, '<script>D01_BRANCH</script>')
                for secret in (document.access_key, "D01_PRIVATE_XML", "D01_PRIVATE_SOAP_TRACEBACK_SECRET", "Traceback"):
                    self.assertNotContains(response, secret)
