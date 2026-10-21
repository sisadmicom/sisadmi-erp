"""D-02A Phase 1: frozen browser contracts from the approved Phase 0.

Only initial_setup and select_company route names are fixed. Native buttons
are discovered by human labels; hidden wizard/draft tokens and POST endpoints
are read from HTML. Step fields use existing domain names, with ``address``
for Person's legal address (never a duplicate Company address).

No JavaScript is executed. Geography actions accept incomplete drafts, use
native POST, and return to the originating wizard. Storage/session draft
format is deliberately unspecified. Back, cancel and copy-address buttons
must bypass browser validation. Company/actor authority is server owned.

Identity collisions may echo user input. Only independent stored sentinels,
record links and existence-revealing messages are treated as disclosures.
DOM keyboard/focus checks do not certify actual screen-reader usability;
that remains a human GREEN gate. Sequential double submission is covered;
simultaneous first-company races remain an explicit GREEN design decision.
"""

from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.db import connection
from django.db.models.signals import post_save, m2m_changed
from django.test import Client, TestCase, TransactionTestCase, tag
from django.urls import reverse

from core.models import Branch, Company
from core.tests.test_form_ux_foundation_red import Document, FormUXAssertions
from people.models import CompanyPersonAccess, Person
from people.models.geography import Canton, Continent, Country, Parish, Province
from users.models import UserProfile


RED_TAG = "d02a_initial_company_setup_red"
GEO = (("continent", Continent), ("country", Country), ("province", Province),
       ("canton", Canton), ("parish", Parish))
STEPS = ("Datos de la empresa", "Ubicación", "Sucursal principal", "Revisar y crear")
FIELDS = (("identification_type", "identification", "full_name", "email", "phone", "commercial_name"),
          ("continent", "country", "province", "canton", "parish", "address"),
          ("branch_code", "branch_name", "branch_address"))


