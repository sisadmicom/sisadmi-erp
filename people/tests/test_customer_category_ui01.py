from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from core.models import Branch, Company
from people.models import CustomerCategory, Person


class CustomerCategoryUITests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(person=Person.objects.create(
            identification="UI01-A", full_name="Empresa A"))
        self.other = Company.objects.create(person=Person.objects.create(
            identification="UI01-B", full_name="Empresa B"))
        self.branch = Branch.objects.create(company=self.company, code="001", name="Matriz")
        self.user = get_user_model().objects.create_user("ui01-operator")
        self.user.profile.companies.add(self.company)
        self.user.profile.branches.add(self.branch)
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="people", content_type__model="customercategory",
            codename__in=["view_customercategory", "add_customercategory", "change_customercategory"]))
        self.client.force_login(self.user)
        session = self.client.session
        session.update({"company_id": self.company.pk, "branch_id": self.branch.pk})
        session.save()
        self.category = CustomerCategory.objects.create(company=self.company, code="VIP", name="Preferentes")
        self.foreign = CustomerCategory.objects.create(company=self.other, code="PRIVATE", name="NO MOSTRAR")

    def url(self, operation="list", obj=None):
        return reverse("customer_category_" + operation, args=[obj.pk] if obj else [])

    def test_list_search_and_inactive_visibility(self):
        self.category.is_active = False
        self.category.save()
        for query in ("", "vip", "ferent"):
            with self.subTest(query=query):
                response = self.client.get(self.url(), {"q": query})
                self.assertContains(response, "Preferentes")
                self.assertContains(response, "Inactivo")
                self.assertNotContains(response, "NO MOSTRAR")
        self.assertNotContains(self.client.get(self.url(), {"q": "absent"}), "Preferentes")

    def test_create_uses_server_company_and_records_actor(self):
        response = self.client.post(self.url("create"), {
            "code": " regular ", "name": " Habituales ", "company": self.other.pk,
            "is_active": "", "created_by": "99999",
        })
        obj = CustomerCategory.objects.get(company=self.company, code="REGULAR")
        self.assertRedirects(response, self.url("detail", obj))
        self.assertEqual(obj.name, "Habituales")
        self.assertEqual(obj.created_by, self.user)
        self.assertEqual(obj.updated_by, self.user)
        self.assertTrue(obj.is_active)

    def test_edit_persists_fields_without_changing_company_or_activity(self):
        self.category.is_active = False
        self.category.save()
        response = self.client.post(self.url("update", self.category), {
            "code": "NEW", "name": "Actualizada", "company": self.other.pk, "is_active": "1",
        })
        self.assertRedirects(response, self.url("detail", self.category))
        self.category.refresh_from_db()
        self.assertEqual((self.category.code, self.category.name), ("NEW", "Actualizada"))
        self.assertEqual(self.category.company, self.company)
        self.assertFalse(self.category.is_active)
        self.assertEqual(self.category.updated_by, self.user)

    def test_required_fields_and_duplicate_code_are_field_errors(self):
        for data, field, code in (({"code": " ", "name": "Nombre"}, "code", "required"),
                                  ({"code": "NEW", "name": " "}, "name", "required"),
                                  ({"code": "vip", "name": "Otra"}, "code", "duplicate_code")):
            with self.subTest(data=data):
                response = self.client.post(self.url("create"), data)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["form"].errors.as_data()[field][0].code, code)
        self.assertEqual(CustomerCategory.objects.filter(company=self.company).count(), 1)

    def test_code_is_unique_per_company_including_inactive(self):
        self.category.is_active = False
        self.category.save()
        with transaction.atomic():
            with self.assertRaises(IntegrityError) as caught:
                CustomerCategory.objects.create(company=self.company, code="VIP", name="Duplicada")
        self.assertEqual(caught.exception.__cause__.sqlstate, "23505")
        self.assertEqual(caught.exception.__cause__.diag.constraint_name,
                         "people_customer_category_company_code_unique")
        CustomerCategory.objects.create(company=self.other, code="VIP", name="Permitida")

    def test_edit_can_keep_own_code_but_cannot_take_another_code(self):
        other = CustomerCategory.objects.create(company=self.company, code="SECOND", name="Segunda")
        response = self.client.post(self.url("update", self.category), {"code": "VIP", "name": "Editada"})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(self.url("update", self.category), {"code": other.code, "name": "Inválida"})
        self.assertEqual(response.context["form"].errors.as_data()["code"][0].code, "duplicate_code")
        self.category.refresh_from_db()
        self.assertEqual(self.category.code, "VIP")

    def test_activity_is_post_only_and_preserves_record(self):
        for operation, expected in (("deactivate", False), ("reactivate", True)):
            url = self.url(operation, self.category)
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertRedirects(self.client.post(url), self.url("detail", self.category))
            self.category.refresh_from_db()
            self.assertEqual(self.category.is_active, expected)
            self.assertEqual(self.category.updated_by, self.user)
        self.assertEqual(CustomerCategory.objects.filter(pk=self.category.pk).count(), 1)

    def test_csrf_required_for_all_mutations(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.user)
        session = browser.session
        session.update({"company_id": self.company.pk, "branch_id": self.branch.pk})
        session.save()
        for url in (self.url("create"), self.url("update", self.category), self.url("deactivate", self.category)):
            self.assertEqual(browser.post(url, {"code": "ATTACK", "name": "Attack"}).status_code, 403)
        browser.get(self.url("create"))
        response = browser.post(self.url("create"), {"code": "CSRF", "name": "Válida"},
                                HTTP_X_CSRFTOKEN=browser.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 302)

    def test_foreign_objects_are_not_readable_or_mutable(self):
        for operation in ("detail", "update", "deactivate", "reactivate"):
            for method in (("get", "post") if operation == "update" else
                           ("post",) if operation in ("deactivate", "reactivate") else ("get",)):
                with self.subTest(operation=operation, method=method):
                    response = getattr(self.client, method)(self.url(operation, self.foreign),
                                                          {"code": "STOLEN", "name": "Attack"})
                    self.assertEqual(response.status_code, 404)
        self.foreign.refresh_from_db()
        self.assertEqual(self.foreign.code, "PRIVATE")
        self.assertTrue(self.foreign.is_active)

    def test_missing_permissions_block_each_operation(self):
        self.user.user_permissions.clear()
        for operation, obj, method in (("list", None, "get"), ("detail", self.category, "get"),
                                      ("create", None, "get"), ("create", None, "post"),
                                      ("update", self.category, "post"), ("deactivate", self.category, "post")):
            with self.subTest(operation=operation):
                self.assertEqual(getattr(self.client, method)(self.url(operation, obj)).status_code, 403)

    def test_read_only_operator_can_consult_but_not_mutate(self):
        self.user.user_permissions.clear()
        self.user.user_permissions.add(Permission.objects.get(codename="view_customercategory"))
        self.assertContains(self.client.get(self.url("detail", self.category)), "Preferentes")
        self.assertNotContains(self.client.get(self.url()), "Adicionar categoría")
        self.assertEqual(self.client.post(self.url("deactivate", self.category)).status_code, 403)

    def test_context_cannot_be_forged_or_omitted(self):
        for company_id, branch_id in ((None, None), (self.company.pk, None), (self.other.pk, self.branch.pk)):
            with self.subTest(company=company_id, branch=branch_id):
                session = self.client.session
                session.update({"company_id": company_id, "branch_id": branch_id})
                session.save()
                self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_anonymous_requires_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get(self.url()), reverse("login") + "?next=" + self.url())

    def test_detail_escapes_html_and_does_not_offer_delete(self):
        self.category.name = "<script>alert(1)</script>"
        self.category.save()
        response = self.client.get(self.url("detail", self.category))
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert")
        self.assertEqual(self.client.post(self.url("detail", self.category) + "delete/").status_code, 404)

    def test_login_company_branch_and_menu_reach_category_screen(self):
        self.user.set_password("ui01-synthetic-password")
        self.user.save()
        self.client.logout()
        self.assertRedirects(self.client.post(reverse("login"), {
            "username": self.user.username, "password": "ui01-synthetic-password",
        }), reverse("select_company"))
        self.assertRedirects(self.client.post(reverse("select_company"), {"company_id": self.company.pk}), reverse("select_branch"))
        self.assertRedirects(self.client.post(reverse("select_branch"), {"branch_id": self.branch.pk}), reverse("dashboard"))
        self.assertContains(self.client.get(reverse("dashboard")), self.url())
        self.assertContains(self.client.get(self.url()), "Categorías de clientes")
