from django.db import transaction

from core.models.document_type import DocumentType
from catalog.models import Product

from core.models import Branch, Company

from inventory.models import (
    Transfer,
    TransferDetail,
    Warehouse,
)

from inventory.validators import TransferValidator


class TransferCreator:

    @staticmethod
    @transaction.atomic
    def create(dto):

        TransferValidator.validate(dto)

        company = Company.objects.get(
            pk=dto.company_id
        )

        branch = Branch.objects.get(
            pk=dto.branch_id
        )

        source = Warehouse.objects.get(
            pk=dto.source_warehouse_id
        )

        destination = Warehouse.objects.get(
            pk=dto.destination_warehouse_id
        )

        transfer = Transfer.objects.create(
            document_type=DocumentType.objects.get(code=Transfer.DOCUMENT_TYPE_CODE),
            company=company,
            branch=branch,
            source_warehouse=source,
            destination_warehouse=destination,
            number="",
            issue_date=dto.issue_date,
            notes=dto.notes,
        )

        details = []

        for line, item in enumerate(
            dto.details,
            start=1,
        ):

            product = Product.objects.get(
                pk=item.product_id
            )

            details.append(
                TransferDetail(
                    transfer=transfer,
                    line=line,
                    product=product,
                    quantity=item.quantity,
                )
            )

        TransferDetail.objects.bulk_create(
            details
        )

        transfer.refresh_from_db()

        return transfer
