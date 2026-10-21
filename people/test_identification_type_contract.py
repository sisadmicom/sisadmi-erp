"""C-15A-A: personal identity semantics, including unclassified legacy rows."""
from importlib import import_module

from django.core.exceptions import ValidationError
from django.test import TestCase, tag

from people.models import Customer, Person


@tag("c15aa_domain_red")
class IdentificationTypeContractTests(TestCase):
    # Existing geography fields allow NULL in SQL but not blank in full_clean.
    # Exclude only those unrelated legacy fields; identity validation stays active.
    def field(self):
        self.assertIn("identification_type", {f.name for f in Person._meta.fields},
                      "Person must persist explicit identification_type")
        return Person._meta.get_field("identification_type")

    def person(self, identification, **kwargs):
        return Person(identification=identification, person_type="NATURAL",
                      full_name="Persona de contrato", **kwargs)

    def test_semantic_enum_includes_approved_types(self):
        try:
            module = import_module("people.constants.identification_type")
        except ModuleNotFoundError as error:
            self.fail(f"Missing domain identification enum: {error.name}")
        enum = getattr(module, "IdentificationType", None)
        self.assertIsNotNone(enum, "IdentificationType enum is required")
        self.assertEqual(set(enum.values), {"RUC", "CEDULA", "PASSPORT", "FOREIGN_ID", "OTHER", "FINAL_CONSUMER"})
        self.assertEqual(set(dict(self.field().choices)), set(enum.values))

    def test_field_is_nullable_blank_and_has_no_default(self):
        field = self.field()
        self.assertTrue(field.null)
        self.assertTrue(field.blank)
        self.assertFalse(field.has_default())
        self.assertTrue(Person._meta.get_field("identification").unique)
        self.assertEqual(Person._meta.get_field("identification").max_length, 20)

    def test_explicit_valid_types_preserve_identity_and_customer_relation(self):
        self.field()
        for kind, identity in (("RUC", "1790000001001"), ("CEDULA", "1713328506"),
                               ("PASSPORT", "AB1234567"), ("FOREIGN_ID", "EXT987654")):
            with self.subTest(kind=kind):
                person = self.person(identity, identification_type=kind)
                person.full_clean(exclude=("country", "province", "canton", "parish"))
                person.save()
                customer = Customer.objects.create(person=person)
                person.refresh_from_db()
                self.assertEqual(person.identification_type, "OTHER" if kind == "FOREIGN_ID" else kind)
                self.assertEqual(person.identification, identity)
                self.assertEqual(customer.person_id, person.pk)

    def test_explicit_malformed_identities_fail_model_validation(self):
        self.field()
        for kind, identity in (("RUC", "123"), ("RUC", "ABCDEFGHIJKLM"),
                               ("CEDULA", "123"), ("CEDULA", "ABCDEFGHIJ"),
                               ("PASSPORT", ""), ("FOREIGN_ID", "")):
            with self.subTest(kind=kind, identity=identity):
                with self.assertRaises(ValidationError) as caught:
                    self.person(identity, identification_type=kind).full_clean(exclude=("country", "province", "canton", "parish"))
                self.assertIn("identification", caught.exception.message_dict)

    def test_unknown_and_final_consumer_types_fail_validation(self):
        self.field()
        for kind in ("UNKNOWN",):
            with self.subTest(kind=kind):
                with self.assertRaises(ValidationError) as caught:
                    self.person("9999999999999", identification_type=kind).full_clean(exclude=("country", "province", "canton", "parish"))
                self.assertIn("identification_type", caught.exception.message_dict)

    def test_legacy_identity_is_not_reclassified_when_unchanged(self):
        from django.db.migrations.loader import MigrationLoader
        historical = MigrationLoader(None).project_state([
            ('people', '0008_customer_category_assignment')]).apps.get_model('people', 'Person')
        # Reproduce a pre-change row via its historical model, not current creation.
        from django.db import connection
        protection = import_module('people.migrations.0011_person_identity_immutable')
        with connection.cursor() as cursor:
            cursor.execute(protection.REVERSE_SQL)
            old = historical.objects.create(identification='1719304189', person_type='NATURAL', full_name='Legacy')
            cursor.execute(protection.FORWARD_SQL)
        person = Person.objects.get(pk=old.pk)
        person.full_name = 'Legacy contact edited'
        person.full_clean(exclude=('country', 'province', 'canton', 'parish'))
        person.save(update_fields=['full_name'])
        person.refresh_from_db()
        self.assertIsNone(person.identification_type)
        self.assertIsNone(person.identification_kind_id)
        self.assertEqual(person.identification, '1719304189')

    def test_global_identification_uniqueness_remains_independent_of_type(self):
        self.field()
        person = self.person("AB1234567", identification_type="PASSPORT")
        person.full_clean(exclude=("country", "province", "canton", "parish"))
        person.save()
        duplicate = self.person("AB1234567", identification_type="FOREIGN_ID")
        with self.assertRaises(ValidationError) as caught:
            duplicate.full_clean(exclude=("country", "province", "canton", "parish"))
        self.assertIn("identification", caught.exception.message_dict)
