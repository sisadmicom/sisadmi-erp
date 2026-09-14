"""B-03: fiscal allocation must not interpret the commercial ERP number."""
from xml.etree import ElementTree

from django.test import TestCase

from core.models import PointOfEmission
from sales.models import Sale
from sri.services.access_key_service import AccessKeyService
from sri.services.electronic_document_service import ElectronicDocumentService
from sri.services.xml_generator_service import XmlGeneratorService
from sri.tests.helpers.invoice_factory import create_test_invoice_environment


class FiscalNumberingIndependenceTests(TestCase):
    def setUp(self):
        self.context = create_test_invoice_environment()
        self.sale = self.context['sale']

    def issue(self, sale, point=None):
        return ElectronicDocumentService.create(
            document=sale,
            document_type='01',
            emission_point=point or self.context['emission_point'],
            environment=self.context['environment'],
            emission_type=self.context['emission_type'],
        )

    def another_sale(self, number):
        # Reuse the existing fiscal fixture's context; allocation needs a header.
        return Sale.objects.create(
            company=self.sale.company, branch=self.sale.branch,
            warehouse=self.sale.warehouse, customer=self.sale.customer,
            document_type=self.sale.document_type, status=self.sale.status,
            issue_date=self.sale.issue_date, number=number,
        )

    def test_erp_number_without_separators_can_be_issued(self):
        self.sale.number = 'ERP20260025'
        self.sale.save(update_fields=['number'])
        electronic = self.issue(self.sale)
        self.assertEqual(electronic.sequential, '000000001')
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.number, 'ERP20260025')

    def test_erp_number_with_nonnumeric_suffix_can_be_issued(self):
        self.sale.number = 'ERP-2026-ALFA'
        self.sale.save(update_fields=['number'])
        electronic = self.issue(self.sale)
        self.assertEqual(electronic.sequential, '000000001')
        self.sale.refresh_from_db()
        self.assertEqual(self.sale.number, 'ERP-2026-ALFA')

    def test_fiscal_sequence_advances_independently_of_erp_numbers(self):
        second_sale = self.another_sale('ERP-OTHER-000900')
        first = self.issue(self.sale)
        second = self.issue(second_sale)
        self.assertEqual([first.sequential, second.sequential],
                         ['000000001', '000000002'])
        self.sale.refresh_from_db()
        second_sale.refresh_from_db()
        self.assertEqual(self.sale.number, 'SAL-001-000000025')
        self.assertEqual(second_sale.number, 'ERP-OTHER-000900')

    def test_emission_points_allocate_independently(self):
        other_point = PointOfEmission.objects.create(
            branch=self.sale.branch, code='002', name='Segunda caja',
        )
        first = self.issue(self.sale)
        other = self.issue(self.another_sale('SAL-001-000026'), other_point)
        following = self.issue(self.another_sale('SAL-001-000027'))
        self.assertEqual([first.sequential, other.sequential, following.sequential],
                         ['000000001', '000000001', '000000002'])

    def test_access_key_uses_allocated_fiscal_sequence(self):
        electronic = self.issue(self.sale)
        self.assertEqual(len(electronic.access_key), 49)
        self.assertEqual(electronic.access_key[30:39], '000000001')
        self.assertEqual(electronic.access_key[30:39], electronic.sequential)

    def test_existing_fiscal_snapshot_survives_erp_number_change(self):
        electronic = self.issue(self.sale)
        original = (electronic.sequential, electronic.access_key,
                    electronic.establishment, electronic.emission_point)
        self.sale.number = 'ERP-NEW-ALFA'
        self.sale.save(update_fields=['number'])
        electronic.refresh_from_db()
        self.assertEqual((electronic.sequential, electronic.access_key,
                          electronic.establishment, electronic.emission_point), original)
        self.assertEqual(AccessKeyService.generate_from_document(electronic), original[1])
        xml = ElementTree.fromstring(XmlGeneratorService.generate_invoice(electronic))
        self.assertEqual(xml.findtext('infoTributaria/secuencial'), original[0])
        self.assertEqual(xml.findtext('infoTributaria/claveAcceso'), original[1])
