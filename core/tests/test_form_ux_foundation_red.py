"""D-02E.1 frozen RED: reusable form presentation, not domain expansion.

Public rendering seam: core/components/form_fields.html receives ``form``.
It renders fields/help/errors only; callers own POST, CSRF and submit actions.
The host has data-form-ux; inline help has data-help-for=<widget id>.
The contextual panel has data-contextual-help; JavaScript activation is optional. Inline help remains
available without JavaScript; enhancement must never own validation.

Pilot: existing FoundingPersonForm / founding_person_edit, unchanged fields,
permissions, persistence and domain rules. A synthetic Form proves reuse.
Keyboard DOM contracts are automated; real focus/help transitions, responsive
layout and assistive-technology behavior remain mandatory human UX gates.
"""

from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.test import Client, SimpleTestCase, TestCase, tag
from django.urls import reverse

from core.forms import FoundingPersonForm
from core.models import Branch, Company
from people.models import Person


RED_TAG = "d02e1_form_ux_foundation_red"
COMPONENT = "core/components/form_fields.html"
PILOT_FIELDS = ("identification_type", "identification", "full_name", "email", "phone", "address")
ATTACK = '<script>alert("unsafe")</script>'


class Element:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children = []

    @property
    def text(self):
        return "".join(child.text if isinstance(child, Element) else child for child in self.children)

    def visible_without_js(self):
        current = self
        while current is not None:
            attrs = current.attrs
            style = attrs.get("style", "").replace(" ", "").lower()
            if "hidden" in attrs or attrs.get("aria-hidden") == "true":
                return False
            if "display:none" in style or "visibility:hidden" in style:
                return False
            current = current.parent
        return True


class Document(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Element("document")
        self.current = self.root
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs, self.current)
        self.current.children.append(node)
        self.elements.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        if self.current.tag == "textarea" and not self.current.children and data.startswith("\n"):
            data = data[1:]
        self.current.children.append(data)

    def matching(self, tag=None, **attrs):
        return [node for node in self.elements if (tag is None or node.tag == tag)
                and all(node.attrs.get(key) == value for key, value in attrs.items())]


class PresentationProbeForm(forms.Form):
    reference = forms.CharField(label="Referencia", help_text="Escriba la referencia de esta operación.")
    contact = forms.CharField(label="Contacto", required=False, help_text="Contacto para comunicaciones.")
    units = forms.DecimalField(label="Unidades", min_value=1, help_text="Indique las unidades.")
    memo = forms.CharField(label="Observación", required=False, widget=forms.Textarea)
    token = forms.CharField(widget=forms.HiddenInput, initial="opaque-test-token")


class FormUXAssertions:
    def one(self, document, tag=None, **attrs):
        found = document.matching(tag, **attrs)
        self.assertEqual(len(found), 1, f"Expected one {tag or 'element'} with {attrs}; found {len(found)}")
        return found[0]

    def control(self, document, field):
        return self.one(document, id=field.id_for_label)

    def label(self, document, field):
        return self.one(document, "label", **{"for": field.id_for_label})

    def assert_keyboard_contract(self, document):
        for node in document.elements:
            if "tabindex" in node.attrs:
                self.assertLessEqual(int(node.attrs["tabindex"]), 0, "No artificial positive tab order")
            if node.tag in {"input", "select", "textarea", "button"} and node.attrs.get("type") != "hidden":
                self.assertNotEqual(node.attrs.get("tabindex"), "-1", "Interactive controls must remain keyboard reachable")
                self.assertNotIn("onfocus", node.attrs)
                self.assertNotIn("onblur", node.attrs)
            self.assertNotIn("accesskey", node.attrs, "Do not override browser/assistive-technology shortcuts")

    def assert_local_assets_and_no_js_validation(self, document):
        for node in document.elements:
            if node.tag not in {"script", "link"}:
                continue
            attribute = "src" if node.tag == "script" else "href"
            asset = node.attrs.get(attribute)
            if asset:
                parsed = urlsplit(asset)
                self.assertFalse(parsed.scheme or parsed.netloc, "No CDN or external asset")
                self.assertTrue(parsed.path.startswith(settings.STATIC_URL), "Assets must use local Django static")
                relative = parsed.path[len(settings.STATIC_URL):]
                resolved = finders.find(relative)
                self.assertIsNotNone(resolved, f"Missing local asset: {relative}")
                if node.tag == "script":
                    source = Path(resolved).read_text()
                    self.assertNotRegex(source, r"setCustomValidity\s*\(|checkValidity\s*\(|reportValidity\s*\(")
                    self.assertNotRegex(source, r"\b(?:RUC|CEDULA|identification_type)\b", "Presentation JS must not duplicate identity rules")
                    self.assertNotRegex(source, r"\b(?:fetch|XMLHttpRequest|WebSocket)\b", "Help must not need network")
            elif node.tag == "script":
                self.assertFalse(node.text.strip(), "Progressive enhancement must use a local static asset")


