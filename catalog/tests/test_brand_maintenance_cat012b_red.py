"""CAT-01.2B RED: human Brand maintenance, a global permissioned catalog.

CONTEXTUAL RETURN CONTRACT (deferred integration, no API/storage prescribed):
An authorized Product create/edit draft may open NORMAL Brand create.
Saving persists the brand independently, returns to that SAME authorized draft,
preserves every preservable product value (including selected annexes/taxes),
and selects ONLY the newly created brand in the authorized brand field. Cancelling returns to
the same draft with its previous selection and creates neither brand nor product.
The actor, parent operation, field and return purpose must be server-bound,
revalidated, expiring and protected against forged/cross-actor/replayed returns;
no external return or field/object substitution is authority. No Product save,
new Company/Branch authority or global permission is granted by a continuation.
Standalone create/update remain functional without any Product continuation.
The future HTTP integration is intentionally not required by this RED.

Routes follow existing brand_list/create/update/delete conventions; brand_detail
is the missing normal consultation. Logical deletion preserves shared product
references; physical-delete/integrity redesign and reactivation are out of scope.
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

from catalog.models import Brand, Product
from core.models import Company
from people.models import Person
from people.tests import person_ui_support as html_support


class BrandMaintenanceRedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = get_user_model().objects.create_user(username='brand-operator')
        cls.audit_author = get_user_model().objects.create_user(username='brand-audit-author')
        cls.audit_editor = get_user_model().objects.create_user(username='brand-audit-editor')
        cls.brand = Brand.objects.create(name='Marca visible', created_by=cls.audit_author, updated_by=cls.audit_editor)
        cls.inactive = Brand.objects.create(name='Marca inactiva', is_active=False)
        cls.company = Company.objects.create(person=Person.objects.create(
            identification='1790000002001', person_type='LEGAL', full_name='Empresa A'),
            commercial_name='Empresa A')
        cls.other_company = Company.objects.create(person=Person.objects.create(
            identification='1790000002002', person_type='LEGAL', full_name='Empresa B'),
            commercial_name='Empresa B')
        cls.actor.profile.companies.add(cls.company)
        cls.product = Product.objects.create(company=cls.company,code='P1',name='Producto propio',brand=cls.brand)
        cls.foreign_product = Product.objects.create(company=cls.other_company,code='P2',
            name='PRODUCTO AJENO CONFIDENCIAL',brand=cls.brand)

    def setUp(self):
        self.grant('view','add','change','delete')
        self.client.force_login(self.actor)

    def grant(self, *operations):
        self.actor.user_permissions.set(Permission.objects.filter(
            content_type__app_label='catalog', content_type__model='brand',
            codename__in=[op+'_brand' for op in operations]))
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
        return list(Brand.objects.order_by('pk').values())

    def controls(self, response):
        return [n for n in html_support.Document(response.content.decode()).nodes if n.tag in ('a','button')]

    def test_all_normal_routes_require_authentication(self):
        anonymous=Client(raise_request_exception=False)
        for route,obj in [('brand_list',None),('brand_detail',self.brand),('brand_create',None),
                          ('brand_update',self.brand),('brand_delete',self.brand)]:
            with self.subTest(route=route), self.isolated_case():
                before=self.rows()
                for method in ('get','post'):
                    response=getattr(anonymous,method)(self.url(route,obj))
                    self.assertIn(response.status_code,(302,401,403))
                    if response.status_code==302:
                        self.assertEqual(urlsplit(response.url).path,reverse('login'))
                self.assertEqual(self.rows(),before)

    def test_operation_permission_cannot_be_replaced_by_other_permissions(self):
        routes=[('brand_list',None,'view'),('brand_detail',self.brand,'view'),('brand_create',None,'add'),
                ('brand_update',self.brand,'change'),('brand_delete',self.brand,'delete')]
        for route,obj,required in routes:
            with self.subTest(route=route), self.isolated_case():
                self.grant(*[op for op in ('view','add','change','delete') if op!=required])
                before=self.rows()
                response=self.client.get(self.url(route,obj)) if required=='view' else self.post(route,{'name':'Intento'},obj)
                self.assertIn(response.status_code,(403,404))
                self.assertEqual(self.rows(),before)

    def test_company_membership_does_not_authorize_global_mutation(self):
        self.grant('view')
        session=self.client.session; session['company_id']=self.company.pk; session.save()
        for route,obj in [('brand_create',None),('brand_update',self.brand),('brand_delete',self.brand)]:
            with self.subTest(route=route), self.isolated_case():
                before=self.rows()
                self.assertIn(self.post(route,{'name':'Intento'},obj).status_code,(403,404))
                self.assertEqual(self.rows(),before)

    def test_list_shows_only_active_brands_with_view_permission(self):
        self.grant('view')
        response=self.client.get(self.url('brand_list'))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,self.brand.name)
        self.assertNotContains(response,self.inactive.name)
        self.assertNotContains(response,self.foreign_product.name)

    def test_consultation_is_read_only_and_does_not_reveal_product_references(self):
        before=self.rows()
        response=self.client.get(self.url('brand_detail',self.brand))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,self.brand.name)
        self.assertContains(response,self.audit_author.username)
        self.assertContains(response,self.audit_editor.username)
        self.assertIn('estado', response.content.decode().casefold())
        self.assertIn('activa', response.content.decode().casefold())
        self.assertNotContains(response,self.foreign_product.name)
        self.assertEqual(self.rows(),before)

    def test_standalone_create_and_edit_do_not_require_product_or_company_context(self):
        self.actor.profile.companies.clear()
        before=list(Product.objects.order_by('pk').values())
        response=self.post('brand_create',{'name':'Nueva marca'})
        self.assertEqual(response.status_code,302)
        created=Brand.objects.get(name='Nueva marca')
        self.assertEqual(created.created_by_id,self.actor.pk)
        response=self.post('brand_update',{'name':'Marca editada'},created)
        self.assertEqual(response.status_code,302)
        created.refresh_from_db()
        self.assertEqual((created.name,created.updated_by_id),('Marca editada',self.actor.pk))
        self.assertEqual(list(Product.objects.order_by('pk').values()),before)

    def test_get_form_has_only_brand_fields_and_edit_values_are_unbound(self):
        for route,obj in [('brand_create',None),('brand_update',self.brand)]:
            with self.subTest(route=route):
                response=self.client.get(self.url(route,obj))
                self.assertEqual(response.status_code,200)
                form=response.context['form']
                self.assertFalse(form.is_bound)
                self.assertEqual(set(form.fields),{'name'})
                if obj:
                    self.assertEqual(form['name'].value(),obj.name)

    def test_required_empty_name_is_rejected_without_writes(self):
        for route,obj in [('brand_create',None),('brand_update',self.brand)]:
            for name in ('', '   '):
                with self.subTest(route=route,name=name), self.isolated_case():
                    before=self.rows()
                    response=self.post(route,{'name':name},obj)
                    self.assertEqual(response.status_code,200)
                    self.assertIn('name',response.context['form'].errors)
                    self.assertEqual(self.rows(),before)

    def test_global_name_uniqueness_includes_inactive_brands(self):
        for route,obj in [('brand_create',None),('brand_update',self.brand)]:
            for name in (self.brand.name,self.inactive.name):
                if obj and name==obj.name:
                    continue
                with self.subTest(route=route,name=name), self.isolated_case():
                    before=self.rows()
                    response=self.post(route,{'name':name},obj)
                    self.assertEqual(response.status_code,200)
                    self.assertIn('name',response.context['form'].errors)
                    self.assertEqual(self.rows(),before)

    def test_concurrent_unique_collision_is_controlled_without_500(self):
        for route,obj in [('brand_create',None),('brand_update',self.brand)]:
            with self.subTest(route=route), self.isolated_case():
                before=self.rows()
                with patch.object(Brand,'save',side_effect=IntegrityError('private concurrency detail')):
                    response=self.post(route,{'name':'Nueva marca'},obj)
                self.assertEqual(response.status_code,200)
                self.assertTrue(response.context['form'].errors)
                self.assertNotContains(response,'private concurrency detail')
                self.assertEqual(self.rows(),before)

    def test_get_and_head_deactivation_show_confirmation_without_writes(self):
        before=self.rows()
        for method in ('get','head'):
            with self.subTest(method=method):
                response=getattr(self.client,method)(self.url('brand_delete',self.brand))
                self.assertEqual(response.status_code,200)
                self.assertEqual(self.rows(),before)
                if method=='get':
                    forms=html_support.Document(response.content.decode()).matching('form',method='post')
                    self.assertTrue(forms)
                    self.assertContains(response,'csrfmiddlewaretoken')
                    self.assertContains(response,self.brand.name)

    def test_post_deactivation_requires_csrf_and_preserves_shared_product_references(self):
        browser=Client(enforce_csrf_checks=True); browser.force_login(self.actor)
        before=self.rows(); products=list(Product.objects.order_by('pk').values())
        self.assertEqual(self.post('brand_delete',{},self.brand,browser).status_code,403)
        self.assertEqual(self.rows(),before)
        browser.get(self.url('brand_delete',self.brand))
        response=self.post('brand_delete',{'csrfmiddlewaretoken':browser.cookies['csrftoken'].value},self.brand,browser)
        self.assertEqual(response.status_code,302)
        self.brand.refresh_from_db()
        self.assertFalse(self.brand.is_active)
        self.assertIsNotNone(self.brand.deleted_at)
        self.assertEqual(self.brand.updated_by_id,self.actor.pk)
        self.assertEqual(Brand.objects.count(),len(before))
        original=next(row for row in before if row['id']==self.brand.pk)
        self.assertEqual(self.brand.name,original['name'])
        self.assertEqual(list(Product.objects.order_by('pk').values()),products)
        self.assertEqual(Product.objects.filter(brand_id=self.brand.pk).count(),2)

    def test_list_uses_shared_sisadmi_actions_with_accessible_names_and_local_icons(self):
        response=self.client.get(self.url('brand_list'))
        self.assertTemplateUsed(response,'core/components/entity_action.html')
        expected=[('Adicionar marca','add','brand_create',None),('Consultar marca','view','brand_detail',self.brand),
                  ('Editar marca','edit','brand_update',self.brand),('Eliminar marca','delete','brand_delete',self.brand)]
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
        response=self.client.get(self.url('brand_list'))
        controls=self.controls(response)
        targets={n.attrs.get('href') for n in controls}
        self.assertIn(self.url('brand_detail',self.brand),targets)
        for route,obj in [('brand_create',None),('brand_update',self.brand),('brand_delete',self.brand)]:
            self.assertNotIn(self.url(route,obj),targets)

    def test_action_controls_are_keyboard_focusable_with_shared_size_and_focus_style(self):
        response=self.client.get(self.url('brand_list'))
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
        page=self.client.get(self.url('brand_create'))
        form=page.context['form']
        self.assertEqual(set(form.fields),{'name'})
        native=html_support.Document(page.content.decode()).matching('form',method='post')
        self.assertTrue(native)
        self.assertContains(page, 'name="name"')
        created=self.post('brand_create',{'name':'Sin JavaScript'})
        self.assertEqual(created.status_code,302)
        brand=Brand.objects.get(name='Sin JavaScript')
        self.assertEqual(self.post('brand_update',{'name':'Editada'},brand).status_code,302)
        self.assertEqual(self.client.get(self.url('brand_delete',brand)).status_code,200)
        self.assertEqual(self.post('brand_delete',{},brand).status_code,302)
        brand.refresh_from_db(); self.assertFalse(brand.is_active)
