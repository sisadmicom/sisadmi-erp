from django.core.exceptions import ValidationError
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from people.models import Person, CompanyPersonAccess
from people.services import customer_maintenance
from people.tests import test_customer_ui_actions as actions


class CustomerPersonReplacementTests(TestCase):
    def setUp(self):
        actions.CustomerUIActionsTests.setUp(self)
        self.customer = actions.CustomerUIActionsTests.customer(self)
        self.replacement = Person.objects.create(person_type='NATURAL', identification_type='PASSPORT',
            identification='REPLACE-PERSON', full_name='Replacement person')
        CompanyPersonAccess.objects.create(company=self.company, person=self.replacement)
        self.url = reverse('customer_update', args=[self.customer.pk])

    def sale(self):
        from core.models import DocumentType
        from inventory.models import Warehouse
        from sales.models import Sale
        warehouse = Warehouse.objects.create(company=self.company, branch=self.branch, name='Replacement warehouse')
        return Sale.objects.create(company=self.company, branch=self.branch, customer=self.customer,
            warehouse=warehouse, document_type=DocumentType.objects.get(code=Sale.DOCUMENT_TYPE_CODE))

    def data(self):
        return {'person': self.replacement.pk, 'category': self.active.pk, 'notes': 'Edited', 'credit_limit': '12.34'}

    def test_edit_shows_person_selector_and_plus(self):
        page = self.client.get(self.url)
        self.assertContains(page, 'name="person"')
        self.assertContains(page, 'value="add:person"')
        self.assertEqual(page.context['form'].initial['person'], self.person.pk)

    def test_http_changes_person_without_documents(self):
        self.assertEqual(self.client.post(self.url, self.data()).status_code, 302)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.person_id, self.replacement.pk)
        self.assertEqual(self.customer.category_id, self.active.pk)

    def test_service_changes_person_without_documents(self):
        obj = customer_maintenance.update(actor=self.user, company=self.company,
            relation_id=self.customer.pk, data={'person': self.replacement})
        self.assertEqual(obj.person_id, self.replacement.pk)

    def test_document_blocks_http_and_preserves_history(self):
        sale = self.sale()
        page = self.client.post(self.url, self.data())
        self.assertContains(page, 'documentos asociados')
        self.assertEqual(page.context['form'].errors.as_data()['person'][0].code, 'person_has_documents')
        self.customer.refresh_from_db(); sale.refresh_from_db()
        self.assertEqual(self.customer.person_id, self.person.pk)
        self.assertEqual(sale.customer_id, self.customer.pk)
        self.assertEqual(self.customer.notes, '')

    def test_document_blocks_service_with_specific_error(self):
        self.sale()
        with self.assertRaises(ValidationError) as caught:
            customer_maintenance.update(actor=self.user, company=self.company,
                relation_id=self.customer.pk, data={'person': self.replacement.pk})
        self.assertEqual(caught.exception.error_dict['person'][0].code, 'person_has_documents')
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.person_id, self.person.pk)

    def test_unchanged_person_and_partial_edit_allowed_with_document(self):
        self.sale()
        customer_maintenance.update(actor=self.user, company=self.company,
            relation_id=self.customer.pk, data={'person': self.person.pk, 'notes': 'Same person'})
        customer_maintenance.update(actor=self.user, company=self.company,
            relation_id=self.customer.pk, data={'notes': 'Partial edit'})
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.person_id, self.person.pk)
        self.assertEqual(self.customer.notes, 'Partial edit')

    def test_document_added_after_form_open_blocks_save(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.sale()
        self.assertContains(self.client.post(self.url, self.data()), 'documentos asociados')
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.person_id, self.person.pk)

    def test_other_company_person_rejected(self):
        CompanyPersonAccess.objects.filter(company=self.company, person=self.replacement).delete()
        CompanyPersonAccess.objects.create(company=self.other, person=self.replacement)
        with self.assertRaises(ValidationError) as caught:
            customer_maintenance.update(actor=self.user, company=self.company,
                relation_id=self.customer.pk, data={'person': self.replacement.pk})
        self.assertEqual(caught.exception.error_dict['person'][0].code, 'identity_unavailable')
        self.assertEqual(self.client.post(self.url, self.data()).status_code, 200)

    def test_change_requires_permission(self):
        self.user.user_permissions.remove(Permission.objects.get(codename='change_customer'))
        self.assertEqual(self.client.post(self.url, self.data()).status_code, 403)

    def test_duplicate_person_rejected(self):
        customer_maintenance.create(actor=self.user, company=self.company, person_id=self.replacement.pk, data={})
        with self.assertRaises(ValidationError) as caught:
            customer_maintenance.update(actor=self.user, company=self.company,
                relation_id=self.customer.pk, data={'person': self.replacement.pk})
        self.assertEqual(caught.exception.error_dict['person'][0].code, 'duplicate_relationship')

    def test_plus_person_in_edit_returns_and_preserves_draft(self):
        child, token = actions.CustomerUIActionsTests.begin(self, 'person', self.customer.pk)
        data = actions.CustomerUIActionsTests.person_data(self)
        data['draft'] = token
        response = self.client.post(child, data)
        self.assertEqual(response.status_code, 302)
        page = self.client.get(response.url)
        new_person = Person.objects.get(identification='UIACT-PERSON')
        self.assertEqual(str(page.context['form'].initial['person']), str(new_person.pk))
        self.assertEqual(page.context['form'].initial['notes'], 'KEEP THIS DRAFT')
        posted = {'draft': token, 'person': new_person.pk, 'category': self.active.pk,
                  'notes': 'KEEP THIS DRAFT', 'credit_limit': '123.45'}
        self.assertEqual(self.client.post(self.url, posted).status_code, 302)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.person_id, new_person.pk)

    def test_plus_person_blocked_when_document_exists(self):
        self.sale()
        data = self.data(); data['related'] = 'add:person'
        self.assertContains(self.client.post(self.url, data), 'documentos asociados')
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.person_id, self.person.pk)
