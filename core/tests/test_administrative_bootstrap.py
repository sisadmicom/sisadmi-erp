from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, TransactionTestCase
from django.urls import NoReverseMatch, reverse

from core.models import Branch, Company
from people.models import Person
from users.models import UserProfile


User = get_user_model()

RED_TAG = "d011_administrative_bootstrap_red"


class AdministrativeBootstrapMixin:
    """
    D-01.1 contract fixtures.

    Production is intentionally expected to be RED when this module is frozen.
    """

    def create_user(
        self,
        *,
        username="bootstrap-admin",
        password="StrongBootstrapPass123!",
        is_superuser=True,
        is_staff=True,
    ):
        return User.objects.create_user(
            username=username,
            password=password,
            is_superuser=is_superuser,
            is_staff=is_staff,
            is_active=True,
        )

    def login(self, user, password="StrongBootstrapPass123!"):
        client = Client()
        self.assertTrue(
            client.login(username=user.username, password=password)
        )
        return client

    def bootstrap_url(self):
        try:
            return reverse("initial_setup")
        except NoReverseMatch:
            self.fail(
                "D-01.1 RED: route 'initial_setup' is not registered."
            )

    def valid_payload(self):
        return {
            "identification_type": "RUC",
            "identification": "1300000001001",
            "full_name": "Empresa Bootstrap S.A.",
            "commercial_name": "Empresa Bootstrap",
            "company_address": "Dirección empresa",
            "branch_code": "001",
            "branch_name": "Matriz",
            "branch_address": "Dirección matriz",
        }

    def assert_empty_business_bootstrap(self):
        self.assertEqual(Person.objects.count(), 0)
        self.assertEqual(Company.objects.count(), 0)
        self.assertEqual(Branch.objects.count(), 0)


@__import__("django").test.tag(RED_TAG)
class AdministrativeBootstrapAccessTests(
    AdministrativeBootstrapMixin,
    TestCase,
):
    def test_new_user_gets_profile_from_existing_lifecycle(self):
        user = self.create_user()

        self.assertTrue(
            UserProfile.objects.filter(user=user).exists(),
            "A newly created User must receive its UserProfile through "
            "the existing users lifecycle.",
        )

    def test_anonymous_user_cannot_open_initial_setup(self):
        response = self.client.get(self.bootstrap_url())

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assert_empty_business_bootstrap()

    def test_authenticated_non_superuser_cannot_bootstrap(self):
        user = self.create_user(
            username="normal-user",
            is_superuser=False,
            is_staff=False,
        )
        client = self.login(user)

        response = client.get(self.bootstrap_url())

        self.assertIn(response.status_code, (302, 403, 404))
        self.assert_empty_business_bootstrap()

    def test_staff_without_superuser_cannot_bootstrap(self):
        user = self.create_user(
            username="staff-user",
            is_superuser=False,
            is_staff=True,
        )
        client = self.login(user)

        response = client.get(self.bootstrap_url())

        self.assertIn(response.status_code, (302, 403, 404))
        self.assert_empty_business_bootstrap()

    def test_superuser_can_open_bootstrap_only_when_installation_is_empty(self):
        user = self.create_user()
        client = self.login(user)

        response = client.get(self.bootstrap_url())

        self.assertEqual(response.status_code, 200)
        self.assert_empty_business_bootstrap()

    def test_get_and_head_do_not_create_business_records(self):
        user = self.create_user()
        client = self.login(user)

        for method in ("get", "head"):
            with self.subTest(method=method):
                response = getattr(client, method)(self.bootstrap_url())
                self.assertEqual(response.status_code, 200)
                self.assert_empty_business_bootstrap()

    def test_existing_company_closes_initial_bootstrap(self):
        admin = self.create_user()
        profile = admin.profile

        person = Person.objects.create(
            identification="1790000000001",
            person_type="LEGAL",
            full_name="Empresa ya existente",
        )
        company = Company.objects.create(
            person=person,
            commercial_name="Existente",
        )

        client = self.login(admin)
        response = client.get(self.bootstrap_url())

        self.assertNotEqual(response.status_code, 200)
        self.assertEqual(Company.objects.count(), 1)
        self.assertFalse(profile.companies.filter(pk=company.pk).exists())


