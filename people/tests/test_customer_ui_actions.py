from urllib.parse import urlsplit, parse_qs

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase
from django.urls import reverse

from people.models import Customer, Person, CustomerCategory, CompanyPersonAccess
from people.models.geography import Continent, Country, Province, Canton, Parish
from people.tests import test_customer_category_assignment as category_tests


class CustomerUIActionsTests(TestCase):
    def setUp(self):
        category_tests.CustomerCategoryAssignmentTests.setUp(self)
        self.user.user_permissions.add(*Permission.objects.filter(codename__in=[
            'delete_customer', 'add_person', 'add_customercategory',
        ], content_type__app_label='people'))

    def customer(self):
        from people.services import customer_maintenance
        return customer_maintenance.create(actor=self.user, company=self.company,
            person_id=self.person.pk, data={'category': self.active})

    def begin(self, field, pk=None):
        url = reverse('customer_update', args=[pk]) if pk else reverse('customer_create')
        data = {'person': self.person.pk, 'category': self.active.pk,
                'credit_limit': '123.45', 'notes': 'KEEP THIS DRAFT', 'related': 'add:' + field}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        token = parse_qs(urlsplit(response.url).query)['draft'][0]
        return response.url, token

    def person_data(self):
        continent = Continent.objects.create(name='UI actions continent')
        country = Country.objects.create(continent=continent, code='UIACT', name='UI actions country')
        province = Province.objects.create(country=country, name='Province')
        canton = Canton.objects.create(province=province, name='Canton')
        parish = Parish.objects.create(canton=canton, name='Parish')
        return {'person_type': 'NATURAL', 'identification_type': 'PASSPORT',
            'identification': 'UIACT-PERSON', 'full_name': 'New related person',
            'email': '', 'phone': '', 'address': 'Test address',
            'continent': continent.pk, 'country': country.pk, 'province': province.pk,
            'canton': canton.pk, 'parish': parish.pk}

    def test_list_exposes_add_edit_and_delete_directly(self):
        customer = self.customer()
        page = self.client.get(reverse('customer_list'))
        self.assertContains(page, reverse('customer_create'))
        self.assertContains(page, reverse('customer_update', args=[customer.pk]))
        self.assertContains(page, reverse('customer_delete', args=[customer.pk]))
        self.assertContains(page, 'Borrar')

    def test_delete_requires_confirmation_and_keeps_person_and_category(self):
        customer = self.customer()
        pk = customer.pk
        url = reverse('customer_delete', args=[pk])
        self.assertContains(self.client.get(url), 'Confirmar borrado')
        self.assertTrue(Customer.objects.filter(pk=pk).exists())
        self.assertEqual(self.client.post(url).status_code, 200)
        self.assertTrue(Customer.objects.filter(pk=pk).exists())
        self.assertRedirects(self.client.post(url, {'confirm': 'yes'}), reverse('customer_list'))
        self.assertFalse(Customer.objects.filter(pk=pk).exists())
        self.assertTrue(Person.objects.filter(pk=self.person.pk).exists())
        self.assertTrue(CustomerCategory.objects.filter(pk=self.active.pk).exists())

    def test_cancel_does_not_delete(self):
        customer = self.customer()
        self.assertRedirects(self.client.post(reverse('customer_delete', args=[customer.pk]),
                                             {'action': 'cancel'}), reverse('customer_list'))
        self.assertTrue(Customer.objects.filter(pk=customer.pk).exists())

    def test_documents_block_customer_deletion_without_cascades(self):
        from core.models import DocumentType
        from inventory.models import Warehouse
        from sales.models import Sale
        customer = self.customer()
        warehouse = Warehouse.objects.create(company=self.company, branch=self.branch, name='UI action warehouse')
        sale = Sale.objects.create(company=self.company, branch=self.branch, customer=customer,
            warehouse=warehouse, document_type=DocumentType.objects.get(code=Sale.DOCUMENT_TYPE_CODE))
        page = self.client.post(reverse('customer_delete', args=[customer.pk]), {'confirm': 'yes'})
        self.assertContains(page, 'registros relacionados')
        self.assertTrue(Customer.objects.filter(pk=customer.pk).exists())
        self.assertTrue(Sale.objects.filter(pk=sale.pk).exists())

    def test_generic_references_also_block_deletion(self):
        from sri.models import ElectronicDocument
        customer = self.customer()
        document = ElectronicDocument.objects.create(company=self.company, branch=self.branch,
            content_type=ContentType.objects.get_for_model(Customer), object_id=customer.pk,
            document_type='01', establishment='001', emission_point='001', sequential='000000001',
            numeric_code='12345678', access_key='7' * 49)
        page = self.client.post(reverse('customer_delete', args=[customer.pk]), {'confirm': 'yes'})
        self.assertContains(page, 'registros relacionados')
        self.assertTrue(Customer.objects.filter(pk=customer.pk).exists())
        self.assertTrue(ElectronicDocument.objects.filter(pk=document.pk).exists())

    def test_delete_requires_permission_and_is_company_scoped(self):
        customer = self.customer()
        self.user.user_permissions.remove(Permission.objects.get(codename='delete_customer'))
        self.assertEqual(self.client.post(reverse('customer_delete', args=[customer.pk]), {'confirm': 'yes'}).status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(codename='delete_customer'))
        foreign = Customer.objects.create(company=self.other, person=self.person)
        self.assertEqual(self.client.post(reverse('customer_delete', args=[foreign.pk]), {'confirm': 'yes'}).status_code, 404)
        self.assertTrue(Customer.objects.filter(pk=foreign.pk).exists())

    def test_delete_and_related_actions_require_csrf(self):
        customer = self.customer()
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.user)
        session = browser.session
        session.update({'company_id': self.company.pk, 'branch_id': self.branch.pk})
        session.save()
        self.assertEqual(browser.post(reverse('customer_delete', args=[customer.pk]), {'confirm': 'yes'}).status_code, 403)
        self.assertEqual(browser.post(reverse('customer_create'), {'related': 'add:person'}).status_code, 403)

    def test_person_plus_creates_selects_and_preserves_parent_data(self):
        child, token = self.begin('person')
        self.assertContains(self.client.get(child), 'Guardar persona')
        response = self.client.post(child, self.person_data() | {'draft': token})
        self.assertEqual(response.status_code, 302)
        person = Person.objects.get(identification='UIACT-PERSON')
        self.assertTrue(CompanyPersonAccess.objects.filter(company=self.company, person=person).exists())
        page = self.client.get(response.url)
        self.assertContains(page, 'KEEP THIS DRAFT')
        self.assertEqual(str(page.context['form']['person'].value()), str(person.pk))
        self.assertEqual(str(page.context['form']['category'].value()), str(self.active.pk))
        self.assertEqual(str(page.context['form']['credit_limit'].value()), '123.45')
        parent_token = parse_qs(urlsplit(response.url).query)['draft'][0]
        saved = self.client.post(reverse('customer_create'), {
            'draft': parent_token, 'person': person.pk, 'category': self.active.pk,
            'credit_limit': '123.45', 'notes': 'KEEP THIS DRAFT',
        })
        self.assertEqual(saved.status_code, 302)
        self.assertTrue(Customer.objects.filter(company=self.company, person=person,
                                               category=self.active, notes='KEEP THIS DRAFT').exists())

    def test_person_creation_can_be_cancelled_without_losing_draft(self):
        child, token = self.begin('person')
        response = self.client.post(child, {'draft': token, 'action': 'cancel'})
        self.assertEqual(response.status_code, 302)
        page = self.client.get(response.url)
        self.assertContains(page, 'KEEP THIS DRAFT')
        self.assertEqual(str(page.context['form']['person'].value()), str(self.person.pk))

    def test_plus_bypasses_required_validation_and_preserves_incomplete_values(self):
        response = self.client.post(reverse('customer_create'), {
            'related': 'add:person', 'person': '', 'credit_limit': 'not-a-number', 'notes': 'INCOMPLETE',
        })
        self.assertEqual(response.status_code, 302)
        token = parse_qs(urlsplit(response.url).query)['draft'][0]
        back = self.client.post(response.url, {'draft': token, 'action': 'cancel'})
        page = self.client.get(back.url)
        self.assertEqual(page.context['form']['credit_limit'].value(), 'not-a-number')
        self.assertContains(page, 'INCOMPLETE')

    def test_category_plus_returns_to_customer_creation_and_editing(self):
        customer = self.customer()
        for pk in (None, customer.pk):
            with self.subTest(editing=pk is not None):
                child, token = self.begin('category', pk)
                response = self.client.post(child, {'draft': token, 'code': 'EDIT' if pk else 'ADD', 'name': 'Related category'})
                self.assertEqual(response.status_code, 302)
                category = CustomerCategory.objects.get(company=self.company, code='EDIT' if pk else 'ADD')
                page = self.client.get(response.url)
                self.assertContains(page, 'KEEP THIS DRAFT')
                self.assertEqual(str(page.context['form']['category'].value()), str(category.pk))

    def test_child_permissions_and_tokens_cannot_be_bypassed(self):
        child, token = self.begin('person')
        browser = Client();browser.force_login(self.user)
        session = browser.session;session.update({'company_id': self.company.pk, 'branch_id': self.branch.pk});session.save()
        self.assertEqual(browser.get(child).status_code, 403)
        self.user.user_permissions.remove(Permission.objects.get(codename='add_person'))
        self.assertEqual(self.client.get(child).status_code, 403)
        self.assertEqual(self.client.post(reverse('customer_create'), {'related': 'add:person'}).status_code, 403)

    def test_new_category_return_replaces_inactive_initial_selection(self):
        customer = self.customer()
        self.active.is_active = False
        self.active.save(update_fields=['is_active'])
        child, token = self.begin('category', customer.pk)
        response = self.client.post(child, {'draft': token, 'code': 'REPLACE', 'name': 'New active category'})
        self.assertEqual(response.status_code, 302)
        category = CustomerCategory.objects.get(company=self.company, code='REPLACE')
        page = self.client.get(response.url)
        self.assertEqual(str(page.context['form']['category'].value()), str(category.pk))

    def test_cross_company_and_forged_field_continuations_are_rejected(self):
        child, token = self.begin('category')
        self.assertEqual(self.client.get(reverse('person_create') + '?draft=' + token).status_code, 403)
        session = self.client.session;session.update({'company_id': self.other.pk, 'branch_id': None});session.save()
        self.assertEqual(self.client.get(child).status_code, 403)

    def test_replayed_person_submission_does_not_create_a_second_person(self):
        child, token = self.begin('person')
        data = self.person_data() | {'draft': token}
        self.assertEqual(self.client.post(child, data).status_code, 302)
        self.assertEqual(self.client.post(child, data).status_code, 403)
        self.assertEqual(Person.objects.filter(identification='UIACT-PERSON').count(), 1)

    def test_nested_location_creation_preserves_person_and_customer_returns(self):
        self.user.user_permissions.add(Permission.objects.get(codename='add_country'))
        child, token = self.begin('person')
        data = self.person_data()
        related = self.client.post(child, data | {'draft': token, 'related': 'add:country'})
        self.assertEqual(related.status_code, 302)
        location_token = parse_qs(urlsplit(related.url).query)['draft'][0]
        result = self.client.post(related.url, {
            'draft': location_token, 'continent': data['continent'], 'code': 'UACT2', 'name': 'New location',
        })
        self.assertEqual(result.status_code, 302)
        page = self.client.get(result.url)
        self.assertContains(page, 'UIACT-PERSON')
        back = self.client.post(result.url, {'draft': location_token, 'action': 'cancel'})
        self.assertEqual(back.status_code, 302)
        self.assertContains(self.client.get(back.url), 'KEEP THIS DRAFT')
