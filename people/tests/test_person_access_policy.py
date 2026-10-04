"""D-02B.1a: policy seam for a global Person, never tenant ownership.

Future public seam: people.services.person_access_policy, keyword-only actor,
company and person; visible_people returns a Person QuerySet; availability and
authority predicates return bool. Mutations raise PermissionDenied without
authority. create_person(actor, company, data) creates AND explicitly associates
a new identity atomically; a globally occupied identity raises the same neutral
IdentityUnavailable as an occupied visible identity, without payload or cause.
associate_person/revoke_person_access require global administration AND valid
company membership. Selection uses view_person; creation uses add_person;
global administration uses change_person (Django permissions, including groups).
Superuser is an explicit global administrator, never an ordinary scope bypass.

Proposed GREEN model: people.CompanyPersonAccess, plain models.Model, company
and person FKs with unique pair; no branch, role, ownership or activity metadata.
The name freezes a small explicit association, not a new RBAC architecture.
Revocation removes the association, never Person or its roles. Global activity
filters operational selectors independently of historical association rows.

Future data migration (NOT run here): apps.get_model + get_or_create for each
core.Company.person only; deterministic and idempotent, including inactive
companies/persons. No inference from roles, documents, actor or identification.
Admin follow-up: enforce global administration for master changes and explicit
association authority; restrict list/search/autocomplete and prevent bulk bypass.
No CRUD, URLs, forms, geography, fiscal workflows or physical Person deletion.
"""

from datetime import date
from importlib import import_module
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.test import TestCase, tag

from core.models import Branch, Company, DocumentType
from core.services.context_service import clear_context, set_current_branch
from inventory.models import Warehouse
from people.models import Customer, Employee, Person, Supplier
from sales.models import Sale


RED_TAG = "d02b1a_person_access_policy_red"


