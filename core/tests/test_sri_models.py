from django.db import IntegrityError
from django.test import TestCase

from core.models import (
    Branch,
    Company,
    PointOfEmission,
    SriConfiguration,
)
from people.models import Person


class SriModelsTest(TestCase):

    def setUp(self):

        company_person = Person.objects.create(
            identification="1790000001001",
            person_type="LEGAL",
            full_name="Empresa Test",
        )

        self.company = Company.objects.create(
            person=company_person,
            commercial_name="Empresa Test",
        )

        self.branch = Branch.objects.create(
            company=self.company,
            code="001",
            name="Matriz",
        )

    def test_create_sri_configuration(self):

        configuration = SriConfiguration.objects.create(
            company=self.company,
        )

        self.assertEqual(
            configuration.environment,
            "1",
        )

        self.assertEqual(
            configuration.emission_type,
            "1",
        )

        self.assertFalse(
            configuration.accounting_required,
        )

        self.assertEqual(
            configuration.company,
            self.company,
        )

    def test_company_can_have_only_one_sri_configuration(self):

        SriConfiguration.objects.create(
            company=self.company,
        )

        with self.assertRaises(IntegrityError):

            SriConfiguration.objects.create(
                company=self.company,
            )

    def test_create_point_of_emission(self):

        point = PointOfEmission.objects.create(
            branch=self.branch,
            code="001",
            name="Caja Principal",
        )

        self.assertEqual(
            point.branch,
            self.branch,
        )

        self.assertEqual(
            point.code,
            "001",
        )

        self.assertTrue(
            point.is_active,
        )

    def test_point_of_emission_code_is_unique_per_branch(self):

        PointOfEmission.objects.create(
            branch=self.branch,
            code="001",
            name="Caja Principal",
        )

        with self.assertRaises(IntegrityError):

            PointOfEmission.objects.create(
                branch=self.branch,
                code="001",
                name="Caja Secundaria",
            )

    def test_same_point_code_can_exist_in_different_branches(self):

        branch2 = Branch.objects.create(
            company=self.company,
            code="002",
            name="Sucursal 2",
        )

        point1 = PointOfEmission.objects.create(
            branch=self.branch,
            code="001",
            name="Caja Matriz",
        )

        point2 = PointOfEmission.objects.create(
            branch=branch2,
            code="001",
            name="Caja Sucursal 2",
        )

        self.assertNotEqual(
            point1.branch,
            point2.branch,
        )

        self.assertEqual(
            point1.code,
            point2.code,
        )

    def test_point_gets_company_through_branch(self):

        point = PointOfEmission.objects.create(
            branch=self.branch,
            code="001",
            name="Caja Principal",
        )

        self.assertEqual(
            point.branch.company,
            self.company,
        )
