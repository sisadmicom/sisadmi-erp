"""CAT-02.3 FASE 3: integración web RED, sin implementación web.

Convención ratificada FASE 3.2 (rutas todavía inexistentes):
/people/{customers,suppliers}/, new/, <pk>/, <pk>/edit/,
<pk>/deactivate/ y <pk>/reactivate/; nombres {customer,supplier}_
{list,create,detail,update,deactivate,reactivate}, sin namespace.
Person inspira q, POST/redirect/detail, form/context y errores HTTP 200;
403 autorización, 404 relación inaccesible, 405 GET de actividad, CSRF 403.
include_inactive=1 solicita inactivos; campo Person del alta: person.
No fija nombres de Forms/Views/templates ni texto exacto de mensajes nuevos.
Las rutas ausentes son FAIL explícitos; cuerpos funcionales no se ocultan.
"""
from contextlib import contextmanager
from decimal import Decimal
from importlib import import_module
import sys
from urllib.parse import urlsplit, parse_qs
from types import SimpleNamespace
from inspect import unwrap
from html import unescape

from django.conf import settings
from django.contrib.messages import SUCCESS, get_messages
from django.shortcuts import resolve_url
from django.test import Client, tag
from django.db import transaction
from django.urls import NoReverseMatch, reverse

from people.models import CompanyPersonAccess, Customer, Person, Supplier
from people.tests.person_ui_support import PersonUIFixture, Document
from people.tests.test_commercial_relationship_maintenance_cat023_red import database_snapshot
from people.tests.test_customer_company_cat022a_red import require_isolated_postgresql


def business_snapshot():
    # Session/context/messages bookkeeping is infrastructure, not business data.
    return {key: rows for key, rows in database_snapshot().items() if key != 'sessions.Session'}


