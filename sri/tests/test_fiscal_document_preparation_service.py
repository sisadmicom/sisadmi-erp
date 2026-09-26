from xml.etree.ElementTree import fromstring

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from unittest.mock import patch

from core.constants.document_status import DocumentStatus
from core.constants.document_category import DocumentCategory
from core.constants.sri import SriDocumentType
from core.models import Branch, DocumentType, PointOfEmission, SriConfiguration
from sri.constants.document_status import SriDocumentStatus
from sri.models import ElectronicDocument, FiscalSequence
from sri.tests.helpers.invoice_factory import create_test_invoice_environment


class FiscalDocumentPreparationBoundaryREDTests(TestCase):
    def setUp(self):
        self.context = create_test_invoice_environment()
        self.sale = self.context["sale"]
        self.company = self.context["company"]
        self.branch = self.context["branch"]
        self.point = self.context["emission_point"]
        self.configuration = SriConfiguration.objects.create(
            company=self.company,
            environment="2",
            emission_type="1",
        )

    def _boundary(self):
        from sri.services.fiscal_document_preparation_service import (
            FiscalDocumentPreparationService,
        )

        return FiscalDocumentPreparationService

    def _prepare(self):
        return self._boundary().prepare(
            sale=self.sale,
            point_of_emission=self.point,
        )

    def _origin(self):
        return ContentType.objects.get_for_model(self.sale, for_concrete_model=False)

    def _electronic_documents(self):
        return ElectronicDocument.objects.filter(
            content_type=self._origin(),
            object_id=self.sale.pk,
        )

    def _sequence_snapshot(self):
        return list(
            FiscalSequence.objects.filter(company=self.company)
            .order_by("pk")
            .values(
                "establishment",
                "emission_point",
                "document_type",
                "next_number",
            )
        )

    def test_confirmed_eligible_sale_prepares_generated_electronic_document(self):
        electronic = self._prepare()

        self.assertEqual(electronic.document, self.sale)
        self.assertEqual(electronic.company_id, self.sale.company_id)
        self.assertEqual(electronic.branch_id, self.sale.branch_id)
        self.assertEqual(electronic.document_type, SriDocumentType.INVOICE)
        self.assertEqual(electronic.environment, self.configuration.environment)
        self.assertEqual(electronic.emission_type, self.configuration.emission_type)
        self.assertEqual(electronic.emission_point, self.point.code)
        self.assertEqual(electronic.status, SriDocumentStatus.GENERATED)
        self.assertTrue(electronic.xml)
        self.assertEqual(self._electronic_documents().count(), 1)

    def test_non_electronic_document_type_is_rejected_without_fiscal_effects(self):
        non_electronic = DocumentType.objects.create(
            code="SALES_INTERNAL",
            name="Venta interna",
            category=DocumentCategory.SALES,
            can_issue_electronic=False,
        )
        self.sale.document_type = non_electronic
        self.sale.save(update_fields=["document_type"])
        before_sequences = self._sequence_snapshot()

        service = self._boundary()
        with self.assertRaises(ValueError):
            service.prepare(sale=self.sale, point_of_emission=self.point)

        self.assertEqual(self._electronic_documents().count(), 0)
        self.assertEqual(self._sequence_snapshot(), before_sequences)

    def test_draft_sale_is_rejected_without_fiscal_effects(self):
        self.sale.status = DocumentStatus.DRAFT
        self.sale.save(update_fields=["status"])
        before_sequences = self._sequence_snapshot()

        service = self._boundary()
        with self.assertRaises(ValueError):
            service.prepare(sale=self.sale, point_of_emission=self.point)

        self.assertEqual(self._electronic_documents().count(), 0)
        self.assertEqual(self._sequence_snapshot(), before_sequences)

    def test_fiscal_sequential_is_independent_from_sale_number(self):
        self.sale.number = "ERP-ONLY-999999"
        self.sale.save(update_fields=["number"])

        electronic = self._prepare()

        self.assertNotEqual(electronic.sequential, self.sale.number)
        root = fromstring(electronic.xml)
        self.assertEqual(
            root.findtext("infoTributaria/secuencial"),
            electronic.sequential,
        )

    def test_point_of_emission_from_other_branch_is_rejected_without_fiscal_effects(self):
        other_branch = Branch.objects.create(
            company=self.company,
            code="002",
            name="Otra sucursal",
        )
        other_point = PointOfEmission.objects.create(
            branch=other_branch,
            code="001",
            name="Punto ajeno",
            is_active=True,
        )
        before_sequences = self._sequence_snapshot()

        service = self._boundary()
        with self.assertRaises(ValueError):
            service.prepare(sale=self.sale, point_of_emission=other_point)

        self.assertEqual(self._electronic_documents().count(), 0)
        self.assertEqual(self._sequence_snapshot(), before_sequences)

    def test_missing_sri_configuration_is_rejected_without_fiscal_effects(self):
        self.configuration.delete()
        before_sequences = self._sequence_snapshot()

        service = self._boundary()
        with self.assertRaises(ValueError):
            service.prepare(sale=self.sale, point_of_emission=self.point)

        self.assertEqual(self._electronic_documents().count(), 0)
        self.assertEqual(self._sequence_snapshot(), before_sequences)

    def test_second_prepare_is_rejected_without_consuming_second_sequence(self):
        first = self._prepare()
        before_second = self._sequence_snapshot()

        service = self._boundary()
        with self.assertRaises(ValueError):
            service.prepare(sale=self.sale, point_of_emission=self.point)

        current = self._electronic_documents().get()
        self.assertEqual(current.pk, first.pk)
        self.assertEqual(current.access_key, first.access_key)
        self.assertEqual(current.sequential, first.sequential)
        self.assertEqual(current.status, first.status)
        self.assertEqual(current.xml, first.xml)
        self.assertEqual(self._electronic_documents().count(), 1)
        self.assertEqual(self._sequence_snapshot(), before_second)

    def test_xml_generation_failure_rolls_back_document_and_fiscal_sequence(self):
        before_sequences = self._sequence_snapshot()

        with patch(
            "sri.services.xml_generation_service.XmlGenerationService.generate",
            side_effect=RuntimeError("xml generation failure"),
        ):
            with self.assertRaises(RuntimeError):
                self._prepare()

        self.assertEqual(self._electronic_documents().count(), 0)
        self.assertEqual(self._sequence_snapshot(), before_sequences)

    def test_prepare_does_not_sign_document(self):
        with patch("sri.services.xml_signing_service.XmlSigningService.sign") as sign:
            electronic = self._prepare()

        self.assertEqual(electronic.status, SriDocumentStatus.GENERATED)
        sign.assert_not_called()