class SetupContract(FormUXAssertions):
    def setUp(self):
        super().setUp()
        self.actor = get_user_model().objects.create_superuser("sisadmi", "", "setup-test-pass")
        self.assertTrue(UserProfile.objects.filter(user=self.actor).exists())
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.actor)
        self.url = reverse("initial_setup")
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        # Local PostgreSQL is allowed; guards activate after test DB connection.
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection",
                       "requests.sessions.Session.request",
                       "sri.services.fiscal_document_preparation_service.FiscalDocumentPreparationService.prepare",
                       "sri.services.electronic_document_service.ElectronicDocumentService.create"):
            self.stack.enter_context(patch(target, side_effect=AssertionError("D-02A: no network or fiscal effects")))
        self.assert_business_empty()

    def counts(self):
        return tuple(model.objects.count() for model in (Person, Company, Branch, CompanyPersonAccess,
                     UserProfile.companies.through, UserProfile.branches.through))

    def assert_business_empty(self):
        self.assertEqual(self.counts(), (0, 0, 0, 0, 0, 0))
        self.assertIsNone(self.client.session.get("company_id"))
        self.assertIsNone(self.client.session.get("branch_id"))

    def chain(self, suffix="A"):
        # Every call owns a chain; multiple subtests must not collide on code.
        suffix = str(Country.objects.count()) + suffix
        suffix = suffix[:5]
        result = {}
        for index, (kind, model) in enumerate(GEO):
            data = {"name": "Setup " + kind + suffix}
            if index:
                data[GEO[index - 1][0]] = result[GEO[index - 1][0]]
            if kind == "country":
                data["code"] = suffix
            result[kind] = model.objects.create(**data)
        return result

    def company_data(self, **changes):
        data = dict(identification_type="RUC", identification="1300000001001",
                    full_name="Empresa escrita por el usuario", commercial_name="Comercial escrito",
                    email="", phone="")
        data.update(changes)
        return data

    def location_data(self, chain=None, **changes):
        chain = chain or self.chain()
        data = {kind: obj.pk for kind, obj in chain.items()}
        data["address"] = "Dirección legal escrita"
        data.update(changes)
        return data

    def branch_data(self, **changes):
        data = dict(branch_code="007", branch_name="Sucursal escrita", branch_address="Dirección sucursal escrita")
        data.update(changes)
        return data

    def document(self, page):
        self.assertEqual(page.status_code, 200)
        return Document(page.content.decode())

    def field_node(self, page, name):
        nodes = [n for n in self.document(page).matching(name=name) if n.tag in {"input", "select", "textarea"}]
        self.assertEqual(len(nodes), 1, "Native wizard field: " + name)
        return nodes[0]

    def button(self, page, label, document=None):
        nodes = [n for n in (document if document is not None else self.document(page)).matching("button") if label.casefold() in
                 (n.text + " " + n.attrs.get("aria-label", "")).casefold()]
        self.assertEqual(len(nodes), 1, "Discoverable native action: " + label)
        node = nodes[0]
        self.assertEqual(node.attrs.get("type", "submit"), "submit")
        self.assertNotIn("disabled", node.attrs)
        return node

    def inside(self, node, parent):
        while node:
            if node is parent:
                return True
            node = node.parent
        return False

    def submission(self, page, data, label):
        doc = self.document(page)
        button = self.button(page, label, document=doc)
        form = button
        while form and form.tag != "form":
            form = form.parent
        self.assertIsNotNone(form, "Action must be usable without JavaScript")
        self.assertEqual(form.attrs.get("method", "get").lower(), "post")
        payload = {}
        for n in doc.elements:
            if not self.inside(n, form) or not n.attrs.get("name") or "disabled" in n.attrs:
                continue
            name = n.attrs["name"]
            if n.tag == "input" and n.attrs.get("type") not in {"submit", "button", "checkbox", "radio"}:
                payload[name] = n.attrs.get("value", "")
            elif n.tag == "textarea":
                payload[name] = n.text
            elif n.tag == "select":
                chosen = [o for o in n.children if getattr(o, "tag", None) == "option" and "selected" in o.attrs]
                payload[name] = chosen[0].attrs.get("value", "") if chosen else ""
        payload.update(data)
        if button.attrs.get("name"):
            payload[button.attrs["name"]] = button.attrs.get("value", "")
        target = button.attrs.get("formaction") or form.attrs.get("action") or page.wsgi_request.get_full_path()
        self.assertFalse(urlsplit(target).netloc or urlsplit(target).scheme)
        self.assertIn("csrfmiddlewaretoken", payload)
        return target, payload

    def submit(self, page, data, label, *, follow=True):
        target, payload = self.submission(page, data, label)
        response = self.client.post(target, payload)
        if follow and response.status_code in (302, 303):
            self.assertFalse(urlsplit(response.url).netloc or urlsplit(response.url).scheme)
            response = self.client.get(response.url)
        return response

    def start(self):
        page = self.client.get(self.url)
        doc = self.document(page)
        if any(n.attrs.get("aria-current") == "step" and STEPS[0] not in n.text for n in doc.elements):
            self.submit(page, {}, "Cancelar")
            page = self.client.get(self.url)
        self.assert_step(page, 0)
        return page

    def assert_step(self, page, index):
        doc = self.document(page)
        self.assertIn(STEPS[index], doc.root.text)
        current = [n for n in doc.elements if n.attrs.get("aria-current") == "step"]
        self.assertEqual(len(current), 1, "Accessible current setup progress")
        self.assertIn(STEPS[index], current[0].text)
        for title in STEPS:
            self.assertIn(title, doc.root.text)
        if index < 3:
            self.assertEqual(set(page.context["form"].fields), set(FIELDS[index]))

    def location(self, **company_changes):
        page = self.submit(self.start(), self.company_data(**company_changes), "Continuar")
        self.assert_step(page, 1)
        self.assert_business_empty()
        return page

    def branch(self, chain=None):
        page = self.submit(self.location(), self.location_data(chain), "Continuar")
        self.assert_step(page, 2)
        self.assert_business_empty()
        return page

    def review(self, chain=None, **company_changes):
        page = self.location(**company_changes)
        page = self.submit(page, self.location_data(chain), "Continuar")
        self.assert_step(page, 2)
        page = self.submit(page, self.branch_data(), "Continuar")
        self.assert_step(page, 3)
        self.assert_business_empty()
        return page

    def assert_values(self, page, values):
        for name, value in values.items():
            n = self.field_node(page, name)
            if n.tag == "select":
                selected = [o.attrs.get("value", "") for o in n.children
                            if getattr(o, "tag", None) == "option" and "selected" in o.attrs]
                self.assertIn(str(value), selected)
            else:
                self.assertEqual(n.text.strip() if n.tag == "textarea" else n.attrs.get("value", ""), str(value))


