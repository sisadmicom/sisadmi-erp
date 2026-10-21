"""CAT-01.2C RED: company-scoped ProductGroup maintenance.

Normal routes: group_list/detail/create/update/delete. Existing company=NULL
annexes are consultable, read-only, within an authorized Company context. No
global administration or new global uniqueness rule is defined. ProductForm,
TaxResolver and operational services keep their existing semantics.
Name-only edits preserve existing taxes: no Tax editor or new tax-assignment
policy is required. Company comes from server context, never browser authority.

DEFERRED PRODUCT RETURN CONTRACT (documentation, not HTTP integration):
Normal Group create from an authorized Product draft preserves the same draft,
actor, Company and previous selection on cancel. Saving persists independently
and selects only the new Company-scoped group in the authorized group field.
Operation, purpose, field, expiration, actor and local return must be bound and
revalidated against forgery, cross-actor reuse and replay. No Product save,
global administration or extra permission follows from a continuation. No
storage format or continuation API is prescribed by this RED.
"""
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.staticfiles import finders
from django.db import IntegrityError
from django.test import Client, TestCase
from django.templatetags.static import static
from django.urls import reverse

from catalog.forms import ProductGroupForm
from catalog.models import Product, ProductGroup, ProductSubGroup, Tax
from catalog.services import TaxResolver
from catalog.tests import test_tax_resolver as tax_fixtures
from catalog.tests import test_brand_maintenance_cat012b_red as catalog_harness
from core.models import Company
from people.models import Person
from people.tests import person_ui_support as html_support


