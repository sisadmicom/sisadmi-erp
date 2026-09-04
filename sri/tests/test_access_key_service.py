from datetime import date

from django.test import SimpleTestCase

from sri.services.access_key_service import (
    AccessKeyService,
)


class AccessKeyServiceTest(SimpleTestCase):

    def test_generate_numeric_code_has_eight_digits(self):

        numeric_code = (
            AccessKeyService.generate_numeric_code()
        )

        self.assertEqual(
            len(numeric_code),
            8,
        )

        self.assertTrue(
            numeric_code.isdigit(),
        )

    def test_generate_numeric_codes_are_not_always_equal(self):

        first_code = (
            AccessKeyService.generate_numeric_code()
        )

        second_code = (
            AccessKeyService.generate_numeric_code()
        )

        self.assertNotEqual(
            first_code,
            second_code,
        )

    def test_calculate_mod11(self):

        value = "010120260117900000010011001000000025123456781"

        verifier = (
            AccessKeyService.calculate_mod11(
                value
            )
        )

        self.assertTrue(
            verifier.isdigit(),
        )

        self.assertEqual(
            len(verifier),
            1,
        )

    def test_generate_access_key_has_49_digits(self):

        access_key = AccessKeyService.generate(
            issue_date=date(2026, 1, 1),
            document_type="01",
            ruc="1790000001001",
            environment="1",
            establishment="001",
            emission_point="001",
            sequential="000000025",
            numeric_code="12345678",
            emission_type="1",
        )

        self.assertEqual(
            len(access_key),
            49,
        )

        self.assertTrue(
            access_key.isdigit(),
        )

    def test_access_key_contains_expected_base(self):

        access_key = AccessKeyService.generate(
            issue_date=date(2026, 1, 1),
            document_type="01",
            ruc="1790000001001",
            environment="1",
            establishment="001",
            emission_point="001",
            sequential="000000025",
            numeric_code="12345678",
            emission_type="1",
        )

        expected_base = (
            "01012026"
            "01"
            "1790000001001"
            "1"
            "001"
            "001"
            "000000025"
            "12345678"
            "1"
        )

        self.assertEqual(
            access_key[:48],
            expected_base,
        )

    def test_calculate_mod11_official_sri_example(self):

        value = "41261533"

        verifier = AccessKeyService.calculate_mod11(
            value
        )

        self.assertEqual(
            verifier,
            "6",
        )