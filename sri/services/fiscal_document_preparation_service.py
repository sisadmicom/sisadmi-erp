from django.db import transaction

from core.constants.document_status import DocumentStatus
from core.constants.document_type_codes import DocumentTypeCodes
from core.constants.sri import SriDocumentType
from sales.models import Sale
from core.models import SriConfiguration
from sri.services.electronic_invoice_service import ElectronicInvoiceService


class FiscalDocumentPreparationService:
    """Prepare a confirmed electronic sales invoice through the SRI pipeline."""

    @staticmethod
    @transaction.atomic
    def prepare(*, sale, point_of_emission):
        if not isinstance(sale, Sale) or not sale.pk:
            raise ValueError("La venta debe estar persistida.")

        if sale.status != DocumentStatus.CONFIRMED:
            raise ValueError("La venta debe estar confirmada.")

        document_type = sale.document_type
        if (
            not document_type.can_issue_electronic
            or document_type.code != DocumentTypeCodes.SALES_INVOICE
        ):
            raise ValueError("El tipo de documento no permite emisión electrónica.")

        sale.company.refresh_from_db()
        try:
            sri_configuration = sale.company.sri_configuration
        except SriConfiguration.DoesNotExist:
            raise ValueError("La empresa no tiene configuración SRI.")

        if point_of_emission is None or not point_of_emission.is_active:
            raise ValueError("El punto de emisión no está activo.")

        if point_of_emission.branch_id != sale.branch_id:
            raise ValueError("El punto de emisión no pertenece a la sucursal de la venta.")

        if point_of_emission.branch.company_id != sale.company_id:
            raise ValueError("El punto de emisión no pertenece a la empresa de la venta.")

        return ElectronicInvoiceService.generate(
            document=sale,
            document_type=SriDocumentType.INVOICE,
            emission_point=point_of_emission,
            environment=sri_configuration.environment,
            emission_type=sri_configuration.emission_type,
        )
