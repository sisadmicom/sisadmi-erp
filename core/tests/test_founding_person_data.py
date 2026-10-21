"""D-01.1 2.1: complete founding identity without replacing its origin."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, tag
from django.urls import NoReverseMatch, reverse

from core.models import Branch, Company
from people.models import Person
from people.models.geography import Country, Province, Canton, Parish


@tag("d011_founding_person_data")
class FoundingPersonDataTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("founder", "", "test-password")
        self.client.force_login(self.user)
        for target in ("socket.socket.connect", "requests.sessions.Session.request"):
            guard = patch(target, side_effect=AssertionError("No external network"))
            mock = guard.start()
            self.addCleanup(guard.stop)
            self.addCleanup(mock.assert_not_called)

    def payload(self, **changes):
        values = dict(identification_type="RUC", identification="1300000001001", full_name="Fundadora",
                      email="founder@example.invalid", phone="0991234567", company_address="Dirección empresa",
                      commercial_name="Empresa", branch_code="001", branch_name="Matriz", branch_address="Sucursal")
        values.update(changes)
        return values

    def bootstrap(self):
        return reverse("initial_setup")

    def edit(self):
        try:
            return reverse("founding_person_edit")
        except NoReverseMatch:
            self.fail("Missing scoped founding_person_edit boundary")

    def founded(self):
        self.assertEqual(self.client.post(self.bootstrap(), self.payload()).status_code, 302)
        return Company.objects.select_related("person").get()

    def edit_payload(self, **changes):
        values = {key: value for key, value in self.payload().items()
                  if key in ("identification_type", "identification", "full_name", "email", "phone")}
        values["address"] = "Dirección corregida"
        values.update(changes)
        return values

    def test_bootstrap_exposes_explicit_identity_and_contacts(self):
        response = self.client.get(self.bootstrap())
        for name in ("identification_type", "identification", "full_name", "email", "phone", "company_address"):
            with self.subTest(field=name):
                self.assertContains(response, f'name="{name}"')

    def test_bootstrap_persists_complete_legal_identity_and_relationships(self):
        company = self.founded()
        person = company.person
        self.assertEqual((person.email, person.phone, person.address),
                         ("founder@example.invalid", "0991234567", "Dirección empresa"))
        self.assertEqual(person.person_type, "LEGAL")
        self.assertEqual(person.identification_type, "RUC")
        self.assertEqual(Person.objects.count(), 1)
        self.assertEqual(Branch.objects.get().company_id, company.pk)
        for obj in (person, company, Branch.objects.get()):
            self.assertEqual(obj.created_by, self.user)
            self.assertEqual(obj.updated_by, self.user)

    def test_identity_is_explicit_and_model_validation_rejects_bad_data(self):
        for changes in (dict(identification_type=""), dict(identification="123"), dict(email="not-an-email")):
            with self.subTest(changes=changes):
                response = self.client.post(self.bootstrap(), self.payload(**changes))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertEqual(Person.objects.count(), 0)
                self.assertEqual(Company.objects.count(), 0)

    def test_bootstrap_contact_creation_stays_atomic(self):
        with patch("core.models.Branch.objects.create", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.bootstrap(), self.payload())
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(Company.objects.count(), 0)
        self.assertEqual(self.user.profile.companies.count(), 0)

    def test_geography_is_not_invented_on_creation_or_edit(self):
        company = self.founded()
        self.client.post(self.edit(), self.edit_payload())
        company.person.refresh_from_db()
        for field in ("country_id", "province_id", "canton_id", "parish_id"):
            self.assertIsNone(getattr(company.person, field))
        for model in (Country, Province, Canton, Parish):
            self.assertEqual(model.objects.count(), 0)

    def test_edit_get_head_are_read_only_and_existing_bootstrap_stays_closed(self):
        company = self.founded()
        before = (company.person.email, company.person.updated_at)
        for method in ("get", "head"):
            self.assertEqual(getattr(self.client, method)(self.edit()).status_code, 200)
        company.person.refresh_from_db()
        self.assertEqual((company.person.email, company.person.updated_at), before)
        self.assertEqual(self.client.get(self.bootstrap()).status_code, 302)

    def test_edit_updates_exact_linked_person_without_duplicates_or_new_memberships(self):
        company = self.founded()
        person_id = company.person_id
        original_actor = company.person.created_by_id
        response = self.client.post(self.edit(), self.edit_payload(email="updated@example.invalid", phone="022345678"))
        self.assertEqual(response.status_code, 302)
        company.refresh_from_db()
        self.assertEqual(company.person_id, person_id)
        person = Person.objects.get(pk=person_id)
        self.assertEqual((person.email, person.phone, person.address),
                         ("updated@example.invalid", "022345678", "Dirección corregida"))
        self.assertEqual(person.created_by_id, original_actor)
        self.assertEqual(person.updated_by, self.user)
        self.assertEqual((Person.objects.count(), Company.objects.count(), Branch.objects.count()), (1, 1, 1))
        self.assertEqual(self.user.profile.companies.count(), 1)
        self.assertEqual(self.user.profile.branches.count(), 1)

    def test_forged_identity_company_and_actors_never_choose_edit_target(self):
        company = self.founded()
        foreign_person = Person.objects.create(identification="FOREIGN", person_type="LEGAL", full_name="Foreign")
        foreign = Company.objects.create(person=foreign_person, commercial_name="Foreign")
        payload = self.edit_payload(person_id=foreign_person.pk, company_id=foreign.pk,
                                    created_by=999999, updated_by=999999, person_type="NATURAL")
        self.assertEqual(self.client.post(self.edit(), payload).status_code, 302)
        company.person.refresh_from_db()
        foreign_person.refresh_from_db()
        self.assertEqual(company.person.person_type, "LEGAL")
        self.assertEqual(company.person.updated_by, self.user)
        self.assertEqual(foreign_person.full_name, "Foreign")

    def test_invalid_edit_preserves_all_existing_values(self):
        company = self.founded()
        response = self.client.post(self.edit(), self.edit_payload(identification="123", email="invalid"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        company.person.refresh_from_db()
        self.assertEqual(company.person.identification, "1300000001001")
        self.assertEqual(company.person.email, "founder@example.invalid")

    def test_edit_requires_authenticated_superuser_and_valid_active_membership(self):
        company = self.founded()
        anonymous = Client()
        self.assertEqual(anonymous.get(self.edit()).status_code, 302)
        for superuser, membership in ((False, True), (True, False)):
            with self.subTest(superuser=superuser, membership=membership):
                actor = get_user_model().objects.create_user(f"actor-{superuser}", is_staff=True, is_superuser=superuser)
                if membership:
                    actor.profile.companies.add(company)
                    actor.profile.branches.add(Branch.objects.get())
                client = Client()
                client.force_login(actor)
                session = client.session
                session.update({"company_id": company.pk, "branch_id": Branch.objects.get().pk})
                session.save()
                response = client.post(self.edit(), self.edit_payload(email="forbidden@example.invalid"))
                self.assertIn(response.status_code, (302, 403))
        company.person.refresh_from_db()
        self.assertEqual(company.person.email, "founder@example.invalid")

    def test_csrf_protects_both_post_boundaries(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        self.assertEqual(strict.post(self.bootstrap(), self.payload()).status_code, 403)
        self.founded()
        session = strict.session
        session.update({"company_id": Company.objects.get().pk, "branch_id": Branch.objects.get().pk})
        session.save()
        self.assertEqual(strict.post(self.edit(), self.edit_payload()).status_code, 403)