class CommercialWebContracts:
    def setUp(self):
        require_isolated_postgresql(self)
        super().setUp()
        self.restrict(self.actor, 'view_person', *(f'{op}_{self.role}' for op in ('view', 'add', 'change')))
        self.actor.profile.companies.remove(self.b)
        self.actor.profile.branches.clear()
        self.context(self.client, self.a, None)
        self.local=self.model.objects.create(company=self.a,person=self.visible_person,notes='Local commercial')
        self.foreign=self.model.objects.create(company=self.b,person=self.hidden_person,notes='Foreign commercial')
        self.hidden_local=self.model.objects.create(company=self.a,person=self.hidden_person)
        self.available=self.make_person('WEB-AVAILABLE',email='available@example.invalid')
        CompanyPersonAccess.objects.create(company=self.a,person=self.available)
        self.legacy=self.model.objects.create(company=None,person=self.available,notes='Legacy unclassified')
        self.inactive_identity=self.make_person('WEB-INACTIVE-ROLE')
        CompanyPersonAccess.objects.create(company=self.a,person=self.inactive_identity)
        self.inactive=self.model.objects.create(company=self.a,person=self.inactive_identity,is_active=False)

    def route(self, operation, obj=None):
        name=f'{self.role}_{operation}'
        try:return reverse(name,args=[obj.pk] if obj is not None else [])
        except NoReverseMatch:self.fail(f'RED WEB: falta ruta propuesta {name}')

    def payload(self, **extra):
        values={'person':str(self.available.pk),'notes':'Web created'}
        if self.model is Customer:values['credit_limit']='123.45'
        return {**values,**extra}

    def edit_payload(self, **extra):
        values={'notes':'Web updated'}
        if self.model is Customer:values['credit_limit']=str(self.local.credit_limit)
        return {**values,**extra}

    def private_absent(self,response):
        surfaces=[unescape(response.content.decode())]
        surfaces.extend(str(value) for _,value in response.items())
        # Iteration marks storage used; restore flag so this observer has no semantic effect.
        storage=getattr(response.wsgi_request,'_messages',None)
        if storage is not None:
            used=storage.used
            surfaces.extend(str(message) for message in storage)
            storage.used=used
        from urllib.parse import unquote
        for surface in surfaces:
            for value in (self.hidden_person.identification,self.hidden_person.full_name,self.hidden_person.email,
                          self.hidden_person.phone,self.hidden_person.address,self.foreign.notes):
                self.assertNotIn(value,unquote(surface))

    def read(self, operation, obj=None, data=None):
        url=self.route(operation,obj);before=business_snapshot()
        response=self.client.get(url,data or {})
        self.assertEqual(response.status_code,200)
        self.assertEqual(business_snapshot(),before,'GET con escrituras de negocio')
        self.private_absent(response)
        return response

    def deny(self,operation,obj=None,*,post=False,data=None,status=403,client=None):
        url=self.route(operation,obj);before=business_snapshot()
        browser=client or self.client
        response=browser.post(url,data or {}) if post else browser.get(url)
        self.assertEqual(response.status_code,status)
        self.assertEqual(business_snapshot(),before,'Rechazo con escrituras parciales')
        self.private_absent(response)
        return response

    def invalid(self,operation,data,obj=None,*,fields,codes):
        response=self.deny(operation,obj,post=True,data=data,status=200)
        errors=response.context['form'].errors.as_data()
        matching=[error for field,items in errors.items() if field in fields for error in items]
        self.assertTrue(matching, f'Falta error en los campos esperados: {fields}')
        self.assertTrue(any(error.code in codes for error in matching),
                        f'El error debe corresponder a la causa probada: {codes}')
        return response

    def delta(self,before,pk,allowed=(),created=False):
        after=business_snapshot();label=self.model._meta.label
        for key,rows in before.items():
            if key==label:continue
            if key=='core.AuditLog':
                current={r['id']:r for r in after[key]}
                for row in rows:self.assertEqual(current.get(row['id']),row)
            else:self.assertEqual(after[key],rows,key)
        old={r['id']:r for r in before[label]};current={r['id']:r for r in after[label]}
        self.assertEqual(set(current),set(old)|({pk} if created else set()))
        if created:self.assertNotIn(pk,old)
        for key,row in old.items():
            if key!=pk or created:self.assertEqual(current[key],row)
            else:self.assertEqual({k:v for k,v in current[key].items() if k not in allowed},
                                  {k:v for k,v in row.items() if k not in allowed})

    def successful_redirect(self,response,obj):
        self.assertEqual(response.status_code,302)
        self.assertEqual(response['Location'],self.route('detail',obj))
        messages=list(get_messages(response.wsgi_request))
        self.assertTrue(any(m.level==SUCCESS and str(m) for m in messages))

    def endpoints(self):
        return [('list',None,False,{}),('create',None,False,{}),('create',None,True,self.payload()),
                ('detail',self.local,False,{}),('update',self.local,False,{}),
                ('update',self.local,True,self.edit_payload()),
                ('deactivate',self.local,True,{}),('reactivate',self.inactive,True,{})]

    @contextmanager
    def service_spy(self,operation):
        # Observe actual public function entry regardless of imported aliases.
        # No service replacement, monkeypatch of modules, or simulated result.
        function=getattr(import_module(f'people.services.{self.role}_maintenance'),operation)
        code=unwrap(function).__code__
        calls=[];spy=SimpleNamespace(calls=calls)
        previous=sys.getprofile()
        def observe(frame,event,arg):
            if event=='call' and frame.f_code is code:
                values=dict(frame.f_locals)
                if 'data' in values:values['data']=dict(values['data'])
                calls.append(values)
            if previous is not None:previous(frame,event,arg)
        sys.setprofile(observe)
        try:yield spy
        finally:sys.setprofile(previous)

    def service_call(self,spy,**expected):
        self.assertTrue(spy.calls,'Debe invocarse la función pública GREEN real')
        for call in spy.calls:
            if call.get('actor')!=self.actor or call.get('company')!=self.a:continue
            matches=True
            for key,value in expected.items():
                actual=call.get(key)
                if key in {'person_id','relation_id'}:
                    matches=matches and str(actual)==str(value)
                elif key=='data':
                    normalized=dict(actual or {})
                    if 'credit_limit' in normalized:normalized['credit_limit']=Decimal(str(normalized['credit_limit']))
                    matches=matches and normalized==value
                else:matches=matches and actual==value
            if matches:return
        self.fail('Servicio invocado sin actor, Company o argumentos comerciales correctos')

    def contains_node(self,node,parent):
        while node is not None:
            if node is parent:return True
            node=node.parent
        return False

    def html_form(self,response,action,expected_fields=None):
        document=Document(response.content.decode())
        forms=[node for node in document.matching('form')
               if node.visible() and node.attrs.get('method','get').lower()=='post'
               and (node.attrs.get('action') or response.wsgi_request.path)==action]
        self.assertEqual(len(forms),1,'Debe existir un formulario POST utilizable para esta operación')
        form=forms[0]
        controls=[node for node in document.nodes if node.tag in {'input','select','textarea','button'}
                  and self.contains_node(node,form)]
        csrf=[node for node in controls if node.attrs.get('name')=='csrfmiddlewaretoken']
        self.assertEqual(len(csrf),1);self.assertTrue(csrf[0].attrs.get('value'))
        submits=[node for node in controls if node.visible() and 'disabled' not in node.attrs and
                 ((node.tag=='button' and node.attrs.get('type','submit').lower()=='submit') or
                  (node.tag=='input' and node.attrs.get('type','').lower()=='submit'))]
        self.assertTrue(submits,'Falta botón submit utilizable')
        if expected_fields is not None:
            named=[node for node in controls if node.attrs.get('name') and node not in submits
                   and node.attrs.get('name')!='csrfmiddlewaretoken']
            self.assertEqual({node.attrs['name'] for node in named},set(expected_fields))
            for name in expected_fields:
                nodes=[node for node in named if node.attrs['name']==name]
                self.assertEqual(len(nodes),1)
                self.assertTrue(nodes[0].visible());self.assertNotIn('disabled',nodes[0].attrs)
                self.assertNotEqual(nodes[0].attrs.get('type'),'hidden')
                if name=='person':self.assertEqual(nodes[0].tag,'select')
        return csrf[0].attrs['value']

    def link(self,response,target):
        self.assertTrue(any(node.visible() and node.attrs.get('href')==target
                            for node in Document(response.content.decode()).matching('a')),
                        'Falta enlace navegable autorizado')

    def test_00_post_payloads_are_valid_for_existing_green_services(self):
        service=import_module(f'people.services.{self.role}_maintenance')
        for operation,obj,post,data in self.endpoints():
            if not post:continue
            before=business_snapshot()
            with transaction.atomic():
                if operation=='create':
                    self.assertEqual(set(data),{'person','notes'}|({'credit_limit'} if self.model is Customer else set()))
                    values={k:v for k,v in data.items() if k!='person'}
                    result=service.create(actor=self.actor,company=self.a,person_id=data['person'],data=values)
                    self.assertEqual(result.person_id,self.available.pk)
                elif operation=='update':
                    self.assertNotIn('person',data)
                    result=service.update(actor=self.actor,company=self.a,relation_id=obj.pk,data=data)
                    self.assertEqual(result.notes,'Web updated')
                else:
                    self.assertEqual(data,{})
                    result=service.set_active(actor=self.actor,company=self.a,relation_id=obj.pk,is_active=operation=='reactivate')
                    self.assertIs(result.is_active,operation=='reactivate')
                transaction.set_rollback(True)
            self.assertEqual(business_snapshot(),before)

    def test_01_proposed_routes_are_consistent_with_person_convention(self):
        self.route('list')
        prefix=f'/people/{self.plural}/'
        for operation,suffix,obj in [('list','',None),('create','new/',None),
                                    ('detail',f'{self.local.pk}/',self.local),
                                    ('update',f'{self.local.pk}/edit/',self.local),
                                    ('deactivate',f'{self.local.pk}/deactivate/',self.local),
                                    ('reactivate',f'{self.local.pk}/reactivate/',self.local)]:
            with self.subTest(operation=operation):self.assertEqual(self.route(operation,obj),prefix+suffix)

    def test_02_login_required_on_every_entrypoint(self):
        self.route('list')
        browser=Client()
        for operation,obj,post,data in self.endpoints():
            with self.subTest(operation=operation,post=post):
                response=self.deny(operation,obj,post=post,data=data,status=302,client=browser)
                target=urlsplit(response['Location'])
                self.assertEqual(target.path,resolve_url(settings.LOGIN_URL))
                self.assertEqual(parse_qs(target.query).get('next'),[self.route(operation,obj)])

    def test_03_company_context_required_on_every_entrypoint(self):
        self.context(self.client,None,None)
        for operation,obj,post,data in self.endpoints():
            with self.subTest(operation=operation,post=post):self.deny(operation,obj,post=post,data=data)

    def test_04_foreign_session_company_is_rejected(self):
        self.context(self.client,self.b,self.branch_b)
        for operation,obj,post,data in self.endpoints():self.deny(operation,obj,post=post,data=data)

    def test_05_revoked_membership_blocks_existing_session(self):
        self.actor.profile.companies.remove(self.a)
        for operation,obj,post,data in self.endpoints():self.deny(operation,obj,post=post,data=data)

    def test_06_inactive_company_blocks_every_entrypoint(self):
        self.a.is_active=False;self.a.save(update_fields=['is_active'])
        for operation,obj,post,data in self.endpoints():self.deny(operation,obj,post=post,data=data)

    def test_07_list_and_detail_require_commercial_view(self):
        self.restrict(self.actor,'view_person',f'add_{self.role}',f'change_{self.role}')
        self.deny('list');self.deny('detail',self.local)

    def test_08_create_get_and_post_require_commercial_add(self):
        self.restrict(self.actor,'view_person',f'view_{self.role}',f'change_{self.role}')
        self.deny('create');self.deny('create',post=True,data=self.payload())

    def test_09_edit_and_activity_require_commercial_change(self):
        self.restrict(self.actor,'view_person',f'view_{self.role}',f'add_{self.role}')
        self.deny('update',self.local);self.deny('update',self.local,post=True,data=self.edit_payload(notes='Denied'))
        self.deny('deactivate',self.local,post=True);self.deny('reactivate',self.inactive,post=True)

    def test_10_list_excludes_foreign_hidden_unclassified_and_inactive(self):
        response=self.read('list');html=response.content.decode()
        self.assertIn(self.visible_person.full_name,html)
        self.assertNotIn(self.inactive_identity.full_name,html)
        self.assertNotIn(self.available.full_name,html)
        self.assertNotIn(self.legacy.notes,html)

    def test_11_search_is_scoped_and_read_only(self):
        for query in (self.visible_person.identification,self.visible_person.full_name,self.visible_person.email):
            response=self.read('list',data={'q':query})
            self.assertIn(self.visible_person.full_name,response.content.decode())
        for query in (self.hidden_person.identification,self.hidden_person.full_name,self.hidden_person.email):
            response=self.read('list',data={'q':query})
            self.assertNotIn(self.visible_person.full_name,response.content.decode())

    def test_12_inactive_inclusion_is_explicit(self):
        response=self.read('list',data={'include_inactive':'1'})
        self.assertIn(self.inactive_identity.full_name,response.content.decode())
        response=self.read('list',data={'include_inactive':'0'})
        self.assertNotIn(self.inactive_identity.full_name,response.content.decode())

    def test_13_person_permission_and_access_are_not_implied_by_role(self):
        self.restrict(self.actor,*(f'{op}_{self.role}' for op in ('view','add','change')))
        response=self.read('list');self.assertNotIn(self.visible_person.full_name,response.content.decode())
        self.deny('detail',self.local,status=404)
        self.invalid('create',self.payload(),fields={'person','__all__'},codes={'invalid_choice','identity_unavailable'})
        self.deny('update',self.local,status=404)
        self.deny('update',self.local,post=True,data=self.edit_payload(notes='Denied'),status=404)
        self.deny('deactivate',self.local,post=True,status=404)
        self.deny('reactivate',self.inactive,post=True,status=404)

    def test_14_create_get_has_only_available_person_and_local_fields(self):
        response=self.read('create');form=response.context['form']
        self.assertEqual(set(form.fields),{'person','notes'}|({'credit_limit'} if self.model is Customer else set()))
        self.assertIn(self.available.pk,list(form.fields['person'].queryset.values_list('pk',flat=True)))
        self.assertNotIn(self.hidden_person.pk,list(form.fields['person'].queryset.values_list('pk',flat=True)))
        self.assertFalse(self.actor.profile.branches.exists())
        self.html_form(response,self.route('create'),set(form.fields))

    def test_15_create_post_reuses_person_session_company_and_actor(self):
        other=Supplier if self.model is Customer else Customer
        other.objects.create(company=self.a,person=self.available)
        self.model.objects.create(company=self.b,person=self.available)
        url=self.route('create');before=business_snapshot()
        with self.service_spy('create') as spy:response=self.client.post(url,self.payload())
        self.service_call(spy,person_id=self.available.pk,data={'notes':'Web created',**({'credit_limit':Decimal('123.45')} if self.model is Customer else {})})
        obj=self.model.objects.get(company=self.a,person=self.available)
        self.assertEqual(obj.notes,'Web created');self.assertEqual(obj.created_by_id,self.actor.pk)
        self.assertEqual(obj.updated_by_id,self.actor.pk);self.assertTrue(obj.is_active)
        self.assertIsNone(obj.deleted_at)
        if self.model is Customer:self.assertEqual(obj.credit_limit,Decimal('123.45'))
        self.delta(before,obj.pk,created=True);self.successful_redirect(response,obj);self.private_absent(response)
        self.assertFalse(self.actor.profile.branches.exists())

    def test_16_hidden_and_missing_identity_have_equivalent_form_errors(self):
        missing=Person.objects.order_by('-pk').first().pk+1
        self.assertFalse(Person.objects.filter(pk=missing).exists())
        hidden=self.invalid('create',self.payload(person=str(self.hidden_person.pk)),fields={'person','__all__'},codes={'invalid_choice','identity_unavailable'})
        absent=self.invalid('create',self.payload(person=str(missing)),fields={'person','__all__'},codes={'invalid_choice','identity_unavailable'})
        self.assertEqual(hidden.context['form'].errors.as_json(),absent.context['form'].errors.as_json())
        self.assertFalse(CompanyPersonAccess.objects.filter(company=self.a,person=self.hidden_person).exists())

    def test_17_duplicate_active_or_inactive_is_not_created_or_reactivated(self):
        for obj in (self.local,self.inactive):
            self.invalid('create',self.payload(person=str(obj.person_id)),fields={'person','__all__'},codes={'duplicate_relationship'})

    def protected(self,*,editing=False):
        values={'id':self.foreign.pk,'pk':self.foreign.pk,'company':self.b.pk,'company_id':self.b.pk,
                'person_id':self.hidden_person.pk,'created_by':self.other.pk,'updated_by':self.other.pk,
                'created_by_id':self.other.pk,'updated_by_id':self.other.pk,
                'created_at':'2026-01-01T00:00:00+00:00','updated_at':'2026-01-01T00:00:00+00:00',
                'deleted_at':'2026-01-01T00:00:00+00:00','is_active':'0','unknown_commercial_field':'x'}
        for field in Person._meta.concrete_fields:
            if field.name not in {'id','created_by','updated_by','created_at','updated_at','deleted_at','is_active'}:
                values[field.name]=str(getattr(self.hidden_person,field.attname))
        if editing:values['person']=self.hidden_person.pk
        for key,value in values.items():yield {key:value}

    def test_18_create_rejects_company_and_protected_payload_injection(self):
        self.route('create')
        for extra in self.protected():
            with self.subTest(field=next(iter(extra))):self.invalid('create',self.payload(**extra),fields={next(iter(extra)),'__all__'},codes={'invalid_fields'})

    def test_19_detail_and_edit_get_are_scoped_and_read_only(self):
        self.assertIn(self.visible_person.full_name,self.read('detail',self.local).content.decode())
        response=self.read('update',self.local)
        self.assertEqual(set(response.context['form'].fields),{'notes'}|({'credit_limit'} if self.model is Customer else set()))
        self.html_form(response,self.route('update',self.local),set(response.context['form'].fields))
        self.assertFalse(self.actor.profile.branches.exists())

    def test_20_edit_post_uses_service_and_changes_only_local_fields(self):
        other=Supplier if self.model is Customer else Customer
        other.objects.create(company=self.a,person=self.visible_person)
        self.model.objects.create(company=self.b,person=self.visible_person)
        url=self.route('update',self.local);before=business_snapshot()
        with self.service_spy('update') as spy:response=self.client.post(url,self.edit_payload())
        self.service_call(spy,relation_id=self.local.pk,data={'notes':'Web updated',**({'credit_limit':Decimal(str(self.local.credit_limit))} if self.model is Customer else {})})
        self.local.refresh_from_db();self.assertEqual(self.local.notes,'Web updated')
        self.assertEqual(self.local.updated_by_id,self.actor.pk)
        self.delta(before,self.local.pk,{'notes','updated_by_id','updated_at'})
        self.successful_redirect(response,self.local);self.private_absent(response)

    def test_21_foreign_hidden_and_unclassified_relations_are_not_found(self):
        for obj in (self.foreign,self.hidden_local,self.legacy):
            self.deny('detail',obj,status=404);self.deny('update',obj,status=404)
            self.deny('update',obj,post=True,data=self.edit_payload(notes='Denied'),status=404)
            self.deny('deactivate',obj,post=True,status=404)
            self.deny('reactivate',obj,post=True,status=404)

    def test_22_edit_rejects_protected_fields_atomically(self):
        self.route('update',self.local)
        for extra in self.protected(editing=True):
            with self.subTest(field=next(iter(extra))):
                self.invalid('update',self.edit_payload(notes='Must rollback',**extra),self.local,fields={next(iter(extra)),'__all__'},codes={'invalid_fields'})

    def history(self):
        from core.models import DocumentType
        from sales.models import Sale
        from purchases.models import Purchase
        if self.model is Customer:
            from inventory.models import Warehouse
            warehouse=Warehouse.objects.create(company=self.a,branch=self.branch,code='WEB-H',name='History')
            dtype,_=DocumentType.objects.get_or_create(code=Sale.DOCUMENT_TYPE_CODE,defaults={'name':'Sale','category':'SALES'})
            Sale.objects.create(company=self.a,branch=self.branch,warehouse=warehouse,customer=self.local,document_type=dtype)
        else:
            dtype,_=DocumentType.objects.get_or_create(code=Purchase.DOCUMENT_TYPE_CODE,defaults={'name':'Purchase','category':'PURCHASES'})
            Purchase.objects.create(company=self.a,branch=self.branch,supplier=self.local,document_type=dtype)

    def test_23_edit_preserves_historical_documents(self):
        self.history();url=self.route('update',self.local);before=business_snapshot()
        response=self.client.post(url,self.edit_payload(notes='With history'))
        self.assertEqual(response.status_code,302)
        self.local.refresh_from_db();self.assertEqual(self.local.notes,'With history')
        self.delta(before,self.local.pk,{'notes','updated_by_id','updated_at'})
        self.private_absent(response)

    def test_24_activity_post_reuses_same_pk_preserves_all_history_and_roles(self):
        self.history();other=Supplier if self.model is Customer else Customer
        other.objects.create(company=self.a,person=self.visible_person)
        self.model.objects.create(company=self.b,person=self.visible_person)
        for operation,active in [('deactivate',False),('reactivate',True)]:
            url=self.route(operation,self.local);before=business_snapshot()
            with self.service_spy('set_active') as spy:response=self.client.post(url)
            self.service_call(spy,relation_id=self.local.pk,is_active=active)
            self.assertEqual(response.status_code,302)
            # Activity may return to its detail or list, both existing project patterns.
            self.assertIn(response['Location'],[self.route('detail',self.local),self.route('list')])
            self.local.refresh_from_db();self.assertIs(self.local.is_active,active)
            self.assertEqual(self.local.updated_by_id,self.actor.pk)
            self.delta(before,self.local.pk,{'is_active','updated_by_id','updated_at'})
            self.assertFalse(self.actor.profile.branches.exists())
            self.private_absent(response)

    def test_25_activity_get_is_not_mutating_and_returns_405(self):
        self.deny('deactivate',self.local,status=405)
        self.deny('reactivate',self.inactive,status=405)

    def csrf_browser(self):
        browser=Client(enforce_csrf_checks=True);browser.force_login(self.actor)
        self.context(browser,self.a,None)
        return browser

    def test_26_all_write_entrypoints_require_csrf(self):
        browser=self.csrf_browser()
        for operation,obj,data in [('create',None,self.payload()),('update',self.local,self.edit_payload(notes='CSRF')),
                                   ('deactivate',self.local,{}),('reactivate',self.inactive,{})]:
            self.deny(operation,obj,post=True,data=data,status=403,client=browser)

    def test_27_valid_csrf_token_allows_real_create(self):
        url=self.route('create');browser=self.csrf_browser()
        page=browser.get(url);self.assertEqual(page.status_code,200)
        token=self.html_form(page,url,set(page.context['form'].fields))
        before=business_snapshot()
        response=browser.post(url,{**self.payload(),'csrfmiddlewaretoken':token})
        self.assertEqual(response.status_code,302)
        obj=self.model.objects.get(company=self.a,person=self.available)
        self.delta(before,obj.pk,created=True)
        self.private_absent(response)

    def test_28_queries_use_real_green_services_without_writes(self):
        for operation,service,obj in [('list','list_relations',None),('detail','get_relation',self.local)]:
            self.route(operation,obj)
            with self.service_spy(service) as spy:self.read(operation,obj)
            if service=='get_relation':self.service_call(spy,relation_id=self.local.pk)
            else:
                self.service_call(spy,include_inactive=False)
                self.assertTrue(all(call.get('query') in (None,'') for call in spy.calls))

    def test_29_revoking_person_access_hides_relation_and_blocks_mutations(self):
        CompanyPersonAccess.objects.filter(company=self.a,person__in=[self.visible_person,self.inactive_identity]).delete()
        response=self.read('list');self.assertNotIn(self.visible_person.full_name,response.content.decode())
        self.deny('detail',self.local,status=404);self.deny('update',self.local,status=404)
        self.deny('update',self.local,post=True,data=self.edit_payload(notes='Denied'),status=404)
        self.deny('deactivate',self.local,post=True,status=404)
        self.deny('reactivate',self.inactive,post=True,status=404)
        self.assertTrue(self.model.objects.filter(pk=self.local.pk).exists())

    def test_30_switch_company_changes_available_commercial_relations(self):
        self.actor.profile.companies.add(self.b)
        response=self.read('list');self.assertIn(self.visible_person.full_name,response.content.decode())
        self.context(self.client,self.b,None)
        url=self.route('list');before=business_snapshot();response=self.client.get(url)
        self.assertEqual(response.status_code,200);self.assertEqual(business_snapshot(),before)
        self.assertIn(self.hidden_person.full_name,response.content.decode())
        self.assertNotIn(self.visible_person.full_name,response.content.decode())
        self.context(self.client,self.a,None)
        response=self.read('list');self.assertIn(self.visible_person.full_name,response.content.decode())


    def test_000_observer_tracks_preimported_public_alias_without_replacing_service(self):
        alias=getattr(import_module(f'people.services.{self.role}_maintenance'),'create')
        before=business_snapshot();previous=sys.getprofile()
        data={'notes':'Observed'}
        with transaction.atomic():
            with self.service_spy('create') as spy:
                obj=alias(actor=self.actor,company=self.a,person_id=self.available.pk,data=data)
            self.service_call(spy,person_id=self.available.pk,data=data)
            self.assertEqual(obj.notes,'Observed')
            self.assertIs(sys.getprofile(),previous)
            transaction.set_rollback(True)
        self.assertEqual(business_snapshot(),before)

    def activity_source(self,browser,obj,operation):
        target=self.route(operation,obj)
        for name,instance,data in [('detail',obj,{}),('list',None,{'include_inactive':'1'})]:
            url=self.route(name,instance);before=business_snapshot()
            response=browser.get(url,data)
            self.assertEqual(response.status_code,200)
            self.assertEqual(business_snapshot(),before)
            self.private_absent(response)
            forms=Document(response.content.decode()).matching('form')
            if any(node.visible() and node.attrs.get('action')==target for node in forms):
                token=self.html_form(response,target,())
                return response,token
        self.fail('Actividad autorizada debe ofrecer formulario POST desde detalle o listado')

    def test_32_navigation_and_post_activity_forms_are_usable(self):
        listing=self.read('list')
        self.link(listing,self.route('create'));self.link(listing,self.route('detail',self.local))
        detail=self.read('detail',self.local);self.link(detail,self.route('update',self.local))
        for obj,operation in [(self.local,'deactivate'),(self.inactive,'reactivate')]:
            self.activity_source(self.client,obj,operation)

    def test_33_navigation_does_not_offer_unauthorized_add_change_actions(self):
        self.restrict(self.actor,'view_person',f'view_{self.role}')
        forbidden_links={self.route('create'),self.route('update',self.local)}
        forbidden_actions={self.route('deactivate',self.local),self.route('reactivate',self.inactive)}
        for response in [self.read('list',data={'include_inactive':'1'}),self.read('detail',self.local)]:
            document=Document(response.content.decode())
            self.assertFalse(any(node.visible() and node.attrs.get('href') in forbidden_links
                                 for node in document.matching('a')))
            self.assertFalse(any(node.visible() and node.attrs.get('action') in forbidden_actions
                                 for node in document.matching('form')))

    def test_34_valid_csrf_token_allows_real_edit(self):
        url=self.route('update',self.local);browser=self.csrf_browser()
        page=browser.get(url);self.assertEqual(page.status_code,200)
        token=self.html_form(page,url,set(page.context['form'].fields))
        before=business_snapshot()
        data=self.edit_payload(notes='CSRF updated')
        with self.service_spy('update') as spy:
            response=browser.post(url,{**data,'csrfmiddlewaretoken':token})
        expected={'notes':'CSRF updated',**({'credit_limit':Decimal(str(self.local.credit_limit))} if self.model is Customer else {})}
        self.service_call(spy,relation_id=self.local.pk,data=expected)
        self.local.refresh_from_db();self.assertEqual(self.local.notes,'CSRF updated')
        self.assertEqual(self.local.updated_by_id,self.actor.pk)
        self.delta(before,self.local.pk,{'notes','updated_by_id','updated_at'})
        self.successful_redirect(response,self.local);self.private_absent(response)

    def csrf_activity(self,operation,obj,active):
        self.route(operation,obj);browser=self.csrf_browser()
        _,token=self.activity_source(browser,obj,operation)
        before=business_snapshot()
        with self.service_spy('set_active') as spy:
            response=browser.post(self.route(operation,obj),{'csrfmiddlewaretoken':token})
        self.service_call(spy,relation_id=obj.pk,is_active=active)
        self.assertEqual(response.status_code,302)
        self.assertIn(response['Location'],[self.route('detail',obj),self.route('list')])
        obj.refresh_from_db();self.assertIs(obj.is_active,active)
        self.assertEqual(obj.updated_by_id,self.actor.pk)
        self.delta(before,obj.pk,{'is_active','updated_by_id','updated_at'})
        self.private_absent(response)

    def test_35_valid_csrf_token_allows_deactivation(self):
        self.csrf_activity('deactivate',self.local,False)

    def test_36_valid_csrf_token_allows_reactivation(self):
        self.csrf_activity('reactivate',self.inactive,True)


