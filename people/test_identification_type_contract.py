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

    def test_semantic_enum_excludes_final_consumer(self):
        try:
            module = import_module("people.constants.identification_type")
        except ModuleNotFoundError as error:
            self.fail(f"Missing domain identification enum: {error.name}")
        enum = getattr(module, "IdentificationType", None)
        self.assertIsNotNone(enum, "IdentificationType enum is required")
        self.assertEqual(set(enum.values), {"RUC", "CEDULA", "PASSPORT", "FOREIGN_ID"})
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
                self.assertEqual(person.identification_type, kind)
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
        for kind in ("UNKNOWN", "FINAL_CONSUMER"):
            with self.subTest(kind=kind):
                with self.assertRaises(ValidationError) as caught:
                    self.person("9999999999999", identification_type=kind).full_clean(exclude=("country", "province", "canton", "parish"))
                self.assertIn("identification_type", caught.exception.message_dict)

    def test_legacy_identity_is_not_classified_from_person_type_or_content(self):
        self.field()
        for i, (identity, person_type) in enumerate((("1790000001001", "LEGAL"),
                ("1713328506", "NATURAL"), ("LEGACY-CUSTOMER", "LEGAL"))):
            with self.subTest(identity=identity):
                person = Person(
                    identification=identity, person_type=person_type, full_name=f"Legacy {i}")
                person.full_clean(exclude=("country", "province", "canton", "parish"))
                person.save()
                person.refresh_from_db()
                self.assertIsNone(person.identification_type)
                self.assertEqual(person.identification, identity)

    def test_global_identification_uniqueness_remains_independent_of_type(self):
        self.field()
        person = self.person("AB1234567", identification_type="PASSPORT")
        person.full_clean(exclude=("country", "province", "canton", "parish"))
        person.save()
        duplicate = self.person("AB1234567", identification_type="FOREIGN_ID")
        with self.assertRaises(ValidationError) as caught:
            duplicate.full_clean(exclude=("country", "province", "canton", "parish"))
        self.assertIn("identification", caught.exception.message_dict)