@tag(RED_TAG)
class InitialSetupEntryRedTests(SetupContract, TestCase):
    def test_acceptance_fixture_has_empty_business_and_geography(self):
        self.assert_business_empty()
        self.assertTrue(self.actor.is_active and self.actor.is_superuser)
        self.assertEqual([m.objects.count() for _, m in GEO], [0] * 5)

    def test_existing_login_leads_to_natural_setup_action(self):
        self.client.logout()
        login = self.client.get(reverse("login"))
        doc = self.document(login)
        token = doc.matching("input", name="csrfmiddlewaretoken")[0].attrs["value"]
        response = self.client.post(reverse("login"), {"username": "sisadmi", "password": "setup-test-pass", "csrfmiddlewaretoken": token})
        self.assertRedirects(response, reverse("select_company"), fetch_redirect_response=False)
        page = self.client.get(response.url)
        links = [n for n in self.document(page).matching("a") if "Configurar empresa" in n.text]
        self.assertEqual(len(links), 1)
        self.assertEqual(urlsplit(links[0].attrs["href"]).path, self.url)
        self.assert_business_empty()

    def test_pre_context_shell_only_relevant_navigation(self):
        for url in (reverse("select_company"), self.url):
            with self.subTest(url=url):
                page = self.client.get(url)
                doc = self.document(page)
                for text in ("SISADMI", self.actor.username, "Ayuda", "Cerrar sesión"):
                    self.assertIn(text.casefold(), doc.root.text.casefold())
                for n in doc.elements:
                    if n.tag in {"a", "button"}:
                        for text in ("Productos", "Nueva venta", "Inventario", "Compras"):
                            self.assertNotIn(text.casefold(), n.text.casefold())
                for text in ("CompanyPersonAccess", "memberships", "Person", "/admin/"):
                    self.assertNotIn(text, page.content.decode())

    def test_anonymous_cannot_enter_or_submit(self):
        self.client.logout()
        for method in ("get", "head", "post"):
            response = getattr(self.client, method)(self.url)
            self.assertIn(response.status_code, (302, 403))
            if response.status_code == 302:
                self.assertIn(reverse("login"), response.url)
        self.assert_business_empty()

    def test_staff_supervisor_developer_do_not_grant_bootstrap(self):
        self.actor.is_superuser = False
        self.actor.is_staff = True
        self.actor.save()
        profile = self.actor.profile
        profile.is_supervisor = profile.is_developer = True
        profile.save()
        page = self.client.get(reverse("select_company"))
        self.assertNotContains(page, "Configurar empresa")
        self.assertRegex(self.document(page).root.text.casefold(), r"administrador|solicite|autoriz")
        self.assertIn(self.client.get(self.url).status_code, (302, 403, 404))
        self.assert_business_empty()

    def test_inactive_actor_cannot_submit_even_with_session(self):
        self.actor.is_active = False
        self.actor.save()
        self.assertIn(self.client.get(self.url).status_code, (302, 403, 404))
        self.assert_business_empty()

    def test_missing_profile_denies_without_recreating_profile(self):
        UserProfile.objects.filter(user=self.actor).delete()
        self.client.raise_request_exception = False
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertFalse(UserProfile.objects.filter(user=self.actor).exists())
        self.assert_business_empty()

    def test_any_company_including_inactive_closes_entry_and_post(self):
        person = Person.objects.create(identification="EXISTING", person_type="LEGAL", full_name="Existing")
        company = Company.objects.create(person=person, commercial_name="Existing", is_active=False)
        before = self.counts()
        self.assertNotContains(self.client.get(reverse("select_company")), "Configurar empresa")
        self.assertIn(self.client.get(self.url).status_code, (302, 403, 404))
        page = self.client.get(reverse("select_company"))
        token = self.document(page).matching("input", name="csrfmiddlewaretoken")[0].attrs["value"]
        response = self.client.post(self.url, {**self.company_data(), "csrfmiddlewaretoken": token})
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertEqual(self.counts(), before)
        self.assertFalse(self.actor.profile.companies.filter(pk=company.pk).exists())