@__import__("django").test.tag(RED_TAG)
class AdministrativeBootstrapFormTests(
    AdministrativeBootstrapMixin,
    TestCase,
):
    def setUp(self):
        self.user = self.create_user()
        self.client = self.login(self.user)

    def test_get_renders_human_entry_form_without_mutation(self):
        response = self.client.get(self.bootstrap_url())

        self.assertEqual(response.status_code, 200)

        for field_name in (
            "identification_type",
            "identification",
            "full_name",
            "commercial_name",
            "company_address",
            "branch_code",
            "branch_name",
            "branch_address",
        ):
            with self.subTest(field=field_name):
                self.assertContains(response, f'name="{field_name}"')

        self.assertContains(response, "csrfmiddlewaretoken")
        self.assert_empty_business_bootstrap()

    def test_invalid_post_does_not_create_partial_records(self):
        response = self.client.post(
            self.bootstrap_url(),
            {
                "identification_type": "RUC",
                "identification": "",
                "full_name": "",
                "commercial_name": "",
                "company_address": "",
                "branch_code": "",
                "branch_name": "",
                "branch_address": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assert_empty_business_bootstrap()
        self.assertEqual(self.user.profile.companies.count(), 0)
        self.assertEqual(self.user.profile.branches.count(), 0)

    def test_csrf_is_required_for_bootstrap_post(self):
        csrf_client = Client(enforce_csrf_checks=True)
        self.assertTrue(
            csrf_client.login(
                username=self.user.username,
                password="StrongBootstrapPass123!",
            )
        )

        response = csrf_client.post(
            self.bootstrap_url(),
            self.valid_payload(),
        )

        self.assertEqual(response.status_code, 403)
        self.assert_empty_business_bootstrap()

    def test_bootstrap_does_not_accept_existing_company_or_branch_authority(self):
        payload = self.valid_payload()
        payload.update(
            {
                "company_id": "999999",
                "branch_id": "999999",
                "created_by": "999999",
                "updated_by": "999999",
                "is_superuser": "1",
            }
        )

        response = self.client.post(self.bootstrap_url(), payload)

        self.assertEqual(response.status_code, 302)

        company = Company.objects.get()
        branch = Branch.objects.get()

        self.assertNotEqual(str(company.pk), payload["company_id"])
        self.assertNotEqual(str(branch.pk), payload["branch_id"])
        self.assertEqual(company.created_by, self.user)
        self.assertEqual(branch.created_by, self.user)


@__import__("django").test.tag(RED_TAG)
class AdministrativeBootstrapPersistenceTests(
    AdministrativeBootstrapMixin,
    TestCase,
):
    def setUp(self):
        self.user = self.create_user()
        self.profile_pk = self.user.profile.pk
        self.client = self.login(self.user)

    def test_valid_post_creates_person_company_branch_and_memberships(self):
        response = self.client.post(
            self.bootstrap_url(),
            self.valid_payload(),
        )

        self.assertEqual(response.status_code, 302)

        self.assertEqual(Person.objects.count(), 1)
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(Branch.objects.count(), 1)

        person = Person.objects.get()
        company = Company.objects.get()
        branch = Branch.objects.get()

        self.assertEqual(company.person, person)
        self.assertEqual(branch.company, company)

        profile = UserProfile.objects.get(pk=self.profile_pk)
        self.assertEqual(UserProfile.objects.filter(user=self.user).count(), 1)
        self.assertTrue(profile.companies.filter(pk=company.pk).exists())
        self.assertTrue(profile.branches.filter(pk=branch.pk).exists())

    def test_valid_post_preserves_human_entered_values(self):
        payload = self.valid_payload()

        self.client.post(self.bootstrap_url(), payload)

        person = Person.objects.get()
        company = Company.objects.get()
        branch = Branch.objects.get()

        self.assertEqual(person.identification_type, "RUC")
        self.assertEqual(person.identification, payload["identification"])
        self.assertEqual(person.full_name, payload["full_name"])
        self.assertEqual(company.commercial_name, payload["commercial_name"])
        self.assertEqual(branch.code, payload["branch_code"])
        self.assertEqual(branch.name, payload["branch_name"])
        self.assertEqual(branch.address, payload["branch_address"])

    def test_created_and_updated_by_are_authenticated_operator(self):
        self.client.post(self.bootstrap_url(), self.valid_payload())

        person = Person.objects.get()
        company = Company.objects.get()
        branch = Branch.objects.get()

        for obj in (person, company, branch):
            with self.subTest(model=obj._meta.label):
                self.assertEqual(obj.created_by, self.user)
                self.assertEqual(obj.updated_by, self.user)

    def test_success_sets_active_context_and_redirects_to_dashboard(self):
        response = self.client.post(
            self.bootstrap_url(),
            self.valid_payload(),
        )

        company = Company.objects.get()
        branch = Branch.objects.get()

        self.assertRedirects(
            response,
            reverse("dashboard"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.session.get("company_id"),
            company.pk,
        )
        self.assertEqual(
            self.client.session.get("branch_id"),
            branch.pk,
        )

        dashboard = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard.status_code, 200)

    def test_successful_bootstrap_cannot_be_repeated(self):
        first = self.client.post(
            self.bootstrap_url(),
            self.valid_payload(),
        )
        self.assertEqual(first.status_code, 302)

        original_person_count = Person.objects.count()
        original_company_count = Company.objects.count()
        original_branch_count = Branch.objects.count()

        second = self.client.post(
            self.bootstrap_url(),
            self.valid_payload(),
        )

        self.assertNotEqual(second.status_code, 200)
        self.assertEqual(Person.objects.count(), original_person_count)
        self.assertEqual(Company.objects.count(), original_company_count)
        self.assertEqual(Branch.objects.count(), original_branch_count)

    def test_existing_company_is_never_auto_assigned_to_unrelated_user(self):
        owner = self.create_user(username="owner")
        owner_client = self.login(owner)
        owner_client.post(self.bootstrap_url(), self.valid_payload())

        company = Company.objects.get()
        branch = Branch.objects.get()

        outsider = self.create_user(
            username="outsider",
            is_superuser=False,
            is_staff=False,
        )
        outsider_client = self.login(outsider)

        response = outsider_client.get(reverse("select_company"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            outsider.profile.companies.filter(pk=company.pk).exists()
        )
        self.assertFalse(
            outsider.profile.branches.filter(pk=branch.pk).exists()
        )


@__import__("django").test.tag(RED_TAG)
class AdministrativeBootstrapAtomicityTests(
    AdministrativeBootstrapMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self):
        self.user = self.create_user()
        self.client = self.login(self.user)

    def test_failure_during_branch_creation_rolls_back_entire_bootstrap(self):
        with patch(
            "core.models.Branch.objects.create",
            side_effect=RuntimeError("sentinel bootstrap failure"),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    self.bootstrap_url(),
                    self.valid_payload(),
                )

        self.assert_empty_business_bootstrap()

        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.companies.count(), 0)
        self.assertEqual(profile.branches.count(), 0)

    def test_business_creation_occurs_inside_one_atomic_boundary(self):
        observed = {}

        original_create = Branch.objects.create

        def observed_create(*args, **kwargs):
            from django.db import connection

            observed["in_atomic_block"] = connection.in_atomic_block
            return original_create(*args, **kwargs)

        with patch(
            "core.models.Branch.objects.create",
            side_effect=observed_create,
        ):
            response = self.client.post(
                self.bootstrap_url(),
                self.valid_payload(),
            )

        self.assertEqual(response.status_code, 302)
        self.assertIs(
            observed.get("in_atomic_block"),
            True,
            "Person, Company, Branch and memberships must form one "
            "administrative bootstrap transaction.",
        )
