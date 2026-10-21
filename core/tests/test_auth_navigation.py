"""D-01: public login, existing membership flow and explicit POST logout."""
from urllib.parse import urlsplit

from django.conf import settings
from django.shortcuts import resolve_url
from django.test import Client, TestCase, tag
from django.urls import reverse

from core.tests import test_application_shell as shell_contract


@tag("d01_application_shell_red")
class AuthNavigationTests(shell_contract.ShellFixture, TestCase):
    def anonymous(self):
        self.client.logout()

    def test_login_is_public_without_context_or_private_navigation(self):
        self.anonymous()
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/login.html")
        self.assertContains(response, 'name="username"')
        self.assertContains(response, 'name="password"')
        html = shell_contract.ShellHTML(response.content.decode())
        for name in ("dashboard", "product_list", "sale_create", "select_company", "select_branch"):
            self.assertNotIn(reverse(name), html.links)
        self.assertFalse(any("/sri/" in link for link in html.links))
        self.assertNotContains(response, self.company.commercial_name)
        self.assertNotContains(response, self.branch.name)

    def test_effective_login_url_and_anonymous_redirect_resolve_to_core(self):
        self.assertEqual(urlsplit(resolve_url(settings.LOGIN_URL)).path, reverse("login"))
        self.anonymous()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlsplit(response["Location"]).path, reverse("login"))

    def test_invalid_login_has_safe_visible_feedback_without_authentication(self):
        self.anonymous()
        response = self.client.post(reverse("login"), {"username": self.user.username, "password": "D01_PRIVATE_WRONG_PASSWORD"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(shell_contract.ShellHTML(response.content.decode()).error_signals,
                        "Invalid login needs a visible semantic error signal")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIsNone(self.client.session.get("company_id"))
        self.assertIsNone(self.client.session.get("branch_id"))
        for secret in ("D01_PRIVATE_WRONG_PASSWORD", "Traceback", "SECRET_KEY", "SOAP"):
            self.assertNotContains(response, secret)

    def test_valid_public_login_preserves_company_branch_dashboard_flow(self):
        self.anonymous()
        response = self.client.post(reverse("login"), {"username": self.user.username, "password": "d01-test-password"})
        self.assertRedirects(response, reverse("select_company"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
        self.assertIsNone(self.client.session.get("company_id"))
        self.assertIsNone(self.client.session.get("branch_id"))
        self.assertRedirects(self.client.post(reverse("select_company"), {"company_id": self.company.pk}),
                             reverse("select_branch"), fetch_redirect_response=False)
        self.assertRedirects(self.client.post(reverse("select_branch"), {"branch_id": self.branch.pk}),
                             reverse("dashboard"))

    def test_missing_and_revoked_context_still_use_existing_middleware_policy(self):
        for company_id, branch_id, destination in ((None, None, "select_company"),
                (self.company.pk, None, "select_branch"), (self.company.pk, self.branch.pk, None)):
            with self.subTest(context=(company_id, branch_id)):
                self.set_context(company_id, branch_id)
                response = self.client.get(reverse("dashboard"))
                if destination:
                    self.assertRedirects(response, reverse(destination), fetch_redirect_response=False)
                else:
                    self.assertEqual(response.status_code, 200)
        self.user.profile.companies.remove(self.company)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("select_company"), fetch_redirect_response=False)
        self.assertIsNone(self.client.session.get("company_id"))
        self.assertIsNone(self.client.session.get("branch_id"))

    def test_context_navigation_get_does_not_change_selection_but_post_does(self):
        html = shell_contract.ShellHTML(self.client.get(reverse("dashboard")).content.decode())
        for name in ("select_company", "select_branch"):
            with self.subTest(route=name):
                self.assertIn(reverse(name), html.links)
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
                self.assertEqual(self.client.session["company_id"], self.company.pk)
                self.assertEqual(self.client.session["branch_id"], self.branch.pk)
        self.client.post(reverse("select_branch"), {"branch_id": self.other_branch.pk})
        self.assertEqual(self.client.session["branch_id"], self.other_branch.pk)
        self.client.post(reverse("select_company"), {"company_id": self.other_company.pk})
        self.assertEqual(self.client.session["company_id"], self.other_company.pk)
        self.assertIsNone(self.client.session["branch_id"])
        self.client.post(reverse("select_branch"), {"branch_id": self.other_company_branch.pk})
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, self.other_company.commercial_name)
        self.assertContains(response, self.other_company_branch.name)

    def test_logout_requires_authenticated_csrf_post_and_clears_context(self):
        path = self.logout_path()
        self.assertEqual(self.client.get(path).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.session["company_id"], self.company.pk)
        self.assertEqual(self.client.session["branch_id"], self.branch.pk)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.set_context(self.company.pk, self.branch.pk, client=strict)
        self.assertEqual(strict.post(path).status_code, 403)
        self.assertIn("_auth_user_id", strict.session)
        page = strict.get(reverse("sale_create"))
        self.assertEqual(page.status_code, 200)
        token = strict.cookies[settings.CSRF_COOKIE_NAME].value
        response = strict.post(path, {"csrfmiddlewaretoken": token}, follow=True)
        self.assertEqual(response.redirect_chain, [(reverse("login"), 302)])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        for key in ("_auth_user_id", "company_id", "branch_id"):
            self.assertNotIn(key, strict.session)
        anonymous = Client()
        anonymous_response = anonymous.post(path)
        self.assertEqual(anonymous_response.status_code, 302)
        self.assertEqual(urlsplit(anonymous_response["Location"]).path, reverse("login"))
