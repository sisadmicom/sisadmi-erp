"""CAT-01.2D RED: Company-scoped ProductSubGroup maintenance.

Routes: subgroup_list/detail/create/update/delete. Company is validated server
context; company=NULL subgroups have no administration or visibility here.
Eligible new parents are active own-Company or existing global groups. This is
compatible with the legacy SubGroup form and read-only global Group policy;
it changes neither Product's selector policy nor Group modification authority.
An existing inactive own/global parent can be retained during a valid edit,
but is not eligible for another/new assignment. Foreign parents are rejected.
Name and group are the maintenance fields; historical taxes remain untouched.
No new policy for tax editing, global subgroups or automatic Product rewriting.

DEFERRED PRODUCT RETURN CONTRACT (documentation, not executable integration):
Normal SubGroup create from an authorized Product draft must retain that SAME
draft, Company, actor, parent-group selection and preservable values. Cancel
preserves previous selection. Save persists independently and selects ONLY the
new subgroup in the authorized subgroup field, validating its Group coherence.
Parent operation, field, purpose, actor, expiration, anti-replay and safe local
return are revalidated; continuation grants no extra/global authority and does
not save Product. No storage representation or return API is prescribed here.
"""
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.staticfiles import finders
from django.db import IntegrityError
from django.test import Client, TestCase
from django.templatetags.static import static

from catalog.forms import ProductSubGroupForm
from catalog.models import Product, ProductGroup, ProductSubGroup, Tax
from catalog.services import TaxResolver
from catalog.tests import test_product_group_maintenance_cat012c_red as group_harness
from people.tests import person_ui_support as html_support


