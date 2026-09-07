from decimal import Decimal

from django.contrib.contenttypes.models import ContentType

from core.models.document_type import DocumentType
from core.constants.document_status import DocumentStatus
from core.models import Company, Branch

from people.models import Person, Customer

from inventory.models import Warehouse

from catalog.models import (
    UnitMeasure,
    Brand,
    ProductGroup,
    ProductSubGroup,
    Product,
    Tax,
)

from sales.models import (
    Sale,
    SaleDetail,
    SaleDetailTax,
)

from sri.models import ElectronicDocument
from sri.constants.document_status import SriDocumentStatus


def create_test_electronic_document():

    # --------------------------------------------------
    # 1. PERSONA / EMPRESA
    # --------------------------------------------------

    company_person = Person.objects.create(
        identification="1790000001001",
        full_name="Empresa Test",
    )

    company = Company.objects.create(
        person=company_person,
    )

    # --------------------------------------------------
    # 2. PERSONA / CLIENTE
    # --------------------------------------------------

    customer_person = Person.objects.create(
        identification="0999999999001",
        full_name="Cliente Test",
    )

    customer = Customer.objects.create(
        person=customer_person,
    )

    # --------------------------------------------------
    # 3. SUCURSAL
    # --------------------------------------------------

    branch = Branch.objects.create(
        company=company,
        code="001",
        name="Sucursal Principal",
    )

    # --------------------------------------------------
    # 4. BODEGA
    # --------------------------------------------------

    warehouse = Warehouse.objects.create(
        company=company,
        branch=branch,
        code="001",
        name="Bodega Principal",
        is_main=True,
    )

    # --------------------------------------------------
    # 5. UNIDAD DE MEDIDA
    # --------------------------------------------------

    unit_measure = UnitMeasure.objects.create(
        code="UND",
        name="Unidad",
    )

    # --------------------------------------------------
    # 6. MARCA
    # --------------------------------------------------

    brand = Brand.objects.create(
        name="Marca Test",
    )

    # --------------------------------------------------
    # 7. GRUPO
    # --------------------------------------------------

    group = ProductGroup.objects.create(
        company=company,
        name="Grupo Test",
    )

    # --------------------------------------------------
    # 8. SUBGRUPO
    # --------------------------------------------------

    subgroup = ProductSubGroup.objects.create(
        company=company,
        group=group,
        name="Subgrupo Test",
    )

    # --------------------------------------------------
    # 9. IMPUESTO
    # --------------------------------------------------

    tax_model = Tax.objects.create(
        company=company,
        code="2",
        name="IVA",
        rate=Decimal("15.00"),
    )

    # --------------------------------------------------
    # 10. PRODUCTO
    # --------------------------------------------------

    product = Product.objects.create(
        company=company,
        code="PROD001",
        name="Producto Test",
        description="Producto de prueba",
        group=group,
        subgroup=subgroup,
        brand=brand,
        unit_measure=unit_measure,
        cost_price=Decimal("40.00"),
        sale_price=Decimal("50.00"),
    )

    product.taxes.add(tax_model)

    # --------------------------------------------------
    # 11. VENTA
    # --------------------------------------------------

    sale = Sale.objects.create(
        document_type=DocumentType.objects.get(code=Sale.DOCUMENT_TYPE_CODE),
        company=company,
        branch=branch,
        customer=customer,
        warehouse=warehouse,
        number="001-001-000000025",
        issue_date="2026-08-28",
        status=DocumentStatus.CONFIRMED,
        subtotal=Decimal("100.00"),
        tax=Decimal("15.00"),
        total=Decimal("115.00"),
    )

    # --------------------------------------------------
    # 12. DETALLE DE VENTA
    #
    # SaleDetail hereda de BaseDetail.
    # --------------------------------------------------

    detail = SaleDetail.objects.create(
        sale=sale,
        product=product,

        line=1,

        quantity=Decimal("2.000000"),

        unit_price=Decimal("50.000000"),

        discount=Decimal("0.00"),

        subtotal=Decimal("100.00"),

        tax_amount=Decimal("15.00"),

        total=Decimal("115.00"),
    )

    # --------------------------------------------------
    # 13. IMPUESTO APLICADO AL DETALLE
    # --------------------------------------------------

    SaleDetailTax.objects.create(
        detail=detail,
        tax=tax_model,
        tax_code="2",
        rate=Decimal("15.0000"),
        base=Decimal("100.00"),
        amount=Decimal("15.00"),
    )

    # --------------------------------------------------
    # 14. DOCUMENTO ELECTRÓNICO
    # --------------------------------------------------

    content_type = ContentType.objects.get_for_model(
        sale
    )

    electronic_document = ElectronicDocument.objects.create(
        company=company,
        branch=branch,
        content_type=content_type,
        object_id=sale.pk,
        document_type="01",
        environment="1",
        emission_type="1",
        establishment="001",
        emission_point="001",
        sequential="000000025",
        numeric_code="12345678",
        access_key=(
            "1234567890123456789012345678901234567890123456789"
        ),
        status=SriDocumentStatus.DRAFT,
    )

    return electronic_document