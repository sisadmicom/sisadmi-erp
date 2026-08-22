# purchases/services/purchase_creator.py

from django.db import transaction

from catalog.models import Product
from core.models import Branch, Company
from core.services.document_totals_service import DocumentTotalsService
from people.models import Supplier

from purchases.models import Purchase, PurchaseDetail
from purchases.validators.purchase_validator import PurchaseValidator


class PurchaseCreator:

    @staticmethod
    @transaction.atomic
    def create(
        dto,
    ):
        """
        Crea una compra en estado borrador.

        La compra se crea con todos sus detalles y
        sus totales son calculados antes de retornar.
        """

        PurchaseValidator.validate_create(dto)

        company = Company.objects.get(
            pk=dto.company_id
        )

        branch = Branch.objects.get(
            pk=dto.branch_id
        )

        supplier = Supplier.objects.get(
            pk=dto.supplier_id
        )

        purchase = Purchase.objects.create(
            company=company,
            branch=branch,
            supplier=supplier,
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
                PurchaseDetail(
                    purchase=purchase,
                    line=line,
                    product=product,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    discount=item.discount,
                )
            )

        PurchaseDetail.objects.bulk_create(
            details
        )

        DocumentTotalsService.calculate(
            purchase
        )

        return purchase