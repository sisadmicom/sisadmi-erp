from decimal import Decimal

# purchases/services/purchase_creator.py

from django.db import transaction

from core.models.document_type import DocumentType
from catalog.models import Product
from core.models import Branch, Company
from core.services.commercial import (
    CommercialLineCalculator,
    CommercialTotalsCalculator,
)
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
            document_type=DocumentType.objects.get(code=Purchase.DOCUMENT_TYPE_CODE),
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

            subtotal = CommercialLineCalculator.calculate_subtotal(
                item.quantity,
                item.unit_price,
                item.discount,
            )
            tax_amount = Decimal("0")
            total = CommercialLineCalculator.calculate_total(
                subtotal,
                tax_amount,
            )

            details.append(
                PurchaseDetail(
                    purchase=purchase,
                    line=line,
                    product=product,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    discount=item.discount,
                    subtotal=subtotal,
                    tax_amount=tax_amount,
                    total=total,
                )
            )

        PurchaseDetail.objects.bulk_create(
            details
        )

        totals = CommercialTotalsCalculator.calculate(details)
        purchase.subtotal = totals.subtotal
        purchase.tax = totals.tax
        purchase.total = totals.total
        purchase.save(
            update_fields=[
                "subtotal",
                "tax",
                "total",
                "updated_at",
            ]
        )
        purchase.refresh_from_db()

        return purchase
