"""Document lifecycle restrictions, through real services and HTTP."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction, IntegrityError
from django.test import TestCase
from django.urls import reverse
from people.models import Customer, CompanyPersonAccess, Person
from people.services import customer_maintenance
from sales.use_cases.confirm_sale import ConfirmSale
from people.tests.clientes013_support import CustomerDocumentFixture, business_snapshot


class CustomerDocumentRestrictionTests(CustomerDocumentFixture, TestCase):
    def check_document(self, status):
        sale = self.sale_in_state(status)
        before = business_snapshot()
        with self.assertRaises(ValidationError) as change:
            customer_maintenance.update(actor=self.actor, company=self.company,
                relation_id=self.customer.pk, data={'person': self.replacement.pk, 'notes': 'must rollback'})
        self.assertEqual(change.exception.error_dict['person'][0].code, 'person_has_documents')
        with self.assertRaises(ValidationError) as deletion:
            customer_maintenance.delete(actor=self.actor, company=self.company, relation_id=self.customer.pk)
        self.assertEqual(deletion.exception.code, 'customer_in_use')
        self.assertEqual(business_snapshot(), before)
        self.client.force_login(self.actor)
        session = self.client.session
        session.update({'company_id': self.company.pk, 'branch_id': self.branch.pk}); session.save()
        response = self.client.post(reverse('customer_update', args=[self.customer.pk]),
            {'person': self.replacement.pk, 'category': self.category.pk, 'credit_limit': '0', 'notes': 'must rollback'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].errors.as_data()['person'][0].code, 'person_has_documents')
        response = self.client.post(reverse('customer_delete', args=[self.customer.pk]), {'confirm': 'yes'})
        self.assertContains(response, 'registros relacionados')
        self.assertEqual(business_snapshot(), before)
        sale.refresh_from_db(); self.customer.refresh_from_db()
        self.assertEqual(self.customer.person_id, self.original.pk)
        self.assertEqual(sale.customer_id, self.customer.pk)

    def test_draft_blocks_replacement_and_deletion(self): self.check_document('DRAFT')
    def test_confirmed_blocks_replacement_and_deletion(self): self.check_document('CONFIRMED')
    def test_cancelled_blocks_replacement_and_deletion(self): self.check_document('CANCELLED')

    def test_commercial_edit_allowed_for_all_document_states(self):
        sale = self.sale()
        for status in ['DRAFT', 'CONFIRMED', 'CANCELLED']:
            if status == 'CONFIRMED':
                ConfirmSale.execute(sale.pk, user=self.actor)
            if status == 'CANCELLED':
                from sales.use_cases.cancel_sale import CancelSale
                CancelSale.execute(sale.pk, user=self.actor)
            customer_maintenance.update(actor=self.actor, company=self.company, relation_id=self.customer.pk,
                data={'person': self.original.pk, 'notes': status, 'credit_limit': '15.00'})
            self.customer.refresh_from_db(); sale.refresh_from_db()
            self.assertEqual(self.customer.notes, status)
            self.assertEqual(self.customer.person_id, self.original.pk)
            self.assertEqual(sale.status, status)

    def test_foreign_company_customer_is_unavailable(self):
        before = business_snapshot()
        from django.core.exceptions import ObjectDoesNotExist
        for op in ['get_relation', 'delete']:
            with self.assertRaises(PermissionDenied):
                getattr(customer_maintenance, op)(actor=self.actor, company=self.other, relation_id=self.customer.pk)
        self.actor.profile.companies.add(self.other)
        with self.assertRaises(ObjectDoesNotExist):
            customer_maintenance.delete(actor=self.actor, company=self.other, relation_id=self.customer.pk)
        self.assertEqual(business_snapshot(), before)

    def test_foreign_replacement_person_rejected(self):
        CompanyPersonAccess.objects.filter(company=self.company, person=self.replacement).delete()
        CompanyPersonAccess.objects.create(company=self.other, person=self.replacement)
        before = business_snapshot()
        with self.assertRaises(ValidationError) as error:
            customer_maintenance.update(actor=self.actor, company=self.company,
                relation_id=self.customer.pk, data={'person': self.replacement.pk})
        self.assertEqual(error.exception.error_dict['person'][0].code, 'identity_unavailable')
        self.assertEqual(business_snapshot(), before)

    def test_inactive_person_does_not_block_sale_creation_or_confirmation(self):
        self.original.is_active = False; self.original.save(update_fields=['is_active'])
        people = list(Person.objects.order_by('pk').values())
        self.assertFalse(customer_maintenance.list_relations(actor=self.actor, company=self.company,
            include_inactive=True).filter(pk=self.customer.pk).exists())
        sale = self.sale(); ConfirmSale.execute(sale.pk, user=self.actor)
        sale.refresh_from_db(); self.assertEqual(sale.status, 'CONFIRMED')
        self.assertEqual(list(Person.objects.order_by('pk').values()), people)

    def test_revoked_access_does_not_block_sale_or_recreate_access(self):
        CompanyPersonAccess.objects.filter(company=self.company, person=self.original).delete()
        before = list(CompanyPersonAccess.objects.order_by('pk').values())
        self.assertFalse(customer_maintenance.list_relations(actor=self.actor, company=self.company,
            include_inactive=True).filter(pk=self.customer.pk).exists())
        sale = self.sale(); ConfirmSale.execute(sale.pk, user=self.actor)
        self.assertEqual(list(CompanyPersonAccess.objects.order_by('pk').values()), before)
        sale.refresh_from_db(); self.assertEqual(sale.status, 'CONFIRMED')

    def test_postgresql_fk_prevents_raw_customer_delete(self):
        self.sale()
        with connection.cursor() as cursor:
            cursor.execute("SELECT conname FROM pg_constraint WHERE conrelid='sales_sale'::regclass AND confrelid='people_customer'::regclass AND contype='f'")
            constraints = cursor.fetchall()
        self.assertEqual(len(constraints), 1)
        with self.assertRaises(IntegrityError) as error:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('DELETE FROM people_customer WHERE id=%s', [self.customer.pk])
                    cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
        self.assertEqual(error.exception.__cause__.sqlstate, '23503')
        self.assertEqual(error.exception.__cause__.diag.table_name, 'sales_sale')
        self.assertEqual(error.exception.__cause__.diag.constraint_name, constraints[0][0])
        self.assertTrue(Customer.objects.filter(pk=self.customer.pk).exists())

    def check_unavailable_current_person(self, *, deactivate=False):
        customer_maintenance.update(actor=self.actor, company=self.company,
            relation_id=self.customer.pk, data={'person': self.replacement.pk})
        if deactivate:
            self.replacement.is_active = False
            self.replacement.save(update_fields=['is_active'])
        else:
            CompanyPersonAccess.objects.filter(company=self.company, person=self.replacement).delete()
        before = business_snapshot()
        from django.core.exceptions import ObjectDoesNotExist
        operations = [
            lambda: customer_maintenance.update(actor=self.actor, company=self.company,
                relation_id=self.customer.pk, data={'notes': 'not permitted'}),
            lambda: customer_maintenance.update(actor=self.actor, company=self.company,
                relation_id=self.customer.pk, data={'person': self.original.pk}),
            lambda: customer_maintenance.set_active(actor=self.actor, company=self.company,
                relation_id=self.customer.pk, is_active=False),
            lambda: customer_maintenance.delete(actor=self.actor, company=self.company,
                relation_id=self.customer.pk),
        ]
        for operation in operations:
            with self.assertRaises(ObjectDoesNotExist) as error:
                operation()
            self.assertEqual(str(error.exception), 'Commercial relationship unavailable.')
            self.assertEqual(business_snapshot(), before)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.person_id, self.replacement.pk)

    def test_revoked_replacement_access_blocks_all_customer_mutations(self):
        self.check_unavailable_current_person()

    def test_inactive_replacement_blocks_all_customer_mutations(self):
        self.check_unavailable_current_person(deactivate=True)

    def test_missing_delete_permission_rejects_before_customer_lock(self):
        from django.contrib.auth import get_user_model
        from django.test.utils import CaptureQueriesContext
        self.actor.is_superuser = False
        self.actor.save(update_fields=['is_superuser'])
        actor = get_user_model().objects.get(pk=self.actor.pk)
        before = business_snapshot()
        with CaptureQueriesContext(connection) as queries:
            with self.assertRaises(PermissionDenied):
                customer_maintenance.delete(actor=actor, company=self.company,
                    relation_id=self.customer.pk)
        self.assertFalse(any('FOR UPDATE' in item['sql'].upper() for item in queries))
        self.assertEqual(business_snapshot(), before)