@tag(RED_TAG)
class ReusableFormUXRedTests(FormUXAssertions, SimpleTestCase):
    def render_component(self, form):
        try:
            html = render_to_string(COMPONENT, {"form": form})
        except TemplateDoesNotExist:
            self.fail(f"D-02E.1 RED: reusable component {COMPONENT} does not exist")
        return Document(html)

    def test_component_is_reusable_and_does_not_own_form_or_submit(self):
        form = PresentationProbeForm(prefix="operation")
        doc = self.render_component(form)
        self.assertEqual(len([node for node in doc.elements if "data-form-ux" in node.attrs]), 1)
        self.assertFalse(doc.matching("form"), "Host owns POST and CSRF")
        self.assertFalse([node for node in doc.elements if node.tag == "button" or node.attrs.get("type") == "submit"])
        for field in form:
            self.control(doc, field)

    def test_required_is_derived_from_field_required_including_runtime_changes(self):
        for required in (True, False):
            with self.subTest(required=required):
                form = PresentationProbeForm()
                form.fields["reference"].required = required
                doc = self.render_component(form)
                label = self.label(doc, form["reference"])
                self.assertEqual("*" in label.text, required)
                self.assertEqual("required" in self.control(doc, form["reference"]).attrs, required)
                self.assertEqual("opcional" in label.text.lower(), not required)

    def test_required_star_has_textual_explanation_and_native_semantics(self):
        form = PresentationProbeForm()
        doc = self.render_component(form)
        self.assertIn("*", self.label(doc, form["reference"]).text)
        self.assertRegex(" ".join(doc.root.text.lower().split()), r"(?:\*.*obligatori|obligatori.*\*)")
        self.assertIn("required", self.control(doc, form["reference"]).attrs)

    def test_optional_fields_are_explicit_without_required_star(self):
        form = PresentationProbeForm()
        doc = self.render_component(form)
        for name in ("contact", "memo"):
            label = self.label(doc, form[name])
            self.assertIn("(opcional)", label.text.lower())
            self.assertNotIn("*", label.text)
            self.assertNotIn("required", self.control(doc, form[name]).attrs)

    def test_help_text_is_dynamic_source_and_accessibly_associated(self):
        form = PresentationProbeForm(prefix="arbitrary")
        form.fields["contact"].help_text = "Ayuda distinta declarada exclusivamente en el Form."
        doc = self.render_component(form)
        for name in ("reference", "contact", "units"):
            field = form[name]
            helper = self.one(doc, **{"data-help-for": field.id_for_label})
            self.assertIn(str(field.help_text), helper.text)
            self.assertTrue(helper.attrs.get("id"))
            self.assertIn(helper.attrs["id"], self.control(doc, field).attrs.get("aria-describedby", "").split())

    def test_inline_help_is_available_without_javascript(self):
        form = PresentationProbeForm()
        doc = self.render_component(form)
        for name in ("reference", "contact", "units"):
            helper = self.one(doc, **{"data-help-for": form[name].id_for_label})
            self.assertTrue(helper.visible_without_js())
        self.assertFalse(doc.matching("noscript"), "Normal form and help cannot depend on a noscript fallback")

    def test_contextual_help_has_generic_progressive_enhancement_seam(self):
        form = PresentationProbeForm(prefix="other")
        doc = self.render_component(form)
        panels = [node for node in doc.elements if "data-contextual-help" in node.attrs]
        self.assertEqual(len(panels), 1, "Shared contextual-help target, not a screen-specific panel")
        panel = panels[0]
        self.assertEqual(panel.attrs.get("aria-live"), "polite")
        self.assertTrue(panel.attrs.get("aria-label") or panel.attrs.get("aria-labelledby"))
        for identifier in panel.attrs.get("aria-labelledby", "").split():
            self.assertTrue(self.one(doc, id=identifier).text.strip())
        self.assert_keyboard_contract(doc)
        self.assert_local_assets_and_no_js_validation(doc)

    def test_field_errors_have_ids_invalid_semantics_and_text_not_only_color(self):
        form = PresentationProbeForm(data={"reference": "", "units": "0", "token": "opaque"}, prefix=None)
        self.assertFalse(form.is_valid())
        doc = self.render_component(form)
        for name in ("reference", "units"):
            field = form[name]
            control = self.control(doc, field)
            self.assertEqual(control.attrs.get("aria-invalid"), "true")
            described = control.attrs.get("aria-describedby", "").split()
            for error in field.errors:
                associated = [node for node in doc.elements if node.attrs.get("id") in described and str(error) in node.text]
                self.assertTrue(associated, f"Error for {name} must be linked and readable")
                self.assertTrue(any(node.visible_without_js() for node in associated))

    def test_non_field_errors_are_visible_and_announced(self):
        form = PresentationProbeForm(data={"reference": "valid", "units": "2", "token": "opaque"})
        self.assertTrue(form.is_valid())
        message = "La operación necesita revisión conjunta."
        form.add_error(None, message)
        doc = self.render_component(form)
        alerts = [node for node in doc.elements if node.attrs.get("role") == "alert" and message in node.text]
        self.assertTrue(alerts, "Non-field errors need visible alert semantics")
        self.assertTrue(any(node.visible_without_js() for node in alerts))

    def test_invalid_bound_form_retains_values_including_textarea(self):
        values = {"reference": "Referencia digitada", "contact": "contacto digitado", "units": "not-a-number", "memo": "Primera línea\nSegunda línea", "token": "opaque"}
        form = PresentationProbeForm(data=values)
        self.assertFalse(form.is_valid())
        doc = self.render_component(form)
        for name in ("reference", "contact", "units"):
            self.assertEqual(self.control(doc, form[name]).attrs.get("value"), values[name])
        self.assertEqual(self.control(doc, form["memo"]).text.strip(), values["memo"])

    def test_labels_help_values_and_error_text_are_escaped(self):
        form = PresentationProbeForm(data={"reference": ATTACK, "contact": ATTACK, "units": "2", "memo": ATTACK, "token": "opaque"})
        form.fields["reference"].label = ATTACK
        form.fields["contact"].help_text = ATTACK
        self.assertTrue(form.is_valid())
        form.add_error("units", ATTACK)
        form.add_error(None, ATTACK)
        doc = self.render_component(form)
        self.assertFalse([node for node in doc.matching("script") if not node.attrs.get("src")], "Untrusted strings must not become executable markup")
        self.assert_local_assets_and_no_js_validation(doc)
        self.assertIn(ATTACK, self.label(doc, form["reference"]).text)
        self.assertIn(ATTACK, self.one(doc, **{"data-help-for": form["contact"].id_for_label}).text)
        self.assertEqual(self.control(doc, form["reference"]).attrs.get("value"), ATTACK)
        control = self.control(doc, form["units"])
        described = control.attrs.get("aria-describedby", "").split()
        self.assertTrue(any(node.attrs.get("id") in described and ATTACK in node.text for node in doc.elements))
        self.assertTrue(any(node.attrs.get("role") == "alert" and ATTACK in node.text for node in doc.elements))

    def test_multiple_prefixed_forms_keep_unique_ids_and_help_associations(self):
        first = self.render_component(PresentationProbeForm(prefix="first"))
        second = self.render_component(PresentationProbeForm(prefix="second"))
        ids = [node.attrs["id"] for doc in (first, second) for node in doc.elements if node.attrs.get("id")]
        self.assertEqual(len(ids), len(set(ids)), "Component IDs cannot be hard-coded across instances")

    def test_hidden_fields_do_not_gain_visible_required_optional_labels(self):
        form = PresentationProbeForm()
        doc = self.render_component(form)
        self.assertFalse(doc.matching("label", **{"for": form["token"].id_for_label}))
        self.assertEqual(self.control(doc, form["token"]).attrs.get("type"), "hidden")

    def test_keyboard_order_is_native_and_every_visible_field_has_a_label(self):
        form = PresentationProbeForm(prefix="keyboard")
        doc = self.render_component(form)
        self.assert_keyboard_contract(doc)
        controls = [node.attrs.get("name") for node in doc.elements if node.tag in {"input", "select", "textarea"} and node.attrs.get("type") != "hidden"]
        self.assertEqual(controls, [field.html_name for field in form.visible_fields()])
        for field in form.visible_fields():
            self.assertTrue(self.label(doc, field).text.strip())

    def test_presentation_does_not_mutate_required_help_or_form_validation(self):
        form = PresentationProbeForm(data={"reference": "", "units": "0", "token": "opaque"})
        self.assertFalse(form.is_valid())
        before = (tuple((name, tuple(errors)) for name, errors in form.errors.items()), {name: (field.required, field.help_text) for name, field in form.fields.items()})
        self.render_component(form)
        after = (tuple((name, tuple(errors)) for name, errors in form.errors.items()), {name: (field.required, field.help_text) for name, field in form.fields.items()})
        self.assertEqual(after, before)


