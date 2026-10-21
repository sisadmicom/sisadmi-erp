"""Human navigation and scope: no authentication redesign or global search."""

from urllib.parse import urlsplit

from django.test import Client

from people.models import CompanyPersonAccess
from people.tests.person_ui_support import PersonUIFixture, normalized


class PersonNavigationTests(PersonUIFixture):
    def test_dashboard_exposes_personas_and_retires_founding_identity_link(self):
        for actor in (self.actor, self.admin):
            with self.subTest(actor=actor.username):
                self.client.force_login(actor)
                self.context(self.client, self.a, self.branch)
                response = self.page("dashboard")
                doc = self.doc(response)
                self.assertNotIn("completar identidad legal", normalized(doc.root.text))
                links = doc.matching("a", href=self.url("person_list"))
                self.assertTrue([link for link in links if "personas" in normalized(link.text)])
                self.assertFalse([node for node in doc.nodes if node.attrs.get("aria-disabled") == "true"
                                  and "personas" in normalized(node.text)])
                self.assertNotIn(self.url("founding_person_edit"), response.content.decode())

    def test_list_searches_identification_name_email_only_through_visible_people(self):
        route = self.url("person_list")
        self.assertEqual(route, "/people/")
        different = self.make_person("SECOND-A", email="different@example.invalid")
        CompanyPersonAccess.objects.create(company=self.a, person=different)
        for query in ("VISIBLE-A", "Name VISIBLE", "visible@example.invalid"):
            with self.subTest(query=query), self.policy_spy("visible_people", route) as selector:
                response = self.client.get(route, {"q": query})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(selector.called, "Reuse B.1a policy, do not reimplement scope")
                self.assertContains(response, self.visible_person.full_name)
                self.assertNotContains(response, different.full_name)
                self.assert_no_private_person(response, self.hidden_person)
                self.assert_no_private_person(response, self.inactive_person)
        response = self.page("person_list")
        for value in ("Identificación", "Nombre", "Correo", "Teléfono"):
            self.assertIn(normalized(value), normalized(self.doc(response).root.text))
        self.assertNotRegex(normalized(self.doc(response).root.text), r"\b(?:pk|foreignkey|queryset)\b")
        self.assertContains(response, self.url("person_detail", self.visible_person))

    def test_empty_and_no_result_states_explain_next_action_without_disclosure(self):
        response = self.page("person_list", data={"q": "NO-MATCH"})
        self.assertRegex(normalized(self.doc(response).root.text), r"(?:sin resultados|no.*(?:coincid|encontr))")
        self.assertNotContains(response, self.visible_person.full_name)
        self.assertTrue([link for link in self.doc(response).matching("a") if "limpiar" in normalized(link.text)])
        for query in (self.hidden_person.identification, self.hidden_person.full_name, self.hidden_person.email,
                      self.inactive_person.identification):
            with self.subTest(query=query):
                result = self.page("person_list", data={"q": query})
                self.assert_no_private_person(result, self.hidden_person)
                self.assert_no_private_person(result, self.inactive_person)
                self.assertNotContains(result, self.url("person_detail", self.hidden_person))
        CompanyPersonAccess.objects.filter(company=self.a, person=self.visible_person).delete()
        empty = self.page("person_list")
        self.assertRegex(normalized(self.doc(empty).root.text), r"no.*personas.*(?:disponib|registrad)")
        self.assertContains(empty, self.url("person_create"))

    def test_known_pk_never_reveals_hidden_or_inactive_person_in_detail_or_edit(self):
        for actor in (self.actor, self.admin):
            self.client.force_login(actor)
            self.context(self.client, self.a, self.branch)
            for person in (self.hidden_person, self.inactive_person):
                for name in ("person_detail", "person_update"):
                    for method in ("get", "post"):
                        with self.subTest(actor=actor.username, person=person.identification, route=name, method=method):
                            response = getattr(self.client, method)(self.url(name, person), self.payload())
                            self.assertIn(response.status_code, (403, 404))
                            self.assert_no_private_person(response, person)
                            self.assertNotContains(response, "Traceback", status_code=response.status_code)

    def test_actions_and_views_separate_view_add_and_global_change_permissions(self):
        self.restrict(self.actor, "view_person")
        response = self.page("person_list")
        self.assertNotContains(response, self.url("person_create"))
        detail = self.page("person_detail", self.visible_person)
        self.assertNotContains(detail, self.url("person_update", self.visible_person))
        for name, obj in (("person_create", None), ("person_update", self.visible_person)):
            for method in ("get", "post"):
                with self.subTest(route=name, method=method):
                    denied = getattr(self.client, method)(self.url(name, obj), self.payload())
                    self.assertEqual(denied.status_code, 403)
        self.restrict(self.actor, "add_person", "change_person")
        denied = self.client.get(self.url("person_list"))
        self.assertEqual(denied.status_code, 403)

    def test_anonymous_requests_are_redirected_to_existing_login(self):
        anonymous = Client()
        for name, obj in (("person_list", None), ("person_create", None),
                          ("person_detail", self.visible_person), ("person_update", self.visible_person)):
            with self.subTest(route=name):
                response = anonymous.get(self.url(name, obj))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(urlsplit(response["Location"]).path, self.url("login"))
                self.assert_no_private_person(response, self.visible_person)

    def test_company_activity_membership_and_branch_independence_are_revalidated(self):
        for branch in (self.branch, self.branch_two):
            with self.subTest(branch=branch.name):
                self.context(self.client, self.a, branch)
                response = self.page("person_list")
                self.assertContains(response, self.visible_person.full_name)
        self.a.is_active = False
        self.a.save(update_fields=["is_active"])
        response = self.client.get(self.url("person_list"))
        self.assertIn(response.status_code, (302, 403))
        self.assert_no_private_person(response, self.visible_person)
        self.a.is_active = True
        self.a.save(update_fields=["is_active"])
        self.actor.profile.companies.remove(self.a)
        self.context(self.client, self.a, self.branch)
        response = self.client.get(self.url("person_detail", self.visible_person))
        self.assertIn(response.status_code, (302, 403, 404))
        self.assert_no_private_person(response, self.visible_person)

    def test_person_get_head_search_and_forms_do_not_mutate_business_records(self):
        before = self.snapshot()
        for name, obj in (("person_list", None), ("person_create", None),
                          ("person_detail", self.visible_person), ("person_update", self.visible_person)):
            for method in ("get", "head"):
                with self.subTest(route=name, method=method):
                    response = getattr(self.client, method)(self.url(name, obj), {"q": "VISIBLE"})
                    self.assertEqual(response.status_code, 200)
        self.assertEqual(self.snapshot(), before)

    def test_detail_groups_human_data_and_offers_contextual_back_and_authorized_edit(self):
        geography = self.chain()
        for kind in ("country", "province", "canton", "parish"):
            setattr(self.visible_person, kind, geography[kind])
        self.visible_person.address = "Human street"
        self.visible_person.save()
        response = self.page("person_detail", self.visible_person)
        text = normalized(self.doc(response).root.text)
        for group in ("Identidad", "Contacto", "Ubicación"):
            self.assertIn(normalized(group), text)
        for value in (self.visible_person.full_name, self.visible_person.email, self.visible_person.phone,
                      self.visible_person.address, *[obj.name for obj in geography.values()]):
            self.assertContains(response, value)
        self.assertContains(response, self.url("person_list"))
        self.assertContains(response, self.url("person_update", self.visible_person))
        for technical in ("CompanyPersonAccess", "ForeignKey", "QuerySet", "created_by", "updated_by", "Traceback"):
            self.assertNotContains(response, technical)
