from decimal import Decimal

from django.db import transaction

from core.models.document_type import DocumentType
from core.models import Company
from core.models import Branch
from core.services.commercial import (
    CommercialLineCalculator,
    CommercialTotalsCalculator,
)

from people.models import Customer

from catalog.models import Product
from catalog.services.tax_resolver import TaxResolver
from catalog.services.tax_calculation_service import (
    TaxCalculationService,
)

from inventory.models import Warehouse

from sales.models import Sale
from sales.models import SaleDetail
from sales.models import SaleDetailTax

from sales.services.sale_validator import SaleValidator


class CreateSale:

    @staticmethod
    @transaction.atomic
    def execute(dto):

        SaleValidator.validate(dto)

        company = Company.objects.get(
            pk=dto.company_id
        )

        branch = Branch.objects.get(
            pk=dto.branch_id
        )

        warehouse = Warehouse.objects.get(
            pk=dto.warehouse_id
        )

        customer = Customer.objects.get(
            pk=dto.customer_id
        )

        sale = Sale.objects.create(
            document_type=DocumentType.objects.get(code=Sale.DOCUMENT_TYPE_CODE),
            company=company,
            branch=branch,
            warehouse=warehouse,
            customer=customer,
            issue_date=dto.issue_date,
            notes=dto.notes,
        )

        calculated_details = []

        for line_number, item in enumerate(
            dto.details,
            start=1,
        ):

            product = Product.objects.get(
                pk=item.product_id
            )

            # -------------------------------------------------
            # 1. SUBTOTAL DE LA LÍNEA
            # -------------------------------------------------

            line_subtotal = CommercialLineCalculator.calculate_subtotal(
                item.quantity,
                item.unit_price,
                item.discount,
            )

            detail = SaleDetail.objects.create(
                sale=sale,
                line=line_number,
                product=product,
                quantity=item.quantity,
                unit_price=item.unit_price,
                discount=item.discount,
                subtotal=line_subtotal,
            )

            # -------------------------------------------------
            # 2. RESOLVER IMPUESTOS
            #
            # Producto
            #     ↓
            # Subgrupo
            #     ↓
            # Grupo
            #     ↓
            # Configuración global
            # -------------------------------------------------

            taxes = TaxResolver.resolve(product)

            # -------------------------------------------------
            # 3. CALCULAR IMPUESTOS
            # -------------------------------------------------

            tax_results = TaxCalculationService.calculate(
                line_subtotal,
                taxes,
            )

            line_tax = Decimal("0.00")

            # -------------------------------------------------
            # 4. GUARDAR IMPUESTOS APLICADOS
            # -------------------------------------------------

            for result in tax_results:

                tax = result["tax"]
                amount = result["amount"]

                SaleDetailTax.objects.create(
                    detail=detail,
                    tax=tax,
                    tax_code=tax.code,
                    tax_name=tax.name,
                    tax_type=tax.tax_type,
                    rate=tax.rate,
                    base=result["base"],
                    amount=amount,
                )

                line_tax += amount

            # -------------------------------------------------
            # 5. TOTALES DEL DETALLE
            # -------------------------------------------------

            detail.tax_amount = line_tax

            detail.total = CommercialLineCalculator.calculate_total(
                line_subtotal,
                line_tax,
            )

            detail.save(
                update_fields=[
                    "tax_amount",
                    "total",
                    "updated_at",
                ]
            )

            calculated_details.append(detail)

        totals = CommercialTotalsCalculator.calculate(calculated_details)
        sale.subtotal = totals.subtotal
        sale.tax = totals.tax
        sale.total = totals.total

        sale.save(
            update_fields=[
                "subtotal",
                "tax",
                "total",
            ]
        )

        return sale