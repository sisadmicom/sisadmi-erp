"""D-02A.1 FASE 3 RED: Company -> Branch selection -> explicit Continue -> ERP.

SUPERSEDED BY HUMAN VALIDATION: EntityCompanyPersonRedTests.
 test_company_save_creates_access_membership_audit_without_operational_context
 in core/tests/test_entity_company_person_d02a1_red.py, approximately line 228,
 requires company_detail. This separate RED requires select_branch instead.
 The protected old RED is intentionally unchanged; both destination contracts
 cannot be satisfied simultaneously for the same initial-access operation.

Normal route: branch_create. Native links/forms expose continuation transport;
 no particular session store, token name, CSS layout or JavaScript is required.
 Membership is not creation authority. The positive initial actor uses the
 existing administrative authority; negative fixtures isolate Django add_branch
 permission from Company scope. No general multi-company creation policy is
 prescribed. HTTP 500 is a production failure, not an uncaught harness error;
 the deliberate membership fault only asserts rollback and never leaks into
 another test. All fixtures are validated in Django's PostgreSQL test database.
"""
from contextlib import ExitStack
from unittest.mock import patch
from urllib.parse import urlsplit

from django import forms
from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.db.models.signals import m2m_changed
from django.test import Client, TestCase, tag
from django.urls import NoReverseMatch, reverse

from core.models import Branch, Company
from people.forms import PersonForm
from people.models import CompanyPersonAccess, Person
from people.models.geography import Continent, Country, Province, Canton, Parish
from people.tests.person_ui_support import Document, Element, normalized
from users.models import UserProfile

BRANCH_FIELDS = ('code', 'name', 'address', 'is_main')
BUSINESS_APPS = {'core', 'users', 'people', 'catalog', 'inventory', 'sales', 'purchases', 'sri'}


