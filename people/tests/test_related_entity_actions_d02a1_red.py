"""D-02A.1/2.1 RED: native related actions, Geography first.

Normal routes follow existing <kind>_create/update conventions; <kind>_delete
adds the normal confirmation operation. Buttons, form targets and opaque
continuation transport are discovered from HTML. Draft storage is not fixed.
Actions must share a local control group with their selector, without fixing
CSS classes or a particular container element. No JavaScript is executed.

Person keeps four persistent geographic relations. An existing nonpersistent
Continent filter is not a new Person relation and is not removed by this RED.
One Company -> Person -> Geography -> Person cancellation is covered; arbitrary
recursion is not prescribed. Expiry is tested after a year, without fixing TTL.

CASCADE safety uses restored, test-only FK deletion metadata to simulate a
future cascade. No production model, schema, migration or database is changed.
HTML textarea values follow browser semantics (one initial LF is ignored),
avoiding the known legacy parser discrepancy. Rejected requests use a client
that exposes server exceptions as HTTP 500 so missing safeguards are failures,
never accidental harness errors. Dependency messages may vary in wording.
"""
from contextlib import ExitStack
import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection, models
from django.test import Client, TestCase, tag
from django.urls import NoReverseMatch, reverse

from core.models import Branch, Company
from people.forms import PersonForm, geography_form
from people.models import Person
from people.models.geography import Continent, Country, Province, Canton, Parish
from people.tests.person_ui_support import Document, Element, normalized
from users.models import UserProfile

GEO = {'continent': Continent, 'country': Country, 'province': Province,
       'canton': Canton, 'parish': Parish}
RELATIONS = (('country', 'continent'), ('province', 'country'),
             ('canton', 'province'), ('parish', 'canton'))
PERSON_RELATIONS = ('country', 'province', 'canton', 'parish')
ACTIONS = ('Adicionar', 'Editar', 'Borrar')


