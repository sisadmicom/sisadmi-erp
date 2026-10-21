"""D-02A.1: entity-centric first Company, RED only.

Normal route names follow person_create conventions: company_create/detail.
Continuation transport is discovered from native HTML, never from session
internals. Expiry must reject a continuation after one year (no exact TTL).
Logo presence is frozen; temporary binary preservation is deliberately absent.
No JS executes. DOM/CSS checks cannot certify real assistive technology use.
Fixtures write only through Django's PostgreSQL test database.
"""
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.db import connection
from django.db.models.signals import m2m_changed
from django.test import Client, tag
from django.urls import reverse

from core.models import Branch, Company
from people.models import CompanyPersonAccess, Person
from people.services import person_access_policy as policy
from people.tests.person_ui_support import PersonUIFixture, GEOGRAPHY, normalized
from users.models import UserProfile

TAG = 'd02a1_entity_company_person_red'


@tag(TAG)
class EntityCompanyPersonRedTests(PersonUIFixture):
    company_context = False

    def setUp(self):
        # Do not inherit the operational/multi-company fixture or its RED tag.
        self.assertEqual(connection.vendor, 'postgresql')
        self.assertTrue(connection.settings_dict['NAME'].startswith('test_'),
                        'Never run acceptance fixtures against the human database')
        self.actor = get_user_model().objects.create_superuser('entity-admin', '', 'entity-password')
        self.other = get_user_model().objects.create_user('entity-other')
        self.assertTrue(UserProfile.objects.filter(user=self.actor).exists())
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.actor)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for target in ('socket.socket.connect', 'socket.socket.connect_ex',
                       'socket.create_connection', 'requests.sessions.Session.request',
                       'sri.services.fiscal_document_preparation_service.FiscalDocumentPreparationService.prepare',
                       'sri.services.electronic_document_service.ElectronicDocumentService.create'):
            self.stack.enter_context(patch(target, side_effect=AssertionError('No network/fiscal side effects')))
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0, 0))

    def make_person(self, identity, **data):
        values = dict(identification=identity, person_type='LEGAL', full_name='Name ' + identity)
        geography = self.chain('F' + str(Person.objects.count()))
        values.update({kind: obj for kind, obj in geography.items() if kind != 'continent'})
        values.update(data)
        person = Person(**values)
        person.full_clean()
        person.save()
        return person

    def counts(self):
        return tuple(m.objects.count() for m in (Person, Company, CompanyPersonAccess,
            UserProfile.companies.through, Branch, UserProfile.branches.through))

    def start(self):
        return self.page('company_create')

    def action(self, page, label):
        buttons = [n for n in self.doc(page).matching('button')
                   if normalized(label) in normalized(n.text + ' ' + n.attrs.get('aria-label', ''))]
        self.assertEqual(len(buttons), 1, 'Discoverable native action: ' + label)
        button = buttons[0]
        self.assertEqual(button.attrs.get('type', 'submit'), 'submit')
        self.assertNotIn('disabled', button.attrs)
        return button

    def send(self, page, data, label, field='person', client=None):
        button = self.action(page, label)
        if label in ('Adicionar persona', 'Cancelar'):
            self.assertIn('formnovalidate', button.attrs)
        doc = self.doc(page)
        controls = [n for n in doc.matching(name=field) if n.tag in {'input', 'select', 'textarea'}]
        self.assertEqual(len(controls), 1)
        node = controls[0]
        while node is not None and node.tag != 'form':
            node = node.parent
        self.assertIsNotNone(node, 'Native form required for navigation without JS')
        self.assertEqual(node.attrs.get('method', 'get').lower(), 'post')
        payload = {n.attrs['name']: n.attrs.get('value', '')
                   for n in doc.matching('input')
                   if n.attrs.get('type') == 'hidden' and n.attrs.get('name')
                   and self.inside(n, node)}
        payload.update(data)
        if button.attrs.get('name'):
            payload[button.attrs['name']] = button.attrs.get('value', '')
        target = button.attrs.get('formaction') or node.attrs.get('action') or page.wsgi_request.get_full_path()
        self.assertFalse(urlsplit(target).netloc or urlsplit(target).scheme)
        self.assertIn('csrfmiddlewaretoken', payload)
        return (client or self.client).post(target, payload)

    def continuation(self, commercial_name='Comercial <script>alert(1)</script>'):
        before = self.counts()
        page = self.start()
        response = self.send(page, {'commercial_name': commercial_name}, 'Adicionar persona')
        page = self.follow(response)
        self.assertEqual(page.wsgi_request.path, self.url('person_create'))
        self.assertEqual(self.counts(), before)
        return page

    def save_person(self, page=None, **changes):
        page = page if page is not None else self.continuation()
        data = self.payload(self.chain(), identification='ENTITY-NEW', **changes)
        response = self.send(page, data, 'Guardar', 'person_type')
        self.assertEqual(Person.objects.count(), 1, 'Person persists before Company save')
        person = Person.objects.get()
        person.full_clean()
        self.assertEqual((person.created_by_id, person.updated_by_id), (self.actor.pk, self.actor.pk))
        self.assertEqual(self.counts(), (1, 0, 0, 0, 0, 0))
        return self.follow(response), person

    def assert_parent(self, page, person=None, name='Comercial <script>alert(1)</script>'):
        self.assertEqual(page.wsgi_request.path, self.url('company_create'))
        self.assertEqual(self.control(page, 'commercial_name').attrs.get('value'), name)
        selected = self.selected_values(page, 'person')
        self.assertEqual([v for v in selected if v], [str(person.pk)] if person else [])
        self.assertNotIn('<script>alert(1)</script>', page.content.decode())

    def deny(self, response):
        self.assertIn(response.status_code, (302, 303, 400, 403, 404, 410))
        if response.status_code in (302, 303):
            self.assertFalse(urlsplit(response.url).netloc or urlsplit(response.url).scheme)
            self.assertNotEqual(urlsplit(response.url).path, self.url('person_create'))

    def test_fixture_is_valid_empty_postgresql_installation(self):
        self.assertEqual([m.objects.count() for _, m, *_ in GEOGRAPHY], [0]*5)
        self.assertTrue(self.actor.is_active and self.actor.is_superuser)
        self.assertIsNone(self.client.session.get('company_id'))
        self.assertIsNone(self.client.session.get('branch_id'))

    def test_login_enters_normal_company_create_directly(self):
        self.client.logout()
        page = self.client.get(reverse('login'))
        token = self.doc(page).matching('input', name='csrfmiddlewaretoken')[0].attrs['value']
        response = self.client.post(reverse('login'), dict(username=self.actor.username,
            password='entity-password', csrfmiddlewaretoken=token))
        self.assertRedirects(response, self.url('company_create'), fetch_redirect_response=False)
        self.assertEqual(self.follow(response).wsgi_request.path, self.url('company_create'))

    def test_anonymous_login_does_not_disclose_company_or_branch(self):
        person = self.make_person('SECRET-IDENTITY')
        company = Company.objects.create(person=person, commercial_name='Hidden corporate sentinel')
        Branch.objects.create(company=company, code='001', name='Hidden branch sentinel')
        self.client.logout()
        page = self.client.get(reverse('login'))
        for secret in (company.commercial_name, 'Hidden branch sentinel', person.full_name):
            self.assertNotIn(secret, page.content.decode())

    def test_company_has_only_its_own_fields_and_discreet_human_actions(self):
        page = self.start()
        self.assertEqual(set(page.context['form'].fields), {'person', 'commercial_name', 'logo'})
        text = self.doc(page).root.text
        self.assertIn('Adicionar empresa', text)
        self.assertEqual(text.count('* Campo obligatorio'), 1)
        self.assertEqual(self.control(page, 'logo').attrs.get('type'), 'file')
        for label in ('Adicionar persona', 'Guardar', 'Cancelar'):
            self.action(page, label)
        for forbidden in ('Paso 1 de 4', 'Ubicación', 'Revisar y crear', 'Crear empresa y entrar',
                          'Empresa jurídica', 'Configurar empresa', 'bootstrap', '(opcional)',
                          'Este campo no tiene ayuda adicional'):
            self.assertNotIn(forbidden.casefold(), text.casefold())
        for name in ('person', 'commercial_name', 'logo'):
            node = self.control(page, name)
            self.assertEqual(len(self.doc(page).matching('label', **{'for': node.attrs.get('id')})), 1)
            self.assertEqual('required' in node.attrs, name != 'logo')
        css = finders.find('core/css/erp.css')
        self.assertIsNotNone(css)
        self.assertIn(':focus-visible', Path(css).read_text())
        for node in self.doc(page).nodes:
            if 'tabindex' in node.attrs:
                self.assertLessEqual(int(node.attrs['tabindex']), 0)
            if node.tag in ('script', 'link'):
                self.assertFalse(urlsplit(node.attrs.get('src', node.attrs.get('href', ''))).netloc)

    def test_invalid_company_errors_are_associated_and_do_not_persist(self):
        page = self.send(self.start(), {'person': '', 'commercial_name': ''}, 'Guardar')
        self.assertEqual(page.status_code, 200)
        for name in ('person', 'commercial_name'):
            node = self.control(page, name)
            self.assertEqual(node.attrs.get('aria-invalid'), 'true')
            ids = node.attrs.get('aria-describedby', '').split()
            self.assertTrue(ids)
            for error in page.context['form'][name].errors:
                self.assertTrue(any(str(error) in n.text and n.attrs.get('id') in ids for n in self.doc(page).nodes))
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0, 0))

    def test_company_to_normal_person_and_cancel_preserves_incomplete_draft(self):
        page = self.continuation('')
        self.assertIn('person_type', page.context['form'].fields)
        self.assertNotIn('FoundingPersonForm', type(page.context['form']).__name__)
        returned = self.follow(self.send(page, {}, 'Cancelar', 'person_type'))
        self.assert_parent(returned, name='')
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0, 0))

    def test_person_save_returns_only_new_selection_and_persists_independently(self):
        page, person = self.save_person()
        self.assert_parent(page, person)
        self.assertFalse(policy.visible_people(actor=self.actor, company=None).exists())
        self.assertFalse(policy.is_available(actor=self.actor, company=None, person=person))

    def test_company_save_creates_access_membership_audit_without_operational_context(self):
        before = {m: m.objects.count() for m in apps.get_models()
                  if m._meta.app_label in {'sri', 'sales', 'purchases', 'inventory'}}
        page, person = self.save_person()
        response = self.send(page, {'person': person.pk, 'commercial_name': 'Comercial final'}, 'Guardar')
        self.assertEqual(self.counts(), (1, 1, 1, 1, 0, 0))
        company = Company.objects.get()
        self.assertEqual(company.person_id, person.pk)
        self.assertEqual(company.commercial_name, 'Comercial final')
        self.assertEqual((company.created_by_id, company.updated_by_id), (self.actor.pk, self.actor.pk))
        self.assertTrue(CompanyPersonAccess.objects.filter(company=company, person=person).exists())
        self.assertTrue(self.actor.profile.companies.filter(pk=company.pk).exists())
        self.assertIsNone(self.client.session.get('branch_id'))
        destination = self.follow(response)
        self.assertEqual(destination.wsgi_request.path, self.url('company_detail', company))
        self.assertEqual({m: m.objects.count() for m in before}, before)

    def test_company_save_is_atomic_when_membership_fails(self):
        page, person = self.save_person()
        def reject(sender, action, **kwargs):
            if action == 'pre_add':
                raise RuntimeError('Injected membership failure')
        m2m_changed.connect(reject, sender=UserProfile.companies.through, weak=False)
        try:
            try:
                response = self.send(page, {'person': person.pk, 'commercial_name': 'Atomic'}, 'Guardar')
                self.assertGreaterEqual(response.status_code, 400)
            except RuntimeError as error:
                self.assertEqual(str(error), 'Injected membership failure')
        finally:
            m2m_changed.disconnect(reject, sender=UserProfile.companies.through)
        self.assertEqual(self.counts(), (1, 0, 0, 0, 0, 0))

    def test_cancel_company_keeps_person_and_invalidates_continuation(self):
        child = self.continuation()
        child_url = child.wsgi_request.get_full_path()
        page, person = self.save_person(child)
        response = self.send(page, {}, 'Cancelar')
        self.assertIn(response.status_code, (302, 303))
        self.assertFalse(urlsplit(response.url).netloc or urlsplit(response.url).scheme)
        self.assertEqual(self.counts(), (1, 0, 0, 0, 0, 0))
        self.deny(self.client.get(child_url))
        self.assertTrue(Person.objects.filter(pk=person.pk).exists())

    def test_cancel_empty_company_has_safe_local_destination_and_no_effects(self):
        response = self.send(self.start(), {}, 'Cancelar')
        self.assertIn(response.status_code, (302, 303))
        self.assertFalse(urlsplit(response.url).netloc or urlsplit(response.url).scheme)
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0, 0))

    def test_first_company_requires_active_authenticated_profile_and_initial_authority(self):
        target = self.url('company_create')
        for kind in ('anonymous', 'ordinary', 'inactive', 'no-profile'):
            with self.subTest(actor=kind):
                client = Client()
                if kind != 'anonymous':
                    user = get_user_model().objects.create_user('denied-'+kind,
                        is_active=kind != 'inactive', is_superuser=kind in ('inactive', 'no-profile'))
                    if kind == 'no-profile':
                        user.profile.delete()
                    client.force_login(user)
                self.deny(client.get(target))
                self.deny(client.post(target, {'commercial_name': 'Unauthorized'}))
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0, 0))

    def test_superuser_has_no_ordinary_companyless_person_creation_or_global_scope(self):
        hidden = self.make_person('PRIVATE', created_by=self.actor, full_name='Hidden name sentinel')
        self.assertFalse(policy.can_create_person(actor=self.actor, company=None))
        self.assertFalse(policy.visible_people(actor=self.actor, company=None).exists())
        self.assertFalse(policy.is_available(actor=self.actor, company=None, person=hidden))
        self.deny(self.client.get(self.url('person_create')))
        self.deny(self.client.get(self.url('person_list'), {'q': hidden.identification}))
        for route in ('person_detail', 'person_update'):
            response = self.client.get(self.url(route, hidden))
            self.deny(response)
            self.assert_no_private_person(response, hidden)

    def test_contextual_selector_search_and_forged_selection_never_reveal_or_associate_global_person(self):
        hidden = self.make_person('PRIVATE-SELECTION', created_by=self.actor,
                                  full_name='Stored hidden selection', email='hidden@example.invalid')
        page = self.client.get(self.url('company_create'), {'q': hidden.identification, 'person': hidden.pk})
        self.assertEqual(page.status_code, 200)
        self.assert_no_private_person(page, hidden)
        response = self.send(page, {'person': hidden.pk, 'commercial_name': 'Forged'}, 'Guardar')
        self.assertEqual(response.status_code, 200)
        self.assert_no_private_person(response, hidden)
        self.assertEqual(self.counts(), (1, 0, 0, 0, 0, 0))

    def test_contextual_identity_collision_is_neutral_and_does_not_reuse(self):
        hidden = self.make_person('ENTITY-COLLISION', full_name='Stored collision sentinel',
                                  email='collision@example.invalid', address='Stored address sentinel')
        page = self.continuation()
        response = self.send(page, self.payload(self.chain(), identification=hidden.identification), 'Guardar', 'person_type')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assert_no_private_person(response, hidden)
        self.assertEqual(self.counts(), (1, 0, 0, 0, 0, 0))
        for phrase in ('ya existe', 'otra empresa', 'already exists'):
            self.assertNotIn(phrase, self.doc(response).root.text.casefold())

    def test_csrf_required_for_company_and_contextual_person_posts(self):
        page = self.start()
        self.assertEqual(self.client.post(page.wsgi_request.get_full_path(), {'commercial_name': 'No csrf'}).status_code, 403)
        child = self.continuation()
        self.assertEqual(self.client.post(child.wsgi_request.get_full_path(), self.payload(self.chain())).status_code, 403)
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0, 0))

    def test_actor_bound_continuation_rejects_other_user_even_with_initial_authority(self):
        child = self.continuation()
        other = get_user_model().objects.create_superuser('second-admin', '', 'password')
        client = Client(enforce_csrf_checks=True)
        client.force_login(other)
        response = client.get(child.wsgi_request.get_full_path())
        self.deny(response)
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0, 0))

    def test_continuation_revalidates_authority_and_profile(self):
        for revoke in ('inactive', 'authority', 'profile'):
            with self.subTest(revoke=revoke):
                child = self.continuation()
                if revoke == 'profile':
                    self.actor.profile.delete()
                else:
                    setattr(self.actor, 'is_active' if revoke == 'inactive' else 'is_superuser', False)
                    self.actor.save()
                self.deny(self.client.get(child.wsgi_request.get_full_path()))
                self.assertEqual(self.counts(), (0, 0, 0, 0, 0, 0))
                self.actor.is_active = self.actor.is_superuser = True
                self.actor.save()
                UserProfile.objects.get_or_create(user=self.actor)
                self.client.force_login(self.actor)

    def test_forged_expired_and_replayed_continuations_cannot_create_second_person(self):
        child = self.continuation()
        original = child.wsgi_request.get_full_path()
        parts = urlsplit(original)
        query = parse_qs(parts.query)
        self.assertTrue(query, 'Continuation must survive native redirected navigation')
        forged = urlunsplit(parts._replace(query=urlencode({key: 'forged-unpredictable-token' for key in query})))
        self.deny(self.client.get(forged))
        import time
        future = time.time() + 366*86400
        with patch('time.time', return_value=future):
            self.deny(self.client.get(original))
        # Expiration may invalidate the original permanently; obtain a fresh draft.
        fresh = self.continuation()
        fresh_url = fresh.wsgi_request.get_full_path()
        self.save_person(fresh)
        self.deny(self.client.get(fresh_url))
        self.assertEqual(self.counts(), (1, 0, 0, 0, 0, 0))

    def test_return_purpose_parent_operation_field_and_external_destination_are_server_owned(self):
        child = self.continuation()
        injection = dict(next='https://attacker.invalid/', return_url='https://attacker.invalid/',
                         field='logo', return_field='commercial_name', parent='Person',
                         operation='update', purpose='arbitrary-form')
        response = self.send(child, {**self.payload(self.chain()), **injection}, 'Guardar', 'person_type')
        if response.status_code in (400, 403, 404):
            self.assertEqual(self.counts(), (0, 0, 0, 0, 0, 0))
        else:
            self.assertEqual(self.counts(), (1, 0, 0, 0, 0, 0))
            self.assert_parent(self.follow(response), Person.objects.get())

    def test_two_drafts_return_to_their_own_company_values(self):
        first = self.continuation('Primer borrador')
        second = self.continuation('Segundo borrador')
        self.assertNotEqual(first.wsgi_request.get_full_path(), second.wsgi_request.get_full_path())
        returned, person = self.save_person(first)
        self.assert_parent(returned, person, 'Primer borrador')
        returned = self.follow(self.send(second, {}, 'Cancelar', 'person_type'))
        self.assert_parent(returned, name='Segundo borrador')

    def test_initial_authority_does_not_become_general_company_creation(self):
        person = self.make_person('EXISTING-COMPANY')
        Company.objects.create(person=person, commercial_name='Existing Company')
        before = self.counts()
        self.deny(self.client.get(self.url('company_create')))
        self.assertEqual(self.counts(), before)

    def test_person_payload_fixture_matches_normal_form_validation(self):
        from people.forms import PersonForm
        form = PersonForm(data=self.payload(self.chain(), identification='FIXTURE-PASSPORT'))
        self.assertTrue(form.is_valid(), form.errors.as_json())
        person = form.save(commit=False)
        person.full_clean()
        self.assertEqual(Person.objects.count(), 0)
