"""PostgreSQL tests: no flush; test rows and temporary DDL roll back."""
from importlib import import_module
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from people.models import Person, IdentificationKind
from people.services import person_access_policy as policy
from people.tests import test_customer_category_assignment as categories
from people.tests import test_customer_ui_actions as actions


class PersonIdentityImmutabilityTests(TestCase):
    def setUp(self):
        categories.CustomerCategoryAssignmentTests.setUp(self)
        self.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='people',
            codename__in=['add_person', 'change_person']))
        self.person = Person.objects.create(identification='1719304188', person_type='NATURAL', full_name='Identity immutable')
        from people.models import CompanyPersonAccess
        CompanyPersonAccess.objects.create(company=self.company, person=self.person)
        CompanyPersonAccess.objects.get_or_create(company=self.company, person=self.company.person)

    def sql_error(self, statement, params, constraint):
        with self.assertRaises(IntegrityError) as caught:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(statement, params)
        self.assertEqual(caught.exception.__cause__.sqlstate, '23514')
        self.assertEqual(caught.exception.__cause__.diag.constraint_name, constraint)
        self.assertNotIn(self.person.identification, str(caught.exception))

    def test_create_valid_identity(self):
        self.assertEqual(self.person.identification_type, 'CEDULA')
        self.assertEqual(self.person.identification_kind.code, 'CEDULA')

    def test_model_rejects_all_three_fields(self):
        for name, value in [('identification', '1713328506'), ('identification_type', 'PASSPORT'),
                            ('identification_kind_id', IdentificationKind.objects.get(code='PASSPORT').pk)]:
            with self.subTest(field=name):
                self.person.refresh_from_db(); setattr(self.person, name, value)
                with self.assertRaises(ValidationError) as caught:
                    self.person.save()
                self.assertEqual(caught.exception.code, 'immutable_person_identity')
        self.person.refresh_from_db()
        self.assertEqual(self.person.identification, '1719304188')

    def test_service_rejects_identity_change(self):
        with self.assertRaises(ValidationError) as caught:
            policy.update_person(actor=self.user, company=self.company, person_id=self.person.pk,
                                 data={'identification_type': 'PASSPORT'})
        self.assertEqual(caught.exception.code, 'immutable_person_identity')

    def test_service_allows_descriptive_edits(self):
        person = policy.update_person(actor=self.user, company=self.company, person_id=self.person.pk,
            data={'full_name': 'Updated name', 'address': 'Updated address', 'email': 'changed@example.invalid', 'phone': '123'})
        self.assertEqual(person.full_name, 'Updated name')
        self.assertEqual(person.identification, '1719304188')

    def test_sql_rejects_all_identity_fields_and_rolls_back(self):
        changes = [('identification', '1713328506'), ('identification_type', 'PASSPORT'),
                   ('identification_kind_id', IdentificationKind.objects.get(code='PASSPORT').pk)]
        for column, value in changes:
            with self.subTest(column=column):
                self.sql_error(f'UPDATE people_person SET {column}=%s, full_name=%s WHERE id=%s',
                    [value, 'Must roll back', self.person.pk], 'people_person_identity_immutable')
        self.person.refresh_from_db()
        self.assertEqual(self.person.full_name, 'Identity immutable')

    def test_same_values_permitted_by_sql_and_model(self):
        with connection.cursor() as cursor:
            cursor.execute('UPDATE people_person SET identification=identification, identification_type=identification_type, identification_kind_id=identification_kind_id WHERE id=%s', [self.person.pk])
        self.person.save()
        self.person.refresh_from_db()
        self.assertEqual(self.person.identification_type, 'CEDULA')

    def test_queryset_rejects_real_change_and_accepts_same_value(self):
        self.sql_error('UPDATE people_person SET identification_type=%s WHERE id=%s', ['OTHER', self.person.pk], 'people_person_identity_immutable')
        self.assertEqual(Person.objects.filter(pk=self.person.pk).update(identification=self.person.identification), 1)

    def test_sql_insert_rejects_mismatching_catalog(self):
        kind = IdentificationKind.objects.get(code='PASSPORT')
        self.sql_error('INSERT INTO people_person (created_at,updated_at,is_active,identification,identification_type,identification_kind_id,person_type,full_name,phone,address) VALUES (NOW(),NOW(),true,%s,%s,%s,%s,%s,%s,%s)',
            ['1713328506', 'CEDULA', kind.pk, 'NATURAL', 'Not inserted', '', ''], 'people_person_identity_coherent')
        self.assertFalse(Person.objects.filter(identification='1713328506').exists())

    def test_model_insert_rejects_mismatching_catalog(self):
        with self.assertRaises(ValidationError) as caught:
            Person.objects.create(identification='1713328506', identification_kind=IdentificationKind.objects.get(code='PASSPORT'),
                                  person_type='NATURAL', full_name='Wrong classification')
        self.assertEqual(caught.exception.code, 'incoherent_person_identity')

    def test_catalog_code_immutable_in_model_and_sql(self):
        kind = IdentificationKind.objects.get(code='CEDULA')
        kind.code = 'CHANGED'
        with self.assertRaises(ValidationError): kind.save()
        self.sql_error('UPDATE people_identificationkind SET code=%s WHERE id=%s', ['CHANGED', kind.pk],
                       'people_identification_kind_code_immutable')
        with connection.cursor() as cursor:
            cursor.execute('UPDATE people_identificationkind SET code=code WHERE id=%s', [kind.pk])

    def payload(self):
        data = actions.CustomerUIActionsTests.person_data(self)
        data.update(identification=self.person.identification, identification_type='CEDULA', full_name='Editable name')
        return data

    def test_http_identity_read_only_and_forgery_rejected(self):
        url = reverse('person_update', args=[self.person.pk])
        page = self.client.get(url)
        self.assertTrue(page.context['form'].fields['identification'].disabled)
        self.assertTrue(page.context['form'].fields['identification_type'].disabled)
        data = self.payload(); data['identification'] = '1713328506'
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].errors.as_data()['identification'][0].code, 'immutable_person_identity')
        self.person.refresh_from_db()
        self.assertEqual(self.person.identification, '1719304188')

    def test_superuser_http_cannot_change_type_or_catalog(self):
        self.user.is_superuser = True; self.user.save(update_fields=['is_superuser'])
        data = self.payload(); data['identification_type'] = 'PASSPORT'
        url = reverse('person_update', args=[self.person.pk])
        self.assertEqual(self.client.post(url, data).status_code, 200)
        data['identification_type'] = 'CEDULA'
        data['identification_kind_id'] = IdentificationKind.objects.get(code='PASSPORT').pk
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].non_field_errors())
        self.person.refresh_from_db(); self.assertEqual(self.person.identification_type, 'CEDULA')

    def test_customer_person_descriptive_fields_and_location_editable(self):
        from people.models import Customer
        Customer.objects.create(company=self.company, person=self.person)
        data = self.payload(); data.pop('identification'); data.pop('identification_type')
        response = self.client.post(reverse('person_update', args=[self.person.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.person.refresh_from_db()
        self.assertEqual(self.person.full_name, 'Editable name')
        self.assertEqual(self.person.parish_id, data['parish'])

    def test_company_person_descriptive_edit_allowed(self):
        person = self.company.person
        policy.update_person(actor=self.user, company=self.company, person_id=person.pk, data={'full_name':'Company description'})
        person.refresh_from_db();self.assertEqual(person.full_name,'Company description')

    def test_company_scope_preserved(self):
        with self.assertRaises(policy.IdentityUnavailable):
            policy.update_person(actor=self.user, company=self.company, person_id=self.other.person_id, data={'full_name':'Forbidden'})

    def test_reserved_sql_update_and_delete_are_blocked(self):
        person = Person.objects.get(identification='9999999999999')
        self.sql_error('UPDATE people_person SET full_name=%s WHERE id=%s', ['Forbidden', person.pk], 'people_person_reserved_protected')
        self.sql_error('DELETE FROM people_person WHERE id=%s', [person.pk], 'people_person_reserved_protected')

    def test_reversible_install_preserves_legacy_nulls(self):
        migration = import_module('people.migrations.0011_person_identity_immutable')
        # Explicit transactional migration reversal simulates a row predating protection.
        # No runtime exemption or flag is introduced; the DDL and row roll back.
        with connection.cursor() as cursor:
            cursor.execute(migration.REVERSE_SQL)
            cursor.execute('INSERT INTO people_person (created_at,updated_at,is_active,identification,person_type,full_name,phone,address) VALUES (NOW(),NOW(),true,%s,%s,%s,%s,%s) RETURNING id', ['LEGACY-IMMUTABLE','NATURAL','Legacy','',''])
            pk = cursor.fetchone()[0]
            cursor.execute(migration.FORWARD_SQL)
        person = Person.objects.get(pk=pk)
        person.full_name='Updated legacy';person.save(update_fields=['full_name'])
        person.refresh_from_db()
        self.assertIsNone(person.identification_type);self.assertIsNone(person.identification_kind_id)
        self.sql_error('UPDATE people_person SET identification_type=%s WHERE id=%s', ['OTHER',pk], 'people_person_identity_immutable')