@tag('d02a1_related_entity_actions_red')
class RelatedEntityActionsRedTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        self.assertTrue(connection.settings_dict['NAME'].startswith('test_'))
        self.actor = get_user_model().objects.create_user('related-operator')
        self.assertTrue(UserProfile.objects.filter(user=self.actor).exists())
        self.client = Client(enforce_csrf_checks=True, raise_request_exception=False)
        self.permissions(self.actor, *[f'{op}_{kind}' for kind in GEO
                                      for op in ('view', 'add', 'change', 'delete')],
                         'view_person', 'add_person', 'change_person')
        self.client.force_login(self.actor)
        self.sequence = 0
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for target in ('socket.socket.connect', 'socket.socket.connect_ex',
                       'socket.create_connection', 'requests.sessions.Session.request',
                       'sri.services.fiscal_document_preparation_service.FiscalDocumentPreparationService.prepare',
                       'sri.services.electronic_document_service.ElectronicDocumentService.create'):
            self.stack.enter_context(patch(target, side_effect=AssertionError('No network or fiscal effects')))

    def permissions(self, actor, *codes):
        actor.user_permissions.set(Permission.objects.filter(content_type__app_label='people', codename__in=codes))
        actor.groups.clear()
        for key in ('_perm_cache', '_user_perm_cache', '_group_perm_cache'):
            actor.__dict__.pop(key, None)

    def url(self, route, obj=None):
        try:
            return reverse(route, args=[obj.pk] if obj is not None else [])
        except NoReverseMatch:
            self.fail('RED: missing normal maintenance route ' + route)

    def page(self, route, obj=None, data=None):
        response = self.client.get(self.url(route, obj), data or {})
        self.assertEqual(response.status_code, 200)
        return response

    def snapshot(self):
        return {m._meta.label: list(m.objects.order_by('pk').values()) for m in apps.get_models()
                if m._meta.app_label in {'core', 'people', 'catalog', 'inventory', 'sales', 'purchases', 'sri'}}

    def chain(self, last='parish'):
        self.sequence += 1
        return self.extend_chain({}, last)

    def extend_chain(self, result, last='parish'):
        for kind, model in GEO.items():
            if kind in result:
                continue
            data = {'name': f'Catalog {kind} {self.sequence}'}
            index = tuple(GEO).index(kind)
            if index:
                data[tuple(GEO)[index - 1]] = result[tuple(GEO)[index - 1]]
            if kind == 'country':
                data['code'] = 'G' + str(self.sequence)
            obj = model(**data)
            obj.full_clean()
            obj.save()
            result[kind] = obj
            if kind == last:
                break
        return result

    def person_data(self, chain):
        return dict(person_type='NATURAL', identification_type='PASSPORT', identification='RELATED-DRAFT',
                    full_name='Draft <script>unsafe()</script>', email='draft@example.invalid', phone='0991111111',
                    address='First line\nSecond line', **{kind: obj.pk for kind, obj in chain.items()})

    def make_person(self, chain, identity='ROOT-PERSON', **changes):
        data = self.person_data(chain)
        data.pop('continent', None)
        data.update({kind: chain[kind] for kind in PERSON_RELATIONS})
        data.update(identification=identity, **changes)
        obj = Person(**data)
        obj.full_clean()
        obj.save()
        return obj

    def workspace(self):
        if not hasattr(self, 'workspace_chain'):
            self.workspace_chain = self.chain()
            company = Company.objects.create(person=self.make_person(self.workspace_chain), commercial_name='Test workspace')
            self.actor.profile.companies.add(company)
            session = self.client.session
            session['company_id'], session['branch_id'] = company.pk, None
            session.save()
        return self.workspace_chain

    def field(self, page, name, doc=None):
        nodes = [n for n in (doc or Document(page.content.decode())).matching(name=name)
                 if n.tag in {'input', 'select', 'textarea'}]
        self.assertEqual(len(nodes), 1, 'Usable field: ' + name)
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

    def inside(self, node, parent):
        while node:
            if node is parent:
                return True
            node = node.parent
        return False

    def near(self, control, button, doc):
        node = control.parent
        while node:
            if self.inside(button, node):
                others = [n for n in doc.nodes if n is not control and self.inside(n, node)
                          and n.tag in {'input', 'select', 'textarea'} and n.attrs.get('type') != 'hidden']
                return not others
            node = node.parent
        return False

    def actions(self, page, field, label):
        doc = Document(page.content.decode())
        control = self.field(page, field, doc)
        return [n for n in doc.matching('button') if n.visible() and 'disabled' not in n.attrs
                and normalized(label) in normalized(n.text + ' ' + n.attrs.get('aria-label', ''))
                and self.near(control, n, doc)]

    def action(self, page, label, field=None):
        nodes = self.actions(page, field, label) if field else [n for n in Document(page.content.decode()).matching('button')
                if n.visible() and 'disabled' not in n.attrs
                and normalized(label) in normalized(n.text + ' ' + n.attrs.get('aria-label', ''))]
        self.assertEqual(len(nodes), 1, f'Native {label} action beside {field}' if field else f'Native {label} action')
        self.assertEqual(nodes[0].attrs.get('type', 'submit'), 'submit')
        if field or label == 'Cancelar':
            self.assertIn('formnovalidate', nodes[0].attrs)
        return nodes[0]

    def payload(self, page, data, button):
        doc = Document(page.content.decode())
        # A button discovered in another rendering supplies only name/value/formaction.
        forms = [n for n in doc.matching('form') if any(self.inside(c, n)
                 for c in doc.matching('input', name='csrfmiddlewaretoken'))]
        forms = [f for f in forms if any(self.inside(n, f) for n in doc.nodes
                 if n.tag in {'input', 'select', 'textarea'} and n.attrs.get('name') != 'csrfmiddlewaretoken')]
        if not forms:  # Delete confirmation may contain only CSRF and buttons.
            forms = [f for f in doc.matching('form') if any(self.inside(n, f) and n.tag == 'button'
                     and normalized(button.text) in normalized(n.text) for n in doc.nodes)]
        self.assertEqual(len(forms), 1, 'One native maintenance form')
        form = forms[0]
        self.assertEqual(form.attrs.get('method', 'get').lower(), 'post')
        values = {}
        for n in doc.nodes:
            if not self.inside(n, form) or not n.attrs.get('name') or 'disabled' in n.attrs:
                continue
            if n.tag in {'input', 'select', 'textarea'} and n.attrs.get('type') not in {'button', 'submit', 'checkbox', 'radio'}:
                if n.attrs.get('type') == 'hidden':
                    values[n.attrs['name']] = n.attrs.get('value', '')
                else:
                    values[n.attrs['name']] = self.value(page, n.attrs['name'])
        values.update(data)
        if button.attrs.get('name'):
            values[button.attrs['name']] = button.attrs.get('value', '')
        target = button.attrs.get('formaction') or form.attrs.get('action') or page.wsgi_request.get_full_path()
        self.assertFalse(urlsplit(target).scheme or urlsplit(target).netloc)
        self.assertIn('csrfmiddlewaretoken', values)
        return target, values

    def send(self, page, data, label='Guardar', field=None, button=None, client=None, csrf=None):
        target, payload = self.payload(page, data, button or self.action(page, label, field))
        if csrf is not None:
            payload['csrfmiddlewaretoken'] = csrf
        return (client or self.client).post(target, payload)

    def follow(self, response, expected=None):
        self.assertIn(response.status_code, (302, 303))
        parts = urlsplit(response['Location'])
        self.assertFalse(parts.netloc or parts.scheme)
        if expected:
            self.assertEqual(parts.path, expected)
        page = self.client.get(response['Location'])
        self.assertEqual(page.status_code, 200)
        return page

    def begin(self, page, data, field, label='Adicionar', selected=None):
        response = self.send(page, data, label, field)
        suffix = 'create' if label == 'Adicionar' else ('update' if label == 'Editar' else 'delete')
        return self.follow(response, self.url(field + '_' + suffix, selected if suffix != 'create' else None))

    def geo_data(self, kind, chain, name='New catalog'):
        data = {'name': name}
        index = tuple(GEO).index(kind)
        if index:
            field = tuple(GEO)[index - 1]
            data[field] = chain[field].pk
        if kind == 'country':
            self.sequence += 1
            data['code'] = 'N' + str(self.sequence)
        return data

    def assert_draft(self, page, path, data):
        self.assertEqual(page.wsgi_request.path, path)
        for name, value in data.items():
            self.assertEqual(self.value(page, name), str(value), 'Preserved field: ' + name)
        self.assertNotIn('<script>unsafe()</script>', page.content.decode())

    def deny(self, response):
        self.assertIn(response.status_code, (400, 403, 404, 410))

    def blocked(self, response, before, hidden=None):
        self.assertIn(response.status_code, (200, 302, 303, 409))
        page = self.follow(response) if response.status_code in (302, 303) else response
        text = Document(page.content.decode()).root.text
        self.assertRegex(normalized(text), r'(?:no se puede|no es posible|no puede).*(?:borrar|eliminar)')
        self.assertRegex(normalized(text), r'(?:utilizad|en uso|dependenc|relacionad)')
        for forbidden in ('Traceback', 'ProtectedError', 'CompanyPersonAccess', 'people.Person', '<class'):
            self.assertNotIn(forbidden, page.content.decode())
        self.assertNotRegex(text, r'\b(?:PK|ID)\s*[:=#]\s*\d+')
        if hidden:
            for value in (hidden.full_name, hidden.email, hidden.address):
                self.assertNotIn(value, page.content.decode())
        self.assertEqual(self.snapshot(), before)

    def test_fixture_payloads_validate_and_do_not_require_a_branch(self):
        chain = self.workspace()
        form = PersonForm(data=self.person_data(chain))
        self.assertTrue(form.is_valid(), form.errors.as_json())
        for kind in GEO:
            form = geography_form(kind)(data=self.geo_data(kind, chain))
            self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertEqual(Branch.objects.count(), 0)

    def test_catalog_relations_show_adjacent_actions_only_when_selected(self):
        chain = self.chain()
        for parent, field in RELATIONS:
            with self.subTest(parent=parent):
                empty = self.page(parent + '_create')
                doc = Document(empty.content.decode())
                form = self.field(empty, field, doc)
                while form is not None and form.tag != 'form':
                    form = form.parent
                self.assertIsNotNone(form)
                expected = {field, 'name'} | ({'code'} if parent == 'country' else set())
                visible = {n.attrs.get('name') for n in doc.nodes if self.inside(n, form)
                           and n.tag in {'input', 'select', 'textarea'} and n.attrs.get('type') != 'hidden'}
                self.assertEqual(visible, expected, 'Only fields of the normal geographic entity')
                for name in expected:
                    control = self.field(empty, name, doc)
                    self.assertIn('required', control.attrs)
                    self.assertEqual(len(doc.matching('label', **{'for': control.attrs.get('id')})), 1)
                self.action(empty, 'Adicionar', field)
                self.assertFalse(self.actions(empty, field, 'Editar'))
                self.assertFalse(self.actions(empty, field, 'Borrar'))
                selected = self.page(parent + '_update', chain[parent])
                for action in ACTIONS:
                    self.action(selected, action, field)

    def test_person_has_same_actions_for_four_persistent_relations_not_continent(self):
        chain = self.workspace()
        self.assertNotIn('continent', {f.name for f in Person._meta.get_fields()})
        page = self.page('person_create', data={k: o.pk for k, o in chain.items()})
        for field in PERSON_RELATIONS:
            with self.subTest(field=field):
                self.assertEqual(Person._meta.get_field(field).related_model, GEO[field])
                for action in ACTIONS:
                    self.action(page, action, field)

    def test_add_save_selects_new_record_and_preserves_same_geo_edit_draft(self):
        chain = self.chain()
        for parent, field in RELATIONS:
            with self.subTest(parent=parent):
                obj = chain[parent]
                data = self.geo_data(parent, chain, 'Draft <script>unsafe()</script>')
                persisted = list(GEO[parent].objects.filter(pk=obj.pk).values())
                child = self.begin(self.page(parent + '_update', obj), data, field)
                new_data = self.geo_data(field, chain, 'Created ' + parent)
                returned = self.follow(self.send(child, new_data), self.url(parent + '_update', obj))
                created = GEO[field].objects.get(name=new_data['name'])
                data[field] = created.pk
                self.assert_draft(returned, self.url(parent + '_update', obj), data)
                self.assertEqual(list(GEO[parent].objects.filter(pk=obj.pk).values()), persisted)

    def test_cancel_add_and_edit_keeps_country_draft_and_previous_selection(self):
        chain = self.chain()
        country = chain['country']
        for action in ('Adicionar', 'Editar'):
            with self.subTest(action=action):
                data = self.geo_data('country', chain, 'Unfinished country draft')
                child = self.begin(self.page('country_update', country), data, 'continent', action, chain['continent'])
                before = self.snapshot()
                returned = self.follow(self.send(child, {}, 'Cancelar'), self.url('country_update', country))
                self.assert_draft(returned, self.url('country_update', country), data)
                self.assertEqual(self.snapshot(), before)

    def test_edit_returns_to_same_parent_and_preserves_selected_record_id(self):
        chain = self.chain()
        for parent, field in RELATIONS:
            with self.subTest(parent=parent):
                data = self.geo_data(parent, chain, 'Preserved parent draft')
                child = self.begin(self.page(parent + '_update', chain[parent]), data, field, 'Editar', chain[field])
                changed = self.geo_data(field, chain, 'Renamed ' + field)
                returned = self.follow(self.send(child, changed), self.url(parent + '_update', chain[parent]))
                chain[field].refresh_from_db()
                self.assertEqual(chain[field].name, changed['name'])
                self.assert_draft(returned, self.url(parent + '_update', chain[parent]), data)
                self.assertContains(returned, changed['name'])

    def test_edit_and_delete_require_selection_on_ui_and_server(self):
        chain = self.chain()
        for action in ('Editar', 'Borrar'):
            with self.subTest(action=action):
                selected = self.page('country_update', chain['country'])
                button = self.action(selected, action, 'continent')
                empty = self.page('country_create')
                self.assertFalse(self.actions(empty, 'continent', action))
                before = self.snapshot()
                response = self.send(empty, {'continent': '', 'name': '', 'code': ''}, button=button)
                self.assertIn(response.status_code, (200, 400, 403, 404))
                self.assertEqual(self.snapshot(), before)
                if response.status_code == 200:
                    self.assertTrue(response.context['form'].errors)

    def test_delete_confirmation_get_head_and_cancel_never_write(self):
        for kind in GEO:
            with self.subTest(kind=kind):
                obj = self.chain(kind)[kind]
                target = self.url(kind + '_delete', obj)
                before = self.snapshot()
                page = self.client.get(target)
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, obj.name)
                self.assertEqual(self.client.head(target).status_code, 200)
                self.assertEqual(self.snapshot(), before)
                self.follow(self.send(page, {}, 'Cancelar'))
                self.assertEqual(self.snapshot(), before)

    def test_delete_post_always_requires_csrf(self):
        for kind in GEO:
            with self.subTest(kind=kind):
                obj = self.chain(kind)[kind]
                target = self.url(kind + '_delete', obj)
                before = self.snapshot()
                self.assertEqual(self.client.post(target, {}).status_code, 403)
                self.assertEqual(self.snapshot(), before)

    def test_valid_delete_returns_to_geo_create_parent_and_clears_selection(self):
        for parent, field in RELATIONS:
            with self.subTest(parent=parent):
                chain = self.chain(field)
                obj = chain[field]  # Unused leaf; no persisted parent points at it.
                data = self.geo_data(parent, chain, '')
                page = self.send(self.page(parent + '_create'), data)
                self.assertEqual(page.status_code, 200)
                confirm = self.begin(page, data, field, 'Borrar', obj)
                before = self.snapshot()
                page = self.follow(self.send(confirm, {}, 'Cancelar'), self.url(parent + '_create'))
                self.assert_draft(page, self.url(parent + '_create'), data)
                self.assertEqual(self.snapshot(), before)
                confirm = self.begin(page, data, field, 'Borrar', obj)
                returned = self.follow(self.send(confirm, {}, 'Borrar'), self.url(parent + '_create'))
                self.assertFalse(GEO[field].objects.filter(pk=obj.pk).exists())
                data[field] = ''
                self.assert_draft(returned, self.url(parent + '_create'), data)

    def test_protect_dependencies_block_deletion_without_private_person_disclosure(self):
        for kind in GEO:
            with self.subTest(kind=kind):
                chain = self.chain(kind)
                page = self.page(kind + '_delete', chain[kind])
                # Dependencies appear AFTER confirmation: POST must check again.
                self.extend_chain(chain)
                hidden = self.make_person(chain, identity='PRIVATE-' + kind,
                    full_name='Hidden dependency ' + kind, email=f'hidden-{kind}@example.invalid',
                    address='Private dependency address ' + kind)
                before = self.snapshot()
                self.blocked(self.send(page, {}, 'Borrar'), before, hidden)

    def test_dependencies_block_even_when_django_relationship_allows_cascade(self):
        for index, (kind, model) in enumerate(GEO.items()):
            with self.subTest(kind=kind):
                if kind == 'parish':
                    chain = self.chain()
                    dependent = self.make_person(chain, identity='CASCADE-DEPENDENT')
                    relation = Person._meta.get_field('parish').remote_field
                else:
                    child = tuple(GEO)[index + 1]
                    chain = self.chain(child)
                    dependent = chain[child]
                    relation = GEO[child]._meta.get_field(kind).remote_field
                before = self.snapshot()
                with patch.object(relation, 'on_delete', models.CASCADE):
                    page = self.page(kind + '_delete', chain[kind])
                    self.blocked(self.send(page, {}, 'Borrar'), before)
                self.assertTrue(type(dependent).objects.filter(pk=dependent.pk).exists())

    def test_real_permissions_independently_control_related_buttons(self):
        chain = self.chain()
        for allowed in ((), ('add',), ('change',), ('delete',), ('add', 'change', 'delete')):
            with self.subTest(allowed=allowed):
                self.permissions(self.actor, 'change_country', 'view_continent',
                                 *[op + '_continent' for op in allowed])
                page = self.page('country_update', chain['country'])
                for label, permission in zip(ACTIONS, ('add', 'change', 'delete')):
                    self.assertEqual(bool(self.actions(page, 'continent', label)), permission in allowed)

    def test_direct_endpoints_enforce_permission_and_revocation_after_navigation(self):
        continent = self.chain('continent')['continent']
        self.permissions(self.actor, 'view_continent')
        for suffix in ('create', 'update', 'delete'):
            with self.subTest(operation=suffix):
                target = self.url('continent_' + suffix, continent if suffix != 'create' else None)
                before = self.snapshot()
                self.deny(self.client.get(target))
                token_page = self.client.get(self.url('login'))
                token = Document(token_page.content.decode()).matching('input', name='csrfmiddlewaretoken')[0].attrs['value']
                self.deny(self.client.post(target, {'name': 'Unauthorized', 'csrfmiddlewaretoken': token}))
                self.assertEqual(self.snapshot(), before)

    def test_authority_is_revalidated_on_delete_post_and_person_requires_profile_scope(self):
        continent = self.chain('continent')['continent']
        confirm = self.page('continent_delete', continent)
        self.permissions(self.actor, 'view_continent')
        before = self.snapshot()
        self.deny(self.send(confirm, {}, 'Borrar'))
        self.assertEqual(self.snapshot(), before)
        self.permissions(self.actor, 'view_person', 'add_person')
        chain = self.workspace()
        person_page = self.page('person_create')
        self.actor.profile.delete()
        before = self.snapshot()
        self.deny(self.client.get(self.url('person_create')))
        self.deny(self.send(person_page, self.person_data(chain)))
        self.assertEqual(self.snapshot(), before)

    def test_geography_operations_require_authentication_and_active_user(self):
        continent = self.chain('continent')['continent']
        for inactive in (False, True):
            with self.subTest(inactive=inactive):
                client = Client(raise_request_exception=False)
                if inactive:
                    actor = get_user_model().objects.create_user('inactive-related', is_active=False)
                    self.permissions(actor, 'add_continent', 'change_continent', 'delete_continent')
                    client.force_login(actor)
                for suffix in ('create', 'update', 'delete'):
                    target = self.url('continent_' + suffix, continent if suffix != 'create' else None)
                    before = self.snapshot()
                    for response in (client.get(target), client.post(target, {'name': 'Unauthorized'})):
                        self.assertIn(response.status_code, (302, 303, 403))
                        if response.status_code in (302, 303):
                            self.assertEqual(urlsplit(response['Location']).path, self.url('login'))
                    self.assertEqual(self.snapshot(), before)

    def test_forged_other_actor_and_expired_tokens_reject_get_and_post(self):
        chain = self.chain()
        parent = self.page('country_update', chain['country'])
        data = self.geo_data('country', chain, 'Actor private draft sentinel')
        for attack in ('forged', 'other_actor', 'expired'):
            with self.subTest(attack=attack):
                child = self.begin(parent, data, 'continent')
                target, payload = self.payload(child, {'name': 'Unauthorized child'}, self.action(child, 'Guardar'))
                url = child.wsgi_request.get_full_path()
                client = self.client
                with ExitStack() as stack:
                    if attack == 'forged':
                        parts = urlsplit(url)
                        query = parse_qs(parts.query)
                        self.assertTrue(query)
                        values = {v for items in query.values() for v in items}
                        forged = urlencode({key: 'invented-unpredictable-token' for key in query})
                        url = urlunsplit(parts._replace(query=forged))
                        target = urlunsplit(urlsplit(target)._replace(query=forged))
                        replaced = [key for key, value in payload.items() if key != 'csrfmiddlewaretoken' and value in values]
                        self.assertTrue(replaced, 'Opaque continuation must survive native POST')
                        for key in replaced:
                            payload[key] = 'invented-unpredictable-token'
                    elif attack == 'other_actor':
                        actor = get_user_model().objects.create_user('other-related')
                        self.permissions(actor, 'add_continent', 'change_country', 'view_continent')
                        client = Client(enforce_csrf_checks=True, raise_request_exception=False)
                        client.force_login(actor)
                        login = client.get(self.url('login'))
                        payload['csrfmiddlewaretoken'] = Document(login.content.decode()).matching('input', name='csrfmiddlewaretoken')[0].attrs['value']
                    else:
                        stack.enter_context(patch('time.time', return_value=time.time() + 366*86400))
                    before = self.snapshot()
                    for response in (client.get(url), client.post(target, payload)):
                        self.deny(response)
                        self.assertNotIn(data['name'], response.content.decode())
                    self.assertEqual(self.snapshot(), before)

    def test_edit_and_delete_continuations_cannot_retarget_another_selected_record(self):
        selected = self.chain('continent')['continent']
        other = self.chain('continent')['continent']
        data = {'name': '', 'code': 'DRAFT', 'continent': selected.pk}
        for action, suffix in (('Editar', 'update'), ('Borrar', 'delete')):
            with self.subTest(action=action):
                parent = self.send(self.page('country_create'), data)
                self.assertEqual(parent.status_code, 200)
                child = self.begin(parent, data, 'continent', action, selected)
                query = urlsplit(child.wsgi_request.get_full_path()).query
                target = self.url('continent_' + suffix, other) + '?' + query
                before = self.snapshot()
                self.deny(self.client.get(target))
                _, payload = self.payload(child, {'name': 'Retargeted change'},
                                          self.action(child, 'Guardar' if action == 'Editar' else 'Borrar'))
                self.deny(self.client.post(target, payload))
                self.assertEqual(self.snapshot(), before)

    def test_continuation_purpose_cannot_change_create_to_edit_delete_or_related_entity(self):
        chain = self.chain()
        for wrong_route, obj in (('continent_update', chain['continent']),
                                 ('continent_delete', chain['continent']), ('country_create', None)):
            with self.subTest(route=wrong_route):
                child = self.begin(self.page('country_update', chain['country']), self.geo_data('country', chain), 'continent')
                query = urlsplit(child.wsgi_request.get_full_path()).query
                target = self.url(wrong_route, obj) + '?' + query
                before = self.snapshot()
                self.deny(self.client.get(target))
                _, payload = self.payload(child, self.geo_data('country', chain), self.action(child, 'Guardar'))
                self.deny(self.client.post(target, payload))
                self.assertEqual(self.snapshot(), before)

    def test_return_destination_and_field_are_server_owned_and_parent_id_is_bound(self):
        chain = self.chain()
        other = self.chain()['country']
        data = self.geo_data('country', chain, 'Original parent draft')
        child = self.begin(self.page('country_update', chain['country']), data, 'continent')
        response = self.send(child, {'name': 'Return safely', 'next': 'https://attacker.invalid/',
            'return_url': '//attacker.invalid/', 'return_to': '/admin/', 'field': 'code',
            'return_field': 'name', 'parent_entity': 'Person', 'operation': 'delete', 'purpose': 'arbitrary'})
        if response.status_code in (400, 403, 404):
            self.assertFalse(Continent.objects.filter(name='Return safely').exists())
        else:
            returned = self.follow(response, self.url('country_update', chain['country']))
            created = Continent.objects.get(name='Return safely')
            data['continent'] = created.pk
            self.assert_draft(returned, self.url('country_update', chain['country']), data)
            query = urlsplit(returned.wsgi_request.get_full_path()).query
            before = self.snapshot()
            self.deny(self.client.get(self.url('country_update', other) + '?' + query))
            self.assertEqual(self.snapshot(), before)

    def test_geo_parent_selectors_reject_invented_keys_server_side(self):
        chain = self.chain()
        for parent, field in RELATIONS:
            with self.subTest(parent=parent):
                data = self.geo_data(parent, chain)
                data[field] = max(GEO[field].objects.values_list('pk', flat=True)) + 1
                before = self.snapshot()
                response = self.send(self.page(parent + '_create'), data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'][field].errors)
                self.assertEqual(self.snapshot(), before)

    def test_person_chain_rejects_unrelated_and_missing_ancestors_server_side(self):
        a, b = self.workspace(), self.chain()
        page = self.page('person_create')
        for field in PERSON_RELATIONS:
            for invalid in (b[field].pk, ''):
                with self.subTest(field=field, invalid=invalid):
                    data = self.person_data(a)
                    data[field] = invalid
                    before = self.snapshot()
                    response = self.send(page, data)
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.context['form'].errors)
                    self.assertEqual(self.snapshot(), before)

    def test_person_add_edit_and_cancel_return_same_draft_with_coherent_selection(self):
        chain = self.workspace()
        for field in PERSON_RELATIONS:
            for action in ('Adicionar', 'Editar', 'Cancelar'):
                with self.subTest(field=field, action=action):
                    data = self.person_data(chain)
                    page = self.page('person_create', data={k: o.pk for k, o in chain.items()})
                    child = self.begin(page, data, field, 'Editar' if action == 'Editar' else 'Adicionar', chain[field])
                    before = self.snapshot()
                    if action == 'Cancelar':
                        returned = self.follow(self.send(child, {}, 'Cancelar'), self.url('person_create'))
                        self.assertEqual(self.snapshot(), before)
                    else:
                        new_data = self.geo_data(field, chain, f'Person related {field} {action}')
                        returned = self.follow(self.send(child, new_data), self.url('person_create'))
                        selected = GEO[field].objects.get(name=new_data['name'])
                        data[field] = selected.pk
                        if action == 'Adicionar':
                            for descendant in PERSON_RELATIONS[PERSON_RELATIONS.index(field) + 1:]:
                                data[descendant] = ''
                    self.assert_draft(returned, self.url('person_create'), data)
                    self.assertFalse(Person.objects.filter(identification=data['identification']).exists())

    def test_person_valid_delete_clears_selected_field_and_invalid_descendants(self):
        self.workspace()
        for field in PERSON_RELATIONS:
            with self.subTest(field=field):
                chain = self.chain(field)
                data = self.person_data(chain)
                data['full_name'] = ''  # Preserve an incomplete, never persisted Person.
                for descendant in PERSON_RELATIONS[PERSON_RELATIONS.index(field) + 1:]:
                    data[descendant] = ''
                page = self.send(self.page('person_create'), data)
                self.assertEqual(page.status_code, 200)
                confirm = self.begin(page, data, field, 'Borrar', chain[field])
                returned = self.follow(self.send(confirm, {}, 'Borrar'), self.url('person_create'))
                self.assertFalse(GEO[field].objects.filter(pk=chain[field].pk).exists())
                data[field] = ''
                self.assert_draft(returned, self.url('person_create'), data)

    def test_initial_company_person_geography_navigation_keeps_outer_company_draft(self):
        chain = self.chain()
        self.actor.is_superuser = self.actor.is_staff = True
        self.actor.save()
        company = self.page('company_create')
        person = self.follow(self.send(company, {'commercial_name': 'Outer Company draft'}, 'Adicionar persona'), self.url('person_create'))
        data = self.person_data(chain)
        person = self.send(person, {**data, 'action': 'refresh'})
        self.assertEqual(person.status_code, 200)
        child = self.begin(person, data, 'country')
        returned = self.follow(self.send(child, {}, 'Cancelar'), self.url('person_create'))
        self.assert_draft(returned, self.url('person_create'), data)
        company = self.follow(self.send(returned, {}, 'Cancelar'), self.url('company_create'))
        self.assertEqual(self.value(company, 'commercial_name'), 'Outer Company draft')
        self.assertEqual((Person.objects.count(), Company.objects.count(), Branch.objects.count()), (0, 0, 0))
