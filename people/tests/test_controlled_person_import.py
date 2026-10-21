"""Hermetic authorization fixtures; real PostgreSQL, TestCase rollback, no flush."""
import csv
import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, IntegrityError
from django.test import TestCase
from django.urls import reverse

from core.models import Branch, Company
from people.models import CompanyPersonAccess, Customer, IdentificationKind, Person
from people.services import controlled_person_import as importer
from people.services import person_access_policy as policy


class ControlledPersonImportTests(TestCase):
    def setUp(self):
        self.audit_model = importer._audit_model()
        self.directory = TemporaryDirectory(prefix='person-import-tests-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.actor = get_user_model().objects.create_superuser('controlled-import-actor', '', None)
        self.company = Company.objects.create(person=Person.objects.create(identification='IMPORT-TARGET-ENTITY',
            person_type='LEGAL', full_name='CONTROLLED-IMPORT-TARGET'))
        self.other = Company.objects.create(person=Person.objects.create(identification='IMPORT-OTHER-ENTITY',
            person_type='LEGAL', full_name='CONTROLLED-IMPORT-OTHER'))
        self.branch = Branch.objects.create(company=self.company, code='IMP', name='Import fixture')
        self.actor.profile.companies.add(self.company)
        self.actor.profile.branches.add(self.branch)
        source = self.root/'source.txt'; manifest = self.root/'manifest.json'
        all_rows = []; raw_lines = []
        kinds = {k.code: k.pk for k in IdentificationKind.objects.all()}
        for index in range(1,101):
            base = f'170{index:06d}'
            total = sum((n-9 if n>9 else n) for n in [int(c)*(2 if i%2==0 else 1) for i,c in enumerate(base)])
            identity = base + str((-total)%10)
            if index==49: identity='1761234567001'
            if index>49: identity=f'EXCLUDED-{index}'
            fields=['']*35;fields[0]=str(index);fields[2]=fields[6]=f'Import fixture {index:03}';fields[5]=identity
            from io import StringIO
            stream=StringIO();csv.writer(stream,delimiter=',',quotechar="'",quoting=csv.QUOTE_ALL,lineterminator='').writerow(fields)
            line=stream.getvalue();raw_lines.append(line)
            kind='RUC' if index==49 else 'CEDULA'
            all_rows.append({'linea':index,'identificador_original':str(index),'identificacion':identity,
                'nombre_columna_3':fields[2],'nombre_columna_7':fields[6],'nombre_propuesto':fields[2],
                'tipo_detectado':kind,'person_type_propuesto':'LEGAL' if index==49 else 'NATURAL',
                'sha256_linea':importer.digest(line.encode()),'company_id_verificada':self.company.pk,
                'resultado_cruce':'PERSONA_NUEVA_ASOCIACION_NUEVA',
                'identification_kind_id_propuesto':kinds[kind], 'accion_propuesta':'CREAR' if index<=49 else 'OMITIR'})
        source.write_text('\n'.join(raw_lines)+'\n')
        manifest.write_text(json.dumps({'resumen':{'source_sha256':importer.digest(source.read_bytes())},'filas':all_rows}))
        self.spec=importer.Authorization(source=source,manifest=manifest,source_sha256=importer.digest(source.read_bytes()),
            manifest_sha256=importer.digest(manifest.read_bytes()),validator_sha256=importer.APPROVED.validator_sha256,
            company_id=self.company.pk,company_name='CONTROLLED-IMPORT-TARGET')
        self.rows=all_rows[:49]

    def execute(self):return importer._execute(actor=self.actor,spec=self.spec)

    def imported(self):return Person.objects.filter(identification__in=[r['identificacion'] for r in self.rows])

    def test_exact_batch_without_customers_contacts_geography_or_other_company_access(self):
        customers=Customer.objects.count();result=self.execute()
        self.assertEqual((result['created_persons'],result['created_accesses'],result['created_audits']),(49,49,49))
        self.assertEqual(Customer.objects.count(),customers)
        self.assertEqual(Counter(self.imported().values_list('person_type',flat=True)),{'NATURAL':48,'LEGAL':1})
        self.assertEqual(CompanyPersonAccess.objects.filter(company=self.company,person__in=self.imported()).count(),49)
        self.assertFalse(CompanyPersonAccess.objects.filter(company=self.other,person__in=self.imported()).exists())
        self.assertFalse(Person.objects.filter(identification__startswith='EXCLUDED-').exists())
        for person in self.imported():
            self.assertIsNone(person.email);self.assertEqual(person.phone,'');self.assertEqual(person.address,'')
            self.assertTrue(all(getattr(person,name+'_id') is None for name in ['country','province','canton','parish']))
        for log in self.audit_model.objects.filter(action=importer.ACTION,detail__batch_manifest_sha256=self.spec.manifest_sha256):
            row=self.rows[log.detail['line']-1]
            self.assertEqual(log.detail['source_id'],row['identificador_original'])
            self.assertEqual(log.detail['identification'],row['identificacion'])
            self.assertEqual(log.detail['source_sha256'],self.spec.source_sha256)
            self.assertEqual(log.executed_by_id,self.actor.pk)

    def test_second_execution_is_read_only_noop(self):
        first=self.execute();counts=(Person.objects.count(),CompanyPersonAccess.objects.count(),self.audit_model.objects.count())
        second=self.execute()
        self.assertEqual(second['status'],'ALREADY_IMPORTED')
        self.assertEqual(second['created_persons'],0)
        self.assertEqual(set(first['person_ids']),set(second['person_ids']))
        self.assertEqual(counts,(Person.objects.count(),CompanyPersonAccess.objects.count(),self.audit_model.objects.count()))

    def test_source_hash_change_blocks_without_writes(self):
        self.spec.source.write_text(self.spec.source.read_text()+'\n')
        with self.assertRaises(ValidationError):self.execute()
        self.assertFalse(self.imported().exists())

    def test_manifest_hash_change_blocks_without_writes(self):
        self.spec.manifest.write_text(self.spec.manifest.read_text()+' ')
        with self.assertRaises(ValidationError):self.execute()
        self.assertFalse(self.imported().exists())

    def test_unauthorized_extra_row_is_rejected(self):
        data=json.loads(self.spec.manifest.read_text());data['filas'][49]['accion_propuesta']='CREAR'
        self.spec.manifest.write_text(json.dumps(data));self.spec=replace(self.spec,manifest_sha256=importer.digest(self.spec.manifest.read_bytes()))
        with self.assertRaises(ValidationError):self.execute()
        self.assertFalse(self.imported().exists())

    def test_existing_person_requires_new_review_no_association(self):
        row=self.rows[0];person=Person.objects.create(identification=row['identificacion'],person_type='NATURAL',full_name='Unrelated existing person')
        CompanyPersonAccess.objects.create(company=self.other,person=person)
        with self.assertRaises(ValidationError):self.execute()
        person.refresh_from_db();self.assertEqual(person.full_name,'Unrelated existing person')
        self.assertFalse(CompanyPersonAccess.objects.filter(company=self.company,person=person).exists())
        self.assertEqual(self.imported().count(),1)

    def test_mid_batch_audit_failure_rolls_back_everything(self):
        original=self.audit_model.objects.create;calls=[]
        def failing(*args,**kwargs):
            calls.append(1)
            if len(calls)==3:raise IntegrityError('Simulated audit write failure')
            return original(*args,**kwargs)
        before=self.audit_model.objects.count()
        with patch.object(self.audit_model.objects,'create',side_effect=failing):
            with self.assertRaises(IntegrityError):self.execute()
        self.assertEqual(len(calls),3);self.assertFalse(self.imported().exists())
        self.assertEqual(self.audit_model.objects.count(),before)

    def test_simulated_identity_collision_rolls_back_prior_rows(self):
        original=policy.create_person;calls=[]
        def racing(**kwargs):
            calls.append(1)
            if len(calls)==3:raise policy.IdentityUnavailable
            return original(**kwargs)
        before=self.audit_model.objects.count()
        with patch.object(policy,'create_person',side_effect=racing):
            with self.assertRaises(policy.IdentityUnavailable):self.execute()
        self.assertFalse(self.imported().exists());self.assertEqual(self.audit_model.objects.count(),before)

    def test_company_membership_and_audit_permissions_required(self):
        self.actor.profile.companies.remove(self.company)
        with self.assertRaises(PermissionDenied):self.execute()
        self.assertFalse(self.imported().exists())

    def test_test_only_guard_rejects_forbidden_database_without_query(self):
        with patch.dict(connection.settings_dict,{'NAME':'sisadmi_erp_dev'}):
            with self.assertNumQueries(0):
                with self.assertRaises(ValidationError):self.execute()

    def test_imported_people_remain_immutable(self):
        self.execute();person=self.imported().first();person.identification_type='PASSPORT'
        with self.assertRaises(ValidationError):person.save()

    def test_browser_search_and_customer_selector_without_creating_customer(self):
        self.execute();row=self.rows[0];customers=Customer.objects.count()
        self.client.force_login(self.actor);session=self.client.session
        session.update({'company_id': self.company.pk, 'branch_id': self.branch.pk})
        session.save()
        response=self.client.get(reverse('person_list'),{'q':row['identificacion']})
        self.assertContains(response,row['nombre_propuesto'])
        response=self.client.get(reverse('customer_create'))
        field=response.context['form'].fields['person']
        person=self.imported().get(identification=row['identificacion'])
        self.assertEqual(field.clean(str(person.pk)).pk,person.pk)
        self.assertEqual(field.queryset.filter(pk__in=self.imported().values('pk')).count(),49)
        self.assertEqual(Customer.objects.count(),customers)
