"""Fixtures and browser-facing assertions for D-02B.1b; no production shim.

Routes use existing unnamespaced naming conventions: person_list/create/detail/
update and <geography>_list/create/update. Search uses q. Geographic parent
selection uses the real field names (continent, country, province, canton,
parish). Context is server-owned. Related actions are discoverable native POST
buttons with accessible names such as 'Adicionar país' / 'Editar país'. Their
name/value, endpoint, draft storage and return-token implementation are NOT
fixed here. Native forms must let these actions preserve incomplete drafts
without browser required validation blocking the related-data operation.

Operational creation must call B.1a create_person; the current seam accepts no
geography and requires Company. GREEN needs an authorized atomic composition
or an explicitly reviewed extension, never a raw-create bypass. Future initial
setup remains a separate controlled, company-less flow; it is not implemented
or replaced by these tests. Geography catalogs are global and require their
own Django permissions even before any Company exists.
"""

from contextlib import contextmanager, ExitStack
from html.parser import HTMLParser
from pathlib import Path
import sys
import unicodedata
from unittest.mock import patch
from urllib.parse import urlsplit

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.staticfiles import finders
from django.test import Client, TestCase, tag
from django.urls import NoReverseMatch, resolve, reverse

from core.models import Branch, Company
from people.models import CompanyPersonAccess, Person
from people.models.geography import Canton, Continent, Country, Parish, Province
from people.services import person_access_policy as policy


RED_TAG = "d02b1b_person_geography_ui_red"
GEOGRAPHY = (
    ("continent", Continent, "continente", ("name",)),
    ("country", Country, "país", ("continent", "code", "name")),
    ("province", Province, "provincia", ("country", "name")),
    ("canton", Canton, "cantón", ("province", "name")),
    ("parish", Parish, "parroquia", ("canton", "name")),
)
PERSON_FIELDS = (
    "person_type", "identification_type", "identification", "full_name",
    "email", "phone", "continent", "country", "province", "canton", "parish", "address",
)
REQUIRED_FIELDS = set(PERSON_FIELDS) - {"email", "phone", "identification_type"}


def normalized(text):
    return " ".join("".join(c for c in unicodedata.normalize("NFD", text)
                            if not unicodedata.combining(c)).casefold().split())


class Element:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []

    @property
    def text(self):
        return "".join(child.text if isinstance(child, Element) else child for child in self.children)

    def visible(self):
        node = self
        while node:
            if "hidden" in node.attrs or node.attrs.get("aria-hidden") == "true":
                return False
            style = node.attrs.get("style", "").replace(" ", "").lower()
            if "display:none" in style or "visibility:hidden" in style:
                return False
            node = node.parent
        return True


class Document(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Element("document")
        self.current = self.root
        self.nodes = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs, self.current)
        self.current.children.append(node)
        self.nodes.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        # HTML's textarea parsing ignores exactly one immediately leading LF.
        if self.current.tag == "textarea" and not self.current.children and data.startswith("\n"):
            data = data[1:]
        self.current.children.append(data)

    def matching(self, tag=None, **attrs):
        return [node for node in self.nodes if (tag is None or node.tag == tag)
                and all(node.attrs.get(key) == value for key, value in attrs.items())]


