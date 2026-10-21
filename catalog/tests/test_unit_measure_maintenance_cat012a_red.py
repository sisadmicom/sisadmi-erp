"""CAT-01.2A RED: human UnitMeasure maintenance, a global permissioned catalog.

CONTEXTUAL RETURN CONTRACT (deferred integration, no API/storage prescribed):
An authorized Product create/edit draft may open NORMAL UnitMeasure create.
Saving persists the unit independently, returns to that SAME authorized draft,
preserves every preservable product value (including selected annexes/taxes),
and selects ONLY the newly created unit in unit_measure. Cancelling returns to
the same draft with its previous selection and creates neither unit nor product.
The actor, parent operation, field and return purpose must be server-bound,
revalidated, expiring and protected against forged/cross-actor/replayed returns;
no external return or field/object substitution is authority. No Product save,
new Company/Branch authority or global permission is granted by a continuation.
Standalone create/update remain functional without any Product continuation.
The future HTTP integration is intentionally not required by this RED.

Routes follow existing unit_list/create/update/delete conventions; unit_detail
is the missing normal consultation. Logical deletion preserves shared product
references; physical-delete/PROTECT redesign and reactivation are out of scope.
All executable scenarios use native GET/POST, with no JavaScript requirement.
"""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.staticfiles import finders
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.templatetags.static import static
from django.urls import NoReverseMatch, reverse

from catalog.models import Product, UnitMeasure
from core.models import Company
from people.models import Person
from people.tests import person_ui_support as html_support


class UnitMeasureMaintenanceRedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.unit = UnitMeasure.objects.create(code='UND', name='Unidad visible')
        cls.inactive = UnitMeasure.objects.create(code='OLD', name='Unidad inactiva', is_active=False)
        cls.actor = get_user_model().objects.create_user(username='unit-operator')
        cls.company = Company.objects.create(person=Person.objects.create(
            identification='1790000002001', person_type='LEGAL', full_name='Empresa A'),
            commercial_name='Empresa A')
        cls.other_company = Company.objects.create(person=Person.objects.create(
            identification='1790000002002', person_type='LEGAL', full_name='Empresa B'),
            commercial_name='Empresa B')
        cls.actor.profile.companies.add(cls.company)
        cls.product = Product.objects.create(company=cls.company,code='P1',name='Producto propio',unit_measure=cls.unit)
        cls.foreign_product = Product.objects.create(company=cls.other_company,code='P2',
            name='PRODUCTO AJENO CONFIDENCIAL',unit_measure=cls.unit)

    def setUp(self):
        self.grant('view','add','change','delete')
        self.client.force_login(self.actor)

    def grant(self, *operations):
        self.actor.user_permissions.set(Permission.objects.filter(
            content_type__app_label='catalog', content_type__model='unitmeasure',
            codename__in=[op+'_unitmeasure' for op in operations]))
        for cache in ('_perm_cache','_user_perm_cache','_group_perm_cache'):
            self.actor.__dict__.pop(cache,None)

    def url(self, route, obj=None):
        try:
            return reverse(route,args=[obj.pk] if obj else [])
        except NoReverseMatch:
            self.fail('Producción faltante: mantenimiento normal '+route)

    @contextmanager
    def isolated_case(self):
        with transaction.atomic():
            try:
                yield
            finally:
                transaction.set_rollback(True)

    def post(self, route, data, obj=None, client=None):
        client = client or self.client
        client.raise_request_exception=False
        with transaction.atomic():
            response=client.post(self.url(route,obj),data)
        return response

    def rows(self):
        return list(UnitMeasure.objects.order_by('pk').values())

    def controls(self, response):
        return [n for n in html_support.Document(response.content.decode()).nodes if n.tag in ('a','button')]

    def test_all_normal_routes_require_authentication(self):
        anonymous=Client(raise_request_exception=False)
        for route,obj in [('unit_list',None),('unit_detail',self.unit),('unit_create',None),
                          ('unit_update',self.unit),('unit_delete',self.unit)]:
            with self.subTest(route=route), self.isolated_case():
                before=self.rows()
                for method in ('get','post'):
                    response=getattr(anonymous,method)(self.url(route,obj))
                    self.assertIn(response.status_code,(302,401,403))
                    if response.status_code==302:
                        self.assertEqual(urlsplit(response.url).path,reverse('login'))
                self.assertEqual(self.rows(),before)

    def test_operation_permission_cannot_be_replaced_by_other_permissions(self):
        routes=[('unit_list',None,'view'),('unit_detail',self.unit,'view'),('unit_create',None,'add'),
                ('unit_update',self.unit,'change'),('unit_delete',self.unit,'delete')]
        for route,obj,required in routes:
            with self.subTest(route=route), self.isolated_case():
                self.grant(*[op for op in ('view','add','change','delete') if op!=required])
                before=self.rows()
                response=self.client.get(self.url(route,obj)) if required=='view' else self.post(route,{'code':'NEW','name':'Intento'},obj)
                self.assertIn(response.status_code,(403,404))
                self.assertEqual(self.rows(),before)

    def test_company_membership_does_not_authorize_global_mutation(self):
        self.grant('view')
        session=self.client.session; session['company_id']=self.company.pk; session.save()
        for route,obj in [('unit_create',None),('unit_update',self.unit),('unit_delete',self.unit)]:
            with self.subTest(route=route), self.isolated_case():
                before=self.rows()
                self.assertIn(self.post(route,{'code':'NEW','name':'Intento'},obj).status_code,(403,404))
                self.assertEqual(self.rows(),before)

    def test_list_shows_only_active_units_with_view_permission(self):
        self.grant('view')
        response=self.client.get(self.url('unit_list'))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,self.unit.code)
        self.assertContains(response,self.unit.name)
        self.assertNotContains(response,self.inactive.name)
        self.assertNotContains(response,self.foreign_product.name)

    def test_consultation_is_read_only_and_does_not_reveal_product_references(self):
        before=self.rows()
        response=self.client.get(self.url('unit_detail',self.unit))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,self.unit.code)
        self.assertContains(response,self.unit.name)
        self.assertNotContains(response,self.foreign_product.name)
        self.assertEqual(self.rows(),before)

    def test_standalone_create_and_edit_do_not_require_product_or_company_context(self):
        self.actor.profile.companies.clear()
        before=list(Product.objects.order_by('pk').values())
        response=self.post('unit_create',{'code':'NEW','name':'Nueva unidad'})
        self.assertEqual(response.status_code,302)
        created=UnitMeasure.objects.get(code='NEW')
        self.assertEqual(created.created_by_id,self.actor.pk)
        response=self.post('unit_update',{'code':'NEW2','name':'Unidad editada'},created)
        self.assertEqual(response.status_code,302)
        created.refresh_from_db()
        self.assertEqual((created.code,created.name,created.updated_by_id),('NEW2','Unidad editada',self.actor.pk))
        self.assertEqual(list(Product.objects.order_by('pk').values()),before)

    def test_get_form_has_only_unit_fields_and_edit_values_are_unbound(self):
        for route,obj in [('unit_create',None),('unit_update',self.unit)]:
            with self.subTest(route=route):
                response=self.client.get(self.url(route,obj))
                self.assertEqual(response.status_code,200)
                form=response.context['form']
                self.assertFalse(form.is_bound)
                self.assertEqual(set(form.fields),{'code','name'})
                if obj:
                    self.assertEqual((form['code'].value(),form['name'].value()),(obj.code,obj.name))

    def test_required_empty_fields_are_rejected_without_writes(self):
        for route,obj in [('unit_create',None),('unit_update',self.unit)]:
            for field in ('code','name'):
                with self.subTest(route=route,field=field), self.isolated_case():
                    before=self.rows(); data={'code':'NEW','name':'Nueva'}; data[field]='   '
                    response=self.post(route,data,obj)
                    self.assertEqual(response.status_code,200)
                    self.assertIn(field,response.context['form'].errors)
                    self.assertEqual(self.rows(),before)

    def test_global_code_uniqueness_includes_inactive_units(self):
        for route,obj in [('unit_create',None),('unit_update',self.unit)]:
            for code in (self.unit.code,self.inactive.code):
                if obj and code==self.unit.code:
                    continue
                with self.subTest(route=route,code=code), self.isolated_case():
                    before=self.rows()
                    response=self.post(route,{'code':code,'name':'Duplicada'},obj)
                    self.assertEqual(response.status_code,200)
                    self.assertIn('code',response.context['form'].errors)
                    self.assertEqual(self.rows(),before)

    def test_concurrent_unique_collision_is_controlled_without_500(self):
        for route,obj in [('unit_create',None),('unit_update',self.unit)]:
            with self.subTest(route=route), self.isolated_case():
                before=self.rows()
                with patch.object(UnitMeasure,'save',side_effect=IntegrityError('private concurrency detail')):
                    response=self.post(route,{'code':'NEW','name':'Nueva'},obj)
                self.assertEqual(response.status_code,200)
                self.assertTrue(response.context['form'].errors)
                self.assertNotContains(response,'private concurrency detail')
                self.assertEqual(self.rows(),before)

    def test_get_and_head_deactivation_show_confirmation_without_writes(self):
        before=self.rows()
        for method in ('get','head'):
            with self.subTest(method=method):
                response=getattr(self.client,method)(self.url('unit_delete',self.unit))
                self.assertEqual(response.status_code,200)
                self.assertEqual(self.rows(),before)
                if method=='get':
                    forms=html_support.Document(response.content.decode()).matching('form',method='post')
                    self.assertTrue(forms)
                    self.assertContains(response,'csrfmiddlewaretoken')
                    self.assertContains(response,self.unit.name)

    def test_post_deactivation_requires_csrf_and_preserves_shared_product_references(self):
        browser=Client(enforce_csrf_checks=True); browser.force_login(self.actor)
        before=self.rows(); products=list(Product.objects.order_by('pk').values())
        self.assertEqual(self.post('unit_delete',{},self.unit,browser).status_code,403)
        self.assertEqual(self.rows(),before)
        browser.get(self.url('unit_delete',self.unit))
        response=self.post('unit_delete',{'csrfmiddlewaretoken':browser.cookies['csrftoken'].value},self.unit,browser)
        self.assertEqual(response.status_code,302)
        self.unit.refresh_from_db()
        self.assertFalse(self.unit.is_active)
        self.assertIsNotNone(self.unit.deleted_at)
        self.assertEqual(self.unit.updated_by_id,self.actor.pk)
        self.assertEqual(UnitMeasure.objects.count(),len(before))
        self.assertEqual((self.unit.code,self.unit.name),(before[0]['code'],before[0]['name']))
        self.assertEqual(list(Product.objects.order_by('pk').values()),products)
        self.assertEqual(Product.objects.filter(unit_measure_id=self.unit.pk).count(),2)

    def test_list_uses_shared_sisadmi_actions_with_accessible_names_and_local_icons(self):
        response=self.client.get(self.url('unit_list'))
        self.assertTemplateUsed(response,'core/components/entity_action.html')
        expected=[('Adicionar unidad','add','unit_create',None),('Consultar unidad','view','unit_detail',self.unit),
                  ('Editar unidad','edit','unit_update',self.unit),('Eliminar unidad','delete','unit_delete',self.unit)]
        controls=self.controls(response)
        for label,kind,route,obj in expected:
            with self.subTest(action=kind):
                selected=[n for n in controls if n.attrs.get('href')==self.url(route,obj)]
                self.assertEqual(len(selected),1)
                control=selected[0]
                self.assertEqual(control.attrs.get('aria-label'),label)
                self.assertIn('entity-action',control.attrs.get('class','').split())
                images=[n for n in control.children if isinstance(n,html_support.Element) and n.tag=='img']
                self.assertEqual(len(images),1)
                self.assertEqual(images[0].attrs.get('src'),static('core/icons/'+kind+'.svg'))
                self.assertEqual(images[0].attrs.get('alt'),'')
                self.assertIsNotNone(finders.find('core/icons/'+kind+'.svg'))

    def test_list_hides_actions_without_operation_authority(self):
        self.grant('view')
        response=self.client.get(self.url('unit_list'))
        controls=self.controls(response)
        targets={n.attrs.get('href') for n in controls}
        self.assertIn(self.url('unit_detail',self.unit),targets)
        for route,obj in [('unit_create',None),('unit_update',self.unit),('unit_delete',self.unit)]:
            self.assertNotIn(self.url(route,obj),targets)

    def test_action_controls_are_keyboard_focusable_with_shared_size_and_focus_style(self):
        response=self.client.get(self.url('unit_list'))
        controls=[n for n in self.controls(response) if 'entity-action' in n.attrs.get('class','').split()]
        self.assertGreaterEqual(len(controls),4)
        for control in controls:
            self.assertTrue(control.tag=='button' or control.attrs.get('href'))
            self.assertNotEqual(control.attrs.get('tabindex'),'-1')
            self.assertTrue(control.attrs.get('aria-label'))
        css_file=finders.find('core/css/erp.css')
        self.assertIsNotNone(css_file)
        css=Path(css_file).read_text()
        self.assertIn('.entity-action',css)
        self.assertIn(':focus-visible',css)
        # Shared class supplies the consistent hit area; do not freeze pixels.
        self.assertRegex(css,r'(?s)\.entity-action\s*\{[^}]*width\s*:')
        self.assertRegex(css,r'(?s)\.entity-action\s*\{[^}]*height\s*:')

    def test_no_javascript_native_form_cycle(self):
        page=self.client.get(self.url('unit_create'))
        form=page.context['form']
        self.assertEqual(set(form.fields),{'code','name'})
        native=html_support.Document(page.content.decode()).matching('form',method='post')
        self.assertTrue(native)
        created=self.post('unit_create',{'code':'NOJS','name':'Sin JavaScript'})
        self.assertEqual(created.status_code,302)
        unit=UnitMeasure.objects.get(code='NOJS')
        self.assertEqual(self.post('unit_update',{'code':'NOJS','name':'Editada'},unit).status_code,302)
        self.assertEqual(self.client.get(self.url('unit_delete',unit)).status_code,200)
        self.assertEqual(self.post('unit_delete',{},unit).status_code,302)
        unit.refresh_from_db(); self.assertFalse(unit.is_active)