@tag(RED_TAG)
class PersonAccessPolicyTests(TestCase):
    def setUp(self):
        for target in ("socket.socket.connect", "socket.socket.connect_ex",
                       "socket.create_connection", "requests.sessions.Session.request",
                       "sri.services.fiscal_document_preparation_service.FiscalDocumentPreparationService.prepare",
                       "sri.services.electronic_document_service.ElectronicDocumentService.create"):
            guard = patch(target, side_effect=AssertionError("No network/fiscal side effects"))
            guard.start()
            self.addCleanup(guard.stop)
        self.addCleanup(clear_context)
        self.actor = get_user_model().objects.create_user("person-operator")
        self.other = get_user_model().objects.create_user("person-outsider")
        self.admin = get_user_model().objects.create_user("person-administrator")
        self.superuser = get_user_model().objects.create_superuser("person-superuser", "", "test-only")
        self.a = Company.objects.create(person=self.make_person("LEGAL-A"), commercial_name="A")
        self.b = Company.objects.create(person=self.make_person("LEGAL-B"), commercial_name="B")
        self.branch = Branch.objects.create(company=self.a, code="001", name="One")
        self.branch_two = Branch.objects.create(company=self.a, code="002", name="Two")
        for user in (self.actor, self.admin, self.superuser):
            user.profile.companies.add(self.a, self.b)
        self.grant(self.actor, "view_person")
        self.grant(self.admin, "view_person", "change_person")
        self.person = self.make_person("PRIVATE", created_by=self.actor, updated_by=self.actor,
                                       email="private@example.invalid", phone="0999999999", address="Private address")

    def make_person(self, identity, **fields):
        return Person.objects.create(identification=identity, person_type="NATURAL",
                                     full_name="Name " + identity, **fields)

    def grant(self, user, *codes):
        group = Group.objects.create(name="permissions-" + user.username + "-" + "-".join(codes))
        group.permissions.add(*Permission.objects.filter(content_type__app_label="people", codename__in=codes))
        user.groups.add(group)
        for cache in ("_perm_cache", "_group_perm_cache", "_user_perm_cache"):
            user.__dict__.pop(cache, None)

    def policy(self):
        try:
            return import_module("people.services.person_access_policy")
        except ModuleNotFoundError as error:
            if error.name not in {"people.services", "people.services.person_access_policy"}:
                raise
            self.fail("RED: productive people.services.person_access_policy is absent")

    def access_model(self):
        model = apps.all_models["people"].get("companypersonaccess")
        self.assertIsNotNone(model, "RED: productive CompanyPersonAccess is absent")
        return model

    def associate(self, company=None, person=None):
        return self.policy().associate_person(actor=self.admin, company=company or self.a,
                                               person=person or self.person)

    def visible(self, company=None, actor=None):
        return set(self.policy().visible_people(actor=actor or self.actor,
                                                 company=company or self.a).values_list("pk", flat=True))

    def available(self, company=None, person=None, actor=None):
        return self.policy().is_available(actor=actor or self.actor, company=company or self.a,
                                          person=person or self.person)

    def payload(self, identity="NEW"):
        return dict(identification=identity, person_type="NATURAL", full_name="New person")

    def test_company_isolation_even_with_known_pk_roles_audit_and_document(self):
        customer = Customer.objects.create(person=self.person)
        Supplier.objects.create(person=self.person)
        Employee.objects.create(person=self.person, hire_date=date(2020, 1, 1))
        warehouse = Warehouse.objects.create(company=self.a, branch=self.branch, code="W", name="W")
        document_type = DocumentType.objects.get(code="SALES_INVOICE")
        Sale.objects.create(company=self.a, branch=self.branch, customer=customer,
                            warehouse=warehouse, document_type=document_type)
        self.associate()
        self.assertIn(self.person.pk, self.visible())
        self.assertTrue(self.available())
        self.assertNotIn(self.person.pk, self.visible(self.b))
        self.assertFalse(self.available(self.b))

    def test_one_global_person_can_be_associated_with_two_companies(self):
        before = Person.objects.count()
        self.associate()
        self.associate(self.b)
        self.assertEqual(Person.objects.count(), before)
        for company in (self.a, self.b):
            with self.subTest(company=company.pk):
                self.assertIn(self.person.pk, self.visible(company))
                self.assertTrue(self.available(company))

    def test_association_pair_is_unique_and_repeated_authorization_idempotent(self):
        self.associate()
        self.associate()
        model = self.access_model()
        self.assertEqual(model.objects.filter(company=self.a, person=self.person).count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            model.objects.create(company=self.a, person=self.person)

    def test_branch_context_does_not_change_company_scope_or_association(self):
        self.associate()
        before = self.access_model().objects.count()
        for branch in (self.branch, self.branch_two):
            with self.subTest(branch=branch.pk):
                set_current_branch(branch)
                self.assertTrue(self.available())
                self.assertIn(self.person.pk, self.visible())
        self.assertEqual(self.access_model().objects.count(), before)

    def test_local_revocation_preserves_global_person_other_company_and_roles(self):
        roles = [model.objects.create(person=self.person) for model in (Customer, Supplier, Employee)]
        self.associate()
        self.associate(self.b)
        with patch.object(Person, "delete", side_effect=AssertionError("No Person deletion")):
            self.policy().revoke_person_access(actor=self.admin, company=self.a, person=self.person)
        self.assertFalse(self.available())
        self.assertNotIn(self.person.pk, self.visible())
        self.assertTrue(self.available(self.b))
        self.person.refresh_from_db()
        self.assertTrue(self.person.is_active)
        for role in roles:
            role.refresh_from_db()
            self.assertEqual(role.person_id, self.person.pk)

    def test_global_inactivity_blocks_all_operational_selection_preserving_associations(self):
        self.associate()
        self.associate(self.b)
        self.person.is_active = False
        self.person.save(update_fields=["is_active"])
        for company in (self.a, self.b):
            with self.subTest(company=company.pk):
                self.assertFalse(self.available(company))
                self.assertNotIn(self.person.pk, self.visible(company))
        self.assertEqual(self.access_model().objects.filter(person=self.person).count(), 2)

    def test_inactive_company_is_not_an_operational_context(self):
        self.associate()
        self.a.is_active = False
        self.a.save(update_fields=["is_active"])
        self.assertFalse(self.available())
        self.assertEqual(self.visible(), set())
        self.assertTrue(self.access_model().objects.filter(company=self.a, person=self.person).exists())

    def test_creator_and_updater_have_no_implicit_visibility_or_global_authority(self):
        self.assertEqual(self.visible(), set())
        self.assertFalse(self.available())
        self.assertFalse(self.policy().can_administer_person(actor=self.actor))
        self.grant(self.actor, "add_person")
        created = self.policy().create_person(actor=self.actor, company=self.a, data=self.payload())
        self.assertTrue(self.available(person=created))
        self.assertFalse(self.policy().can_administer_person(actor=self.actor))
        self.assertFalse(self.available(self.b, person=created))

    def test_collision_is_neutral_without_payload_cause_or_automatic_association(self):
        policy = self.policy()
        self.grant(self.actor, "add_person")
        before = Person.objects.count()
        errors = []
        for visible in (False, True):
            with self.subTest(visible=visible):
                if visible:
                    self.associate(self.b)
                associations = self.access_model().objects.count()
                with self.assertRaises(policy.IdentityUnavailable) as caught:
                    policy.create_person(actor=self.actor, company=self.b, data=self.payload("PRIVATE"))
                error = caught.exception
                self.assertEqual(error.args, ("identity_unavailable",))
                self.assertEqual(vars(error), {})
                self.assertIsNone(error.__cause__)
                self.assertTrue(error.__context__ is None or error.__suppress_context__)
                errors.append(error.args)
                self.assertEqual(self.access_model().objects.count(), associations)
                self.assertEqual(self.access_model().objects.filter(company=self.b, person=self.person).exists(), visible)
        self.assertEqual(errors[0], errors[1])
        self.assertEqual(Person.objects.count(), before)

    def test_client_identifiers_and_membership_do_not_authorize_association(self):
        policy = self.policy()
        for actor in (self.actor, self.other):
            with self.subTest(actor=actor.pk):
                with self.assertRaises(PermissionDenied):
                    policy.associate_person(actor=actor, company=self.a, person=self.person)
        self.assertEqual(self.access_model().objects.count(), 0)
        self.admin.profile.companies.remove(self.b)
        with self.assertRaises(PermissionDenied):
            policy.associate_person(actor=self.admin, company=self.b, person=self.person)
        self.associate()
        with self.assertRaises(PermissionDenied):
            policy.revoke_person_access(actor=self.actor, company=self.a, person=self.person)
        self.assertTrue(self.available())

    def test_selection_creation_and_global_administration_are_separate_permissions(self):
        policy = self.policy()
        self.associate()
        self.assertTrue(self.available())
        self.assertFalse(policy.can_create_person(actor=self.actor, company=self.a))
        self.assertFalse(policy.can_administer_person(actor=self.actor))
        with self.assertRaises(PermissionDenied):
            policy.create_person(actor=self.actor, company=self.a, data=self.payload())
        self.grant(self.other, "add_person")
        self.other.profile.companies.add(self.a)
        self.assertTrue(policy.can_create_person(actor=self.other, company=self.a))
        self.assertFalse(self.available(actor=self.other))
        self.assertEqual(self.visible(actor=self.other), set())
        self.assertFalse(policy.can_administer_person(actor=self.other))
        self.assertTrue(policy.can_administer_person(actor=self.admin))
        self.assertFalse(policy.can_create_person(actor=self.admin, company=self.a))

    def test_anonymous_inactive_and_nonmember_actors_cannot_use_company_scope(self):
        from django.contrib.auth.models import AnonymousUser
        policy = self.policy()
        self.associate()
        self.grant(self.other, "view_person", "add_person", "change_person")
        self.actor.is_active = False
        self.actor.save(update_fields=["is_active"])
        for actor in (AnonymousUser(), self.other, self.actor):
            with self.subTest(actor=str(actor)):
                self.assertEqual(self.visible(actor=actor), set())
                self.assertFalse(self.available(actor=actor))
                self.assertFalse(policy.can_create_person(actor=actor, company=self.a))
                with self.assertRaises(PermissionDenied):
                    policy.create_person(actor=actor, company=self.a, data=self.payload())

    def test_superuser_global_administration_is_explicit_and_not_a_scope_bypass(self):
        policy = self.policy()
        self.assertTrue(policy.can_administer_person(actor=self.superuser))
        self.assertFalse(self.available(actor=self.superuser))
        self.assertEqual(self.visible(actor=self.superuser), set())
        self.associate()
        self.assertTrue(self.available(actor=self.actor))
        self.assertFalse(self.actor.is_superuser)
        self.assertTrue(policy.can_administer_person(actor=self.admin))
        self.assertFalse(self.admin.is_superuser)

    def test_historical_and_company_legal_persons_require_explicit_backfill(self):
        self.assertEqual(Person.objects.get(pk=self.person.pk), self.person)
        self.assertEqual(Person.objects.get(pk=self.a.person_id), self.a.person)
        self.assertEqual(self.visible(), set())
        self.assertFalse(self.available(person=self.a.person))
        self.associate(person=self.a.person)
        self.assertTrue(self.available(person=self.a.person))
        self.assertFalse(self.available(self.b, person=self.a.person))
        self.assertNotIn(self.person.pk, self.visible())

    def test_authorized_creation_associates_only_requested_company_without_fiscal_effects(self):
        policy = self.policy()
        self.grant(self.actor, "add_person")
        fiscal_models = [model for model in apps.get_models() if model._meta.app_label == "sri"]
        from core.models import Sequence
        fiscal_models.append(Sequence)
        before = {model: list(model.objects.order_by("pk").values()) for model in fiscal_models}
        count = Person.objects.count()
        with patch.object(Person, "delete", side_effect=AssertionError("No Person deletion")):
            created = policy.create_person(actor=self.actor, company=self.a, data=self.payload())
            self.assertTrue(self.available(person=created))
            self.assertIn(created.pk, self.visible())
        self.assertEqual(Person.objects.count(), count + 1)
        self.assertEqual(created.identification, "NEW")
        self.assertEqual(set(self.access_model().objects.filter(person=created).values_list("company_id", flat=True)), {self.a.pk})
        self.assertFalse(self.available(self.b, person=created))
        self.assertEqual({model: list(model.objects.order_by("pk").values()) for model in fiscal_models}, before)