class ProductGroupMaintenanceRedTests(TestCase):
    # Reuse test utilities explicitly; do not inherit unrelated Brand tests.
    url = catalog_harness.BrandMaintenanceRedTests.url
    isolated_case = catalog_harness.BrandMaintenanceRedTests.isolated_case
    post = catalog_harness.BrandMaintenanceRedTests.post
    controls = catalog_harness.BrandMaintenanceRedTests.controls

    def setUp(self):
        tax_fixtures.TaxResolverTest.setUp(self)
        self.other_company = Company.objects.create(person=Person.objects.create(
            identification='1790000003002', person_type='LEGAL', full_name='Empresa ajena'),
            commercial_name='Empresa ajena')
        self.foreign = ProductGroup.objects.create(company=self.other_company, name='GRUPO AJENO CONFIDENCIAL')
        self.global_group = ProductGroup.objects.create(name='Grupo global existente')
        self.inactive = ProductGroup.objects.create(company=self.company, name='Grupo inactivo', is_active=False)
        self.group.taxes.add(self.iva, self.ice)
        self.global_group.taxes.add(self.iva)
        self.actor = get_user_model().objects.create_user(username='group-operator')
        self.actor.profile.companies.add(self.company)
        self.grant('view', 'add', 'change', 'delete')
        self.client.force_login(self.actor)
        self.context(self.client)

    def grant(self, *operations):
        self.actor.user_permissions.set(Permission.objects.filter(
            content_type__app_label='catalog', content_type__model='productgroup',
            codename__in=[op + '_productgroup' for op in operations]))
        for cache in ('_perm_cache', '_user_perm_cache', '_group_perm_cache'):
            self.actor.__dict__.pop(cache, None)

    def context(self, browser):
        session = browser.session
        session['company_id'] = self.company.pk
        session['branch_id'] = None
        session.save()

    def snapshot(self):
        return {model._meta.label: list(model.objects.order_by('pk').values())
                for model in (ProductGroup, ProductGroup.taxes.through, Product, ProductSubGroup, Tax)}

    def routes(self):
        return [('group_list', None), ('group_detail', self.group), ('group_create', None),
                ('group_update', self.group), ('group_delete', self.group)]

    def request_route(self, route, obj):
        if route in ('group_list', 'group_detail'):
            return self.client.get(self.url(route, obj))
        return self.post(route, {'name': 'Intento'}, obj)

    def assert_context_rejected(self, response, inactive_actor=False):
        self.assertIn(response.status_code, (302, 403, 404))
        if response.status_code == 302:
            self.assertEqual(urlsplit(response.url).path,
                             reverse('login' if inactive_actor else 'select_company'))
            self.assertFalse(urlsplit(response.url).netloc)
        self.assertNotContains(response, self.foreign.name, status_code=response.status_code)

    def test_existing_fixture_and_form_characterization(self):
        self.assertEqual(self.group.company_id, self.company.pk)
        self.assertIsNone(self.global_group.company_id)
        self.assertEqual(self.product.group_id, self.group.pk)
        self.assertEqual(self.subgroup.group_id, self.group.pk)
        self.assertSetEqual(set(self.group.taxes.values_list('pk', flat=True)), {self.iva.pk, self.ice.pk})
        self.assertNotIn('company', ProductGroupForm().fields)
        self.assertIn('taxes', ProductGroupForm().fields)

    def test_existing_global_group_tax_resolution_is_unchanged(self):
        self.product.group = self.global_group
        self.product.subgroup = None
        self.product.save(update_fields=['group', 'subgroup'])
        self.assertEqual(list(TaxResolver.resolve(self.product)), [self.iva])
        self.product.taxes.add(self.ice)
        self.assertEqual(list(TaxResolver.resolve(self.product)), [self.ice])

    def test_all_routes_require_authentication(self):
        browser = Client(raise_request_exception=False)
        for route, obj in self.routes():
            with self.subTest(route=route), self.isolated_case():
                before = self.snapshot()
                for method in ('get', 'post'):
                    response = getattr(browser, method)(self.url(route, obj))
                    self.assertIn(response.status_code, (302, 401, 403))
                    if response.status_code == 302:
                        self.assertEqual(urlsplit(response.url).path, reverse('login'))
                self.assertEqual(self.snapshot(), before)

    def test_each_operation_requires_its_own_permission(self):
        for (route, obj), required in zip(self.routes(), ('view', 'view', 'add', 'change', 'delete')):
            with self.subTest(route=route), self.isolated_case():
                self.grant(*[op for op in ('view', 'add', 'change', 'delete') if op != required])
                before = self.snapshot()
                self.assertIn(self.request_route(route, obj).status_code, (403, 404))
                self.assertEqual(self.snapshot(), before)

    def test_company_membership_is_not_catalog_permission(self):
        self.grant()
        for route, obj in self.routes():
            with self.subTest(route=route), self.isolated_case():
                before = self.snapshot()
                self.assertIn(self.request_route(route, obj).status_code, (403, 404))
                self.assertEqual(self.snapshot(), before)

    def test_effective_company_context_is_revalidated_on_all_operations(self):
        reasons = ('revoked', 'inactive_company', 'missing_profile', 'inactive_actor',
                   'missing_context', 'foreign_context', 'malformed_context')
        for reason in reasons:
            for route, obj in self.routes():
                with self.subTest(reason=reason, route=route), self.isolated_case():
                    if reason == 'revoked':
                        self.actor.profile.companies.clear()
                    elif reason == 'inactive_company':
                        Company.objects.filter(pk=self.company.pk).update(is_active=False)
                    elif reason == 'missing_profile':
                        type(self.actor.profile).objects.filter(user=self.actor).delete()
                    elif reason == 'inactive_actor':
                        get_user_model().objects.filter(pk=self.actor.pk).update(is_active=False)
                    else:
                        session = self.client.session
                        session['company_id'] = {'missing_context': None,
                            'foreign_context': self.other_company.pk,
                            'malformed_context': 'not-an-id'}[reason]
                        session.save()
                    before = self.snapshot()
                    self.assert_context_rejected(self.request_route(route, obj), reason == 'inactive_actor')
                    self.assertEqual(self.snapshot(), before)

    def test_staff_and_superuser_do_not_bypass_company_membership(self):
        for superuser in (False, True):
            for route, obj in self.routes():
                with self.subTest(superuser=superuser, route=route), self.isolated_case():
                    get_user_model().objects.filter(pk=self.actor.pk).update(is_staff=True, is_superuser=superuser)
                    self.actor.profile.companies.clear()
                    before = self.snapshot()
                    self.assert_context_rejected(self.request_route(route, obj))
                    self.assertEqual(self.snapshot(), before)

    def test_list_is_company_scoped_with_read_only_existing_globals(self):
        response = self.client.get(self.url('group_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.group.name)
        self.assertContains(response, self.global_group.name)
        self.assertNotContains(response, self.foreign.name)
        targets = {n.attrs.get('href') for n in self.controls(response)}
        self.assertIn(self.url('group_detail', self.global_group), targets)
        self.assertNotIn(self.url('group_update', self.global_group), targets)
        self.assertNotIn(self.url('group_delete', self.global_group), targets)

    def test_detail_is_read_only_and_respects_isolation(self):
        for obj in (self.group, self.global_group, self.foreign):
            with self.subTest(object=obj.name), self.isolated_case():
                before = self.snapshot()
                response = self.client.get(self.url('group_detail', obj))
                if obj == self.foreign:
                    self.assertIn(response.status_code, (403, 404))
                    self.assertNotContains(response, obj.name, status_code=response.status_code)
                else:
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, obj.name)
                    self.assertNotContains(response, self.foreign.name)
                self.assertEqual(self.snapshot(), before)

    def test_create_uses_server_company_not_browser_authority(self):
        self.actor.profile.companies.add(self.other_company)
        products = list(Product.objects.order_by('pk').values())
        response = self.post('group_create', {'name': 'Nuevo grupo', 'company': self.other_company.pk,
            'company_id': self.other_company.pk, 'branch': 'browser-value', 'is_active': '', 'created_by': 'browser-value'})
        self.assertEqual(response.status_code, 302)
        created = ProductGroup.objects.get(name='Nuevo grupo')
        self.assertEqual(created.company_id, self.company.pk)
        self.assertEqual(created.created_by_id, self.actor.pk)
        self.assertTrue(created.is_active)
        self.assertFalse(created.taxes.exists())
        self.assertEqual(list(Product.objects.order_by('pk').values()), products)

    def test_name_edit_preserves_company_tax_links_and_references(self):
        before = self.snapshot()
        response = self.post('group_update', {'name': 'Grupo editado', 'company': self.other_company.pk,
                                            'company_id': self.other_company.pk}, self.group)
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertEqual((self.group.name, self.group.company_id, self.group.updated_by_id),
                         ('Grupo editado', self.company.pk, self.actor.pk))
        after = self.snapshot()
        for model in (ProductGroup.taxes.through, Product, ProductSubGroup, Tax):
            self.assertEqual(after[model._meta.label], before[model._meta.label])

    def test_cross_company_idor_is_rejected_even_with_both_memberships(self):
        self.actor.profile.companies.add(self.other_company)
        for route in ('group_detail', 'group_update', 'group_delete'):
            for method in ('get', 'post'):
                with self.subTest(route=route, method=method), self.isolated_case():
                    before = self.snapshot()
                    response = (self.client.get(self.url(route, self.foreign)) if method == 'get'
                                else self.post(route, {'name': 'Intento'}, self.foreign))
                    self.assertIn(response.status_code, (403, 404))
                    self.assertNotContains(response, self.foreign.name, status_code=response.status_code)
                    self.assertEqual(self.snapshot(), before)

    def test_existing_global_groups_cannot_be_modified_by_company_operator(self):
        for route in ('group_update', 'group_delete'):
            for method in ('get', 'post'):
                with self.subTest(route=route, method=method), self.isolated_case():
                    before = self.snapshot()
                    response = (self.client.get(self.url(route, self.global_group)) if method == 'get'
                                else self.post(route, {'name': 'Intento'}, self.global_group))
                    self.assertIn(response.status_code, (403, 404))
                    self.assertEqual(self.snapshot(), before)

    def test_get_forms_are_unbound_and_company_is_not_editable(self):
        for route, obj in [('group_create', None), ('group_update', self.group)]:
            with self.subTest(route=route):
                response = self.client.get(self.url(route, obj))
                self.assertEqual(response.status_code, 200)
                form = response.context['form']
                self.assertFalse(form.is_bound)
                self.assertIn('name', form.fields)
                self.assertNotIn('company', form.fields)
                self.assertNotIn('branch', form.fields)
                if obj:
                    self.assertEqual(form['name'].value(), obj.name)

    def test_required_name_validation_preserves_tax_links(self):
        for route, obj in [('group_create', None), ('group_update', self.group)]:
            for name in ('', '   '):
                with self.subTest(route=route, name=name), self.isolated_case():
                    before = self.snapshot()
                    response = self.post(route, {'name': name}, obj)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn('name', response.context['form'].errors)
                    self.assertEqual(self.snapshot(), before)

    def test_company_name_uniqueness_includes_inactive_groups(self):
        for route, obj, name in [('group_create', None, self.group.name),
                                ('group_create', None, self.inactive.name),
                                ('group_update', self.group, self.inactive.name)]:
            with self.subTest(route=route, name=name), self.isolated_case():
                before = self.snapshot()
                response = self.post(route, {'name': name}, obj)
                self.assertEqual(response.status_code, 200)
                self.assertIn('name', response.context['form'].errors)
                self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.post('group_create', {'name': self.foreign.name}).status_code, 302)
        self.assertTrue(ProductGroup.objects.filter(company=self.company, name=self.foreign.name).exists())

    def test_concurrent_unique_collision_is_controlled_without_500(self):
        for route, obj in [('group_create', None), ('group_update', self.group)]:
            with self.subTest(route=route), self.isolated_case():
                before = self.snapshot()
                with patch.object(ProductGroup, 'save', side_effect=IntegrityError('private concurrency detail')):
                    response = self.post(route, {'name': 'Nombre válido'}, obj)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertNotContains(response, 'private concurrency detail')
                self.assertEqual(self.snapshot(), before)

    def test_get_and_head_deactivation_confirm_without_writes(self):
        before = self.snapshot()
        for method in ('get', 'head'):
            response = getattr(self.client, method)(self.url('group_delete', self.group))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.snapshot(), before)
            if method == 'get':
                self.assertTrue(html_support.Document(response.content.decode()).matching('form', method='post'))
                self.assertContains(response, 'csrfmiddlewaretoken')
                self.assertContains(response, self.group.name)

    def test_post_deactivation_requires_csrf_and_preserves_historical_references(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.actor)
        self.context(browser)
        before = self.snapshot()
        self.assertEqual(self.post('group_delete', {}, self.group, browser).status_code, 403)
        self.assertEqual(self.snapshot(), before)
        browser.get(self.url('group_delete', self.group))
        response = self.post('group_delete', {'csrfmiddlewaretoken': browser.cookies['csrftoken'].value}, self.group, browser)
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertFalse(self.group.is_active)
        self.assertIsNotNone(self.group.deleted_at)
        self.assertEqual(self.group.updated_by_id, self.actor.pk)
        self.assertEqual(self.group.company_id, self.company.pk)
        self.assertEqual(ProductGroup.objects.count(), len(before[ProductGroup._meta.label]))
        after = self.snapshot()
        for model in (ProductGroup.taxes.through, Product, ProductSubGroup, Tax):
            self.assertEqual(after[model._meta.label], before[model._meta.label])

    def test_list_uses_shared_accessible_sisadmi_actions_with_local_icons(self):
        response = self.client.get(self.url('group_list'))
        self.assertTemplateUsed(response, 'core/components/entity_action.html')
        actions = [('Adicionar grupo', 'add', 'group_create', None), ('Consultar grupo', 'view', 'group_detail', self.group),
                   ('Editar grupo', 'edit', 'group_update', self.group), ('Eliminar grupo', 'delete', 'group_delete', self.group)]
        for label, kind, route, obj in actions:
            with self.subTest(action=kind):
                controls = [n for n in self.controls(response) if n.attrs.get('href') == self.url(route, obj)]
                self.assertEqual(len(controls), 1)
                control = controls[0]
                self.assertEqual(control.attrs.get('aria-label'), label)
                self.assertIn('entity-action', control.attrs.get('class', '').split())
                images = [n for n in control.children if isinstance(n, html_support.Element) and n.tag == 'img']
                self.assertEqual(len(images), 1)
                self.assertEqual(images[0].attrs.get('src'), static('core/icons/' + kind + '.svg'))
                self.assertEqual(images[0].attrs.get('alt'), '')
                self.assertIsNotNone(finders.find('core/icons/' + kind + '.svg'))

    def test_view_only_actions_and_keyboard_accessibility(self):
        self.grant('view')
        response = self.client.get(self.url('group_list'))
        self.assertEqual(response.status_code, 200)
        controls = self.controls(response)
        targets = {n.attrs.get('href') for n in controls}
        for obj in (self.group, self.global_group):
            self.assertIn(self.url('group_detail', obj), targets)
            self.assertNotIn(self.url('group_update', obj), targets)
            self.assertNotIn(self.url('group_delete', obj), targets)
        self.assertNotIn(self.url('group_create'), targets)
        actions = [n for n in controls if 'entity-action' in n.attrs.get('class', '').split()]
        self.assertGreaterEqual(len(actions), 2)
        for control in actions:
            self.assertTrue(control.tag == 'button' or control.attrs.get('href'))
            self.assertNotEqual(control.attrs.get('tabindex'), '-1')
            self.assertTrue(control.attrs.get('aria-label'))
        css_file = finders.find('core/css/erp.css')
        self.assertIsNotNone(css_file)
        css = Path(css_file).read_text()
        self.assertIn(':focus-visible', css)
        self.assertRegex(css, r'(?s)\.entity-action\s*\{[^}]*width\s*:')
        self.assertRegex(css, r'(?s)\.entity-action\s*\{[^}]*height\s*:')

    def test_native_no_javascript_cycle_is_independent_of_product(self):
        products = list(Product.objects.order_by('pk').values())
        response = self.client.get(self.url('group_create'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(html_support.Document(response.content.decode()).matching('form', method='post'))
        self.assertContains(response, 'name="name"')
        self.assertEqual(self.post('group_create', {'name': 'Grupo sin JavaScript'}).status_code, 302)
        created = ProductGroup.objects.get(company=self.company, name='Grupo sin JavaScript')
        self.assertEqual(self.post('group_update', {'name': 'Grupo editado'}, created).status_code, 302)
        self.assertEqual(self.client.get(self.url('group_delete', created)).status_code, 200)
        self.assertEqual(self.post('group_delete', {}, created).status_code, 302)
        created.refresh_from_db()
        self.assertFalse(created.is_active)
        self.assertEqual(list(Product.objects.order_by('pk').values()), products)
