from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from core.models import Company, Branch
from people.models import Person, CompanyPersonAccess, Customer, CustomerCategory
from people.services import customer_maintenance


class CustomerCategoryAssignmentTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(person=Person.objects.create(
            identification="CATASSIGN-A", full_name="Assignment company A"))
        self.other = Company.objects.create(person=Person.objects.create(
            identification="CATASSIGN-B", full_name="Assignment company B"))
        self.branch = Branch.objects.create(company=self.company, code="001", name="Matriz")
        self.person = Person.objects.create(identification="CATASSIGN-P", full_name="Assignment buyer")
        CompanyPersonAccess.objects.create(company=self.company, person=self.person)
        self.user = get_user_model().objects.create_user("category-assignment-test")
        self.user.profile.companies.add(self.company)
        self.user.profile.branches.add(self.branch)
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="people", codename__in=[
                "view_person", "view_customer", "add_customer", "change_customer",
            ]))
        self.active = CustomerCategory.objects.create(company=self.company, code="ACTIVE", name="Local active")
        self.inactive = CustomerCategory.objects.create(company=self.company, code="INACTIVE", name="Local inactive", is_active=False)
        self.foreign = CustomerCategory.objects.create(company=self.other, code="PRIVATE", name="Foreign secret")
        self.client.force_login(self.user)
        session = self.client.session
        session.update({"company_id": self.company.pk, "branch_id": self.branch.pk})
        session.save()

    def create(self, category=None):
        return customer_maintenance.create(actor=self.user, company=self.company,
            person_id=self.person.pk, data={"category": category})

    def payload(self, category="", **extra):
        return {"person": self.person.pk, "credit_limit": "0.00", "notes": "Notes",
                "category": category, **extra}

    def test_selector_contains_only_active_categories_of_current_company(self):
        page = self.client.get(reverse("customer_create"))
        self.assertEqual(page.status_code, 200)
        field = page.context["form"].fields["category"]
        self.assertEqual(list(field.queryset), [self.active])
        self.assertFalse(field.required)
        self.assertContains(page, 'name="category"')
        self.assertNotContains(page, self.foreign.name)
        self.assertNotContains(page, self.inactive.name)

    def test_http_creation_persists_category_and_displays_it(self):
        page = self.client.post(reverse("customer_create"), self.payload(self.active.pk))
        customer = Customer.objects.get(company=self.company, person=self.person)
        self.assertRedirects(page, reverse("customer_detail", args=[customer.pk]))
        self.assertEqual(customer.category, self.active)
        self.assertContains(self.client.get(reverse("customer_list")), str(self.active))
        self.assertContains(self.client.get(reverse("customer_detail", args=[customer.pk])), str(self.active))

    def test_http_creation_without_category_remains_valid(self):
        self.assertEqual(self.client.post(reverse("customer_create"), self.payload()).status_code, 302)
        customer = Customer.objects.get(company=self.company, person=self.person)
        self.assertIsNone(customer.category_id)
        self.assertContains(self.client.get(reverse("customer_detail", args=[customer.pk])), "Sin categoría")

    def test_http_edit_initializes_and_changes_category(self):
        customer = self.create()
        url = reverse("customer_update", args=[customer.pk])
        page = self.client.get(url)
        self.assertIsNone(page.context["form"].initial["category"])
        self.assertEqual(self.client.post(url, {"credit_limit": "1.00", "notes": "Edit", "category": self.active.pk}).status_code, 302)
        customer.refresh_from_db()
        self.assertEqual(customer.category, self.active)
        self.assertEqual(self.client.get(url).context["form"]["category"].value(), self.active.pk)

    def test_editing_other_data_preserves_category_even_when_field_is_omitted(self):
        customer = self.create(self.active)
        url = reverse("customer_update", args=[customer.pk])
        self.assertEqual(self.client.post(url, {"credit_limit": "20.00", "notes": "Other edit"}).status_code, 302)
        customer.refresh_from_db()
        self.assertEqual(customer.category, self.active)
        self.assertEqual(customer.notes, "Other edit")
        self.assertEqual(self.client.post(url, {"credit_limit": "20.00", "notes": "Same", "category": self.active.pk}).status_code, 302)
        customer.refresh_from_db()
        self.assertEqual(customer.category, self.active)

    def test_active_category_can_be_explicitly_cleared(self):
        customer = self.create(self.active)
        self.assertEqual(self.client.post(reverse("customer_update", args=[customer.pk]), {
            "credit_limit": "0.00", "notes": "", "category": "",
        }).status_code, 302)
        customer.refresh_from_db()
        self.assertIsNone(customer.category_id)

    def test_existing_inactive_category_is_preserved_and_can_be_replaced(self):
        customer = self.create(self.active)
        self.active.is_active = False
        self.active.save(update_fields=["is_active"])
        url = reverse("customer_update", args=[customer.pk])
        page = self.client.get(url)
        self.assertContains(page, "Conservar categoría actual")
        self.assertEqual(list(page.context["form"].fields["category"].queryset), [])
        self.assertEqual(self.client.post(url, {"notes": "Keep", "credit_limit": "0.00", "category": ""}).status_code, 302)
        customer.refresh_from_db()
        self.assertEqual(customer.category_id, self.active.pk)
        customer_maintenance.update(actor=self.user, company=self.company, relation_id=customer.pk,
                                    data={"notes": "API keep", "category": self.active})
        self.inactive.is_active = True
        self.inactive.save(update_fields=["is_active"])
        self.assertEqual(self.client.post(url, {"notes": "Replace", "credit_limit": "0.00", "category": self.inactive.pk}).status_code, 302)
        customer.refresh_from_db()
        self.assertEqual(customer.category_id, self.inactive.pk)

    def test_http_rejects_foreign_inactive_and_missing_categories(self):
        for pk in (self.foreign.pk, self.inactive.pk, 9223372036854775807):
            with self.subTest(category=pk):
                page = self.client.post(reverse("customer_create"), self.payload(pk))
                self.assertEqual(page.status_code, 200)
                self.assertEqual(page.context["form"].errors.as_data()["category"][0].code, "invalid_choice")
                self.assertNotContains(page, self.foreign.name)
        self.assertFalse(Customer.objects.filter(company=self.company, person=self.person).exists())

    def test_service_rejects_invalid_category_without_changing_customer(self):
        customer = self.create(self.active)
        for value in (self.foreign, self.inactive, 9223372036854775807):
            with self.subTest(category=value.pk if isinstance(value, CustomerCategory) else value):
                with self.assertRaises(ValidationError) as error:
                    customer_maintenance.update(actor=self.user, company=self.company, relation_id=customer.pk,
                        data={"category": value, "notes": "Must rollback"})
                self.assertEqual(error.exception.error_dict["category"][0].code, "invalid_category")
                customer.refresh_from_db()
                self.assertEqual(customer.category_id, self.active.pk)
                self.assertEqual(customer.notes, "")

    def test_service_creation_rejects_foreign_and_inactive_categories(self):
        for value in (self.foreign, self.inactive):
            with self.subTest(category=value.pk):
                with self.assertRaises(ValidationError) as error:
                    self.create(value)
                self.assertEqual(error.exception.error_dict["category"][0].code, "invalid_category")
        self.assertFalse(Customer.objects.filter(company=self.company, person=self.person).exists())

    def test_model_validation_rejects_cross_company_assignment(self):
        customer = Customer(company=self.company, person=self.person, category=self.foreign)
        with self.assertRaises(ValidationError) as error:
            customer.full_clean()
        self.assertEqual(error.exception.error_dict["category"][0].code, "invalid_category")

    def test_associated_category_is_protected_from_deletion(self):
        customer = self.create(self.active)
        with self.assertRaises(ProtectedError):
            self.active.delete()
        customer.refresh_from_db()
        self.assertEqual(customer.category_id, self.active.pk)

    def test_permission_and_company_scope_still_protect_customer_edit(self):
        customer = self.create(self.active)
        url = reverse("customer_update", args=[customer.pk])
        self.user.user_permissions.remove(Permission.objects.get(codename="change_customer"))
        self.assertEqual(self.client.post(url, {"category": self.foreign.pk}).status_code, 403)
        customer.refresh_from_db()
        self.assertEqual(customer.category_id, self.active.pk)

    def test_supplier_form_does_not_get_customer_category(self):
        self.user.user_permissions.add(Permission.objects.get(codename="add_supplier"))
        page = self.client.get(reverse("supplier_create"))
        self.assertEqual(page.status_code, 200)
        self.assertNotIn("category", page.context["form"].fields)