@tag(RED_TAG)
class InitialSetupWizardRedTests(SetupContract, TestCase):
    def test_four_steps_review_retains_values_without_business_persistence(self):
        chain = self.chain()
        page = self.review(chain)
        text = self.document(page).root.text
        for value in (*self.company_data().values(), self.location_data(chain)["address"], *self.branch_data().values()):
            if value:
                self.assertIn(str(value), text)
        for obj in chain.values():
            self.assertIn(obj.name, text)
        self.button(page, "Crear empresa")
        self.assert_business_empty()

    def test_backward_forward_preserves_all_three_drafts(self):
        chain = self.chain()
        page = self.review(chain)
        page = self.submit(page, {}, "Anterior")
        self.assert_step(page, 2)
        self.assert_values(page, self.branch_data())
        page = self.submit(page, self.branch_data(), "Anterior")
        self.assert_step(page, 1)
        self.assert_values(page, self.location_data(chain))
        page = self.submit(page, self.location_data(chain), "Anterior")
        self.assert_step(page, 0)
        self.assert_values(page, self.company_data())
        page = self.submit(page, self.company_data(), "Continuar")
        self.assert_values(page, self.location_data(chain))
        page = self.submit(page, self.location_data(chain), "Continuar")
        self.assert_values(page, self.branch_data())
        self.assert_business_empty()

    def test_branch_has_no_hidden_defaults(self):
        page = self.branch()
        self.assert_values(page, dict.fromkeys(FIELDS[2], ""))
        self.assertNotIn("is_main", page.context["form"].fields)

    def test_explicit_copy_legal_address_works_without_javascript(self):
        page = self.branch()
        button = self.button(page, "Usar la dirección legal")
        self.assertIn("formnovalidate", button.attrs)
        page = self.submit(page, {"branch_code": "008", "branch_name": "Otra", "branch_address": ""}, "Usar la dirección legal")
        self.assert_values(page, {"branch_code": "008", "branch_name": "Otra", "branch_address": "Dirección legal escrita"})
        self.assert_business_empty()

    def test_native_back_and_cancel_bypass_required_validation(self):
        page = self.branch()
        for label in ("Anterior", "Cancelar"):
            self.assertIn("formnovalidate", self.button(page, label).attrs)
        response = self.submit(page, dict.fromkeys(FIELDS[2], ""), "Cancelar")
        self.assertEqual(response.status_code, 200)
        self.assert_business_empty()
        self.assertEqual(self.document(self.start()).matching("input", name="full_name")[0].attrs.get("value", ""), "")

    def test_actor_drafts_are_isolated(self):
        self.location(full_name="Private actor draft sentinel")
        other = get_user_model().objects.create_superuser("other-founder", "", None)
        client = Client()
        client.force_login(other)
        page = client.get(self.url)
        self.assertNotContains(page, "Private actor draft sentinel")
        self.assert_business_empty()

    def test_independent_browser_does_not_reveal_same_actor_draft(self):
        self.location(full_name="Private browser draft sentinel")
        client = Client()
        client.force_login(self.actor)
        self.assertNotContains(client.get(self.url), "Private browser draft sentinel")
        self.assert_business_empty()

    def test_single_legacy_post_cannot_bypass_steps_and_confirmation(self):
        page = self.client.get(self.url)
        token = self.document(page).matching("input", name="csrfmiddlewaretoken")[0].attrs["value"]
        payload = {**self.company_data(), **self.branch_data(), **self.location_data(),
                   "company_address": "Legacy bypass", "csrfmiddlewaretoken": token}
        self.client.post(self.url, payload)
        self.assert_business_empty()

    def test_geography_return_cannot_redirect_to_external_destination(self):
        page = self.location()
        geo = self.submit(page, {"address": "Draft", "next": "https://outside.invalid/", "return_to": "https://outside.invalid/"}, "Adicionar continente")
        result = self.submit(geo, {"name": "Safe return", "next": "https://outside.invalid/", "return_to": "https://outside.invalid/"}, "Guardar")
        self.assert_step(result, 1)
        self.assert_values(result, {"address": "Draft"})
        self.assert_business_empty()

    def test_assets_are_local_and_native_controls_keep_keyboard_access(self):
        for page in (self.start(), self.location(), self.branch(), self.review()):
            doc = self.document(page)
            self.assert_keyboard_contract(doc)
            for node in doc.elements:
                if node.tag in {"script", "link"}:
                    url = node.attrs.get("src" if node.tag == "script" else "href", "")
                    self.assertFalse(urlsplit(url).netloc or urlsplit(url).scheme)
            self.assert_business_empty()

    def test_user_markup_is_escaped_and_retained(self):
        value = '<script>alert("user-input")</script>'
        page = self.submit(self.start(), self.company_data(full_name=value, email="bad-email"), "Continuar")
        self.assert_values(page, {"full_name": value})
        self.assertNotContains(page, value)
        self.assert_business_empty()

    def test_shared_d02e1_required_optional_help_keyboard_focus(self):
        pages = [self.start(), self.location(), self.branch()]
        for index, page in enumerate(pages):
            with self.subTest(step=index):
                self.assertTemplateUsed(page, "core/components/form_fields.html")
                doc = self.document(page)
                form = page.context["form"]
                self.assertRegex(doc.root.text.casefold(), r"\*.*obligatori|obligatori.*\*")
                for name in FIELDS[index]:
                    field = form[name]
                    required = name not in {"email", "phone"}
                    self.assertEqual(field.field.required, required)
                    label = self.label(doc, field)
                    self.assertEqual("*" in label.text, required)
                    self.assertEqual("(opcional)" in label.text.casefold(), not required)
                    self.assertEqual("required" in self.control(doc, field).attrs, required)
                    self.assertTrue(field.help_text)
                    helper = self.one(doc, **{"data-help-for": field.id_for_label})
                    self.assertTrue(helper.visible_without_js())
                    self.assertIn(str(field.help_text), helper.text)
                    self.assertIn(helper.attrs["id"], self.control(doc, field).attrs.get("aria-describedby", "").split())
                self.assert_keyboard_contract(doc)
        css = finders.find("core/css/erp.css")
        self.assertIsNotNone(css)
        self.assertIn(":focus-visible", Path(css).read_text())
        self.assertNotRegex(Path(css).read_text(), r"outline\s*:\s*(?:none|0)\s*[;}]")

    def test_required_errors_per_field_are_linked_without_persistence(self):
        for index in range(3):
            with self.subTest(step=index):
                page = self.start() if index == 0 else self.location() if index == 1 else self.branch()
                page = self.submit(page, dict.fromkeys(FIELDS[index], ""), "Continuar")
                self.assert_step(page, index)
                doc = self.document(page)
                form = page.context["form"]
                for name in set(FIELDS[index]) - {"email", "phone"}:
                    self.assertIn(name, form.errors)
                    control = self.control(doc, form[name])
                    self.assertEqual(control.attrs.get("aria-invalid"), "true")
                    ids = control.attrs.get("aria-describedby", "").split()
                    for error in form[name].errors:
                        self.assertTrue([n for n in doc.elements if n.attrs.get("id") in ids and str(error) in n.text and n.visible_without_js()])
                self.assert_business_empty()

    def test_server_validates_identity_type_shape_email_and_lengths(self):
        for changes, field in (({"identification_type": "INVALID"}, "identification_type"),
                               ({"identification": "123"}, "identification"),
                               ({"email": "invalid"}, "email"),
                               ({"full_name": "x" * 251}, "full_name"),
                               ({"commercial_name": "x" * 201}, "commercial_name")):
            with self.subTest(field=field):
                response = self.submit(self.start(), self.company_data(**changes), "Continuar")
                self.assertIn(field, response.context["form"].errors)
                self.assert_business_empty()

    def test_no_geography_cannot_advance_and_explains_catalog_creation(self):
        page = self.location()
        self.assertRegex(self.document(page).root.text.casefold(), r"no existen|no hay|sin datos|no.*disponib")
        for kind, _ in GEO:
            self.assertEqual(list(page.context["form"].fields[kind].queryset), [])
            self.button(page, "Adicionar " + {"continent": "continente", "country": "país", "province": "provincia", "canton": "cantón", "parish": "parroquia"}[kind])
        page = self.submit(page, {"address": "Written address"}, "Continuar")
        for kind, _ in GEO:
            self.assertIn(kind, page.context["form"].errors)
        self.assert_business_empty()

    def test_geographic_selectors_filter_each_parent_without_js(self):
        chain, other = self.chain("A"), self.chain("B")
        page = self.submit(self.location(), self.location_data(chain, address=""), "Continuar")
        form = page.context["form"]
        for kind, _ in GEO[1:]:
            self.assertIn(chain[kind], form.fields[kind].queryset)
            self.assertNotIn(other[kind], form.fields[kind].queryset)
        self.assert_business_empty()

    def test_server_rejects_each_cross_parent_relation(self):
        chain, other = self.chain("A"), self.chain("B")
        for kind, _ in GEO[1:]:
            with self.subTest(child=kind):
                page = self.submit(self.location(), self.location_data(chain, **{kind: other[kind].pk}), "Continuar")
                self.assert_step(page, 1)
                self.assertIn(kind, page.context["form"].errors)
                self.assert_business_empty()

    def test_server_rejects_missing_deleted_malformed_geography(self):
        chain = self.chain()
        for value in ("", "not-an-id", str(chain["parish"].pk + 1000000)):
            page = self.submit(self.location(), self.location_data(chain, parish=value), "Continuar")
            self.assertIn("parish", page.context["form"].errors)
            self.assert_business_empty()

    def test_native_geography_creation_and_return_preserves_draft_from_empty_catalogs(self):
        page = self.location(full_name="Saved before geography")
        values = {"address": "Incomplete legal draft"}
        for index, (kind, model) in enumerate(GEO):
            label = {"continent": "continente", "country": "país", "province": "provincia", "canton": "cantón", "parish": "parroquia"}[kind]
            button = self.button(page, "Adicionar " + label)
            self.assertIn("formnovalidate", button.attrs)
            geo = self.submit(page, values, "Adicionar " + label)
            data = {"name": "Created from setup " + kind}
            if index:
                data[GEO[index - 1][0]] = values[GEO[index - 1][0]]
            if kind == "country":
                data["code"] = "EC"
            self.assertTemplateUsed(geo, "core/components/form_fields.html")
            page = self.submit(geo, data, "Guardar")
            self.assert_step(page, 1)
            values[kind] = model.objects.get(name=data["name"]).pk
            self.assert_values(page, values)
            self.assert_business_empty()
        page = self.submit(page, values, "Anterior")
        self.assert_values(page, self.company_data(full_name="Saved before geography"))
        self.submit(page, {}, "Cancelar")
        self.assertEqual([m.objects.count() for _, m in GEO], [1] * 5)
        self.assert_business_empty()

    def test_get_head_all_wizard_steps_and_geography_do_not_write_business(self):
        pages = (self.start(), self.location(), self.branch(), self.review())
        for page in pages:
            for method in ("get", "head"):
                getattr(self.client, method)(page.wsgi_request.get_full_path())
                self.assert_business_empty()
        for kind, _ in GEO:
            for method in ("get", "head"):
                getattr(self.client, method)(reverse(kind + "_create"))
                self.assert_business_empty()

    def test_csrf_required_on_every_wizard_and_geographic_post(self):
        for page, data, label in ((self.start(), self.company_data(), "Continuar"),
                                  (self.location(), {}, "Continuar"),
                                  (self.branch(), self.branch_data(), "Continuar"),
                                  (self.review(), {}, "Crear empresa")):
            target, payload = self.submission(page, data, label)
            payload.pop("csrfmiddlewaretoken")
            self.assertEqual(self.client.post(target, payload).status_code, 403)
            self.assert_business_empty()
        for kind, _ in GEO:
            self.assertEqual(self.client.post(reverse(kind + "_create"), {"name": "Without CSRF"}).status_code, 403)


