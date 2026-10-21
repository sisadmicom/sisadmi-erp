"""Global geographic catalogs through ERP UI, including an empty installation."""

from django.test import Client

from core.models import Company
from people.models import Person
from people.tests.person_ui_support import GEOGRAPHY, PersonUIFixture, normalized


class GeographyUITests(PersonUIFixture):
    def geo_data(self, kind, chain, name="New geographic name"):
        values = {"name": name}
        index = [entry[0] for entry in GEOGRAPHY].index(kind)
        if index:
            parent = GEOGRAPHY[index - 1][0]
            values[parent] = chain[parent].pk
        if kind == "country":
            values["code"] = "NEW"
        return values

    def test_catalog_lists_offer_normal_erp_create_edit_without_admin_or_delete(self):
        chain = self.chain()
        for kind, _, label, _ in GEOGRAPHY:
            with self.subTest(catalog=kind):
                response = self.page(kind + "_list")
                self.assertContains(response, chain[kind].name)
                self.assertContains(response, self.url(kind + "_create"))
                self.assertContains(response, self.url(kind + "_update", chain[kind]))
                for link in self.doc(response).matching("a"):
                    self.assertNotIn("/admin/", link.attrs.get("href", ""))
                    self.assertNotIn("/delete/", link.attrs.get("href", ""))
                self.assertNotRegex(normalized(self.doc(response).root.text), r"\b(?:pk|foreignkey|queryset)\b")

    def test_small_geographic_forms_use_real_required_fields_and_accessible_help(self):
        chain = self.chain()
        for kind, _, _, fields in GEOGRAPHY:
            for operation in ("create", "update"):
                with self.subTest(catalog=kind, operation=operation):
                    response = self.page(kind + "_" + operation, chain[kind] if operation == "update" else None)
                    form = response.context["form"]
                    visible = {field.name for field in form.visible_fields()}
                    self.assertEqual(visible, set(fields))
                    self.assertTrue(all(form.fields[field].required for field in fields))
                    self.assert_form_accessibility(response, fields)
                    self.business_form(response, "name")

    def test_empty_person_selectors_explain_missing_catalog_and_offer_authorized_actions(self):
        response = self.page("person_create")
        text = normalized(self.doc(response).root.text)
        self.assertRegex(text, r"(?:no existen|no hay|sin datos|no.*disponib)")
        for kind, _, _, _ in GEOGRAPHY:
            with self.subTest(catalog=kind):
                self.related_button(response, kind, "Adicionar")
        self.restrict(self.actor, "view_person", "add_person", *["view_" + kind for kind, *_ in GEOGRAPHY])
        restricted = self.page("person_create")
        self.assertRegex(normalized(self.doc(restricted).root.text), r"(?:administrador|solicite|solicitar)")
        for node in self.doc(restricted).nodes:
            if node.tag in {"a", "button"}:
                self.assertNotIn("adicionar", normalized(node.attrs.get("aria-label", "") + " " + node.text))
        for technical in ("DoesNotExist", "PermissionDenied", "ForeignKey", "QuerySet", "Traceback"):
            self.assertNotContains(restricted, technical)

    def test_related_add_edit_actions_follow_each_catalog_permission(self):
        chain = self.chain()
        page = self.page("person_create", data={key: value.pk for key, value in chain.items()})
        for kind, *_ in GEOGRAPHY:
            with self.subTest(catalog=kind):
                self.related_button(page, kind, "Adicionar")
                self.related_button(page, kind, "Editar")
        self.restrict(self.actor, "view_person", "add_person", *["view_" + kind for kind, *_ in GEOGRAPHY])
        page = self.page("person_create", data={key: value.pk for key, value in chain.items()})
        for node in self.doc(page).nodes:
            if node.tag in {"a", "button"}:
                action = normalized(node.attrs.get("aria-label", "") + " " + node.text)
                self.assertFalse(any(word in action for word in ("adicionar", "editar")))

    def test_native_create_edit_saves_each_existing_geographic_model(self):
        chain = self.chain()
        self.restrict(self.actor, *[f"{operation}_{kind}" for kind, *_ in GEOGRAPHY for operation in ("view", "add", "change")])
        before_persons = list(Person.objects.order_by("pk").values())
        for kind, model, _, _ in GEOGRAPHY:
            with self.subTest(catalog=kind):
                response = self.page(kind + "_create")
                saved = self.submit(response, self.geo_data(kind, chain, "Created " + kind), field="name")
                landing = self.follow(saved)
                created = model.objects.get(name="Created " + kind)
                self.assertContains(landing, created.name)
                response = self.page(kind + "_update", created)
                edited = self.submit(response, self.geo_data(kind, chain, "Edited " + kind), field="name")
                landing = self.follow(edited)
                created.refresh_from_db()
                self.assertEqual(created.name, "Edited " + kind)
                self.assertContains(landing, created.name)
        self.assertEqual(list(Person.objects.order_by("pk").values()), before_persons)

    def test_geographic_views_enforce_permissions_even_with_known_routes_and_ids(self):
        chain = self.chain()
        self.restrict(self.actor, "view_person", "add_person", "change_person")
        before = self.snapshot()
        for kind, _, _, _ in GEOGRAPHY:
            for operation in ("list", "create", "update"):
                for method in (("get",) if operation == "list" else ("get", "post")):
                    with self.subTest(catalog=kind, operation=operation, method=method):
                        response = getattr(self.client, method)(self.url(kind + "_" + operation, chain[kind] if operation == "update" else None), self.geo_data(kind, chain))
                        self.assertEqual(response.status_code, 403)
                        self.assertRegex(normalized(self.doc(response).root.text), r"(?:permiso|autoriz|acceso)")
                        self.assertNotContains(response, "PermissionDenied", status_code=403)
        self.assertEqual(self.snapshot(), before)

    def test_get_head_catalogs_and_forms_leave_all_business_and_process_records_unchanged(self):
        chain = self.chain()
        before = self.snapshot()
        for kind, *_ in GEOGRAPHY:
            for operation in ("list", "create", "update"):
                for method in ("get", "head"):
                    with self.subTest(catalog=kind, operation=operation, method=method):
                        response = getattr(self.client, method)(self.url(kind + "_" + operation, chain[kind] if operation == "update" else None))
                        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.snapshot(), before)

    def test_geographic_post_requires_csrf_and_preserves_invalid_name(self):
        chain = self.chain()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.actor)
        self.context(strict, self.a, self.branch)
        before = self.snapshot()
        for kind, *_ in GEOGRAPHY:
            for operation in ("create", "update"):
                with self.subTest(catalog=kind, operation=operation):
                    obj = chain[kind] if operation == "update" else None
                    rejected = strict.post(self.url(kind + "_" + operation, obj), self.geo_data(kind, chain))
                    self.assertEqual(rejected.status_code, 403)
                    page = self.page(kind + "_" + operation, obj, client=strict)
                    response = self.submit(page, self.geo_data(kind, chain, ""), field="name", client=strict)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("name", response.context["form"].errors)
                    self.assert_form_accessibility(response, GEOGRAPHY[[row[0] for row in GEOGRAPHY].index(kind)][3])
        self.assertEqual(self.snapshot(), before)


class EmptyInstallationGeographyTests(PersonUIFixture):
    company_context = False

    def test_authorized_admin_can_build_geography_before_company_without_person_scope_bypass(self):
        self.client.force_login(self.admin)
        values = {}
        for kind, model, _, fields in GEOGRAPHY:
            with self.subTest(catalog=kind):
                page = self.page(kind + "_create")
                data = {"name": "Bootstrap " + kind}
                for parent in fields:
                    if parent in values:
                        data[parent] = values[parent].pk
                if kind == "country":
                    data["code"] = "BOOT"
                self.follow(self.submit(page, data, field="name"))
                values[kind] = model.objects.get(name=data["name"])
        self.assertEqual(Company.objects.count(), 0)
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(self.client.get(self.url("initial_setup")).status_code, 200)
        # Normal Person creation remains contextual. A future bootstrap composer
        # must explicitly authorize the company-less legal-person operation.
        response = self.client.post(self.url("person_create"), self.payload(values))
        self.assertIn(response.status_code, (302, 403))
        self.assertEqual(Person.objects.count(), 0)
