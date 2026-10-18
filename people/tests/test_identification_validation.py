"""No database, Django startup or network required."""
import unittest
from django.core.exceptions import ValidationError
from people.identification import (
    detect_identification as detect, validate_cedula, validate_ruc,
)


class IdentificationValidationTests(unittest.TestCase):
    def invalid(self, value, manual=None):
        with self.assertRaises(ValidationError) as caught:
            detect(value, manual)
        self.assertIn('identification', caught.exception.error_dict)

    def test_cedula(self): self.assertEqual(detect('1719304188'), 'CEDULA')
    def test_cedula_checksum(self): self.invalid('1719304189')
    def test_cedula_province(self): self.invalid('0019304188')
    def test_cedula_third_digit(self): self.invalid('1799304188')
    def test_ruc_natural(self): self.assertEqual(detect('1719304188001'), 'RUC')
    def test_ruc_natural_checksum(self): self.invalid('1719304189001')
    def test_ruc_suffix(self): self.invalid('1719304188002')
    def test_ruc_private_no_universal_checksum(self): self.assertEqual(detect('1791234567001'), 'RUC')
    def test_ruc_public_no_universal_checksum(self): self.assertEqual(detect('1761234567001'), 'RUC')
    def test_ruc_wrong_class(self): self.invalid('1781234567001')
    def test_reserved(self): self.assertEqual(detect('9999999999999'), 'FINAL_CONSUMER')
    def test_reserved_not_ruc(self): self.assertEqual(detect('9999999999999', 'RUC'), 'FINAL_CONSUMER')
    def test_passport(self): self.assertEqual(detect('AB-1234', 'PASSPORT'), 'PASSPORT')
    def test_other(self): self.assertEqual(detect('AB-1234'), 'OTHER')
    def test_passport_cannot_bypass_cedula(self): self.invalid('1719304189', 'PASSPORT')
    def test_other_cannot_bypass_ruc(self): self.invalid('1719304189001', 'OTHER')
    def test_valid_numeric_passport_is_detected(self): self.assertEqual(detect('1719304188', 'PASSPORT'), 'CEDULA')
    def test_empty(self): self.invalid('')
    def test_controls(self): self.invalid('AB\x00C')
    def test_no_silent_trim(self): self.invalid(' AB123')
    def test_punctuation_only(self): self.invalid('----')
    def test_unicode_numeric_bypass(self): self.invalid('１７１９３０４１８８')
    def test_length(self): self.invalid('A' * 21)
    def test_false_final_consumer_type_is_not_reserved(self): self.assertEqual(detect('AB123', 'FINAL_CONSUMER'), 'OTHER')


    def assert_validation_error(self, function, *args, field, code):
        with self.assertRaises(ValidationError) as caught:
            function(*args)
        self.assertEqual(set(caught.exception.error_dict), {field})
        self.assertEqual([error.code for error in caught.exception.error_dict[field]], [code])

    def test_detector_rejects_non_text_python_types(self):
        # detect() checks isinstance(str) before length, regex or Unicode access.
        for value in (None, 1719304188, True, 1.5, b"AB123", bytearray(b"AB123"),
                      ["AB123"], {"identification": "AB123"}, object()):
            with self.subTest(python_type=type(value).__name__):
                self.assert_validation_error(detect, value,
                                             field="identification", code="invalid_identification")

    def test_unknown_manual_types_report_the_type_field(self):
        # Manual values outside the explicit tuple fail before classification.
        for manual in ("UNKNOWN", "cedula", "PASSPORT ", 1, b"PASSPORT", [], {}):
            with self.subTest(manual=manual):
                self.assert_validation_error(detect, "AB123", manual,
                                             field="identification_type", code="invalid_type")

    def test_detector_error_keys_and_codes_follow_the_failing_branch(self):
        # Natural RUC delegates its checksum to validate_cedula, preserving that code.
        for value, manual, code in (
            ("", None, "invalid_identification"),
            ("AB123", "CEDULA", "invalid_identification"),
            ("AB123", "RUC", "invalid_identification"),
            ("1719304189", None, "invalid_cedula"),
            ("1719304189001", None, "invalid_cedula"),
            ("1781234567001", None, "invalid_ruc"),
            ("1719304188002", None, "invalid_ruc"),
        ):
            with self.subTest(value=value, manual=manual):
                self.assert_validation_error(detect, value, manual,
                                             field="identification", code=code)

    def test_exact_length_boundaries(self):
        # Existing generic formats accept 1..20 characters; no extra passport minimum.
        for length in (1, 20):
            for manual, expected in ((None, "OTHER"), ("PASSPORT", "PASSPORT")):
                with self.subTest(length=length, manual=manual):
                    self.assertEqual(detect("A" * length, manual), expected)
        for length in (0, 21):
            with self.subTest(length=length):
                self.assert_validation_error(detect, "A" * length,
                                             field="identification", code="invalid_identification")

    def test_cedula_province_boundaries_with_independent_checksum_vectors(self):
        # Hand-calculated weighted sums: 01 -> 1/check 9; 24 -> 8/check 2.
        for value in ("0100000009", "2400000002"):
            with self.subTest(value=value):
                self.assertIsNone(validate_cedula(value))
                self.assertEqual(detect(value), "CEDULA")
        # These have valid arithmetic checks but forbidden provinces 00 and 25.
        for value in ("0000000000", "2500000001"):
            with self.subTest(value=value):
                self.assert_validation_error(validate_cedula, value,
                                             field="identification", code="invalid_cedula")

    def test_cedula_third_digit_boundary(self):
        # 015... has sum 2/check 8; 016... has sum 4/check 6 but class 6 is forbidden.
        self.assertEqual(detect("0150000008"), "CEDULA")
        self.assert_validation_error(validate_cedula, "0160000006",
                                     field="identification", code="invalid_cedula")

    def test_zero_verifier_is_accepted_for_cedula_and_natural_ruc(self):
        # First nine digits have weighted sum 10, hence verifier (10-0)%10 == 0.
        self.assertIsNone(validate_cedula("0100000090"))
        self.assertEqual(detect("0100000090"), "CEDULA")
        self.assertIsNone(validate_ruc("0100000090001"))
        self.assertEqual(detect("0100000090001"), "RUC")
        self.assert_validation_error(validate_cedula, "0100000091",
                                     field="identification", code="invalid_cedula")

    def test_assigned_ruc_classes_enforce_province_suffix_and_length(self):
        # Classes 6/9 skip checksum, but not the explicit structural checks.
        for prefix in ("176", "179"):
            valid = prefix + "1234567" + "001"
            with self.subTest(prefix=prefix):
                self.assertIsNone(validate_ruc(valid))
                for value in ("00" + valid[2:], "25" + valid[2:],
                              valid[:-3] + "000", valid[:-3] + "002",
                              valid[:-1], valid + "0"):
                    with self.subTest(value=value):
                        self.assert_validation_error(validate_ruc, value,
                                                     field="identification", code="invalid_ruc")

    def test_numeric_detection_precedes_all_recognized_manual_types(self):
        # Classification follows the numeric shape, not a conflicting recognized hint.
        for manual in (None, "", "CEDULA", "RUC", "PASSPORT", "FOREIGN_ID", "OTHER", "FINAL_CONSUMER"):
            for value, expected in (("1719304188", "CEDULA"), ("1719304188001", "RUC"),
                                    ("9999999999999", "FINAL_CONSUMER")):
                with self.subTest(manual=manual, expected=expected):
                    self.assertEqual(detect(value, manual), expected)

    def test_invalid_numeric_checks_cannot_be_bypassed_by_manual_types(self):
        for manual in (None, "", "CEDULA", "RUC", "PASSPORT", "FOREIGN_ID", "OTHER", "FINAL_CONSUMER"):
            for value, code in (("1719304189", "invalid_cedula"),
                                ("1781234567001", "invalid_ruc")):
                with self.subTest(manual=manual, code=code):
                    self.assert_validation_error(detect, value, manual,
                                                 field="identification", code=code)

    def test_unknown_manual_type_is_rejected_even_for_reserved_identity(self):
        # The manual whitelist is checked before the reserved-identity branch.
        self.assert_validation_error(detect, "9999999999999", "UNKNOWN",
                                     field="identification_type", code="invalid_type")

    def test_empty_and_historical_manual_types_use_other_for_generic_formats(self):
        for manual in (None, "", "FOREIGN_ID", "OTHER", "FINAL_CONSUMER"):
            with self.subTest(manual=manual):
                self.assertEqual(detect("AB-1234", manual), "OTHER")

    def test_outer_spaces_are_rejected_and_interior_spaces_are_preserved(self):
        # strip() is used to reject, never to silently transform the identifier.
        for value in (" AB123", "AB123 ", " AB123 ", "\u00a0AB123", "AB123\u00a0"):
            with self.subTest(value=value):
                self.assert_validation_error(detect, value,
                                             field="identification", code="invalid_identification")
        self.assertEqual(detect("AB 123"), "OTHER")
        self.assertEqual(detect("AB 123", "PASSPORT"), "PASSPORT")

    def test_controls_and_unicode_format_characters_are_rejected_anywhere(self):
        # The current filter rejects every Unicode category beginning with C.
        for char in ("\t", "\n", "\r", "\x00", "\u200b", "\u200d", "\ufeff"):
            for value in (char + "AB123", "AB" + char + "123", "AB123" + char):
                with self.subTest(value=value):
                    self.assert_validation_error(detect, value,
                                                 field="identification", code="invalid_identification")

    def test_auxiliary_cedula_reports_its_own_string_errors(self):
        for value in ("", "171930418", "17193041880", "ABCDEFGHIJ", "１７１９３０４１８８"):
            with self.subTest(value=value):
                self.assert_validation_error(validate_cedula, value,
                                             field="identification", code="invalid_cedula")
        self.assertIsNone(validate_cedula("1719304188"))

    def test_auxiliary_ruc_reports_structure_errors_and_rejects_reserved(self):
        for value in ("", "171930418800", "17193041880010", "ABCDEFGHIJKLM", "9999999999999"):
            with self.subTest(value=value):
                self.assert_validation_error(validate_ruc, value,
                                             field="identification", code="invalid_ruc")
        self.assert_validation_error(validate_ruc, "1719304189001",
                                     field="identification", code="invalid_cedula")
        self.assertIsNone(validate_ruc("1719304188001"))

    def test_unicode_is_not_normalized_before_length_validation(self):
        # NFC would reduce the decomposed variant from 21 to 20 code points.
        composed = "É" + "A" * 19
        decomposed = "E\u0301" + "A" * 19
        self.assertEqual(detect(composed), "OTHER")
        self.assert_validation_error(detect, decomposed,
                                     field="identification", code="invalid_identification")
        self.assertEqual(detect("E\u0301" + "A" * 18), "OTHER")

    def test_unicode_compatibility_digits_are_rejected_without_nfkc(self):
        # NFKC could turn these into ASCII digits; current code explicitly rejects them.
        for value in ("AB²", "AB①", "١٧١٩٣٠٤١٨٨"):
            with self.subTest(value=value):
                self.assert_validation_error(detect, value,
                                             field="identification", code="invalid_identification")