class ProductSubGroupMaintenanceRedTests(TestCase):
    # Reuse stable fixture/utilities and generic Company guards explicitly,
    # without inheriting or discovering unrelated ProductGroup test methods.
    url = group_harness.ProductGroupMaintenanceRedTests.url
    post = group_harness.ProductGroupMaintenanceRedTests.post
    controls = group_harness.ProductGroupMaintenanceRedTests.controls
    isolated_case = group_harness.ProductGroupMaintenanceRedTests.isolated_case
    assert_context_rejected = group_harness.ProductGroupMaintenanceRedTests.assert_context_rejected
    test_all_routes_require_authentication = group_harness.ProductGroupMaintenanceRedTests.test_all_routes_require_authentication
    test_each_operation_requires_its_own_permission = group_harness.ProductGroupMaintenanceRedTests.test_each_operation_requires_its_own_permission
    test_company_membership_is_not_catalog_permission = group_harness.ProductGroupMaintenanceRedTests.test_company_membership_is_not_catalog_permission
    test_effective_company_context_is_revalidated_on_all_operations = group_harness.ProductGroupMaintenanceRedTests.test_effective_company_context_is_revalidated_on_all_operations
    test_staff_and_superuser_do_not_bypass_company_membership = group_harness.ProductGroupMaintenanceRedTests.test_staff_and_superuser_do_not_bypass_company_membership

    def setUp(self):
        group_harness.ProductGroupMaintenanceRedTests.setUp(self)
        self.foreign_subgroup = ProductSubGroup.objects.create(
            company=self.other_company, group=self.foreign, name='SUBGRUPO AJENO CONFIDENCIAL')
        self.global_subgroup = ProductSubGroup.objects.create(
            group=self.global_group, name='Subgrupo global legado')
        self.global_parent_subgroup = ProductSubGroup.objects.create(
            company=self.company, group=self.global_group, name='Subgrupo empresarial de padre global')
        self.inactive_subgroup = ProductSubGroup.objects.create(
            company=self.company, group=self.group, name='Subgrupo inactivo', is_active=False)
        self.historical = ProductSubGroup.objects.create(
            company=self.company, group=self.inactive, name='Asociación histórica')
        self.subgroup.taxes.add(self.iva, self.ice)
        self.historical.taxes.add(self.iva)

    def grant(self, *operations):
        self.actor.user_permissions.set(Permission.objects.filter(
            content_type__app_label='catalog', content_type__model='productsubgroup',
            codename__in=[op + '_productsubgroup' for op in operations]))
        for cache in ('_perm_cache', '_user_perm_cache', '_group_perm_cache'):
            self.actor.__dict__.pop(cache, None)

    def context(self, browser):
        group_harness.ProductGroupMaintenanceRedTests.context(self, browser)

    def snapshot(self):
        return {model._meta.label: list(model.objects.order_by('pk').values())
                for model in (ProductSubGroup, ProductSubGroup.taxes.through,
                              ProductGroup, ProductGroup.taxes.through, Product, Tax)}

    def routes(self):
        return [('subgroup_list', None), ('subgroup_detail', self.subgroup),
                ('subgroup_create', None), ('subgroup_update', self.subgroup),
                ('subgroup_delete', self.subgroup)]

    def request_route(self, route, obj):
        if route in ('subgroup_list', 'subgroup_detail'):
            return self.client.get(self.url(route, obj))
        return self.post(route, self.payload(name='Intento'), obj)

    def payload(self, **changes):
        return {'name': 'Subgrupo nuevo', 'group': str(self.group.pk), **changes}

    def test_existing_global_parent_eligibility_and_fixture_characterization(self):
        self.assertEqual(self.product.subgroup_id, self.subgroup.pk)
        self.assertEqual(self.subgroup.company_id, self.company.pk)
        self.assertIsNone(self.global_subgroup.company_id)
        self.assertIsNone(self.global_group.company_id)
        form = ProductSubGroupForm(
            data={'name': 'Caracterización', 'group': self.global_group.pk},
            instance=ProductSubGroup(company=self.company))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.instance.company_id, self.company.pk)
        self.assertEqual(form.cleaned_data['group'], self.global_group)
        self.assertNotIn('company', form.fields)

    def test_existing_subgroup_tax_priority_is_unchanged(self):
        self.subgroup.taxes.set([self.iva])
        self.assertEqual(list(TaxResolver.resolve(self.product)), [self.iva])
        self.product.taxes.add(self.ice)
        self.assertEqual(list(TaxResolver.resolve(self.product)), [self.ice])

    def test_subgroup_permission_does_not_authorize_parent_group_changes(self):
        self.assertFalse(self.actor.has_perm('catalog.change_productgroup'))
        before = self.snapshot()
        response = self.post('group_update', {'name': 'Intento'}, self.group)
        self.assertIn(response.status_code, (403, 404))
        self.assertEqual(self.snapshot(), before)

    def test_group_permissions_cannot_replace_subgroup_permissions(self):
        self.grant()
        self.actor.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='catalog', content_type__model='productgroup'))
        for route, obj in self.routes():
            with self.subTest(route=route), self.isolated_case():
                before = self.snapshot()
                self.assertIn(self.request_route(route, obj).status_code, (403, 404))
                self.assertEqual(self.snapshot(), before)

    def test_list_is_company_scoped_and_shows_authorized_parent_groups(self):
        response = self.client.get(self.url('subgroup_list'))
        self.assertEqual(response.status_code, 200)
        for obj in (self.subgroup, self.global_parent_subgroup):
            self.assertContains(response, obj.name)
            self.assertContains(response, obj.group.name)
        for name in (self.foreign_subgroup.name, self.foreign.name, self.global_subgroup.name):
            self.assertNotContains(response, name)

    def test_detail_is_read_only_and_scope_isolation_is_enforced(self):
        for obj in (self.subgroup, self.global_parent_subgroup, self.foreign_subgroup, self.global_subgroup):
            with self.subTest(object=obj.name), self.isolated_case():
                before = self.snapshot()
                response = self.client.get(self.url('subgroup_detail', obj))
                if obj.company_id != self.company.pk:
                    self.assertIn(response.status_code, (403, 404))
                    self.assertNotContains(response, obj.name, status_code=response.status_code)
                else:
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, obj.name)
                    self.assertContains(response, obj.group.name)
                    self.assertNotContains(response, self.foreign_subgroup.name)
                self.assertEqual(self.snapshot(), before)

    def test_create_uses_server_company_and_allows_eligible_read_only_parents(self):
        self.actor.profile.companies.add(self.other_company)
        self.grant('add')
        for parent in (self.group, self.global_group):
            with self.subTest(parent=parent.name), self.isolated_case():
                before = self.snapshot()
                response = self.post('subgroup_create', self.payload(
                    company=self.other_company.pk, company_id=self.other_company.pk,
                    branch='browser-value', group=parent.pk, is_active='', created_by='browser-value'))
                self.assertEqual(response.status_code, 302)
                created = ProductSubGroup.objects.get(company=self.company, name='Subgrupo nuevo')
                self.assertEqual((created.company_id, created.group_id, created.created_by_id),
                                 (self.company.pk, parent.pk, self.actor.pk))
                self.assertTrue(created.is_active)
                self.assertFalse(created.taxes.exists())
                after = self.snapshot()
                for model in (ProductGroup, ProductGroup.taxes.through, Product, Tax):
                    self.assertEqual(after[model._meta.label], before[model._meta.label])

    def test_edit_preserves_company_parent_tax_assignments_and_product(self):
        before = self.snapshot()
        response = self.post('subgroup_update', self.payload(
            name='Subgrupo editado', company=self.other_company.pk, company_id=self.other_company.pk), self.subgroup)
        self.assertEqual(response.status_code, 302)
        self.subgroup.refresh_from_db()
        self.assertEqual((self.subgroup.company_id, self.subgroup.group_id, self.subgroup.updated_by_id),
                         (self.company.pk, self.group.pk, self.actor.pk))
        self.assertEqual(self.subgroup.name, 'Subgrupo editado')
        after = self.snapshot()
        for model in (ProductSubGroup.taxes.through, ProductGroup, ProductGroup.taxes.through, Product, Tax):
            self.assertEqual(after[model._meta.label], before[model._meta.label])

    def test_foreign_and_global_subgroup_idor_is_rejected_even_with_both_memberships(self):
        self.actor.profile.companies.add(self.other_company)
        for obj in (self.foreign_subgroup, self.global_subgroup):
            for route in ('subgroup_detail', 'subgroup_update', 'subgroup_delete'):
                for method in ('get', 'post'):
                    with self.subTest(object=obj.name, route=route, method=method), self.isolated_case():
                        before = self.snapshot()
                        response = (self.client.get(self.url(route, obj)) if method == 'get'
                                    else self.post(route, self.payload(name='Intento'), obj))
                        self.assertIn(response.status_code, (403, 404))
                        self.assertNotContains(response, obj.name, status_code=response.status_code)
                        self.assertEqual(self.snapshot(), before)

    def test_parent_selector_is_scoped_and_forms_are_unbound_on_get(self):
        for route, obj in [('subgroup_create', None), ('subgroup_update', self.subgroup)]:
            with self.subTest(route=route):
                response = self.client.get(self.url(route, obj))
                self.assertEqual(response.status_code, 200)
                form = response.context['form']
                self.assertFalse(form.is_bound)
                self.assertEqual(set(form.fields), {'group', 'name'})
                self.assertTrue(form.fields['group'].required)
                choices = set(form.fields['group'].queryset.values_list('pk', flat=True))
                self.assertTrue({self.group.pk, self.global_group.pk}.issubset(choices))
                self.assertNotIn(self.foreign.pk, choices)
                self.assertNotIn(self.inactive.pk, choices)
                if obj:
                    self.assertEqual(str(form['group'].value()), str(obj.group_id))
                    self.assertEqual(form['name'].value(), obj.name)

    def test_server_rejects_foreign_inactive_missing_and_malformed_parent_ids(self):
        missing_id = max(ProductGroup.objects.values_list('pk', flat=True)) + 1
        for route, obj in [('subgroup_create', None), ('subgroup_update', self.subgroup)]:
            for parent_id in (self.foreign.pk, self.inactive.pk, missing_id, 'invalid-id'):
                with self.subTest(route=route, parent=parent_id), self.isolated_case():
                    before = self.snapshot()
                    response = self.post(route, self.payload(group=parent_id), obj)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn('group', response.context['form'].errors)
                    self.assertNotContains(response, self.foreign.name)
                    self.assertEqual(self.snapshot(), before)

    def test_name_and_parent_are_required_without_accidental_tax_writes(self):
        for route, obj in [('subgroup_create', None), ('subgroup_update', self.subgroup)]:
            for field in ('name', 'group'):
                with self.subTest(route=route, field=field), self.isolated_case():
                    before = self.snapshot()
                    response = self.post(route, self.payload(**{field: '   '}), obj)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(field, response.context['form'].errors)
                    self.assertEqual(self.snapshot(), before)

    def test_composite_uniqueness_includes_inactive_subgroups(self):
        cases = [('subgroup_create', None, self.subgroup.name),
                 ('subgroup_create', None, self.inactive_subgroup.name),
                 ('subgroup_update', self.subgroup, self.inactive_subgroup.name)]
        for route, obj, name in cases:
            with self.subTest(route=route, name=name), self.isolated_case():
                before = self.snapshot()
                response = self.post(route, self.payload(name=name), obj)
                self.assertEqual(response.status_code, 200)
                self.assertIn('name', response.context['form'].errors)
                self.assertEqual(self.snapshot(), before)
        another = ProductGroup.objects.create(company=self.company, name='Otro padre')
        self.assertEqual(self.post('subgroup_create', self.payload(name=self.subgroup.name, group=another.pk)).status_code, 302)
        self.assertTrue(ProductSubGroup.objects.filter(company=self.company, group=another, name=self.subgroup.name).exists())

    def test_composite_uniqueness_is_company_scoped_for_shared_global_parent(self):
        ProductSubGroup.objects.create(company=self.other_company, group=self.global_group, name='Nombre compartido')
        response = self.post('subgroup_create', self.payload(name='Nombre compartido', group=self.global_group.pk))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ProductSubGroup.objects.filter(company=self.company, group=self.global_group, name='Nombre compartido').exists())

    def test_concurrent_uniqueness_collision_is_controlled_without_500(self):
        for route, obj in [('subgroup_create', None), ('subgroup_update', self.subgroup)]:
            with self.subTest(route=route), self.isolated_case():
                before = self.snapshot()
                with patch.object(ProductSubGroup, 'save', side_effect=IntegrityError('private concurrency detail')):
                    response = self.post(route, self.payload(), obj)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertNotContains(response, 'private concurrency detail')
                self.assertEqual(self.snapshot(), before)

    def test_historical_inactive_parent_can_be_kept_without_allowing_new_assignment(self):
        page = self.client.get(self.url('subgroup_update', self.historical))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(str(page.context['form']['group'].value()), str(self.inactive.pk))
        before = self.snapshot()
        response = self.post('subgroup_update', self.payload(name='Histórico editado', group=self.inactive.pk), self.historical)
        self.assertEqual(response.status_code, 302)
        self.historical.refresh_from_db()
        self.assertEqual(self.historical.group_id, self.inactive.pk)
        after = self.snapshot()
        for model in (ProductSubGroup.taxes.through, ProductGroup, ProductGroup.taxes.through, Product, Tax):
            self.assertEqual(after[model._meta.label], before[model._meta.label])
        other = ProductGroup.objects.create(company=self.company, name='Otro inactivo', is_active=False)
        for route, obj, parent in [('subgroup_create', None, self.inactive), ('subgroup_update', self.historical, other)]:
            with self.subTest(route=route), self.isolated_case():
                before = self.snapshot()
                response = self.post(route, self.payload(group=parent.pk), obj)
                self.assertEqual(response.status_code, 200)
                self.assertIn('group', response.context['form'].errors)
                self.assertEqual(self.snapshot(), before)

    def test_historical_global_parent_is_retained_without_modifying_it(self):
        ProductGroup.objects.filter(pk=self.global_group.pk).update(is_active=False)
        before = self.snapshot()
        response = self.post('subgroup_update', self.payload(name='Global histórico', group=self.global_group.pk), self.global_parent_subgroup)
        self.assertEqual(response.status_code, 302)
        self.global_parent_subgroup.refresh_from_db()
        self.assertEqual(self.global_parent_subgroup.group_id, self.global_group.pk)
        after = self.snapshot()
        for model in (ProductGroup, ProductGroup.taxes.through, ProductSubGroup.taxes.through, Product, Tax):
            self.assertEqual(after[model._meta.label], before[model._meta.label])

    def test_get_and_head_deactivation_confirm_without_writes(self):
        before = self.snapshot()
        for method in ('get', 'head'):
            response = getattr(self.client, method)(self.url('subgroup_delete', self.subgroup))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.snapshot(), before)
            if method == 'get':
                self.assertTrue(html_support.Document(response.content.decode()).matching('form', method='post'))
                self.assertContains(response, 'csrfmiddlewaretoken')
                self.assertContains(response, self.subgroup.name)

    def test_post_deactivation_requires_csrf_and_preserves_product_and_taxes(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.actor)
        self.context(browser)
        before = self.snapshot()
        self.assertEqual(self.post('subgroup_delete', {}, self.subgroup, browser).status_code, 403)
        self.assertEqual(self.snapshot(), before)
        browser.get(self.url('subgroup_delete', self.subgroup))
        response = self.post('subgroup_delete', {'csrfmiddlewaretoken': browser.cookies['csrftoken'].value}, self.subgroup, browser)
        self.assertEqual(response.status_code, 302)
        self.subgroup.refresh_from_db()
        self.assertFalse(self.subgroup.is_active)
        self.assertIsNotNone(self.subgroup.deleted_at)
        self.assertEqual(self.subgroup.updated_by_id, self.actor.pk)
        self.assertEqual(ProductSubGroup.objects.count(), len(before[ProductSubGroup._meta.label]))
        self.assertEqual((self.subgroup.company_id, self.subgroup.group_id), (self.company.pk, self.group.pk))
        after = self.snapshot()
        for model in (ProductSubGroup.taxes.through, ProductGroup, ProductGroup.taxes.through, Product, Tax):
            self.assertEqual(after[model._meta.label], before[model._meta.label])

    def test_list_uses_shared_sisadmi_actions_with_accessible_local_icons(self):
        response = self.client.get(self.url('subgroup_list'))
        self.assertTemplateUsed(response, 'core/components/entity_action.html')
        actions = [('Adicionar subgrupo', 'add', 'subgroup_create', None),
                   ('Consultar subgrupo', 'view', 'subgroup_detail', self.subgroup),
                   ('Editar subgrupo', 'edit', 'subgroup_update', self.subgroup),
                   ('Eliminar subgrupo', 'delete', 'subgroup_delete', self.subgroup)]
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

    def test_view_only_actions_remain_keyboard_accessible_and_consistent(self):
        self.grant('view')
        response = self.client.get(self.url('subgroup_list'))
        self.assertEqual(response.status_code, 200)
        controls = self.controls(response)
        targets = {n.attrs.get('href') for n in controls}
        self.assertIn(self.url('subgroup_detail', self.subgroup), targets)
        self.assertNotIn(self.url('subgroup_create'), targets)
        self.assertNotIn(self.url('subgroup_update', self.subgroup), targets)
        self.assertNotIn(self.url('subgroup_delete', self.subgroup), targets)
        actions = [n for n in controls if 'entity-action' in n.attrs.get('class', '').split()]
        self.assertTrue(actions)
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
        page = self.client.get(self.url('subgroup_create'))
        self.assertEqual(page.status_code, 200)
        self.assertTrue(html_support.Document(page.content.decode()).matching('form', method='post'))
        self.assertContains(page, 'name="name"')
        self.assertContains(page, 'name="group"')
        self.assertEqual(self.post('subgroup_create', self.payload(name='Subgrupo sin JavaScript')).status_code, 302)
        created = ProductSubGroup.objects.get(company=self.company, name='Subgrupo sin JavaScript')
        self.assertEqual(self.post('subgroup_update', self.payload(name='Editado'), created).status_code, 302)
        self.assertEqual(self.client.get(self.url('subgroup_delete', created)).status_code, 200)
        self.assertEqual(self.post('subgroup_delete', {}, created).status_code, 302)
        created.refresh_from_db()
        self.assertFalse(created.is_active)
        self.assertEqual(list(Product.objects.order_by('pk').values()), products)
