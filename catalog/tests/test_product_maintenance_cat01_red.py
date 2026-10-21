"""CAT-01 RED: normal catalog maintenance, isolation and logical deactivation.

No new inventory policy: service/stock flags and tax priority are characterized.
Inactive relationships already assigned may be kept during unrelated edits;
new assignments must reject them. Global annex scope is permission-based.
Brand route names follow the existing unnamespaced unit/product convention;
missing endpoints are expected RED failures, not harness exceptions.
"""
from decimal import Decimal
from contextlib import contextmanager
from unittest.mock import patch
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import NoReverseMatch, reverse

from catalog.models import Product, ProductGroup, ProductSubGroup, Tax, Brand, UnitMeasure
from catalog.services import TaxResolver, TaxCalculationService
from catalog.tests import test_tax_resolver as tax_fixtures
from core.models import Company, Branch
from inventory.models import Warehouse, Stock, StockMovement
from inventory.services.stock.increase_stock import IncreaseStock
from inventory.constants.movement_type import MovementType
from people.models import Person


class ProductMaintenanceRedTests(TestCase):
    def setUp(self):
        # Reuse the existing tax/catalog fixture without inheriting its tests.
        tax_fixtures.TaxResolverTest.setUp(self)
        self.other_company = Company.objects.create(person=Person.objects.create(
            identification='1790000001002', person_type='LEGAL', full_name='Empresa ajena'),
            commercial_name='Empresa ajena')
        self.foreign_product = Product.objects.create(company=self.other_company,
            code='FOREIGN', name='PRODUCTO CONFIDENCIAL AJENO')
        self.branch = Branch.objects.create(company=self.company, name='Sucursal', code='01')
        self.unit = UnitMeasure.objects.create(code='UND', name='Unidad')
        self.brand = Brand.objects.create(name='Marca')
        self.user = get_user_model().objects.create_user(username='catalog-actor')
        self.user.profile.companies.add(self.company)
        self.user.profile.branches.add(self.branch)
        self.client.force_login(self.user)
        self.authorize()
        self.context(self.client)

    def authorize(self, *codes):
        permissions = Permission.objects.filter(content_type__app_label='catalog')
        if codes:
            permissions = permissions.filter(codename__in=codes)
        self.user.user_permissions.set(permissions)
        for attr in ('_perm_cache','_user_perm_cache','_group_perm_cache'):
            self.user.__dict__.pop(attr, None)

    def context(self, client):
        session = client.session
        session['company_id'] = self.company.pk
        session['branch_id'] = self.branch.pk
        session.save()

    def url(self, name, obj=None):
        try:
            return reverse(name, args=[obj.pk] if obj else [])
        except NoReverseMatch:
            self.fail('Producción faltante: mantenimiento normal '+name)

    def payload(self, **changes):
        return {'code':'NEW', 'name':'Producto nuevo', 'cost_price':'10.00', 'sale_price':'20.00',
                'group':str(self.group.pk), 'subgroup':str(self.subgroup.pk),
                'brand':str(self.brand.pk), 'unit_measure':str(self.unit.pk),
                'stock_control':'on', **changes}

    @contextmanager
    def isolated_case(self):
        # A failing subtest must not leave an unexpected production write that
        # masks the independent contract exercised by the next subtest.
        with transaction.atomic():
            try:
                yield
            finally:
                transaction.set_rollback(True)

    def send(self, name, data, obj=None, client=None):
        # Isolate DB IntegrityError paths so a production HTTP 500 is an assertion
        # failure and cannot poison this TestCase's surrounding transaction.
        client = client or self.client
        client.raise_request_exception = False
        with transaction.atomic():
            response = client.post(self.url(name,obj), data)
        return response

    def assert_rejected(self, response):
        self.assertIn(response.status_code, (200,400,403,404,409,422),
                      'Se exige rechazo controlado, no éxito ni HTTP 500')

    def test_all_existing_catalog_views_require_authentication(self):
        anonymous = Client(raise_request_exception=False)
        routes = [('product_list',None),('product_create',None),('product_update',self.product),
                  ('product_delete',self.product),('unit_list',None),('unit_create',None),
                  ('unit_update',self.unit),('unit_delete',self.unit)]
        for name,obj in routes:
            with self.subTest(route=name), self.isolated_case():
                response = anonymous.get(self.url(name,obj))
                self.assertIn(response.status_code,(302,401,403))
                if response.status_code==302:
                    self.assertEqual(urlsplit(response.url).path, reverse('login'))
        self.product.refresh_from_db(); self.unit.refresh_from_db()
        self.assertTrue(self.product.is_active and self.unit.is_active)

    def test_product_operations_require_their_own_explicit_permissions(self):
        operations = [('product_list',None,'view_product'),('product_detail',self.product,'view_product'),
                      ('product_create',None,'add_product'),('product_update',self.product,'change_product'),
                      ('product_delete',self.product,'delete_product')]
        for name,obj,required in operations:
            with self.subTest(operation=name), self.isolated_case():
                self.authorize(*[c for c in ('view_product','add_product','change_product','delete_product') if c!=required])
                response = (self.client.get(self.url(name,obj)) if name in ('product_list','product_detail')
                            else self.send(name,self.payload(code='ATTEMPT'),obj))
                self.assertIn(response.status_code,(403,404))
        self.assertFalse(Product.objects.filter(code='ATTEMPT').exists())
        self.product.refresh_from_db(); self.assertTrue(self.product.is_active)

    def test_global_unit_operations_require_explicit_permissions(self):
        self.authorize('view_product','add_product','change_product','delete_product')
        for name,obj in [('unit_list',None),('unit_create',None),('unit_update',self.unit),('unit_delete',self.unit)]:
            with self.subTest(operation=name), self.isolated_case():
                response = self.client.get(self.url(name,obj)) if name=='unit_list' else self.send(name,{'code':'X','name':'Otra'},obj)
                self.assertIn(response.status_code,(403,404))
        self.unit.refresh_from_db(); self.assertTrue(self.unit.is_active)
        self.assertFalse(UnitMeasure.objects.filter(code='X').exists())

    def test_global_brand_operations_require_authentication_and_explicit_permissions(self):
        self.authorize('view_product')
        for name,obj in [('brand_list',None),('brand_create',None),('brand_update',self.brand),('brand_delete',self.brand)]:
            with self.subTest(operation=name), self.isolated_case():
                url = self.url(name,obj)
                self.assertIn(Client().get(url).status_code,(302,401,403))
                response = self.client.get(url) if name=='brand_list' else self.send(name,{'name':'Otra marca'},obj)
                self.assertIn(response.status_code,(403,404))
        self.brand.refresh_from_db(); self.assertTrue(self.brand.is_active)

    def test_authorized_product_consultation_is_read_only(self):
        before = list(Product.objects.filter(pk=self.product.pk).values())
        response = self.client.get(self.url('product_detail', self.product))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.code)
        self.assertContains(response, self.product.name)
        self.assertEqual(list(Product.objects.filter(pk=self.product.pk).values()), before)

    def test_global_annex_creation_works_with_explicit_authority(self):
        for route, model, values in [('unit_create',UnitMeasure,{'code':'NEW-U','name':'Unidad nueva'}),
                                     ('brand_create',Brand,{'name':'Marca nueva'})]:
            with self.subTest(operation=route), self.isolated_case():
                response = self.send(route, values)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(model.objects.filter(**values).exists())

    def test_product_list_does_not_disclose_another_company(self):
        response = self.client.get(self.url('product_list'))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,self.product.name)
        self.assertNotContains(response,self.foreign_product.name)

    def test_foreign_product_consult_edit_and_deactivation_are_denied(self):
        for name in ('product_detail','product_update','product_delete'):
            with self.subTest(operation=name), self.isolated_case():
                response = self.client.get(self.url(name,self.foreign_product)) if name=='product_detail' else self.send(name,self.payload(),self.foreign_product)
                self.assertIn(response.status_code,(403,404))
                self.assertNotIn(self.foreign_product.name,response.content.decode())
        self.foreign_product.refresh_from_db()
        self.assertTrue(self.foreign_product.is_active)

    def test_revoked_company_membership_cannot_be_replaced_by_post_company(self):
        self.user.profile.companies.clear()
        response = self.send('product_create',self.payload(company=self.other_company.pk))
        self.assertNotEqual(response.status_code,500)
        self.assertFalse(Product.objects.filter(code='NEW').exists())

    def test_company_is_server_owned_and_product_has_no_branch_scope(self):
        response = self.send('product_create',self.payload(company=self.other_company.pk,branch=999999))
        self.assertEqual(response.status_code,302)
        product = Product.objects.get(code='NEW')
        self.assertEqual(product.company_id,self.company.pk)
        self.assertNotIn('branch',[f.name for f in Product._meta.fields])

    def test_product_get_deactivation_never_writes(self):
        original = list(Product.objects.filter(pk=self.product.pk).values())
        response = self.client.get(self.url('product_delete',self.product))
        self.assertIn(response.status_code,(200,405))
        self.assertEqual(list(Product.objects.filter(pk=self.product.pk).values()),original)

    def test_product_post_deactivation_requires_csrf_and_never_physically_deletes(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.user); self.context(browser)
        self.assertEqual(self.send('product_delete',{},self.product,browser).status_code,403)
        self.product.refresh_from_db(); self.assertTrue(self.product.is_active)
        browser.get(self.url('product_create'))
        token = browser.cookies['csrftoken'].value
        response = self.send('product_delete',{'csrfmiddlewaretoken':token},self.product,browser)
        self.assertEqual(response.status_code,302)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)
        self.assertIsNotNone(self.product.deleted_at)
        self.assertEqual(self.product.company_id,self.company.pk)

    def test_code_uniqueness_is_per_company_and_duplicates_are_human_errors(self):
        response = self.send('product_create',self.payload(code=self.product.code))
        self.assert_rejected(response)
        self.assertEqual(Product.objects.filter(company=self.company,code=self.product.code).count(),1)
        response = self.send('product_create',self.payload(code=self.foreign_product.code))
        self.assertEqual(response.status_code,302)
        self.assertTrue(Product.objects.filter(company=self.company,code=self.foreign_product.code).exists())

    def test_duplicate_code_edit_is_rejected_without_changing_persisted_product(self):
        other = Product.objects.create(company=self.company,code='OCCUPIED',name='Otra')
        before = list(Product.objects.filter(pk=self.product.pk).values())
        response = self.send('product_update',self.payload(code=other.code),self.product)
        self.assert_rejected(response)
        self.assertEqual(list(Product.objects.filter(pk=self.product.pk).values()),before)

    def test_concurrent_uniqueness_failure_is_controlled(self):
        with patch.object(Product,'save',side_effect=IntegrityError('simulated concurrent unique collision')):
            response = self.send('product_create',self.payload())
        self.assert_rejected(response)
        self.assertNotIn('simulated concurrent',response.content.decode())
        self.assertFalse(Product.objects.filter(code='NEW').exists())

    def test_negative_prices_are_rejected_on_create_and_edit(self):
        for field in ('cost_price','sale_price'):
            for route,obj in [('product_create',None),('product_update',self.product)]:
                with self.subTest(field=field,route=route), self.isolated_case():
                    values = self.payload(); values[field]='-0.01'
                    response = self.send(route,values,obj)
                    self.assert_rejected(response)
                    self.assertFalse(Product.objects.filter(company=self.company,**{field+'__lt':0}).exists())

    def test_subgroup_must_belong_to_selected_group(self):
        other_group = ProductGroup.objects.create(company=self.company,name='Otro grupo')
        wrong = ProductSubGroup.objects.create(company=self.company,group=other_group,name='Otro subgrupo')
        response = self.send('product_create',self.payload(subgroup=wrong.pk))
        self.assert_rejected(response)
        self.assertFalse(Product.objects.filter(code='NEW').exists())

    def test_foreign_group_subgroup_and_tax_assignments_are_rejected(self):
        group = ProductGroup.objects.create(company=self.other_company,name='Ajeno')
        subgroup = ProductSubGroup.objects.create(company=self.other_company,group=group,name='Ajeno')
        tax = Tax.objects.create(company=self.other_company,name='Ajeno',code='FOREIGN',tax_type='IVA',rate=15)
        for field,obj in [('group',group),('subgroup',subgroup),('taxes',tax)]:
            for route,target in [('product_create',None),('product_update',self.product)]:
                with self.subTest(field=field,operation=route), self.isolated_case():
                    before = list(Product.objects.filter(pk=self.product.pk).values())
                    values=self.payload(); values[field]=[obj.pk] if field=='taxes' else obj.pk
                    self.assert_rejected(self.send(route,values,target))
                    self.assertFalse(Product.objects.filter(code='NEW').exists())
                    self.assertEqual(list(Product.objects.filter(pk=self.product.pk).values()),before)

    def test_new_assignments_exclude_inactive_related_records(self):
        target = Product.objects.create(company=self.company,code='ASSIGNMENT-TARGET',name='Sin anexos')
        for field,obj in [('group',self.group),('subgroup',self.subgroup),('brand',self.brand),('unit_measure',self.unit),('taxes',self.iva)]:
            for route,record in [('product_create',None),('product_update',target)]:
                with self.subTest(field=field,operation=route), self.isolated_case():
                    obj.is_active=False; obj.save(update_fields=['is_active'])
                    values=self.payload(); values[field]=[obj.pk] if field=='taxes' else obj.pk
                    self.assert_rejected(self.send(route,values,record))
                    self.assertFalse(Product.objects.filter(code='NEW').exists())
                    obj.is_active=True

    def test_edit_preserves_already_assigned_inactive_historical_relations(self):
        self.product.brand=self.brand; self.product.unit_measure=self.unit; self.product.save()
        self.product.taxes.add(self.iva)
        for obj in (self.group,self.subgroup,self.brand,self.unit,self.iva):
            obj.is_active=False; obj.save(update_fields=['is_active'])
        response=self.send('product_update',self.payload(code=self.product.code,name='Nombre editado',taxes=[self.iva.pk]),self.product)
        self.assertEqual(response.status_code,302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name,'Nombre editado')
        self.assertEqual((self.product.group_id,self.product.subgroup_id,self.product.brand_id,self.product.unit_measure_id),
                         (self.group.pk,self.subgroup.pk,self.brand.pk,self.unit.pk))
        self.assertEqual(list(self.product.taxes.values_list('pk',flat=True)),[self.iva.pk])

    def test_tax_m2m_is_persisted_on_create(self):
        response=self.send('product_create',self.payload(taxes=[self.iva.pk,self.ice.pk]))
        self.assertEqual(response.status_code,302)
        self.assertSetEqual(set(Product.objects.get(code='NEW').taxes.values_list('pk',flat=True)),{self.iva.pk,self.ice.pk})

    def test_tax_m2m_is_replaced_and_can_be_cleared_on_edit(self):
        self.product.taxes.add(self.iva)
        values=self.payload(code=self.product.code,taxes=[self.ice.pk])
        self.assertEqual(self.send('product_update',values,self.product).status_code,302)
        self.assertSetEqual(set(self.product.taxes.values_list('pk',flat=True)),{self.ice.pk})
        values['taxes']=[]
        self.assertEqual(self.send('product_update',values,self.product).status_code,302)
        self.assertFalse(self.product.taxes.exists())

    def test_get_edit_is_unbound_and_shows_persisted_values(self):
        response=self.client.get(self.url('product_update',self.product))
        self.assertEqual(response.status_code,200)
        form=response.context['form']
        self.assertFalse(form.is_bound)
        self.assertEqual(form['code'].value(),self.product.code)
        self.assertEqual(form['name'].value(),self.product.name)
        self.assertFalse(form.errors)

    def test_logical_deactivation_preserves_stock_and_movement_history(self):
        warehouse=Warehouse.objects.create(company=self.company,branch=self.branch,code='W',name='Bodega')
        movement=IncreaseStock().execute(company=self.company,branch=self.branch,warehouse=warehouse,
            product=self.product,quantity=Decimal('2'),movement_type=MovementType.PURCHASE,user=self.user)
        before_stock=list(Stock.objects.values()); before_movements=list(StockMovement.objects.values())
        self.assertEqual(self.send('product_delete',{},self.product).status_code,302)
        self.product.refresh_from_db(); self.assertFalse(self.product.is_active)
        self.assertEqual(list(Stock.objects.values()),before_stock)
        self.assertEqual(list(StockMovement.objects.values()),before_movements)

    def test_tax_resolution_priority_and_calculations_remain_unchanged(self):
        self.configuration.taxes.add(self.iva); self.group.taxes.add(self.ice)
        self.subgroup.taxes.add(self.iva); self.product.taxes.add(self.ice)
        for expected,clear in [(self.ice,self.product.taxes),(self.iva,self.subgroup.taxes),
                               (self.ice,self.group.taxes),(self.iva,self.configuration.taxes)]:
            self.assertEqual(list(TaxResolver.resolve(self.product)),[expected])
            self.assertEqual(TaxCalculationService.calculate(Decimal('100'),[expected])[0]['amount'],expected.rate)
            clear.clear()
        self.assertFalse(TaxResolver.resolve(self.product).exists())

    def test_characterization_service_and_stock_flags_do_not_gate_current_inventory_services(self):
        warehouse=Warehouse.objects.create(company=self.company,branch=self.branch,code='W',name='Bodega')
        for service,control in ((False,False),(False,True),(True,False),(True,True)):
            with self.subTest(is_service=service,stock_control=control), self.isolated_case():
                product=Product.objects.create(company=self.company,code=f'FLAGS-{service}-{control}',name='Flags',
                    is_service=service,stock_control=control)
                IncreaseStock().execute(company=self.company,branch=self.branch,warehouse=warehouse,
                    product=product,quantity=Decimal('1'),movement_type=MovementType.PURCHASE,user=self.user)
                self.assertEqual(Stock.objects.get(product=product).quantity,Decimal('1'))
                self.assertEqual(StockMovement.objects.filter(product=product).count(),1)
