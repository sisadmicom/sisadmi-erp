"""CAT-01.2E: native Product -> normal annex -> same Product continuation.

Controls and tokens are discovered from rendered forms, not a new draft API.
Related writes persist independently; Product and its taxes remain untouched
until its own save. Existing global Group eligibility is not widened.
"""
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse

from catalog.models import Brand, Product, ProductGroup, ProductSubGroup, UnitMeasure
from catalog.tests import test_product_maintenance_cat01_red as fixtures
from people.tests.person_ui_support import Document


RELATIONS = (
    ('unit_measure', 'unidad', 'unit', UnitMeasure, 'unitmeasure'),
    ('brand', 'marca', 'brand', Brand, 'brand'),
    ('group', 'grupo', 'group', ProductGroup, 'productgroup'),
    ('subgroup', 'subgrupo', 'subgroup', ProductSubGroup, 'productsubgroup'),
)


class ProductRelatedContinuationRedTests(TestCase):
    isolated_case = fixtures.ProductMaintenanceRedTests.isolated_case
    authorize = fixtures.ProductMaintenanceRedTests.authorize
    context = fixtures.ProductMaintenanceRedTests.context

    def setUp(self):
        fixtures.ProductMaintenanceRedTests.setUp(self)
        self.product.brand = self.brand
        self.product.unit_measure = self.unit
        self.product.save()
        self.product.taxes.set([self.iva, self.ice])
        self.client.raise_request_exception = False

    def snapshot(self):
        return {m._meta.label: list(m.objects.order_by('pk').values()) for m in
                (Product, Product.taxes.through, ProductGroup, ProductGroup.taxes.through,
                 ProductSubGroup, ProductSubGroup.taxes.through, Brand, UnitMeasure)}

    def parent_url(self, editing=False):
        return reverse('product_update', args=[self.product.pk]) if editing else reverse('product_create')

    def payload(self, **changes):
        return {'code': 'DRAFT', 'name': 'Producto ñ <b> & prueba',
                'description': 'Descripción\ncon tildes', 'barcode': '001234',
                'cost_price': '13.25', 'sale_price': '27.50',
                'group': str(self.group.pk), 'subgroup': str(self.subgroup.pk),
                'brand': str(self.brand.pk), 'unit_measure': str(self.unit.pk),
                'is_service': 'on', 'stock_control': 'on',
                'taxes': [str(self.iva.pk), str(self.ice.pk)], **changes}

    def form(self, response):
        self.assertEqual(response.status_code, 200, 'Respuesta humana controlada requerida')
        self.assertIsNotNone(response.context)
        return response.context['form']

    def hidden(self, response):
        return {n.attrs['name']: n.attrs.get('value', '') for n in Document(response.content.decode()).nodes
                if n.tag == 'input' and n.attrs.get('type') == 'hidden' and n.attrs.get('name')}

    def control(self, response, label):
        nodes = [n for n in Document(response.content.decode()).nodes
                 if n.attrs.get('aria-label') == label and n.tag == 'button']
        self.assertEqual(len(nodes), 1, 'Acción contextual nativa POST faltante: ' + label)
        node = nodes[0]
        self.assertEqual(node.attrs.get('type'), 'submit')
        self.assertTrue(node.attrs.get('name'))
        self.assertIn('formnovalidate', node.attrs)
        return {node.attrs['name']: node.attrs.get('value', '')}

    def begin(self, relation=RELATIONS[0], operation='add', editing=False, data=None, browser=None):
        browser = browser or self.client
        label = {'add':'Adicionar', 'view':'Consultar', 'change':'Editar'}[operation] + ' ' + relation[1]
        parent = (browser.get(self.parent_url(True)) if editing or operation == 'add' else
                  browser.post(self.parent_url(), self.payload(code='')))
        self.form(parent)
        posted = self.hidden(parent) | (self.payload() if data is None else data) | self.control(parent, label)
        before = self.snapshot()
        response = browser.post(self.parent_url(editing), posted)
        self.assertEqual(response.status_code, 302, 'Debe abrir mantenimiento normal conservando borrador')
        target = response['Location']
        obj = getattr(self, relation[0] if relation[0] != 'unit_measure' else 'unit')
        suffix = {'add':'create','view':'detail','change':'update'}[operation]
        self.assertEqual(urlsplit(target).path, reverse(relation[2] + '_' + suffix,
                        args=[] if operation == 'add' else [obj.pk]))
        self.assertFalse(urlsplit(target).netloc)
        self.assertTrue(urlsplit(target).query, 'Continuación ligada al servidor requerida')
        self.assertEqual(self.snapshot(), before, 'Navegar no persiste Product ni anexos')
        return target, posted

    def child_data(self, relation, name='Anexo nuevo'):
        return {'name':name, **({'code':'NEW-U'} if relation[0]=='unit_measure' else {}),
                **({'group':str(self.group.pk)} if relation[0]=='subgroup' else {})}

    def finish(self, target, data=None, cancel=False):
        page = self.client.get(target)
        self.form(page)
        response = self.client.post(target, self.hidden(page) | ({'action':'cancel'} if cancel else data))
        self.assertEqual(response.status_code, 302)
        self.assertIn(urlsplit(response['Location']).path,
                      (reverse('product_create'), reverse('product_update',args=[self.product.pk])))
        self.assertFalse(urlsplit(response['Location']).netloc)
        return response['Location'], self.client.get(response['Location'])

    def assert_values(self, response, data, changes=None):
        form = self.form(response)
        expected = data | (changes or {})
        for field in ('code','name','description','barcode','cost_price','sale_price',
                      'group','subgroup','brand','unit_measure'):
            self.assertEqual(str(form[field].value() or ''), str(expected.get(field, '')),
                             'Borrador perdido: '+field)
        for field in ('is_service','stock_control'):
            self.assertEqual(bool(form[field].value()), bool(expected.get(field)))
        self.assertEqual(sorted(map(str,form['taxes'].value() or [])), sorted(expected.get('taxes', [])))

    def assert_denied(self, response):
        self.assertIn(response.status_code, (400,403,404,409,410), 'Token rechazado antes de escritura')

    def test_actions_are_native_accessible_and_permission_bound_on_create_and_edit(self):
        for editing in (False,True):
            page=(self.client.get(self.parent_url(True)) if editing else
                  self.client.post(self.parent_url(),self.payload(code='')))
            for relation in RELATIONS:
                for verb in ('Adicionar','Consultar','Editar'):
                    with self.subTest(editing=editing,field=relation[0],verb=verb):
                        self.control(page,verb+' '+relation[1])

    def test_add_save_selects_only_new_annex_and_preserves_complete_create_and_edit_drafts(self):
        for editing in (False,True):
            for relation in RELATIONS:
                with self.subTest(editing=editing,field=relation[0]), self.isolated_case():
                    before=list(Product.objects.values());taxes=list(Product.taxes.through.objects.values())
                    target,data=self.begin(relation,editing=editing)
                    location,page=self.finish(target,self.child_data(relation))
                    created=relation[3].objects.get(name='Anexo nuevo')
                    changes={relation[0]:str(created.pk)}
                    if relation[0]=='group': changes['subgroup']=''
                    self.assert_values(page,data,changes)
                    self.assertEqual(list(Product.objects.values()),before)
                    self.assertEqual(list(Product.taxes.through.objects.values()),taxes)
                    self.assertEqual(self.client.get(location).status_code,200)

    def test_cancel_all_annexes_keeps_previous_selection_without_writes(self):
        for editing in (False,True):
            for relation in RELATIONS:
                with self.subTest(editing=editing,field=relation[0]), self.isolated_case():
                    before=self.snapshot();target,data=self.begin(relation,editing=editing)
                    _,page=self.finish(target,cancel=True)
                    self.assert_values(page,data);self.assertEqual(self.snapshot(),before)

    def test_edit_keeps_annex_identity_draft_and_tax_associations(self):
        for relation in RELATIONS:
            with self.subTest(field=relation[0]), self.isolated_case():
                target,data=self.begin(relation,'change',True)
                _,page=self.finish(target,self.child_data(relation,'Nombre editado'))
                self.assert_values(page,data)
                self.assertEqual(relation[3].objects.filter(name='Nombre editado').count(),1)
                self.assertEqual(self.product.taxes.count(),2)

    def test_consultation_returns_without_modifying_any_record(self):
        for relation in RELATIONS:
            with self.subTest(field=relation[0]), self.isolated_case():
                before=self.snapshot();target,data=self.begin(relation,'view',True)
                page=self.client.get(target);self.assertEqual(page.status_code,200)
                doc=Document(page.content.decode())
                links=[n.attrs['href'] for n in doc.nodes if n.tag=='a' and n.text.strip() in ('Volver','Volver al producto')]
                self.assertEqual(len(links),1,'Consulta requiere retorno al borrador')
                self.assert_values(self.client.get(links[0]),data)
                self.assertEqual(self.snapshot(),before)

    def test_invalid_values_and_explicit_empty_multiselect_survive_cancel(self):
        for editing in (False,True):
            with self.subTest(editing=editing),self.isolated_case():
                data=self.payload(code='',sale_price='precio inválido',description='',barcode='',taxes=[],stock_control='')
                target,_=self.begin(editing=editing,data=data)
                _,page=self.finish(target,cancel=True);self.assert_values(page,data)

    def test_absent_values_do_not_restore_old_checkbox_or_tax_values(self):
        data=self.payload();[data.pop(k) for k in ('stock_control','is_service','taxes','barcode')]
        target,_=self.begin(editing=True,data=data)
        _,page=self.finish(target,cancel=True);self.assert_values(page,data)

    def test_child_validation_error_preserves_continuation_then_allows_correction(self):
        target,data=self.begin();page=self.client.get(target)
        invalid=self.client.post(target,self.hidden(page)|{'code':'','name':''})
        self.assertTrue(self.form(invalid).errors)
        response=self.client.post(target,self.hidden(invalid)|self.child_data(RELATIONS[0]))
        self.assertEqual(response.status_code,302)
        self.assert_values(self.client.get(response['Location']),data,{'unit_measure':str(UnitMeasure.objects.get(code='NEW-U').pk)})

    def test_initial_transition_requires_csrf(self):
        browser=Client(enforce_csrf_checks=True,raise_request_exception=False)
        browser.force_login(self.user);self.context(browser)
        page=browser.get(self.parent_url());button=self.control(page,'Adicionar unidad')
        before=self.snapshot()
        self.assertEqual(browser.post(self.parent_url(),self.payload()|button).status_code,403)
        self.assertEqual(self.snapshot(),before)

    def test_child_write_requires_csrf(self):
        target,_=self.begin();browser=Client(enforce_csrf_checks=True,raise_request_exception=False)
        browser.cookies=self.client.cookies
        before=self.snapshot();self.assertEqual(browser.post(target,self.child_data(RELATIONS[0])).status_code,403)
        self.assertEqual(self.snapshot(),before)

    def test_annex_permissions_control_buttons_independently(self):
        self.authorize('add_product','change_product')
        for editing in (False,True):
            page=self.client.get(self.parent_url(editing));self.form(page)
            labels=[n.attrs.get('aria-label') for n in Document(page.content.decode()).nodes]
            for relation in RELATIONS:
                for verb in ('Adicionar','Consultar','Editar'):
                    self.assertNotIn(verb+' '+relation[1],labels)

    def test_product_permission_revocation_blocks_child_write(self):
        for editing in (False,True):
            with self.subTest(editing=editing),self.isolated_case():
                target,_=self.begin(editing=editing)
                self.user.user_permissions.remove(Permission.objects.get(codename='change_product' if editing else 'add_product'))
                before=self.snapshot();self.assert_denied(self.client.post(target,self.child_data(RELATIONS[0])))
                self.assertEqual(self.snapshot(),before)

    def test_annex_permission_revocation_blocks_child_write(self):
        for relation in RELATIONS:
            with self.subTest(field=relation[0]),self.isolated_case():
                target,_=self.begin(relation)
                self.user.user_permissions.remove(Permission.objects.get(codename='add_'+relation[4]))
                before=self.snapshot();self.assert_denied(self.client.post(target,self.child_data(relation)))
                self.assertEqual(self.snapshot(),before)

    def test_membership_revocation_blocks_global_and_company_child_writes(self):
        for relation in RELATIONS:
            with self.subTest(field=relation[0]),self.isolated_case():
                target,_=self.begin(relation);self.user.profile.companies.remove(self.company)
                before=self.snapshot();response=self.client.post(target,self.child_data(relation))
                self.assertIn(response.status_code,(302,403,404))
                if response.status_code==302:self.assertEqual(urlsplit(response['Location']).path,reverse('select_company'))
                self.assertEqual(self.snapshot(),before)

    def test_inactive_actor_or_missing_profile_blocks_child_write(self):
        for missing in (False,True):
            with self.subTest(missing_profile=missing),self.isolated_case():
                target,_=self.begin()
                if missing:self.user.profile.delete()
                else:self.user.is_active=False;self.user.save(update_fields=['is_active'])
                before=self.snapshot();response=self.client.post(target,self.child_data(RELATIONS[0]))
                self.assertIn(response.status_code,(302,403,404));self.assertEqual(self.snapshot(),before)

    def test_token_cannot_cross_user_or_session(self):
        target,_=self.begin()
        other=get_user_model().objects.create_user(username='other-context-actor')
        other.profile.companies.add(self.company);other.profile.branches.add(self.branch)
        other.user_permissions.set(self.user.user_permissions.all())
        for actor in (self.user,other):
            with self.subTest(actor=actor.username):
                browser=Client(raise_request_exception=False);browser.force_login(actor);self.context(browser)
                before=self.snapshot();self.assert_denied(browser.post(target,self.child_data(RELATIONS[0])))
                self.assertEqual(self.snapshot(),before)

    def test_company_switch_rejects_old_continuation_even_with_both_memberships(self):
        target,_=self.begin();self.user.profile.companies.add(self.other_company)
        session=self.client.session;session['company_id']=self.other_company.pk;session['branch_id']=None;session.save()
        before=self.snapshot();self.assert_denied(self.client.post(target,self.child_data(RELATIONS[0])))
        self.assertEqual(self.snapshot(),before)

    def test_forged_token_rejected_before_global_catalog_write(self):
        for relation in RELATIONS:
            with self.subTest(field=relation[0]),self.isolated_case():
                before=self.snapshot();response=self.client.post(reverse(relation[2]+'_create')+'?draft=invented-token',self.child_data(relation)|{'draft':'invented-token'})
                self.assert_denied(response);self.assertEqual(self.snapshot(),before)

    def test_expired_and_evicted_drafts_are_controlled_and_never_write(self):
        target,_=self.begin()
        with patch('people.services.ui_drafts.time.time',return_value=10**12):
            before=self.snapshot();self.assert_denied(self.client.post(target,self.child_data(RELATIONS[0])));self.assertEqual(self.snapshot(),before)
        target,_=self.begin()
        for _ in range(8):self.begin()
        before=self.snapshot();self.assert_denied(self.client.post(target,self.child_data(RELATIONS[0])));self.assertEqual(self.snapshot(),before)

    def test_endpoint_entity_operation_and_selected_object_substitution_rejected(self):
        target,_=self.begin(RELATIONS[1],'change',True)
        another=Brand.objects.create(name='Otra marca')
        query=urlsplit(target).query
        for path in (reverse('brand_update',args=[another.pk]),reverse('brand_create'),reverse('unit_update',args=[self.unit.pk])):
            with self.subTest(endpoint=path):
                before=self.snapshot();self.assert_denied(self.client.post(path+'?'+query,{'name':'Manipulado','code':'HACK'}));self.assertEqual(self.snapshot(),before)

    def test_parent_product_and_parent_operation_substitution_rejected(self):
        target,_=self.begin(editing=True);location,_=self.finish(target,cancel=True)
        second=Product.objects.create(company=self.company,code='SECOND',name='Otro producto')
        for route in (reverse('product_create'),reverse('product_update',args=[second.pk])):
            with self.subTest(route=route):
                before=self.snapshot();self.assert_denied(self.client.get(route+'?'+urlsplit(location).query));self.assertEqual(self.snapshot(),before)

    def test_return_field_purpose_and_external_redirect_parameters_never_authorize(self):
        target,data=self.begin()
        before=list(Product.objects.values())
        location,page=self.finish(target,self.child_data(RELATIONS[0])|{'field':'brand','entity':'brand','purpose':'other','return_url':'https://evil.example/','company_id':self.other_company.pk})
        self.assertFalse(urlsplit(location).netloc)
        self.assert_values(page,data,{'unit_measure':str(UnitMeasure.objects.get(code='NEW-U').pk)})
        self.assertEqual(list(Product.objects.values()),before)

    def test_completed_create_and_edit_cannot_replay_writes_but_parent_can_be_restored(self):
        for operation in ('add','change'):
            with self.subTest(operation=operation),self.isolated_case():
                target,_=self.begin(RELATIONS[1],operation,True)
                page=self.client.get(target);posted=self.hidden(page)|{'name':'Una sola escritura'}
                response=self.client.post(target,posted);self.assertEqual(response.status_code,302)
                self.assertEqual(self.client.get(response['Location']).status_code,200)
                self.assertEqual(self.client.get(response['Location']).status_code,200)
                before=self.snapshot();self.assert_denied(self.client.post(target,posted|{'name':'Replay alterado'}));self.assertEqual(self.snapshot(),before)

    def test_repeated_same_transition_post_does_not_create_duplicate_annexes(self):
        page=self.client.get(self.parent_url());posted=self.payload()|self.hidden(page)|self.control(page,'Adicionar marca')
        first=self.client.post(self.parent_url(),posted);second=self.client.post(self.parent_url(),posted)
        self.assertEqual(first.status_code,302)
        self.assertIn(second.status_code,(302,400,403,409))
        targets=[first['Location']]
        if second.status_code==302: targets.append(second['Location'])
        for index,target in enumerate(targets):
            page=self.client.get(target)
            if page.status_code in (403,409,410): continue
            response=self.client.post(target,self.hidden(page)|{'name':'Resultado reintentado'})
            self.assertIn(response.status_code,(302,403,409,410))
        self.assertEqual(Brand.objects.filter(name='Resultado reintentado').count(),1)
        self.assertEqual(Product.objects.count(),2)

    def test_group_change_post_refreshes_options_clears_subgroup_and_explains(self):
        group=ProductGroup.objects.create(company=self.company,name='Grupo alternativo')
        subgroup=ProductSubGroup.objects.create(company=self.company,group=group,name='Subgrupo alternativo')
        page=self.client.get(self.parent_url(True));doc=Document(page.content.decode())
        buttons=[n for n in doc.nodes if n.tag=='button' and n.attrs.get('name') and 'Actualizar' in (n.attrs.get('aria-label','')+n.text)]
        self.assertTrue(buttons,'Actualización POST sin JavaScript requerida')
        button=buttons[0];before=self.snapshot()
        response=self.client.post(self.parent_url(True),self.payload(group=str(group.pk))|{button.attrs['name']:button.attrs.get('value','')}|self.hidden(page))
        form=self.form(response);self.assertEqual(str(form['group'].value()),str(group.pk));self.assertFalse(form['subgroup'].value())
        self.assertIn(subgroup.pk,list(form.fields['subgroup'].queryset.values_list('pk',flat=True)))
        self.assertNotIn(self.subgroup.pk,list(form.fields['subgroup'].queryset.values_list('pk',flat=True)))
        self.assertContains(response,'subgrupo');self.assertEqual(self.snapshot(),before)

    def test_direct_incompatible_group_subgroup_post_is_rejected_not_auto_reparented(self):
        other=ProductGroup.objects.create(company=self.company,name='Otro grupo')
        before=self.snapshot();response=self.client.post(self.parent_url(True),self.payload(group=str(other.pk)))
        form=self.form(response);self.assertTrue(form.errors.get('subgroup'));self.assertEqual(str(form['group'].value()),str(other.pk));self.assertEqual(self.snapshot(),before)

    def test_new_subgroup_uses_authorized_parent_and_cannot_select_manipulated_result(self):
        target,data=self.begin(RELATIONS[3]);page=self.client.get(target)
        self.assertContains(page,self.group.name)
        alternate=ProductGroup.objects.create(company=self.company,name='Otro padre')
        before=self.snapshot();response=self.client.post(target,self.hidden(page)|{'name':'Incompatible','group':alternate.pk,'company_id':self.other_company.pk})
        self.assertIn(response.status_code,(200,400,403,409,422));self.assertEqual(self.snapshot(),before)

    def test_edit_subgroup_parent_change_clears_selection_without_changing_product_group(self):
        alternate=ProductGroup.objects.create(company=self.company,name='Otro padre')
        target,data=self.begin(RELATIONS[3],'change',True)
        _,page=self.finish(target,{'name':self.subgroup.name,'group':alternate.pk})
        self.assert_values(page,data,{'subgroup':''})
        self.assertContains(page,'subgrupo')
        self.product.refresh_from_db();self.assertEqual(self.product.group_id,self.group.pk)

    def test_historical_inactive_original_assignments_survive_unrelated_return(self):
        for obj in (self.group,self.subgroup,self.brand,self.unit):obj.is_active=False;obj.save(update_fields=['is_active'])
        target,data=self.begin(RELATIONS[1],editing=True)
        _,page=self.finish(target,cancel=True);self.assert_values(page,data)
        create=self.form(self.client.get(self.parent_url()))
        for relation in RELATIONS:
            obj=getattr(self,relation[0] if relation[0]!='unit_measure' else 'unit')
            self.assertFalse(create.fields[relation[0]].queryset.filter(pk=obj.pk).exists())

    def test_foreign_and_global_groups_are_not_new_product_assignments(self):
        foreign=ProductGroup.objects.create(company=self.other_company,name='Grupo ajeno')
        global_group=ProductGroup.objects.create(name='Grupo global')
        for obj in (foreign,global_group):
            with self.subTest(group=obj.pk):
                before=self.snapshot();response=self.client.post(self.parent_url(),self.payload(group=str(obj.pk),subgroup=''))
                self.assertTrue(self.form(response).errors.get('group'));self.assertEqual(self.snapshot(),before)

    def test_standalone_annex_create_still_works_without_product_token(self):
        for relation in RELATIONS:
            with self.subTest(field=relation[0]),self.isolated_case():
                before=list(Product.objects.values());response=self.client.post(reverse(relation[2]+'_create'),self.child_data(relation))
                self.assertEqual(response.status_code,302);self.assertEqual(list(Product.objects.values()),before)