@tag(RED_TAG)
class PersonUIFixture(TestCase):
    company_context = True

    def setUp(self):
        for target in (
            "socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection",
            "requests.sessions.Session.request",
            "sri.services.fiscal_document_preparation_service.FiscalDocumentPreparationService.prepare",
            "sri.services.electronic_document_service.ElectronicDocumentService.create",
            "people.models.Person.delete",
        ):
            guard = patch(target, side_effect=AssertionError("No external network, process expansion or Person deletion"))
            guard.start()
            self.addCleanup(guard.stop)
        self.actor = get_user_model().objects.create_user("ui-operator")
        self.other = get_user_model().objects.create_user("ui-other")
        self.admin = get_user_model().objects.create_superuser("ui-admin", "", None)
        self.grant(self.actor, "view_person", "add_person", "change_person", *[
            f"{operation}_{kind}" for kind, *_ in GEOGRAPHY for operation in ("view", "add", "change")
        ])
        self.client.force_login(self.actor)
        if self.company_context:
            self.a = Company.objects.create(person=self.make_person("LEGAL-A"), commercial_name="Workspace A")
            self.b = Company.objects.create(person=self.make_person("LEGAL-B"), commercial_name="Private workspace B")
            self.branch = Branch.objects.create(company=self.a, code="001", name="Matriz")
            self.branch_two = Branch.objects.create(company=self.a, code="002", name="Alterna")
            self.branch_b = Branch.objects.create(company=self.b, code="001", name="B")
            for user in (self.actor, self.admin):
                user.profile.companies.add(self.a, self.b)
                user.profile.branches.add(self.branch, self.branch_two, self.branch_b)
            self.other.profile.companies.add(self.b)
            self.other.profile.branches.add(self.branch_b)
            self.visible_person = self.make_person("VISIBLE-A", email="visible@example.invalid", phone="0991111111", created_by=self.other)
            self.hidden_person = self.make_person("PRIVATE-B", email="private@example.invalid", phone="0992222222", address="Hidden B street", created_by=self.actor, updated_by=self.actor)
            self.inactive_person = self.make_person("INACTIVE-A", is_active=False)
            CompanyPersonAccess.objects.create(company=self.a, person=self.visible_person)
            CompanyPersonAccess.objects.create(company=self.b, person=self.hidden_person)
            CompanyPersonAccess.objects.create(company=self.a, person=self.inactive_person)
            self.context(self.client, self.a, self.branch)

    def make_person(self, identity, **data):
        return Person.objects.create(identification=identity, person_type="LEGAL", full_name="Name " + identity, **data)

    def grant(self, actor, *codes):
        actor.user_permissions.add(*Permission.objects.filter(content_type__app_label="people", codename__in=codes))
        for key in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
            actor.__dict__.pop(key, None)

    def restrict(self, actor, *codes):
        actor.user_permissions.clear()
        actor.groups.clear()
        self.grant(actor, *codes)

    def context(self, client, company=None, branch=None):
        session = client.session
        session["company_id"] = company.pk if company else None
        session["branch_id"] = branch.pk if branch else None
        session.save()

    def url(self, name, obj=None):
        try:
            return reverse(name, args=[obj.pk] if obj is not None else [])
        except NoReverseMatch:
            self.fail(f"RED: missing ERP UI route {name}")

    def page(self, name, obj=None, data=None, client=None):
        response = (client or self.client).get(self.url(name, obj), data or {})
        self.assertEqual(response.status_code, 200)
        return response

    def doc(self, response):
        return Document(response.content.decode())

    def control(self, response, name):
        nodes = [node for node in self.doc(response).matching(name=name)
                 if node.tag in {"input", "select", "textarea"}]
        self.assertEqual(len(nodes), 1, f"Expected one usable field {name}")
        return nodes[0]

    def business_form(self, response, field="person_type"):
        node = self.control(response, field)
        while node and node.tag != "form":
            node = node.parent
        self.assertIsNotNone(node)
        self.assertEqual(node.attrs.get("method", "get").lower(), "post")
        return node

    def inside(self, node, parent):
        while node:
            if node is parent:
                return True
            node = node.parent
        return False

    def submit(self, response, data, field="person_type", button=None, client=None):
        # Read the real form, including opaque tokens; no session implementation assumption.
        doc = self.doc(response)
        controls = [node for node in doc.matching(name=field) if node.tag in {"input", "select", "textarea"}]
        self.assertEqual(len(controls), 1, f"Expected a native form field {field}")
        form = controls[0]
        while form is not None and form.tag != "form":
            form = form.parent
        self.assertIsNotNone(form)
        self.assertEqual(form.attrs.get("method", "get").lower(), "post")
        payload = {node.attrs["name"]: node.attrs.get("value", "") for node in doc.matching("input")
                   if node.attrs.get("type") == "hidden" and node.attrs.get("name") and self.inside(node, form)}
        payload.update(data)
        target = form.attrs.get("action") or response.wsgi_request.get_full_path()
        if button is not None:
            payload[button.attrs["name"]] = button.attrs.get("value", "")
            target = button.attrs.get("formaction") or target
        self.assertFalse(urlsplit(target).netloc or urlsplit(target).scheme)
        return (client or self.client).post(target, payload)

    def follow(self, response, client=None):
        self.assertIn(response.status_code, (302, 303))
        target = response["Location"]
        self.assertFalse(urlsplit(target).scheme or urlsplit(target).netloc, "No external return URL")
        result = (client or self.client).get(target)
        self.assertEqual(result.status_code, 200)
        return result

    def chain(self, suffix="A"):
        continent = Continent.objects.create(name=f"Continent {suffix}")
        country = Country.objects.create(continent=continent, code=suffix, name=f"Country {suffix}")
        province = Province.objects.create(country=country, name=f"Province {suffix}")
        canton = Canton.objects.create(province=province, name=f"Canton {suffix}")
        parish = Parish.objects.create(canton=canton, name=f"Parish {suffix}")
        return dict(zip((kind for kind, *_ in GEOGRAPHY), (continent, country, province, canton, parish)))

    def payload(self, geography=None, **changes):
        values = dict(person_type="NATURAL", identification_type="PASSPORT", identification="NEW-UI",
                      full_name="Human UI draft", email="draft@example.invalid", phone="0993333333", address="Draft address")
        if geography:
            values.update({kind: obj.pk for kind, obj in geography.items()})
        values.update(changes)
        return values

    def selected_values(self, response, field):
        control = self.control(response, field)
        return [node.attrs.get("value", "") for node in control.children
                if isinstance(node, Element) and node.tag == "option" and "selected" in node.attrs]

    def related_button(self, response, kind, action):
        label = dict((key, label) for key, _, label, _ in GEOGRAPHY)[kind]
        buttons = [node for node in self.doc(response).matching("button")
                   if normalized(action) in normalized(node.attrs.get("aria-label", "") + " " + node.text)
                   and normalized(label) in normalized(node.attrs.get("aria-label", "") + " " + node.text)]
        self.assertEqual(len(buttons), 1, f"Discoverable {action} {label} action")
        button = buttons[0]
        self.assertEqual(button.attrs.get("type", "submit"), "submit")
        self.assertTrue(button.attrs.get("name"), "Native related action submits incomplete draft")
        self.assertIn("formnovalidate", button.attrs, "Related action cannot be blocked by incomplete required fields")
        self.assertNotIn("disabled", button.attrs)
        return button

    def assert_draft(self, response, values):
        self.assertEqual(urlsplit(response.wsgi_request.path).path, self.url("person_create"))
        for name, value in values.items():
            with self.subTest(preserved=name):
                node = self.control(response, name)
                if node.tag == "select":
                    self.assertIn(str(value), self.selected_values(response, name))
                elif node.tag == "textarea":
                    self.assertEqual(node.text, str(value))
                else:
                    self.assertEqual(node.attrs.get("value", ""), str(value))

    def snapshot(self):
        return {model._meta.label: list(model.objects.order_by("pk").values())
                for model in apps.get_models() if model._meta.app_label in {
                    "people", "core", "catalog", "sales", "purchases", "inventory", "sri"
                }}

    def assert_no_private_person(self, response, person):
        document = self.doc(response)
        # The search input may echo the operator's own query. Stored record
        # data, other attributes and record links must still remain absent.
        query = response.wsgi_request.GET.get("q", "").strip()[:250]
        content = document.root.text + " ".join(
            str(value) for node in document.nodes for key, value in node.attrs.items()
            if value is not None and not (
                node.tag == "input" and node.attrs.get("name") == "q"
                and key == "value" and value == query
            )
        )
        for value in (person.full_name, person.email, person.phone, person.address):
            if value:
                self.assertNotIn(value, content)
        for name in ("person_detail", "person_update"):
            self.assertNotIn(self.url(name, person), response.content.decode())

    def assert_form_accessibility(self, response, names):
        form = response.context["form"]
        doc = self.doc(response)
        self.assertRegex(normalized(doc.root.text), r"(?:\*.*obligatori|obligatori.*\*)")
        for name in names:
            field = form[name]
            control = self.control(response, name)
            labels = doc.matching("label", **{"for": control.attrs.get("id")})
            self.assertEqual(len(labels), 1)
            self.assertTrue(labels[0].text.strip())
            self.assertEqual("*" in labels[0].text, field.field.required)
            self.assertEqual("required" in control.attrs, field.field.required)
            self.assertTrue(field.help_text, f"Useful form metadata help for {name}")
            described = control.attrs.get("aria-describedby", "").split()
            help_nodes = [node for node in doc.nodes if node.attrs.get("id") in described
                          and str(field.help_text) in node.text and node.visible()]
            self.assertTrue(help_nodes, f"Inline help usable without JS for {name}")
            if field.errors:
                self.assertEqual(control.attrs.get("aria-invalid"), "true")
                for error in field.errors:
                    self.assertTrue([node for node in doc.nodes if node.attrs.get("id") in described
                                     and str(error) in node.text and node.visible()])
        for node in doc.nodes:
            if "tabindex" in node.attrs:
                self.assertLessEqual(int(node.attrs["tabindex"]), 0)
            if node.tag in {"input", "select", "textarea", "button"} and node.attrs.get("type") != "hidden":
                self.assertNotEqual(node.attrs.get("tabindex"), "-1")
        css_path = finders.find("core/css/erp.css")
        self.assertIsNotNone(css_path)
        self.assertIn(":focus-visible", Path(css_path).read_text())

    @contextmanager
    def policy_spy(self, name, route):
        resolve(route)  # Load productive view modules before finding imported aliases.
        original = getattr(policy, name)
        with ExitStack() as stack:
            spy = stack.enter_context(patch.object(policy, name, wraps=original))
            for module_name, module in list(sys.modules.items()):
                if not module_name.startswith("people.") or module_name.startswith("people.tests") or module is None:
                    continue
                aliases = {key: spy for key, value in list(vars(module).items()) if value is original}
                if aliases:
                    stack.enter_context(patch.dict(vars(module), aliases))
            yield spy