@tag('cat023_web_red')
class CustomerWebRedTests(CommercialWebContracts,PersonUIFixture):
    role='customer';plural='customers';model=Customer

    def test_31_credit_limit_validation_is_model_consistent_and_atomic(self):
        self.route('create')
        for value in ('-0.01','1.001','100000000.00'):
            with self.subTest(value=value):
                codes={'invalid_credit_limit','min_value'} if value=='-0.01' else ({'max_decimal_places'} if value=='1.001' else {'max_digits','max_whole_digits'})
                self.invalid('create',self.payload(credit_limit=value),fields={'credit_limit','__all__'},codes=codes)
                self.invalid('update',self.edit_payload(notes='Must rollback',credit_limit=value),self.local,fields={'credit_limit','__all__'},codes=codes)


    def test_37_valid_credit_update_preserves_precision_and_other_relations(self):
        other=Supplier.objects.create(company=self.a,person=self.visible_person)
        Customer.objects.create(company=self.b,person=self.visible_person)
        url=self.route('update',self.local)
        for value in ('123.45','99999999.99'):
            before=business_snapshot()
            with self.service_spy('update') as spy:
                response=self.client.post(url,self.edit_payload(credit_limit=value))
            expected={'notes':'Web updated','credit_limit':Decimal(value)}
            self.service_call(spy,relation_id=self.local.pk,data=expected)
            self.local.refresh_from_db();self.assertEqual(self.local.credit_limit,Decimal(value))
            self.assertEqual(self.local.notes,'Web updated')
            self.assertEqual(self.local.updated_by_id,self.actor.pk)
            self.delta(before,self.local.pk,{'notes','credit_limit','updated_by_id','updated_at'})
            self.successful_redirect(response,self.local);self.private_absent(response)


@tag('cat023_web_red')
class SupplierWebRedTests(CommercialWebContracts,PersonUIFixture):
    role='supplier';plural='suppliers';model=Supplier

    def test_31_credit_limit_is_not_supplier_data(self):
        self.invalid('create',self.payload(credit_limit='1.00'),fields={'credit_limit','__all__'},codes={'invalid_fields'})
        self.invalid('update',{'notes':'Must rollback','credit_limit':'1.00'},self.local,fields={'credit_limit','__all__'},codes={'invalid_fields'})