@tag(RED_TAG)
class FoundingPersonPilotUXRedTests(FormUXAssertions, TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("form-ux-founder", "", "test-password")
        self.person = Person.objects.create(identification_type="RUC", identification="1790000001001", person_type="LEGAL", full_name="Empresa piloto", email="pilot@example.invalid", phone="022345678", address="Domicilio piloto")
        self.company = Company.objects.create(person=self.person, commercial_name="Piloto")
        self.branch = Branch.objects.create(company=self.company, code="001", name="Matriz")
        self.user.profile.companies.add(self.company)
        self.user.profile.branches.add(self.branch)
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        session = self.client.session
        session["company_id"] = self.company.pk
        session["branch_id"] = self.branch.pk
        session.save()
        self.url = reverse("founding_person_edit")

    def payload(self, **changes):
        result = {name: getattr(self.person, name) for name in FoundingPersonForm.Meta.fields}
        result.update(changes)
        return result

    def pilot_csrf_token(self, doc):
        # The shared shell also has a logout form: inspect the pilot form only.
        pilot_form = self.one(doc, id="id_email").parent
        while pilot_form is not None and pilot_form.tag != "form":
            pilot_form = pilot_form.parent
        self.assertIsNotNone(pilot_form)
        tokens = []
        for node in doc.matching("input", name="csrfmiddlewaretoken"):
            ancestor = node.parent
            while ancestor is not None and ancestor.tag != "form":
                ancestor = ancestor.parent
            if ancestor is pilot_form:
                tokens.append(node)
        self.assertEqual(len(tokens), 1, "Exactly one CSRF token belongs to the pilot POST form")
        return tokens[0]

    def invalid_post(self, **changes):
        response = self.client.get(self.url)
        doc = Document(response.content.decode())
        token = self.pilot_csrf_token(doc).attrs["value"]
        data = self.payload(email="invalid-email", **changes)
        data["csrfmiddlewaretoken"] = token
        return self.client.post(self.url, data)

    def test_pilot_renders_shared_component_with_unchanged_domain_fields(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, COMPONENT)
        self.assertEqual(tuple(response.context["form"].fields), PILOT_FIELDS)
        self.assertEqual(FoundingPersonForm.Meta.fields, PILOT_FIELDS)

    def test_pilot_labels_match_actual_form_required_policy(self):
        response = self.client.get(self.url)
        doc = Document(response.content.decode())
        form = response.context["form"]
        for field in form.visible_fields():
            label = self.label(doc, field)
            self.assertEqual("*" in label.text, field.field.required)
            self.assertEqual("(opcional)" in label.text.lower(), not field.field.required)

    def test_pilot_help_comes_from_form_and_survives_without_javascript(self):
        original_init = FoundingPersonForm.__init__
        help_message = "Ayuda del correo declarada en el formulario piloto."
        def with_help(form, *args, **kwargs):
            original_init(form, *args, **kwargs)
            form.fields["email"].help_text = help_message
        with patch.object(FoundingPersonForm, "__init__", with_help):
            response = self.client.get(self.url)
        doc = Document(response.content.decode())
        field = response.context["form"]["email"]
        helper = self.one(doc, **{"data-help-for": field.id_for_label})
        self.assertIn(help_message, helper.text)
        self.assertTrue(helper.visible_without_js())
        self.assertIn(helper.attrs["id"], self.control(doc, field).attrs.get("aria-describedby", "").split())

    def test_invalid_post_preserves_typed_values_and_does_not_write(self):
        before = (self.person.updated_at, self.person.full_name, self.person.email, self.person.address)
        response = self.invalid_post(full_name="Nombre ya digitado", address="Dirección\nsegunda línea", phone="0998765432")
        self.assertEqual(response.status_code, 200)
        doc = Document(response.content.decode())
        form = response.context["form"]
        self.assertFalse(form.is_valid())
        self.assertEqual(self.control(doc, form["full_name"]).attrs["value"], "Nombre ya digitado")
        self.assertEqual(self.control(doc, form["email"]).attrs["value"], "invalid-email")
        self.assertEqual(self.control(doc, form["phone"]).attrs["value"], "0998765432")
        select = self.control(doc, form["identification_type"])
        options = [node for node in select.children if isinstance(node, Element) and node.tag == "option" and "selected" in node.attrs]
        self.assertEqual([node.attrs["value"] for node in options], ["RUC"])
        self.assertEqual(self.control(doc, form["address"]).text.strip(), "Dirección\nsegunda línea")
        self.person.refresh_from_db()
        self.assertEqual((self.person.updated_at, self.person.full_name, self.person.email, self.person.address), before)
        self.assertEqual((Person.objects.count(), Company.objects.count(), Branch.objects.count()), (1, 1, 1))

    def test_no_javascript_submission_still_uses_server_domain_validation(self):
        response = self.invalid_post(identification="123")
        self.assertEqual(response.status_code, 200)
        self.assertIn("identification", response.context["form"].errors)
        self.assertIn("email", response.context["form"].errors)
        self.person.refresh_from_db()
        self.assertEqual(self.person.identification, "1790000001001")

    def test_valid_native_post_saves_and_returns_without_javascript(self):
        doc = Document(self.client.get(self.url).content.decode())
        data = self.payload(full_name="Nombre actualizado", email="updated@example.invalid")
        data["csrfmiddlewaretoken"] = self.pilot_csrf_token(doc).attrs["value"]
        before_memberships = (set(self.user.profile.companies.values_list("pk", flat=True)),
                              set(self.user.profile.branches.values_list("pk", flat=True)))
        response = self.client.post(self.url, data)
        self.assertRedirects(response, reverse("dashboard"))
        self.person.refresh_from_db()
        self.assertEqual((self.person.full_name, self.person.email), ("Nombre actualizado", "updated@example.invalid"))
        self.assertEqual(self.person.updated_by_id, self.user.pk)
        self.assertEqual((Person.objects.count(), Company.objects.count(), Branch.objects.count()), (1, 1, 1))
        self.assertEqual((set(self.user.profile.companies.values_list("pk", flat=True)),
                          set(self.user.profile.branches.values_list("pk", flat=True))), before_memberships)

    def test_pilot_keeps_csrf_and_rejects_post_without_token(self):
        get_response = self.client.get(self.url)
        doc = Document(get_response.content.decode())
        token = self.pilot_csrf_token(doc)
        self.assertTrue(token.attrs.get("value"))
        self.assertEqual(token.attrs.get("type"), "hidden")
        response = self.client.post(self.url, self.payload(full_name="Unauthorized write"))
        self.assertEqual(response.status_code, 403)
        self.person.refresh_from_db()
        self.assertEqual(self.person.full_name, "Empresa piloto")

    def test_pilot_has_native_post_submit_keyboard_and_local_assets(self):
        response = self.client.get(self.url)
        doc = Document(response.content.decode())
        forms_found = doc.matching("form", method="post")
        self.assertTrue(forms_found)
        self.assertTrue(any(node.tag == "button" and node.attrs.get("type") == "submit" and "Guardar" in node.text for node in doc.elements))
        self.assert_keyboard_contract(doc)
        self.assert_local_assets_and_no_js_validation(doc)
        css = Path(finders.find("core/css/erp.css")).read_text()
        self.assertIn(":focus-visible", css)
        self.assertNotRegex(css, r"outline\s*:\s*(?:none|0)\s*[;}]", "Visible keyboard focus must remain")

    def test_pilot_invalid_values_are_escaped(self):
        response = self.invalid_post(full_name=ATTACK, address=ATTACK)
        doc = Document(response.content.decode())
        self.assertFalse([node for node in doc.matching("script") if not node.attrs.get("src")])
        self.assert_local_assets_and_no_js_validation(doc)
        self.assertEqual(self.control(doc, response.context["form"]["full_name"]).attrs["value"], ATTACK)
        self.assertEqual(self.control(doc, response.context["form"]["address"]).text.strip(), ATTACK)
