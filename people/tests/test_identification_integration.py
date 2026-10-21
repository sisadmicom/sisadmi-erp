"""PostgreSQL TEST only; each case rolls back, never flushes human records."""
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from core.models import Company
from people.models import Person, Customer, CompanyPersonAccess
from people.services.final_consumer import enable_for_company
from people.tests import test_customer_category_assignment as category_tests


class IdentificationIntegrationTests(TestCase):
    def setUp(self):
        category_tests.CustomerCategoryAssignmentTests.setUp(self)
        from django.contrib.auth.models import Permission
        self.user.user_permissions.add(Permission.objects.get(codename='add_person', content_type__app_label='people'))

    def reserved(self):
        return enable_for_company(self.company).person

    def test_catalog_is_reusable(self):
        from people.models import IdentificationKind
        self.assertEqual(set(IdentificationKind.objects.values_list('code', flat=True)),
                         {'CEDULA', 'RUC', 'OTHER', 'PASSPORT', 'FOREIGN_ID', 'FINAL_CONSUMER'})

    def test_new_identity_is_detected_and_linked(self):
        person = Person.objects.create(identification='1719304188', person_type='NATURAL', full_name='Identity test')
        self.assertEqual(person.identification_type, 'CEDULA')
        self.assertEqual(person.identification_kind.code, 'CEDULA')

    def test_invalid_identity_is_blocked_at_save(self):
        with self.assertRaises(ValidationError):
            Person.objects.create(identification='1719304189', identification_type='PASSPORT',
                                  person_type='NATURAL', full_name='Invalid identity')
        self.assertFalse(Person.objects.filter(identification='1719304189').exists())

    def test_final_consumer_is_one_person_with_independent_customers(self):
        first = enable_for_company(self.company)
        second = enable_for_company(self.other)
        self.assertEqual(first.person_id, second.person_id)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.company_id, self.company.pk)
        self.assertEqual(second.company_id, self.other.pk)

    def test_provisioning_is_idempotent(self):
        first = enable_for_company(self.company)
        second = enable_for_company(self.company)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Customer.objects.filter(company=self.company, person=first.person).count(), 1)
        self.assertEqual(CompanyPersonAccess.objects.filter(company=self.company, person=first.person).count(), 1)

    def test_reserved_person_edit_and_deactivation_are_blocked(self):
        person = self.reserved()
        for field, value in [('full_name', 'Changed'), ('is_active', False), ('identification', 'OTHER-IDENTITY')]:
            person.refresh_from_db(); setattr(person, field, value)
            with self.assertRaises(ValidationError) as caught:
                person.save()
            self.assertEqual(caught.exception.code, 'reserved_person')
        person.refresh_from_db()
        self.assertEqual(person.full_name, 'CONSUMIDOR FINAL')
        self.assertTrue(person.is_active)

    def test_reserved_queryset_edit_is_blocked(self):
        person = self.reserved()
        with self.assertRaises(ValidationError):
            Person.objects.filter(pk=person.pk).update(is_active=False)

    def test_reserved_delete_is_blocked(self):
        person = self.reserved()
        with self.assertRaises(ValidationError): person.delete()
        with self.assertRaises(ValidationError): Person.objects.filter(pk=person.pk).delete()
        self.assertTrue(Person.objects.filter(pk=person.pk).exists())

    def test_reserved_company_role_is_blocked(self):
        person = self.reserved()
        with self.assertRaises(ValidationError): Company.objects.create(person=person)

    def test_reserved_supplier_and_employee_roles_are_blocked(self):
        from people.models import Supplier, Employee
        person = self.reserved()
        with self.assertRaises(ValidationError): Supplier.objects.create(company=self.company, person=person)
        with self.assertRaises(ValidationError): Employee.objects.create(person=person)

    def test_detection_http_requires_company_and_permission(self):
        url = reverse('person_identification_detect')
        response = self.client.post(url, {'identification': '1719304188', 'manual': 'PASSPORT'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 'CEDULA')
        self.assertEqual(self.client.post(url, {'identification': '1719304189'}).status_code, 400)
        self.client.logout()
        self.assertEqual(self.client.post(url, {'identification': '1719304188'}).status_code, 302)

    def test_reserved_customer_is_company_scoped(self):
        from people.services import customer_maintenance
        from django.core.exceptions import ObjectDoesNotExist
        customer = enable_for_company(self.other)
        with self.assertRaises(ObjectDoesNotExist):
            customer_maintenance.get_relation(actor=self.user, company=self.company, relation_id=customer.pk)

    def test_form_does_not_require_manual_type(self):
        page = self.client.get(reverse('person_create'))
        self.assertEqual(page.status_code, 200)
        self.assertFalse(page.context['form'].fields['identification_type'].required)
        self.assertContains(page, 'data-identification-url')
        from people.tests import test_customer_ui_actions as actions
        data = actions.CustomerUIActionsTests.person_data(self)
        data.pop('identification_type')
        data['identification'] = '1719304188'
        self.assertEqual(self.client.post(reverse('person_create'), data).status_code, 302)
        person = Person.objects.get(identification='1719304188')
        self.assertEqual(person.identification_type, 'CEDULA')
        self.assertEqual(person.identification_kind.code, 'CEDULA')