@tag(RED_TAG)
class InitialSetupConfirmationRedTests(SetupContract, TransactionTestCase):
    def test_confirmation_creates_exact_graph_memberships_audit_and_context(self):
        chain = self.chain()
        page = self.review(chain)
        response = self.submit(page, {"person_type": "NATURAL", "is_main": "false", "company_id": "99999",
                              "branch_id": "99999", "created_by": "99999", "updated_by": "99999"}, "Crear empresa", follow=False)
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertEqual(self.counts(), (1, 1, 1, 1, 1, 1))
        person, company, branch = Person.objects.get(), Company.objects.get(), Branch.objects.get()
        self.assertEqual(person.person_type, "LEGAL")
        self.assertEqual(company.person_id, person.pk)
        self.assertEqual(branch.company_id, company.pk)
        self.assertTrue(branch.is_main)
        self.assertEqual(person.address, "Dirección legal escrita")
        for kind, obj in chain.items():
            if kind != "continent":
                self.assertEqual(getattr(person, kind + "_id"), obj.pk)
        self.assertNotIn("continent", {f.name for f in Person._meta.fields})
        for name, value in self.company_data().items():
            if name not in {"commercial_name", "email"}:
                self.assertEqual(getattr(person, name), value)
        self.assertFalse(person.email)
        self.assertEqual(company.commercial_name, self.company_data()["commercial_name"])
        self.assertFalse(company.logo)
        for name, value in self.branch_data().items():
            self.assertEqual(getattr(branch, name.removeprefix("branch_")), value)
        for obj in (person, company, branch):
            self.assertEqual((obj.created_by_id, obj.updated_by_id), (self.actor.pk, self.actor.pk))
        access = CompanyPersonAccess.objects.get()
        self.assertEqual((access.company_id, access.person_id), (company.pk, person.pk))
        self.assertEqual(list(self.actor.profile.companies.all()), [company])
        self.assertEqual(list(self.actor.profile.branches.all()), [branch])
        self.assertEqual(self.client.session["company_id"], company.pk)
        self.assertEqual(self.client.session["branch_id"], branch.pk)
        self.assertEqual(UserProfile.objects.filter(user=self.actor).count(), 1)
        self.assertContains(self.client.get(response.url), "Productos")

    def test_each_business_stage_and_membership_failure_rolls_back_and_keeps_session_empty(self):
        # Signals hit real persistence independent of service imports/create style.
        stages = (Person, Company, Branch, CompanyPersonAccess,
                  UserProfile.companies.through, UserProfile.branches.through)
        for index, model in enumerate(stages):
            with self.subTest(stage=model._meta.label):
                page = self.review(self.chain(str(index)))
                fired = []
                def fail(sender, **kwargs):
                    if kwargs.get("action") in (None, "post_add"):
                        fired.append(True)
                        raise RuntimeError("D-02A persistence sentinel")
                signal = m2m_changed if model in stages[-2:] else post_save
                signal.connect(fail, sender=model, weak=False)
                try:
                    self.client.raise_request_exception = False
                    response = self.submit(page, {}, "Crear empresa", follow=False)
                    self.assertTrue(fired, "Fault injection must reach " + model._meta.label)
                    self.assertIn(response.status_code, (200, 302, 303, 500))
                    self.assert_business_empty()
                finally:
                    signal.disconnect(fail, sender=model)
                    self.client.raise_request_exception = True

    def test_creation_and_memberships_are_atomic_context_not_set_before_commit(self):
        observed = []
        models = (Person, Company, Branch, CompanyPersonAccess,
                  UserProfile.companies.through, UserProfile.branches.through)
        def observe(sender, **kwargs):
            if kwargs.get("action") in (None, "post_add"):
                observed.append(sender)
                self.assertTrue(connection.in_atomic_block)
                self.assertIsNone(self.client.session.get("company_id"))
                self.assertIsNone(self.client.session.get("branch_id"))
        page = self.review()
        for model in models:
            (m2m_changed if model in models[-2:] else post_save).connect(observe, sender=model, weak=False)
        try:
            response = self.submit(page, {}, "Crear empresa", follow=False)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(set(observed), set(models))
        finally:
            for model in models:
                (m2m_changed if model in models[-2:] else post_save).disconnect(observe, sender=model)

    def test_double_confirmation_is_idempotent_and_bootstrap_stays_closed(self):
        page = self.review()
        target, payload = self.submission(page, {}, "Crear empresa")
        first = self.client.post(target, payload)
        self.assertEqual(first.status_code, 302)
        counts = self.counts()
        self.assertEqual(counts, (1, 1, 1, 1, 1, 1))
        context = (self.client.session["company_id"], self.client.session["branch_id"])
        self.client.post(target, payload)
        self.assertEqual(self.counts(), counts)
        self.assertEqual((self.client.session["company_id"], self.client.session["branch_id"]), context)
        self.assertIn(self.client.get(self.url).status_code, (302, 403, 404))
        self.assertNotContains(self.client.get(reverse("select_company")), "Configurar empresa")

    def test_revalidates_authority_if_company_appears_before_confirmation(self):
        page = self.review()
        person = Person.objects.create(identification="OTHER", person_type="LEGAL", full_name="Other founder")
        Company.objects.create(person=person, commercial_name="Other", is_active=False)
        before = self.counts()
        self.submit(page, {}, "Crear empresa", follow=False)
        self.assertEqual(self.counts(), before)
        self.assertIsNone(self.client.session.get("company_id"))
        self.assertIsNone(self.client.session.get("branch_id"))

    def test_revalidates_actor_and_profile_at_confirmation(self):
        page = self.review()
        self.actor.is_superuser = False
        self.actor.save()
        self.submit(page, {}, "Crear empresa", follow=False)
        self.assert_business_empty()

    def test_missing_profile_at_confirmation_denies_without_partial_graph(self):
        page = self.review()
        UserProfile.objects.filter(user=self.actor).delete()
        self.client.raise_request_exception = False
        response = self.submit(page, {}, "Crear empresa", follow=False)
        self.assertIn(response.status_code, (302, 403, 404))
        self.assertFalse(UserProfile.objects.filter(user=self.actor).exists())
        self.assert_business_empty()

    def test_existing_identity_at_first_step_is_neutral_and_never_auto_associated(self):
        stored = Person.objects.create(identification=self.company_data()["identification"], person_type="LEGAL",
                                       full_name="PRIVATE first-step name", email="first-private@example.invalid")
        page = self.submit(self.start(), self.company_data(), "Continuar")
        text = self.document(page).root.text.casefold()
        for value in (stored.full_name, stored.email):
            self.assertNotIn(value, page.content.decode())
        self.assertNotRegex(text, r"ya existe|existente|registrad[ao]|duplicad[ao]|unique|integrityerror")
        self.assertEqual(self.counts(), (1, 0, 0, 0, 0, 0))

    def test_session_context_writes_only_after_committed_business_graph(self):
        from django.contrib.sessions.backends.base import SessionBase
        original = SessionBase.__setitem__
        observed = []
        def observe(session, key, value):
            if key in {"company_id", "branch_id"} and value is not None:
                self.assertFalse(connection.in_atomic_block, "Context must be written after commit")
                self.assertEqual(self.counts(), (1, 1, 1, 1, 1, 1))
                observed.append(key)
            return original(session, key, value)
        page = self.review()
        with patch.object(SessionBase, "__setitem__", observe):
            response = self.submit(page, {}, "Crear empresa", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(set(observed), {"company_id", "branch_id"})

    def test_confirmation_revalidates_deleted_geography(self):
        chain = self.chain()
        page = self.review(chain)
        chain["parish"].delete()
        response = self.submit(page, {}, "Crear empresa")
        self.assertEqual(response.status_code, 200)
        self.assertRegex(self.document(response).root.text.casefold(), r"parroquia|ubicación|revise")
        self.assert_business_empty()

    def test_neutral_collision_distinguishes_user_input_from_recovered_system_data(self):
        page = self.review()
        stored = Person.objects.create(identification=self.company_data()["identification"], person_type="LEGAL",
                    full_name="PRIVATE stored name sentinel", email="private-sentinel@example.invalid",
                    phone="PRIVATE-PHONE", address="PRIVATE stored address sentinel")
        before = list(Person.objects.values())
        response = self.submit(page, {}, "Crear empresa")
        self.assertEqual(response.status_code, 200)
        doc = self.document(response)
        # Echoing the typed identification is allowed; stored values are not.
        for value in (stored.full_name, stored.email, stored.phone, stored.address):
            self.assertNotIn(value, response.content.decode())
        for route in ("person_detail", "person_update"):
            self.assertNotIn(reverse(route, args=[stored.pk]), response.content.decode())
        self.assertNotRegex(doc.root.text.casefold(), r"ya existe|existente|registrad[ao]|duplicad[ao]|unique|integrityerror")
        alerts = [n for n in doc.elements if n.attrs.get("role") == "alert" and n.visible_without_js()]
        self.assertTrue(alerts, "Neutral general error must be visible and announced")
        self.assertRegex(" ".join(n.text for n in alerts).casefold(), r"identificación|revise|revis|utilizar")
        self.assertEqual(list(Person.objects.values()), before)
        self.assertEqual(self.counts(), (1, 0, 0, 0, 0, 0))
        self.assertIsNone(self.client.session.get("company_id"))
        self.assertIsNone(self.client.session.get("branch_id"))

    def test_success_has_no_network_fiscal_inventory_sales_purchase_effects(self):
        models = [m for m in apps.get_models() if m._meta.app_label in {"sri", "inventory", "sales", "purchases"}]
        before = {m._meta.label: list(m.objects.order_by("pk").values()) for m in models}
        page = self.review()
        self.assertEqual(self.submit(page, {}, "Crear empresa", follow=False).status_code, 302)
        self.assertEqual({m._meta.label: list(m.objects.order_by("pk").values()) for m in models}, before)
        # Network/fiscal entrypoint guards installed for every test stay active.
