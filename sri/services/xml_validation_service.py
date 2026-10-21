from xml.etree import ElementTree as ET
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from pathlib import Path

from lxml import etree

from sri.services.access_key_service import AccessKeyService
from sri.services.invoice_fiscal_mapping import VAT_RATE_CODES, PAYMENT_CODES


@lru_cache(maxsize=1)
def invoice_schema():
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    path = Path(__file__).resolve().parent.parent / "schemas" / "factura_V1.1.0.xsd"
    return etree.XMLSchema(etree.parse(str(path), parser))


class XmlValidationService:
    """Legacy basic validation plus explicit offline XSD validation.

    ``validate`` retains the minimal structure contract for existing callers.
    ``validate_for_sri`` verifies the supported simple invoice against the local
    official XSD and cross-checks fiscal codes, access key and monetary totals.
    Neither method validates a certificate/signature or contacts SRI.
    """

    REQUIRED_TAGS = [
        "infoTributaria",
        "infoFactura",
        "detalles",
    ]

    @staticmethod
    def validate_for_sri(xml_content):
        """Offline XSD and consistency validation for the simple IVA invoice.

        This is a distinct, explicit contract from the legacy basic validator.
        Success does not attest certificate/signature, taxpayer regime, current
        rate applicability or authorization by SRI.
        """
        try:
            parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
            root = etree.fromstring(xml_content.encode("utf-8"), parser)
            if root.getroottree().docinfo.doctype:
                raise ValueError("No se permiten DTD ni entidades en el comprobante.")
            if root.tag != "factura" or root.get("version") != "1.1.0":
                raise ValueError("La validación requiere factura versión 1.1.0.")
            invoice_schema().assertValid(root)
        except (etree.XMLSyntaxError, etree.DocumentInvalid):
            raise ValueError("La factura no cumple el XSD oficial SRI 1.1.0.") from None

        def text(path):
            return root.findtext(path)

        def amount(path):
            return Decimal(text(path))

        key = text("infoTributaria/claveAcceso")
        date = datetime.strptime(text("infoFactura/fechaEmision"), "%d/%m/%Y")
        expected = (
            date.strftime("%d%m%Y") + text("infoTributaria/codDoc")
            + text("infoTributaria/ruc") + text("infoTributaria/ambiente")
            + text("infoTributaria/estab") + text("infoTributaria/ptoEmi")
            + text("infoTributaria/secuencial")
        )
        if (not key.isdigit() or len(key) != 49 or key[:39] != expected
                or key[47] != text("infoTributaria/tipoEmision")
                or AccessKeyService.calculate_mod11(key[:-1]) != key[-1]):
            raise ValueError("La clave de acceso no coincide con la factura o su dígito verificador.")
        if text("infoTributaria/codDoc") != "01":
            raise ValueError("El comprobante debe ser una factura.")
        payments = root.findall("infoFactura/pagos/pago")
        total = amount("infoFactura/importeTotal")
        if (not payments or any(p.findtext("formaPago") not in PAYMENT_CODES.values() for p in payments)
                or sum((Decimal(p.findtext("total")) for p in payments), Decimal("0")) != total):
            raise ValueError("La factura requiere formas de pago válidas que sumen el importe total.")
        subtotal = Decimal("0")
        discount = Decimal("0")
        detail_taxes = defaultdict(lambda: [Decimal("0"), Decimal("0")])
        rates = {code: rate for rate, code in VAT_RATE_CODES.items()}
        rates.update({"0": Decimal("0"), "6": Decimal("0"), "7": Decimal("0")})
        for line in root.findall("detalles/detalle"):
            base = Decimal(line.findtext("precioTotalSinImpuesto"))
            line_discount = Decimal(line.findtext("descuento"))
            expected_base = (Decimal(line.findtext("cantidad")) * Decimal(line.findtext("precioUnitario")) - line_discount)
            if expected_base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != base:
                raise ValueError("El subtotal del detalle no coincide con cantidad, precio y descuento.")
            subtotal += base
            discount += line_discount
            for tax in line.findall("impuestos/impuesto"):
                pair = (tax.findtext("codigo"), tax.findtext("codigoPorcentaje"))
                if pair[0] != "2" or pair[1] not in rates or Decimal(tax.findtext("tarifa")) != rates[pair[1]]:
                    raise ValueError("El impuesto no coincide con los códigos fiscales de IVA soportados.")
                tax_base, value = Decimal(tax.findtext("baseImponible")), Decimal(tax.findtext("valor"))
                if tax_base != base:
                    raise ValueError("La base de IVA no coincide con el subtotal persistido.")
                # Check cent precision without choosing a new tax rounding
                # policy at half-cent ties (the current engine uses context).
                expected_value = tax_base * rates[pair[1]] / Decimal("100")
                if abs(expected_value - value) > Decimal("0.005") or (rates[pair[1]] == 0 and value != 0):
                    raise ValueError("El valor de IVA no coincide con su base y tarifa a precisión de centavos.")
                detail_taxes[pair][0] += tax_base
                detail_taxes[pair][1] += value
        header_taxes = {}
        for tax in root.findall("infoFactura/totalConImpuestos/totalImpuesto"):
            pair = (tax.findtext("codigo"), tax.findtext("codigoPorcentaje"))
            if pair in header_taxes:
                raise ValueError("Hay totales tributarios duplicados.")
            header_taxes[pair] = [Decimal(tax.findtext("baseImponible")), Decimal(tax.findtext("valor"))]
        if (dict(detail_taxes) != header_taxes or subtotal != amount("infoFactura/totalSinImpuestos")
                or discount != amount("infoFactura/totalDescuento")
                or subtotal + sum((v[1] for v in header_taxes.values()), Decimal("0")) != total):
            raise ValueError("Los totales de la factura no coinciden con sus detalles y snapshots tributarios.")
        return True

    @staticmethod
    def validate(xml_content):
        """
        Recibe XML como string.

        Retorna True si cumple estructura mínima.
        Caso contrario lanza ValueError.
        """

        try:
            root = ET.fromstring(xml_content)

        except ET.ParseError:
            raise ValueError(
                "El contenido recibido no es un XML válido."
            )

        if root.tag != "factura":
            raise ValueError(
                "El XML debe tener nodo raíz factura."
            )

        for tag in XmlValidationService.REQUIRED_TAGS:

            if root.find(tag) is None:
                raise ValueError(
                    f"Falta nodo requerido: {tag}"
                )

        detalles = root.find("detalles")

        if len(detalles.findall("detalle")) == 0:
            raise ValueError(
                "La factura debe contener al menos un detalle."
            )

        return True
