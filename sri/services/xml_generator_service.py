from collections import defaultdict
from decimal import Decimal
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from core.models import SriConfiguration
from sri.services.invoice_fiscal_mapping import IDENTIFICATION_CODES, PAYMENT_CODES, vat_codes


class XmlGeneratorService:
    """Serialize persisted commercial amounts as an unsigned SRI invoice 1.1.0.

    Missing fiscal identity/payment data are not invented. The explicit strict
    validator must approve a candidate before it is considered ready for SRI.
    Existing confirmed amounts and stored XML are never recalculated here.
    """

    @staticmethod
    def generate_invoice(electronic_document):
        sale = electronic_document.document
        company = electronic_document.company
        issuer, buyer = company.person, sale.customer.person
        details = list(sale.details.prefetch_related("applied_taxes", "product").all())
        factura = Element("factura", {"id": "comprobante", "version": "1.1.0"})
        add = XmlGeneratorService._add
        money = XmlGeneratorService._money
        info = SubElement(factura, "infoTributaria")
        for name, value in (
            ("ambiente", electronic_document.environment), ("tipoEmision", electronic_document.emission_type),
            ("razonSocial", issuer.full_name), ("nombreComercial", company.commercial_name),
            ("ruc", issuer.identification), ("claveAcceso", electronic_document.access_key),
            ("codDoc", electronic_document.document_type), ("estab", electronic_document.establishment),
            ("ptoEmi", electronic_document.emission_point), ("secuencial", electronic_document.sequential),
            ("dirMatriz", issuer.address),
        ):
            if name == "nombreComercial" and not value:
                continue
            add(info, name, value)
        info = SubElement(factura, "infoFactura")
        add(info, "fechaEmision", sale.issue_date.strftime("%d/%m/%Y"))
        if sale.branch.address:
            add(info, "dirEstablecimiento", sale.branch.address)
        try:
            configuration = company.sri_configuration
        except SriConfiguration.DoesNotExist:
            configuration = None
        if configuration is not None:
            if configuration.special_taxpayer_number:
                add(info, "contribuyenteEspecial", configuration.special_taxpayer_number)
            add(info, "obligadoContabilidad", "SI" if configuration.accounting_required else "NO")
        add(info, "tipoIdentificacionComprador", IDENTIFICATION_CODES.get(buyer.identification_type, ""))
        add(info, "razonSocialComprador", buyer.full_name)
        add(info, "identificacionComprador", buyer.identification)
        if buyer.address:
            add(info, "direccionComprador", buyer.address)
        add(info, "totalSinImpuestos", money(sale.subtotal))
        add(info, "totalDescuento", money(sum((line.discount for line in details), Decimal("0"))))
        grouped = defaultdict(lambda: [Decimal("0"), Decimal("0")])
        for line in details:
            for tax in line.applied_taxes.all():
                key = vat_codes(tax)
                grouped[key][0] += tax.base
                grouped[key][1] += tax.amount
        total_taxes = SubElement(info, "totalConImpuestos")
        for (code, percentage), (base, amount) in sorted(grouped.items()):
            total_tax = SubElement(total_taxes, "totalImpuesto")
            for name, value in (("codigo", code), ("codigoPorcentaje", percentage),
                                ("baseImponible", money(base)), ("valor", money(amount))):
                add(total_tax, name, value)
        add(info, "importeTotal", money(sale.total))
        add(info, "moneda", "DOLAR")
        if sale.payment_method:
            if sale.payment_method not in PAYMENT_CODES:
                raise ValueError("La forma de pago no tiene código SRI.")
            payment = SubElement(SubElement(info, "pagos"), "pago")
            add(payment, "formaPago", PAYMENT_CODES[sale.payment_method])
            add(payment, "total", money(sale.total))
        lines = SubElement(factura, "detalles")
        for line in details:
            node = SubElement(lines, "detalle")
            for name, value in (("codigoPrincipal", line.product.code), ("descripcion", line.product.name),
                ("cantidad", format(line.quantity, "f")), ("precioUnitario", format(line.unit_price, "f")),
                ("descuento", money(line.discount)), ("precioTotalSinImpuesto", money(line.subtotal))):
                add(node, name, value)
            taxes = SubElement(node, "impuestos")
            for tax in line.applied_taxes.all():
                code, percentage = vat_codes(tax)
                node_tax = SubElement(taxes, "impuesto")
                for name, value in (("codigo", code), ("codigoPorcentaje", percentage),
                    ("tarifa", money(tax.rate if tax.rate is not None else Decimal("0"))),
                    ("baseImponible", money(tax.base)), ("valor", money(tax.amount))):
                    add(node_tax, name, value)
        xml = tostring(factura, encoding="utf-8")
        return minidom.parseString(xml).toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")

    @staticmethod
    def _money(value):
        amount = Decimal(value)
        if not amount.is_finite() or amount != amount.quantize(Decimal("0.01")):
            raise ValueError("El importe fiscal persistido requiere revisión de precisión.")
        return format(amount, ".2f")

    @staticmethod
    def _add(parent, name, value):
        node = SubElement(parent, name)
        node.text = "" if value is None else str(value)
        return node
