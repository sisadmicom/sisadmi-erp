from types import SimpleNamespace

from django.test import SimpleTestCase

from core.tests.test_form_ux_foundation_red import Document as CoreDocument
from people.tests.person_ui_support import Document as PeopleDocument, PersonUIFixture


class HTMLContractTests(SimpleTestCase):
    def test_company_without_optional_commercial_name_has_a_valid_display_label(self):
        from core.models import Company
        from people.models import Person
        company = Company(person=Person(full_name="Razón social"), commercial_name=None)
        self.assertEqual(str(company), "Razón social")
        company.commercial_name = "Nombre comercial"
        self.assertEqual(str(company), "Nombre comercial")

    def test_textarea_matches_browser_initial_newline_semantics(self):
        for parser in (CoreDocument, PeopleDocument):
            for raw, expected in (("\nFirst\nSecond", "First\nSecond"), ("\n\nFirst", "\nFirst"), ("First", "First")):
                with self.subTest(parser=parser.__module__, raw=raw):
                    self.assertEqual(parser("<textarea>" + raw + "</textarea>").matching("textarea")[0].text, expected)

    def test_privacy_assertion_allows_only_exact_search_echo_and_catches_disclosures(self):
        helper = PersonUIFixture()
        person = SimpleNamespace(full_name="Stored private name", email="secret@example.invalid", phone="", address="", pk=23)
        response = SimpleNamespace(wsgi_request=SimpleNamespace(GET={"q": person.email}))
        echo = '<input name="q" value="secret@example.invalid">'
        response.content = echo.encode()
        helper.assert_no_private_person(response, person)
        for disclosure in ('<p>secret@example.invalid</p>', '<input name="other" value="secret@example.invalid">', '<a href="/people/23/">private</a>'):
            with self.subTest(disclosure=disclosure):
                response.content = (echo + disclosure).encode()
                with self.assertRaises(AssertionError):
                    helper.assert_no_private_person(response, person)
