from decimal import Decimal
from datetime import date
from core.models.document_type import DocumentType
from core.constants.document_status import DocumentStatus
from core.constants.sri import (
    SriEmissionType,
    SriEnvironment,
)
from core.models import (
    Branch,
    Company,
    PointOfEmission,
)

from people.models import (
    Customer,
    Person,
)

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


def create_test_invoice_environment():

    # --------------------------------------------------
    # 1. EMPRESA
    # --------------------------------------------------

    company_person = Person.objects.create(
        identification="1790000001001",
        person_type="LEGAL",
        full_name="Empresa Test",
    )

    company = Company.objects.create(
        person=company_person,
        commercial_name="Empresa Test",
    )

    # --------------------------------------------------
    # 2. SUCURSAL
    # --------------------------------------------------

    branch = Branch.objects.create(
        company=company,
        code="001",
        name="Sucursal Principal",
    )

    # --------------------------------------------------
    # 3. PUNTO DE EMISIÓN
    #
    # PointOfEmission pertenece a Branch.
    # --------------------------------------------------

    emission_point = PointOfEmission.objects.create(
        branch=branch,
        code="001",
        name="Caja Principal",
        is_active=True,
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
    # 5. CLIENTE
    # --------------------------------------------------

    customer_person = Person.objects.create(
        identification="0999999999001",
        person_type="NATURAL",
        full_name="Cliente Test",
    )

    customer = Customer.objects.create(
        person=customer_person,
    )

    # --------------------------------------------------
    # 6. UNIDAD DE MEDIDA
    # --------------------------------------------------

    unit_measure = UnitMeasure.objects.create(
        code="UND",
        name="Unidad",
    )

    # --------------------------------------------------
    # 7. MARCA
    # --------------------------------------------------

    brand = Brand.objects.create(
        name="Marca Test",
    )

    # --------------------------------------------------
    # 8. GRUPO
    # --------------------------------------------------

    group = ProductGroup.objects.create(
        company=company,
        name="Grupo Test",
    )

    # --------------------------------------------------
    # 9. SUBGRUPO
    # --------------------------------------------------

    subgroup = ProductSubGroup.objects.create(
        company=company,
        group=group,
        name="Subgrupo Test",
    )

    # --------------------------------------------------
    # 10. IMPUESTO
    # --------------------------------------------------

    tax_model = Tax.objects.create(
        company=company,
        code="2",
        name="IVA",
        rate=Decimal("15.00"),
    )

    # --------------------------------------------------
    # 11. PRODUCTO
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

    product.taxes.add(
        tax_model
    )

    # --------------------------------------------------
    # 12. VENTA CONFIRMADA
    # --------------------------------------------------

    sale = Sale.objects.create(
        document_type=DocumentType.objects.get(code=Sale.DOCUMENT_TYPE_CODE),
        company=company,
        branch=branch,
        customer=customer,
        warehouse=warehouse,
        number="SAL-001-000000025",
        issue_date=date(2026, 8, 28),
        status=DocumentStatus.CONFIRMED,
        subtotal=Decimal("100.00"),
        tax=Decimal("15.00"),
        total=Decimal("115.00"),
    )

    # --------------------------------------------------
    # 13. DETALLE
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
    # 14. IMPUESTO DEL DETALLE
    # --------------------------------------------------

    SaleDetailTax.objects.create(
        detail=detail,
        tax=tax_model,
        tax_code="2",
        tax_name="IVA",
        tax_type="IVA",
        rate=Decimal("15.0000"),
        base=Decimal("100.00"),
        amount=Decimal("15.00"),
    )

    return {
        "company": company,
        "branch": branch,
        "emission_point": emission_point,
        "warehouse": warehouse,
        "customer": customer,
        "product": product,
        "sale": sale,
        "tax": tax_model,
        "environment": SriEnvironment.TEST,
        "emission_type": SriEmissionType.NORMAL,
    }
