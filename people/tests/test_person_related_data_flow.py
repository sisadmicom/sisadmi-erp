"""Complete native related-data journey; opaque drafts, safe return, no JS."""

from urllib.parse import urlsplit

from people.models import CompanyPersonAccess, Person
from people.tests.person_ui_support import GEOGRAPHY, PersonUIFixture, normalized


class RelatedDataFlowTests(PersonUIFixture):
    def begin(self, page, data, kind, action="Adicionar"):
        button = self.related_button(page, kind, action)
        result = self.submit(page, data, button=button)
        self.assertIn(result.status_code, (302, 303))
        expected = self.url(kind + "_create") if action == "Adicionar" else self.url(kind + "_update", self.chain_objects[kind])
        self.assertEqual(urlsplit(result["Location"]).path, expected)
        return self.follow(result)

    def test_empty_chain_can_be_created_from_person_draft_then_complete_person_is_saved(self):
        page = self.page("person_create")
        draft = self.payload(address="Draft line one\nDraft line two")
        original_persons = Person.objects.count()
        before = self.snapshot()
        geography = {}
        for index, (kind, model, _, fields) in enumerate(GEOGRAPHY):
            with self.subTest(catalog=kind):
                related = self.begin(page, draft, kind)
                data = {"name": "Journey " + kind}
                for parent in fields:
                    if parent in geography:
                        data[parent] = geography[parent].pk
                if kind == "country":
                    data["code"] = "JRNY"
                page = self.follow(self.submit(related, data, field="name"))
                created = model.objects.get(name=data["name"])
                geography[kind] = created
                draft[kind] = created.pk
                self.assert_draft(page, draft)
                self.assertEqual(Person.objects.count(), original_persons, "A draft is not a persisted Person")
        result = self.submit(page, draft)
        person = Person.objects.get(identification=draft["identification"])
        self.assertEqual(self.follow(result).wsgi_request.path, self.url("person_detail", person))
        self.assertTrue(CompanyPersonAccess.objects.filter(company=self.a, person=person).exists())
        self.assertEqual(person.parish_id, geography["parish"].pk)
        after = self.snapshot()
        allowed = {"people.Person", "people.CompanyPersonAccess", "core.AuditLog"} | {model._meta.label for _, model, *_ in GEOGRAPHY}
        for model in before.keys() - allowed:
            self.assertEqual(after[model], before[model], model)

    def test_related_edit_returns_to_same_person_draft_and_preserves_safe_selection(self):
        self.chain_objects = self.chain()
        draft = self.payload(self.chain_objects)
        page = self.page("person_create", data={key: value.pk for key, value in self.chain_objects.items()})
        related = self.begin(page, draft, "country", "Editar")
        country = self.chain_objects["country"]
        result = self.submit(related, {"continent": country.continent_id, "code": country.code, "name": "Country renamed"}, field="name")
        returned = self.follow(result)
        self.assert_draft(returned, draft)
        country.refresh_from_db()
        self.assertEqual(country.name, "Country renamed")
        self.assertContains(returned, "Country renamed")
        self.assertFalse(Person.objects.filter(identification=draft["identification"]).exists())

    def test_cancel_related_creation_returns_without_losing_draft_or_creating_catalog_row(self):
        geography = self.chain()
        draft = self.payload(geography)
        page = self.page("person_create", data={key: value.pk for key, value in geography.items()})
        related = self.begin(page, draft, "country")
        before = self.snapshot()
        controls = [node for node in self.doc(related).nodes if node.tag in {"a", "button"}
                    and "cancelar" in normalized(node.attrs.get("aria-label", "") + " " + node.text)]
        self.assertEqual(len(controls), 1)
        cancel = controls[0]
        if cancel.tag == "a":
            target = cancel.attrs["href"]
            self.assertFalse(urlsplit(target).scheme or urlsplit(target).netloc)
            returned = self.client.get(target)
            if returned.status_code in (302, 303):
                returned = self.follow(returned)
        else:
            self.assertIn("formnovalidate", cancel.attrs)
            returned = self.follow(self.submit(related, {}, field="name", button=cancel))
        self.assertEqual(returned.status_code, 200)
        self.assert_draft(returned, draft)
        self.assertEqual(self.snapshot(), before)

    def test_untrusted_return_targets_cannot_redirect_to_external_or_arbitrary_internal_routes(self):
        chain = self.chain()
        for index, target in enumerate(("https://outside.example/steal", "//outside.example/steal", "/admin/")):
            with self.subTest(target=target):
                page = self.page("country_create", data={"next": target, "return_to": target})
                result = self.submit(page, {"continent": chain["continent"].pk, "code": "X" + str(index),
                                            "name": "Return test " + str(index), "next": target, "return_to": target}, field="name")
                self.assertIn(result.status_code, (200, 302, 303, 400, 403))
                if result.status_code in (302, 303):
                    location = urlsplit(result["Location"])
                    self.assertFalse(location.scheme or location.netloc)
                    self.assertNotEqual(location.path, "/admin/")
                self.assertNotIn("Traceback", result.content.decode())

    def test_related_draft_is_not_disclosed_or_restored_to_another_authenticated_actor(self):
        geography = self.chain()
        draft = self.payload(geography, full_name="Private actor draft", email="private-draft@example.invalid")
        page = self.page("person_create", data={key: value.pk for key, value in geography.items()})
        related = self.begin(page, draft, "country")
        saved_url = related.wsgi_request.get_full_path()
        before = list(Person.objects.order_by("pk").values())
        self.grant(self.other, "view_person", "add_person", *[
            f"{operation}_{kind}" for kind, *_ in GEOGRAPHY for operation in ("view", "add", "change")
        ])
        self.client.force_login(self.other)
        self.context(self.client, self.b, self.branch_b)
        result = self.client.get(saved_url)
        self.assertIn(result.status_code, (200, 400, 403, 404))
        for value in (draft["full_name"], draft["email"]):
            self.assertNotIn(value, result.content.decode())
        result = self.submit(related, {"continent": geography["continent"].pk, "code": "OTHER", "name": "Other country"}, field="name")
        self.assertIn(result.status_code, (200, 302, 303, 400, 403, 404))
        if result.status_code in (302, 303):
            result = self.follow(result)
        for value in (draft["full_name"], draft["email"]):
            self.assertNotIn(value, result.content.decode())
        self.assertEqual(list(Person.objects.order_by("pk").values()), before)

    def test_changing_company_during_related_operation_never_rebinds_the_original_draft(self):
        geography = self.chain()
        draft = self.payload(geography, full_name="Private company draft")
        page = self.page("person_create", data={key: value.pk for key, value in geography.items()})
        related = self.begin(page, draft, "country")
        before = list(CompanyPersonAccess.objects.order_by("pk").values())
        self.context(self.client, self.b, self.branch_b)
        result = self.submit(related, {"continent": geography["continent"].pk, "code": "SWCH", "name": "Switch country"}, field="name")
        self.assertIn(result.status_code, (200, 302, 303, 400, 403, 404))
        if result.status_code in (302, 303):
            result = self.follow(result)
        self.assertNotIn(draft["full_name"], result.content.decode())
        self.assertFalse(Person.objects.filter(identification=draft["identification"]).exists())
        self.assertEqual(list(CompanyPersonAccess.objects.order_by("pk").values()), before)