@tag('d02a1_post_company_branch_red')
class PostCompanyBranchFlowRedTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.assertTrue(connection.settings_dict['NAME'].startswith('test_'), 'Never write acceptance fixtures to the human database')
        self.sequence = 0
        self.actor = self.make_actor(admin=True)
        self.client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        self.client.force_login(self.actor)
        continent = Continent.objects.create(name='Test continent')
        country = Country.objects.create(continent=continent, code='TEST', name='Test country')
        province = Province.objects.create(country=country, name='Test province')
        canton = Canton.objects.create(province=province, name='Test canton')
        parish = Parish.objects.create(canton=canton, name='Test parish')
        self.geography = dict(continent=continent, country=country, province=province, canton=canton, parish=parish)
        for obj in self.geography.values():
            obj.full_clean()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for target in ('socket.socket.connect', 'socket.socket.connect_ex', 'socket.create_connection',
                       'requests.sessions.Session.request',
                       'sri.services.fiscal_document_preparation_service.FiscalDocumentPreparationService.prepare',
                       'sri.services.electronic_document_service.ElectronicDocumentService.create'):
            self.stack.enter_context(patch(target, side_effect=AssertionError('No network/fiscal side effects')))

    def make_actor(self, *, admin=False, add_branch=False):
        self.sequence += 1
        actor = get_user_model().objects.create_user('branch-actor-' + str(self.sequence), password='branch-test-password',
                                                    is_superuser=admin, is_staff=admin)
        self.assertTrue(UserProfile.objects.filter(user=actor).exists())
        if add_branch:
            actor.user_permissions.add(Permission.objects.get(content_type__app_label='core', codename='add_branch'))
        return actor

    def person_data(self):
        return dict(person_type='LEGAL', identification_type='PASSPORT', identification='PHASE3-IDENTITY',
                    full_name='Legal Person', email='', phone='', address='Test address',
                    **{key: obj.pk for key, obj in self.geography.items()})

    def company(self, *, member=True, actor=None, name='Context Company'):
        self.sequence += 1
        data = self.person_data()
        data.pop('continent')
        data.update(identification='P3-' + str(self.sequence))
        data.update({key: obj for key, obj in self.geography.items() if key != 'continent'})
        person = Person(**data)
        person.full_clean()
        person.save()
        company = Company(person=person, commercial_name=name)
        company.full_clean()
        company.save()
        if member:
            (actor or self.actor).profile.companies.add(company)
        return company

    def branch(self, company, *, member=True, actor=None, name='Authorized branch'):
        self.sequence += 1
        obj = Branch(company=company, code='SECRET-' + str(self.sequence), name=name,
                     address='Private address ' + str(self.sequence), is_main=False)
        obj.full_clean()
        obj.save()
        if member:
            (actor or self.actor).profile.branches.add(obj)
        return obj

    def url(self, route):
        try:
            return reverse(route)
        except NoReverseMatch:
            self.fail('RED: missing normal maintenance route ' + route)

    def page(self, route, *, client=None):
        response = (client or self.client).get(self.url(route))
        self.assertEqual(response.status_code, 200)
        return response

    def document(self, page):
        return Document(page.content.decode())

    def field(self, page, name):
        nodes = [n for n in self.document(page).matching(name=name) if n.tag in {'input', 'select', 'textarea'}]
        self.assertEqual(len(nodes), 1, 'Native usable field: ' + name)
        return nodes[0]

    def value(self, page, name):
        node = self.field(page, name)
        if node.tag == 'select':
            options = [n for n in node.children if isinstance(n, Element) and n.tag == 'option']
            chosen = [n for n in options if 'selected' in n.attrs] or options[:1]
            return chosen[0].attrs.get('value', '') if chosen else ''
        if node.tag == 'textarea':
            value = node.text.replace('\r\n', '\n')
            return value[1:] if value.startswith('\n') else value
        return node.attrs.get('value', '')

    def actions(self, page, label, *, doc=None):
        return [n for n in (doc or self.document(page)).nodes if n.tag in {'a', 'button', 'input'} and n.visible()
                and normalized(label) in normalized(n.text + ' ' + n.attrs.get('aria-label', '') + ' ' + n.attrs.get('value', ''))]

    def action(self, page, label, *, doc=None):
        nodes = [n for n in self.actions(page, label, doc=doc) if 'disabled' not in n.attrs]
        self.assertEqual(len(nodes), 1, 'Available human action: ' + label)
        return nodes[0]

    def inside(self, node, parent):
        while node:
            if node is parent:
                return True
            node = node.parent
        return False

    def payload(self, page, data, label='Guardar'):
        doc = self.document(page)
        button = self.action(page, label, doc=doc)
        self.assertIn(button.tag, {'button', 'input'}, 'Native form submit action')
        self.assertEqual(button.attrs.get('type', 'submit'), 'submit')
        if label == 'Cancelar':
            self.assertIn('formnovalidate', button.attrs)
        form = button.parent
        while form and form.tag != 'form':
            form = form.parent
        self.assertIsNotNone(form)
        self.assertEqual(form.attrs.get('method', 'get').lower(), 'post')
        values = {}
        for node in doc.nodes:
            name = node.attrs.get('name')
            if not name or not self.inside(node, form) or 'disabled' in node.attrs:
                continue
            if node.tag not in {'input', 'select', 'textarea'} or node.attrs.get('type') in {'submit', 'button', 'file'}:
                continue
            if node.attrs.get('type') in {'checkbox', 'radio'}:
                if 'checked' in node.attrs:
                    values[name] = node.attrs.get('value', 'on')
            elif node.attrs.get('type') == 'hidden':
                values[name] = node.attrs.get('value', '')
            else:
                values[name] = self.value(page, name)
        values.update(data)
        if button.attrs.get('name'):
            values[button.attrs['name']] = button.attrs.get('value', '')
        self.assertIn('csrfmiddlewaretoken', values)
        target = button.attrs.get('formaction') or form.attrs.get('action') or page.wsgi_request.get_full_path()
        self.assert_local(target)
        return target, values

    def send(self, page, data=None, label='Guardar', *, client=None):
        target, values = self.payload(page, data or {}, label)
        return (client or self.client).post(target, values)

    def assert_local(self, url):
        parts = urlsplit(url)
        self.assertFalse(parts.scheme or parts.netloc)
        self.assertTrue(parts.path.startswith('/') and not parts.path.startswith('//'))

    def follow(self, response, route=None):
        self.assertIn(response.status_code, (302, 303))
        self.assert_local(response['Location'])
        if route:
            self.assertEqual(urlsplit(response['Location']).path, self.url(route))
        returned = self.client.get(response['Location'])
        self.assertEqual(returned.status_code, 200)
        return returned

    def csrf(self, client=None):
        page = self.page('login', client=client)
        return self.field(page, 'csrfmiddlewaretoken').attrs['value']

    def select_company(self, company):
        response = self.client.post(self.url('select_company'), {
            'company_id': company.pk, 'csrfmiddlewaretoken': self.csrf(),
        })
        return self.follow(response, 'select_branch')

    def open_branch(self, company, *, page=None):
        page = page if page is not None else self.select_company(company)
        self.url('branch_create')  # Missing normal endpoint is production RED, never NoReverseMatch.
        action = self.action(page, 'Adicionar sucursal')
        if action.tag == 'a':
            target = action.attrs.get('href', '')
            self.assert_local(target)
            self.assertEqual(urlsplit(target).path, self.url('branch_create'))
            response = self.client.get(target)
            self.assertEqual(response.status_code, 200)
            return response
        self.assertIn('formnovalidate', action.attrs)
        return self.follow(self.send(page, label='Adicionar sucursal'), 'branch_create')

    def deny(self, response):
        self.assertIn(response.status_code, (200, 302, 303, 400, 403, 404, 409, 410, 422), 'Controlled rejection, never HTTP 500')
        for internal in ('Traceback', 'ValueError', 'DoesNotExist', 'ProtectedError'):
            self.assertNotIn(internal, response.content.decode())
        if response.status_code in (302, 303):
            self.assert_local(response['Location'])
            self.assertIn(urlsplit(response['Location']).path,
                          [self.url(route) for route in ('login', 'select_company', 'select_branch')])
        elif response.status_code == 200:
            self.assertRegex(normalized(self.document(response).root.text), r'(?:seleccion|revise|permiso|autoriz|disponib|acceso)')

    def erp_blocked(self):
        response = self.client.get(self.url('dashboard'))
        self.assertIn(response.status_code, (302, 303, 403))
        if response.status_code in (302, 303):
            self.assert_local(response['Location'])
            self.assertIn(urlsplit(response['Location']).path,
                          [self.url(route) for route in ('login', 'select_company', 'select_branch')])

    def snapshot(self):
        return {m._meta.label: list(m.objects.order_by('pk').values()) for m in apps.get_models(include_auto_created=True)
                if m._meta.app_label in BUSINESS_APPS}

    def assert_no_side_effects(self, before, *, branch_saved=False):
        allowed = {Branch._meta.label, UserProfile.branches.through._meta.label, 'core.AuditLog'} if branch_saved else set()
        after = self.snapshot()
        for label in before.keys() - allowed:
            self.assertEqual(after[label], before[label], 'Unexpected writes: ' + label)

    def company_form_with_saved_person(self, *, login=False):
        if login:
            self.client.logout()
            response = self.client.post(self.url('login'), dict(username=self.actor.username,
                password='branch-test-password', csrfmiddlewaretoken=self.csrf()))
            page = self.follow(response, 'company_create')
        else:
            page = self.page('company_create')
        person_page = self.follow(self.send(page, {'commercial_name': 'New human Company'}, 'Adicionar persona'), 'person_create')
        returned = self.follow(self.send(person_page, self.person_data()), 'company_create')
        self.assertEqual(Person.objects.count(), 1)
        self.assertEqual(Company.objects.count(), 0)
        return returned

    def test_fixture_data_is_valid_and_writes_only_postgresql_test_database(self):
        person = PersonForm(self.person_data())
        self.assertTrue(person.is_valid(), person.errors)
        form = forms.modelform_factory(Branch, fields=BRANCH_FIELDS)(dict(code='', name='Valid branch', address='', is_main=False))
        self.assertTrue(form.is_valid(), form.errors)
        company = self.company()
        branch = self.branch(company)
        self.assertEqual(branch.company, company)
        self.assertTrue(self.actor.profile.companies.filter(pk=company.pk).exists())
        self.assertTrue(self.actor.profile.branches.filter(pk=branch.pk).exists())

    def test_saved_company_continues_to_branch_selection_without_automatic_branch_or_erp(self):
        page = self.company_form_with_saved_person()
        before = self.snapshot()
        response = self.send(page, {'commercial_name': 'New human Company'})
        self.assertEqual(Company.objects.count(), 1)
        company = Company.objects.get()
        self.assertTrue(self.actor.profile.companies.filter(pk=company.pk).exists())
        self.assertTrue(CompanyPersonAccess.objects.filter(company=company, person=company.person).exists())
        self.assertEqual(Branch.objects.count(), 0)
        self.assertEqual(UserProfile.branches.through.objects.count(), 0)
        for label, rows in before.items():
            if label.split('.')[0] in {'sri', 'sales', 'purchases', 'inventory', 'catalog'}:
                self.assertEqual(self.snapshot()[label], rows)
        selected = self.follow(response, 'select_branch')
        self.assertContains(selected, company.commercial_name)
        self.erp_blocked()

    def test_selected_company_is_visible_and_cannot_enter_erp_without_branch(self):
        company = self.company(name='Correct Company <script>bad()</script>')
        page = self.select_company(company)
        self.assertContains(page, 'Correct Company &lt;script&gt;bad()&lt;/script&gt;')
        self.assertNotContains(page, '<script>bad()</script>')
        self.erp_blocked()
        before = self.snapshot()
        self.deny(self.client.post(self.url('select_branch'), {'branch_id': '', 'csrfmiddlewaretoken': self.csrf()}))
        self.assert_no_side_effects(before)
        self.erp_blocked()

    def test_empty_branch_state_offers_authorized_add_and_no_valid_continue(self):
        company = self.company()
        page = self.select_company(company)
        selector = self.field(page, 'branch_id')
        self.assertEqual(selector.tag, 'select')
        self.assertRegex(normalized(selector.text), r'no existen sucursales')
        self.assertFalse(self.value(page, 'branch_id'))
        labels = self.document(page).matching('label', **{'for': selector.attrs.get('id')})
        self.assertEqual(len(labels), 1)
        self.assertIn('sucursal', normalized(labels[0].text))
        self.assertTrue('required' in selector.attrs or selector.attrs.get('aria-required') == 'true')
        self.action(page, 'Adicionar sucursal')
        self.assertFalse([n for n in self.actions(page, 'Continuar') if 'disabled' not in n.attrs])
        text = normalized(self.document(page).root.text)
        for internal in ('membership', 'active_company', 'active_branch', 'middleware', 'scope', 'bootstrap'):
            self.assertNotIn(internal, text)

    def test_unavailable_branches_use_neutral_state_without_disclosing_records(self):
        actor = self.make_actor()
        company = self.company(actor=actor)
        hidden = [self.branch(company, member=False, name='Hidden Branch sentinel ' + str(i)) for i in range(2)]
        self.client.force_login(actor)
        page = self.select_company(company)
        text = normalized(self.document(page).root.text)
        self.assertRegex(text, r'no tiene sucursales (?:disponibles|autorizadas)')
        self.assertNotIn('no existen sucursales', text)
        self.assertNotRegex(text, r'\b2\s+sucursales\b')
        for obj in hidden:
            for secret in (obj.name, obj.code, obj.address):
                self.assertNotContains(page, secret)
            self.assertFalse(self.document(page).matching('option', value=str(obj.pk)))
        self.assertFalse(self.actions(page, 'Adicionar sucursal'))
        self.erp_blocked()

    def test_branch_add_requires_explicit_authority_and_company_scope(self):
        company = self.company()
        cases = ((False, False, True), (False, True, False), (True, False, False))
        for admin, permission, membership in cases:
            with self.subTest(admin=admin, permission=permission, membership=membership):
                actor = self.make_actor(admin=admin, add_branch=permission)
                if membership:
                    actor.profile.companies.add(company)
                client = Client(enforce_csrf_checks=True, raise_request_exception=False)
                client.force_login(actor)
                token = self.csrf(client)
                response = client.post(self.url('select_company'), {'company_id': company.pk, 'csrfmiddlewaretoken': token})
                self.assertIn(response.status_code, (302, 303))
                view = client.get(response['Location'])
                self.assertFalse(self.actions(view, 'Adicionar sucursal'))
                target = self.url('branch_create')
                before = self.snapshot()
                for response in (client.get(target), client.post(target, {
                    'code': 'NO', 'name': 'Unauthorized Branch', 'csrfmiddlewaretoken': token,
                })):
                    self.deny(response)
                self.assert_no_side_effects(before)

    def test_branch_form_contains_only_real_fields_and_company_context(self):
        company = self.company(name='Context <script>unsafe()</script>')
        page = self.open_branch(company)
        self.assertContains(page, 'Context &lt;script&gt;unsafe()&lt;/script&gt;')
        self.assertNotContains(page, '<script>unsafe()</script>')
        names = {n.attrs['name'] for n in self.document(page).nodes if n.tag in {'input', 'select', 'textarea'}
                 and n.attrs.get('name') and n.attrs.get('type') != 'hidden'}
        self.assertEqual(names, set(BRANCH_FIELDS))
        for name in ('company', 'company_id'):
            self.assertFalse(self.document(page).matching(name=name))
        for name in BRANCH_FIELDS:
            field = self.field(page, name)
            self.assertEqual(len(self.document(page).matching('label', **{'for': field.attrs.get('id')})), 1)
            self.assertEqual('required' in field.attrs, name == 'name')
        self.assertEqual(self.field(page, 'is_main').attrs.get('type'), 'checkbox')
        self.assertEqual(self.document(page).root.text.count('* Campo obligatorio'), 1)
        for label in ('Guardar', 'Cancelar'):
            self.action(page, label)
        for text in ('wizard', 'bootstrap', 'Paso 1', 'Sucursal principal', 'CompanyPersonAccess'):
            self.assertNotIn(text.casefold(), self.document(page).root.text.casefold())
        for node in self.document(page).nodes:
            if node.tag in {'script', 'link'}:
                self.assertFalse(urlsplit(node.attrs.get('src', node.attrs.get('href', ''))).netloc)

    def test_invalid_branch_preserves_values_and_accessibly_reports_required_name(self):
        company = self.company()
        page = self.open_branch(company)
        before = self.snapshot()
        response = self.send(page, dict(code='DRAFT', name='', address='Line one\n<script>unsafe()</script>', is_main='on'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.value(response, 'code'), 'DRAFT')
        self.assertEqual(self.value(response, 'address'), 'Line one\n<script>unsafe()</script>')
        self.assertNotContains(response, '<script>unsafe()</script>')
        field = self.field(response, 'name')
        self.assertEqual(field.attrs.get('aria-invalid'), 'true')
        associated = field.attrs.get('aria-describedby', '').split()
        self.assertTrue(associated)
        self.assertTrue(any(self.document(response).matching(id=value) for value in associated))
        self.assert_no_side_effects(before)

    def test_branch_save_is_audited_scoped_and_returns_selected_without_other_effects(self):
        company = self.company()
        page = self.open_branch(company)
        before = self.snapshot()
        result = self.send(page, dict(code='NEW', name='New Branch <script>unsafe()</script>', address='Address', is_main='on'))
        self.assertEqual(Branch.objects.count(), 1)
        branch = Branch.objects.get()
        branch.full_clean()
        self.assertEqual((branch.company, branch.code, branch.address, branch.is_main), (company, 'NEW', 'Address', True))
        self.assertEqual((branch.created_by_id, branch.updated_by_id), (self.actor.pk, self.actor.pk))
        self.assertEqual(list(self.actor.profile.branches.values_list('pk', flat=True)), [branch.pk])
        page = self.follow(result, 'select_branch')
        self.assertEqual(self.value(page, 'branch_id'), str(branch.pk))
        self.assertContains(page, 'New Branch &lt;script&gt;unsafe()&lt;/script&gt;')
        self.assert_no_side_effects(before, branch_saved=True)
        self.erp_blocked()

    def test_membership_failure_rolls_back_branch_and_audit_atomically(self):
        company = self.company()
        page = self.open_branch(company)
        before = self.snapshot()
        hits = []
        def reject(sender, action, **kwargs):
            if action == 'pre_add':
                hits.append(True)
                raise RuntimeError('Deliberate test-only Branch membership fault')
        m2m_changed.connect(reject, sender=UserProfile.branches.through, weak=False)
        try:
            self.send(page, dict(code='', name='Atomic Branch', address=''))
        finally:
            m2m_changed.disconnect(reject, sender=UserProfile.branches.through)
        self.assertTrue(hits, 'Valid save must reach the real membership operation')
        self.assert_no_side_effects(before)
        self.erp_blocked()

    def test_cancel_branch_has_local_return_preserves_company_and_never_writes(self):
        company = self.company()
        page = self.open_branch(company)
        before = self.snapshot()
        returned = self.follow(self.send(page, {'name': 'Unsaved Branch'}, 'Cancelar'), 'select_branch')
        self.assertContains(returned, company.commercial_name)
        self.assert_no_side_effects(before)
        self.erp_blocked()

    def test_single_authorized_branch_requires_explicit_continue_and_get_head_do_not_write(self):
        company = self.company()
        branch = self.branch(company)
        page = self.select_company(company)
        self.assertEqual(self.value(page, 'branch_id'), str(branch.pk))
        self.action(page, 'Continuar')
        before = self.snapshot()
        self.assertEqual(self.client.head(self.url('select_branch')).status_code, 200)
        self.assertEqual(self.client.get(self.url('select_branch'), {'branch_id': branch.pk}).status_code, 200)
        self.assert_no_side_effects(before)
        self.erp_blocked()

    def test_continue_validates_native_csrf_post_and_establishes_complete_erp_context(self):
        company = self.company()
        branch = self.branch(company)
        page = self.select_company(company)
        self.erp_blocked()
        before = self.snapshot()
        dashboard = self.follow(self.send(page, {'branch_id': branch.pk}, 'Continuar'), 'dashboard')
        self.assertEqual(dashboard.wsgi_request.active_company.pk, company.pk)
        self.assertEqual(dashboard.wsgi_request.active_branch.pk, branch.pk)
        self.assertContains(dashboard, company.commercial_name)
        self.assertContains(dashboard, branch.name)
        self.assert_no_side_effects(before)

    def test_continue_without_csrf_never_establishes_operational_context(self):
        company = self.company()
        branch = self.branch(company)
        page = self.select_company(company)
        target, values = self.payload(page, {'branch_id': branch.pk}, 'Continuar')
        before = self.snapshot()
        for csrf in ('missing', 'invalid'):
            with self.subTest(csrf=csrf):
                payload = dict(values)
                if csrf == 'missing':
                    payload.pop('csrfmiddlewaretoken')
                else:
                    payload['csrfmiddlewaretoken'] = 'invalid'
                self.assertEqual(self.client.post(target, payload).status_code, 403)
                self.assert_no_side_effects(before)
                self.erp_blocked()

    def test_branch_create_post_requires_csrf(self):
        page = self.open_branch(self.company())
        target, values = self.payload(page, {'name': 'CSRF Branch'})
        before = self.snapshot()
        values.pop('csrfmiddlewaretoken')
        self.assertEqual(self.client.post(target, values).status_code, 403)
        self.assert_no_side_effects(before)

    def test_continue_rejects_foreign_unassociated_and_invented_branch_without_disclosure(self):
        company = self.company()
        own = self.branch(company)
        unavailable = self.branch(company, member=False, name='Unavailable Branch sentinel')
        foreign_company = self.company(member=False, name='Foreign Company sentinel')
        foreign = self.branch(foreign_company, name='Foreign Branch sentinel')
        page = self.select_company(company)
        for obj in (unavailable, foreign):
            self.assertNotContains(page, obj.name)
            self.assertFalse(self.document(page).matching('option', value=str(obj.pk)))
        for branch_id in (foreign.pk, unavailable.pk, max(own.pk, foreign.pk, unavailable.pk) + 1000):
            with self.subTest(branch=branch_id):
                before = self.snapshot()
                response = self.send(page, {'branch_id': branch_id}, 'Continuar')
                self.deny(response)
                if response.status_code in (302, 303):
                    response = self.client.get(response['Location'])
                for obj in (unavailable, foreign):
                    for secret in (obj.name, obj.code, obj.address):
                        self.assertNotContains(response, secret, status_code=response.status_code)
                self.assert_no_side_effects(before)
                self.erp_blocked()

    def test_malformed_branch_and_company_ids_have_controlled_rejection(self):
        company = self.company()
        branch = self.branch(company)
        for value in ('', 'not-an-id', '-1', str(2**80)):
            with self.subTest(branch_id=value):
                page = self.select_company(company)
                before = self.snapshot()
                self.deny(self.send(page, {'branch_id': value}, 'Continuar'))
                self.assert_no_side_effects(before)
                self.erp_blocked()
            with self.subTest(company_id=value):
                before = self.snapshot()
                self.deny(self.client.post(self.url('select_company'), {'company_id': value, 'csrfmiddlewaretoken': self.csrf()}))
                self.assert_no_side_effects(before)

    def test_continue_revalidates_revoked_memberships_activity_and_profile(self):
        for change in ('company_membership', 'branch_membership', 'company_inactive', 'branch_inactive', 'actor_inactive', 'profile_missing'):
            with self.subTest(change=change):
                self.actor = self.make_actor(admin=True)
                self.client.force_login(self.actor)
                company = self.company()
                branch = self.branch(company)
                page = self.select_company(company)
                if change == 'company_membership':
                    self.actor.profile.companies.remove(company)
                elif change == 'branch_membership':
                    self.actor.profile.branches.remove(branch)
                elif change == 'profile_missing':
                    self.actor.profile.delete()
                else:
                    obj = {'company_inactive': company, 'branch_inactive': branch, 'actor_inactive': self.actor}[change]
                    obj.is_active = False
                    obj.save(update_fields=['is_active'])
                before = self.snapshot()
                self.deny(self.send(page, {'branch_id': branch.pk}, 'Continuar'))
                self.assert_no_side_effects(before)
                self.erp_blocked()

    def test_branch_company_injection_is_ignored_or_rejected_never_retargets_creation(self):
        company = self.company()
        foreign = self.company(member=False, name='Foreign Company secret')
        for injection in ('post', 'query'):
            with self.subTest(injection=injection):
                page = self.open_branch(company)
                target, payload = self.payload(page, {'code': '', 'name': 'Bound ' + injection, 'address': ''})
                if injection == 'post':
                    payload.update(company=foreign.pk, company_id=foreign.pk, return_url='https://example.invalid/', next='https://example.invalid/')
                else:
                    target += ('&' if '?' in target else '?') + 'company=' + str(foreign.pk) + '&company_id=' + str(foreign.pk) + '&next=https://example.invalid/'
                before = set(Branch.objects.values_list('pk', flat=True))
                response = self.client.post(target, payload)
                created = list(Branch.objects.exclude(pk__in=before))
                self.assertFalse(Branch.objects.filter(company=foreign).exists())
                if created:
                    self.assertEqual(len(created), 1)
                    self.assertEqual(created[0].company, company)
                    self.assertTrue(self.actor.profile.branches.filter(pk=created[0].pk).exists())
                    self.follow(response, 'select_branch')
                else:
                    self.deny(response)
                self.erp_blocked()

    def test_branch_create_revalidates_authority_after_navigation(self):
        for change in ('permission', 'company_membership', 'company_inactive', 'profile_missing'):
            with self.subTest(change=change):
                self.actor = self.make_actor(admin=True)
                self.client.force_login(self.actor)
                company = self.company()
                page = self.open_branch(company)
                if change == 'permission':
                    self.actor.is_superuser = False
                    self.actor.save(update_fields=['is_superuser'])
                elif change == 'company_membership':
                    self.actor.profile.companies.remove(company)
                elif change == 'company_inactive':
                    company.is_active = False
                    company.save(update_fields=['is_active'])
                else:
                    self.actor.profile.delete()
                before = self.snapshot()
                self.deny(self.send(page, {'name': 'Revoked create'}))
                self.assert_no_side_effects(before)
                self.erp_blocked()

    def test_anonymous_and_inactive_actor_cannot_create_branch_or_continue(self):
        company = self.company()
        branch = self.branch(company)
        for inactive in (False, True):
            with self.subTest(inactive=inactive):
                client = Client(enforce_csrf_checks=True, raise_request_exception=False)
                if inactive:
                    actor = self.make_actor(admin=True)
                    actor.profile.companies.add(company)
                    actor.profile.branches.add(branch)
                    client.force_login(actor)
                    actor.is_active = False
                    actor.save(update_fields=['is_active'])
                token = self.csrf(client)
                for route in ('select_branch', 'branch_create'):
                    with self.subTest(route=route):
                        target = self.url(route)
                        before = self.snapshot()
                        for response in (client.get(target), client.post(target, {
                            'name': 'Unauthorized', 'branch_id': branch.pk, 'csrfmiddlewaretoken': token,
                        })):
                            self.deny(response)
                            self.assertNotEqual(response.status_code, 200)
                            self.assertNotContains(response, branch.name, status_code=response.status_code)
                        self.assert_no_side_effects(before)

    def test_complete_initial_access_uses_only_native_navigation_and_explicit_continue(self):
        page = self.company_form_with_saved_person(login=True)
        selection = self.follow(self.send(page, {'commercial_name': 'New human Company'}), 'select_branch')
        company = Company.objects.get()
        self.assertContains(selection, company.commercial_name)
        self.erp_blocked()
        branch_form = self.open_branch(company, page=selection)
        selection = self.follow(self.send(branch_form, dict(code='', name='Human Branch', address='')), 'select_branch')
        branch = Branch.objects.get()
        self.assertEqual(self.value(selection, 'branch_id'), str(branch.pk))
        self.erp_blocked()
        dashboard = self.follow(self.send(selection, {}, 'Continuar'), 'dashboard')
        self.assertContains(dashboard, 'Human Branch')
        self.assertEqual(dashboard.wsgi_request.active_branch.pk, branch.pk)
