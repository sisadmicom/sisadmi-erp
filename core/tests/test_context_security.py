from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from core.models import Branch, Company
from catalog.models import Product
from people.models import Person


class ContextSecurityTests(TestCase):
    def setUp(self):
        self.company_a = self.create_company("A", "1790000001001")
        self.company_b = self.create_company("B", "1790000001002")
        self.branch_a = Branch.objects.create(company=self.company_a, code="A01", name="A")
        self.branch_a2 = Branch.objects.create(company=self.company_a, code="A02", name="A2")
        self.branch_b = Branch.objects.create(company=self.company_b, code="B01", name="B")
        self.product_b = Product.objects.create(company=self.company_b, code="PB", name="Producto B")
        self.user = get_user_model().objects.create_user(username="context-user", password="password")
        self.user.profile.companies.add(self.company_a)
        self.user.profile.branches.add(self.branch_a)
        self.client = Client()
        self.client.force_login(self.user)

    @staticmethod
    def create_company(suffix, identification):
        person = Person.objects.create(
            identification=identification,
            person_type="LEGAL",
            full_name=f"Empresa {suffix}",
        )
        return Company.objects.create(person=person, commercial_name=f"Empresa {suffix}")

    def set_session(self, **values):
        session = self.client.session
        for key, value in values.items():
            session[key] = value
        session.save()

    def test_user_cannot_select_company_outside_profile(self):
        response = self.client.post("/core/select-company/", {"company_id": self.company_b.pk})
        self.assertRedirects(response, "/core/select-company/")
        self.assertNotEqual(self.client.session.get("company_id"), self.company_b.pk)

    def test_user_cannot_select_branch_from_another_company(self):
        self.set_session(company_id=self.company_a.pk)
        response = self.client.post("/core/select-branch/", {"branch_id": self.branch_b.pk})
        self.assertRedirects(response, "/core/select-branch/")
        self.assertNotEqual(self.client.session.get("branch_id"), self.branch_b.pk)

    def test_user_cannot_select_unauthorized_branch_in_authorized_company(self):
        self.set_session(company_id=self.company_a.pk)
        response = self.client.post("/core/select-branch/", {"branch_id": self.branch_a2.pk})
        self.assertRedirects(response, "/core/select-branch/")
        self.assertNotEqual(self.client.session.get("branch_id"), self.branch_a2.pk)

    def test_middleware_rejects_manipulated_company_session(self):
        self.set_session(company_id=self.company_b.pk, branch_id=None)
        response = self.client.get("/core/dashboard/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("select-company", response["Location"])

    def test_middleware_rejects_branch_not_belonging_to_active_company(self):
        self.set_session(company_id=self.company_a.pk, branch_id=self.branch_b.pk)
        response = self.client.get("/core/dashboard/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("select-branch", response["Location"])

    def test_product_list_does_not_read_company_from_manipulated_session(self):
        self.set_session(company_id=self.company_b.pk, branch_id=None)
        response = self.client.get("/catalog/products/", follow=True)
        self.assertNotContains(response, "Producto B")

    def test_revoked_company_membership_invalidates_saved_context(self):
        self.set_session(company_id=self.company_a.pk, branch_id=self.branch_a.pk)
        self.user.profile.companies.remove(self.company_a)
        response = self.client.get("/core/dashboard/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("select-company", response["Location"])
