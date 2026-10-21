"""Database regressions prepared for a separately authorized PostgreSQL run."""
from django.core.management import call_command
from django.test import TestCase

from core.models import Company
from people.identification import FINAL_CONSUMER_ID
from people.models import CompanyPersonAccess, Customer, Person
from people.services.final_consumer import ensure_person


class FinalConsumerInitializationTests(TestCase):
    def test_initialization_without_companies_is_repeatable(self):
        self.assertFalse(Company.objects.exists())
        first = ensure_person()
        call_command('initialize_final_consumer', verbosity=0)
        call_command('initialize_final_consumer', verbosity=0)
        self.assertEqual(ensure_person().pk, first.pk)
        self.assertEqual(Person.objects.filter(identification=FINAL_CONSUMER_ID).count(), 1)
        self.assertFalse(Customer.objects.exists())

    def test_company_creation_provisions_independent_customers(self):
        reserved = ensure_person()
        for identity in ('BOOTSTRAP-A', 'BOOTSTRAP-B'):
            person = Person.objects.create(identification=identity,
                identification_type='OTHER', person_type='LEGAL', full_name=identity)
            self.assertEqual(person.identification_kind.code, person.identification_type)
            company = Company.objects.create(person=person)
            company.save()
            call_command('initialize_final_consumer', verbosity=0)
            self.assertEqual(Customer.objects.filter(company=company, person=reserved).count(), 1)
            self.assertEqual(CompanyPersonAccess.objects.filter(company=company, person=reserved).count(), 1)
        self.assertEqual(Person.objects.filter(identification=FINAL_CONSUMER_ID).count(), 1)
