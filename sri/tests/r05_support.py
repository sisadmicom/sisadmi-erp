"""Synthetic fiscal/crypto fixtures for offline tests, never SRI authorization evidence."""
from datetime import date
from functools import lru_cache

from sri.services.access_key_service import AccessKeyService
from sri.services.certificate_service import CertificateService
from sri.services.pkcs12_xml_signer import Pkcs12XmlSigner


def valid_invoice_xml():
    key = AccessKeyService.generate(issue_date=date(2026, 10, 15), document_type="01",
        ruc="1790000001001", environment="1", establishment="001", emission_point="001",
        sequential="000000001", numeric_code="12345678", emission_type="1")
    return f'''<factura id="comprobante" version="1.1.0">
<infoTributaria><ambiente>1</ambiente><tipoEmision>1</tipoEmision><razonSocial>R05 TEST ONLY</razonSocial>
<ruc>1790000001001</ruc><claveAcceso>{key}</claveAcceso><codDoc>01</codDoc><estab>001</estab>
<ptoEmi>001</ptoEmi><secuencial>000000001</secuencial><dirMatriz>Test address</dirMatriz></infoTributaria>
<infoFactura><fechaEmision>15/10/2026</fechaEmision><tipoIdentificacionComprador>04</tipoIdentificacionComprador>
<razonSocialComprador>TEST BUYER</razonSocialComprador><identificacionComprador>0999999999001</identificacionComprador>
<totalSinImpuestos>100.00</totalSinImpuestos><totalDescuento>0.00</totalDescuento><totalConImpuestos>
<totalImpuesto><codigo>2</codigo><codigoPorcentaje>4</codigoPorcentaje><baseImponible>100.00</baseImponible>
<valor>15.00</valor></totalImpuesto></totalConImpuestos><importeTotal>115.00</importeTotal>
<pagos><pago><formaPago>19</formaPago><total>115.00</total></pago></pagos></infoFactura>
<detalles><detalle><descripcion>TEST PRODUCT</descripcion><cantidad>2</cantidad><precioUnitario>50</precioUnitario>
<descuento>0</descuento><precioTotalSinImpuesto>100</precioTotalSinImpuesto><impuestos><impuesto><codigo>2</codigo>
<codigoPorcentaje>4</codigoPorcentaje><tarifa>15</tarifa><baseImponible>100</baseImponible><valor>15</valor>
</impuesto></impuestos></detalle></detalles></factura>'''


@lru_cache(maxsize=1)
def signed_invoice_fixture():
    from sri.tests.electronic_document_signing_test_support import build_runtime_certificate
    data, password, _ = build_runtime_certificate(common_name="R05 OFFLINE UNIT TEST ONLY")
    loaded = CertificateService.load(data, password)
    source = valid_invoice_xml()
    return source, Pkcs12XmlSigner(loaded).sign(source), loaded


def official_xml(document):
    """Simulated SOAP evidence: same verified bytes, different XML declaration."""
    body = document.xml.split("?>", 1)[-1].lstrip("\n")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body
