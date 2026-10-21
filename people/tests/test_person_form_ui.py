"""Complete Person form: server validation, B.1a creation, accessible UI."""

from django.test import Client

from people.models import CompanyPersonAccess, Person
from people.tests.person_ui_support import PERSON_FIELDS, REQUIRED_FIELDS, PersonUIFixture, normalized


class PersonFormTests(PersonUIFixture):
    def test_form_groups_real_fields_requires_identity_location_and_keeps_contact_optional(self):
        self.chain()
        for name, obj in (("person_create", None), ("person_update", self.visible_person)):
            with self.subTest(route=name):
                response = self.page(name, obj)
                form = response.context["form"]
                self.assertEqual({field.name for field in form.visible_fields()}, set(PERSON_FIELDS))
                self.assertEqual({key for key, field in form.fields.items() if field.required},
                                 REQUIRED_FIELDS - {"identification"} if obj else REQUIRED_FIELDS)
                self.assertNotIn("continent", {field.name for field in Person._meta.fields})
                for group in ("Identidad", "Contacto", "Ubicación"):
                    self.assertIn(normalized(group), normalized(self.doc(response).root.text))
                self.assert_form_accessibility(response, PERSON_FIELDS)
                self.business_form(response)

    def test_creation_calls_secure_seam_saves_full_location_and_company_audit_atomically(self):
        geography = self.chain()
        self.restrict(self.actor, "view_person", "add_person", "view_continent", "view_country", "view_province", "view_canton", "view_parish")
        response = self.page("person_create")
        before = self.snapshot()
        route = self.url("person_create")
        with self.policy_spy("create_person", route) as create, self.policy_spy("can_create_person", route) as authority:
            result = self.submit(response, self.payload(geography))
        self.assertIn(result.status_code, (302, 303))
        self.assertTrue(create.called)
        self.assertTrue(authority.called)
        for call in create.call_args_list:
            self.assertEqual(call.kwargs["actor"].pk, self.actor.pk)
            self.assertEqual(call.kwargs["company"].pk, self.a.pk)
        person = Person.objects.get(identification="NEW-UI")
        self.assertEqual((person.created_by_id, person.updated_by_id), (self.actor.pk, self.actor.pk))
        for kind in ("country", "province", "canton", "parish"):
            self.assertEqual(getattr(person, kind + "_id"), geography[kind].pk)
        self.assertEqual(set(CompanyPersonAccess.objects.filter(person=person).values_list("company_id", flat=True)), {self.a.pk})
        self.assertEqual(self.follow(result).wsgi_request.path, self.url("person_detail", person))
        after = self.snapshot()
        for model in before:
            if model not in {"people.Person", "people.CompanyPersonAccess", "core.AuditLog"}:
                self.assertEqual(after[model], before[model], model)

    def test_required_and_identity_rules_are_enforced_without_javascript(self):
        geography = self.chain()
        route = self.url("person_create")
        before = self.snapshot()
        for field in sorted(REQUIRED_FIELDS):
            with self.subTest(missing=field):
                data = self.payload(geography)
                data[field] = ""
                response = self.client.post(route, data)
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
        response = self.client.post(route, self.payload(geography, identification_type="RUC", identification="123"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("identification", response.context["form"].errors)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_post_preserves_values_and_accessibly_exposes_field_and_general_errors(self):
        geography = self.chain()
        values = self.payload(geography, email="invalid-email", address="First line\nSecond line")
        response = self.client.post(self.url("person_create"), values)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].is_valid())
        self.assert_draft(response, values)
        self.assert_form_accessibility(response, PERSON_FIELDS)
        # An occupied identity supplies a real non-field domain error, rather than
        # fabricating Form.clean behavior just to test a rendering implementation.
        collision = self.client.post(self.url("person_create"), self.payload(geography, identification=self.hidden_person.identification))
        self.assertEqual(collision.status_code, 200)
        self.assertTrue(collision.context["form"].non_field_errors())
        errors = [node for node in self.doc(collision).nodes if node.attrs.get("role") == "alert" and node.visible()]
        self.assertTrue(errors)

    def test_server_rejects_every_inconsistent_geographic_edge_without_partial_creation(self):
        first, second = self.chain("A"), self.chain("B")
        before = self.snapshot()
        for route, obj in (("person_create", None), ("person_update", self.visible_person)):
            for child in ("country", "province", "canton", "parish"):
                with self.subTest(route=route, child=child):
                    values = self.payload(first, identification=obj.identification if obj else "NEW-UI")
                    values[child] = second[child].pk
                    response = self.client.post(self.url(route, obj), values)
                    self.assertEqual(response.status_code, 200)
                    form = response.context["form"]
                    self.assertFalse(form.is_valid())
                    self.assertTrue(form.errors)
                    self.assertEqual(self.control(response, "full_name").attrs["value"], values["full_name"])
                    self.assertNotIn(str(second[child].pk), self.selected_values(response, child))
        self.assertEqual(self.snapshot(), before)

    def test_dependent_selectors_only_offer_children_of_selected_parents(self):
        first, second = self.chain("A"), self.chain("B")
        response = self.page("person_create", data={key: value.pk for key, value in first.items()})
        for child in ("country", "province", "canton", "parish"):
            with self.subTest(child=child):
                options = {node.attrs.get("value") for node in self.control(response, child).children if hasattr(node, "tag") and node.tag == "option"}
                self.assertIn(str(first[child].pk), options)
                self.assertNotIn(str(second[child].pk), options)

    def test_edit_updates_complete_person_only_with_global_authority_and_server_actor(self):
        geography = self.chain()
        self.restrict(self.actor, "view_person", "change_person", "view_continent", "view_country", "view_province", "view_canton", "view_parish")
        original_creator = self.visible_person.created_by_id
        route = self.url("person_update", self.visible_person)
        response = self.page("person_update", self.visible_person)
        with self.policy_spy("can_administer_person", route) as authority:
            result = self.submit(response, self.payload(geography, identification=self.visible_person.identification, identification_type=self.visible_person.identification_type, full_name="Edited person"))
        self.assertIn(result.status_code, (302, 303))
        self.assertTrue(authority.called)
        self.visible_person.refresh_from_db()
        self.assertEqual(self.visible_person.full_name, "Edited person")
        self.assertEqual(self.visible_person.created_by_id, original_creator)
        self.assertEqual(self.visible_person.updated_by_id, self.actor.pk)
        for kind in ("country", "province", "canton", "parish"):
            self.assertEqual(getattr(self.visible_person, kind + "_id"), geography[kind].pk)
        self.assertEqual(self.follow(result).wsgi_request.path, self.url("person_detail", self.visible_person))

    def test_forged_pk_company_and_audit_cannot_retarget_edit_or_change_associations(self):
        geography = self.chain()
        before_access = list(CompanyPersonAccess.objects.order_by("pk").values())
        before_hidden = Person.objects.filter(pk=self.hidden_person.pk).values().get()
        original_creator = self.visible_person.created_by_id
        payload = self.payload(geography, identification=self.visible_person.identification, identification_type=self.visible_person.identification_type,
                               id=self.hidden_person.pk, pk=self.hidden_person.pk, person_id=self.hidden_person.pk,
                               company_id=self.b.pk, created_by=self.admin.pk, updated_by=self.other.pk,
                               created_by_id=self.admin.pk, updated_by_id=self.other.pk,
                               companypersonaccess=self.b.pk)
        result = self.client.post(self.url("person_update", self.visible_person), payload)
        self.assertIn(result.status_code, (200, 302, 303, 400))
        self.assertEqual(Person.objects.filter(pk=self.hidden_person.pk).values().get(), before_hidden)
        self.assertEqual(list(CompanyPersonAccess.objects.order_by("pk").values()), before_access)
        self.visible_person.refresh_from_db()
        self.assertEqual(self.visible_person.created_by_id, original_creator)
        self.assertNotEqual(self.visible_person.updated_by_id, self.other.pk)
        count = Person.objects.count()
        result = self.client.post(self.url("person_create"), {**payload, "identification": "FORGED-CREATE"})
        self.assertIn(result.status_code, (200, 302, 303, 400))
        created = Person.objects.filter(identification="FORGED-CREATE").first()
        if created is not None:
            self.assertEqual((created.created_by_id, created.updated_by_id), (self.actor.pk, self.actor.pk))
            self.assertEqual(set(CompanyPersonAccess.objects.filter(person=created).values_list("company_id", flat=True)), {self.a.pk})
            self.assertEqual(Person.objects.count(), count + 1)
        else:
            self.assertEqual(Person.objects.count(), count)
        self.assertEqual(Person.objects.filter(pk=self.hidden_person.pk).values().get(), before_hidden)

    def test_collision_is_neutral_and_does_not_discover_or_associate_global_person(self):
        geography = self.chain()
        before = self.snapshot()
        result = self.client.post(self.url("person_create"), self.payload(geography, identification=self.hidden_person.identification))
        self.assertEqual(result.status_code, 200)
        self.assert_no_private_person(result, self.hidden_person)
        self.assertNotContains(result, self.b.commercial_name)
        self.assertTrue(result.context["form"].errors)
        self.assertIsNone(result.context["form"].instance.pk)
        for technical in ("IntegrityError", "unique constraint", "Traceback", "CompanyPersonAccess"):
            self.assertNotContains(result, technical)
        self.assertEqual(self.snapshot(), before)

    def test_csrf_protects_person_create_edit_and_related_draft_actions(self):
        geography = self.chain()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.actor)
        self.context(strict, self.a, self.branch)
        before = self.snapshot()
        for name, obj in (("person_create", None), ("person_update", self.visible_person)):
            with self.subTest(route=name):
                route = self.url(name, obj)
                rejected = strict.post(route, self.payload(geography))
                self.assertEqual(rejected.status_code, 403)
                page = self.page(name, obj, client=strict)
                accepted = self.submit(page, self.payload(geography, email="invalid-email"), client=strict)
                self.assertEqual(accepted.status_code, 200)
                self.assertIn("email", accepted.context["form"].errors)
        page = self.page("person_create")
        action = self.related_button(page, "country", "Adicionar")
        payload = self.payload(geography)
        payload[action.attrs["name"]] = action.attrs.get("value", "")
        rejected = strict.post(action.attrs.get("formaction") or self.url("person_create"), payload)
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(self.snapshot(), before)
