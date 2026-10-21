"""Mandatory fiscal/XAdES checks; never transforms a persisted signed XML."""
import base64

from cryptography import x509
from lxml import etree
from signxml.xades import XAdESVerifier

from core.constants.sri import SriEnvironment
from sri.services.certificate_service import CertificateService
from sri.services.xml_validation_service import XmlValidationService

DS = "{http://www.w3.org/2000/09/xmldsig#}"
SIGNING_ERROR = "No se pudo firmar. Revise el XML fiscal y el certificado configurado."


class FiscalValidationError(ValueError):
    """Safe operator-facing message with no exception payload or secret."""


def require_test_environment(environment):
    if environment != SriEnvironment.TEST:
        raise FiscalValidationError("Esta etapa permite únicamente el ambiente de pruebas del SRI.")


def fiscal_root(xml):
    try:
        if isinstance(xml, bytes):
            xml = xml.decode("utf-8")
        XmlValidationService.validate_for_sri(xml)
        return etree.fromstring(xml.encode("utf-8"), etree.XMLParser(
            resolve_entities=False, no_network=True, load_dtd=False,
        ))
    except Exception:
        raise FiscalValidationError(
            "XML fiscal inválido. Revise identificación, impuestos, totales y forma de pago."
        ) from None


def embedded_certificate(xml):
    root = fiscal_root(xml)
    nodes = root.findall(f"./{DS}Signature/{DS}KeyInfo/{DS}X509Data/{DS}X509Certificate")
    try:
        raw = "".join(nodes[0].text.split())
        return x509.load_der_x509_certificate(base64.b64decode(raw, validate=True))
    except Exception:
        raise FiscalValidationError("El XML no contiene un certificado de firma válido.") from None


def verify_signed_invoice(xml, *, certificate=None, source_xml=None):
    root = fiscal_root(xml)
    require_test_environment(root.findtext("infoTributaria/ambiente"))
    if len(root.findall(f".//{DS}Signature")) != 1 or root.find(f"{DS}Signature") is None:
        raise FiscalValidationError("La factura requiere una única firma XAdES sobre el comprobante.")
    try:
        certificate = certificate if certificate is not None else embedded_certificate(xml)
        CertificateService.validate_certificate(certificate)
        results = XAdESVerifier().verify(
            xml.encode("utf-8") if isinstance(xml, str) else xml,
            x509_cert=CertificateService.get_certificate_pem(certificate),
        )
        payloads = [r.signed_xml for r in results if r.signed_xml is not None
                    and r.signed_xml.tag == "factura" and r.signed_xml.get("id") == "comprobante"]
        if len(payloads) != 1:
            raise ValueError("Missing verified invoice reference")
        if source_xml is not None:
            source = fiscal_root(source_xml)
            for signature in source.findall(f"{DS}Signature"):
                source.remove(signature)
            before = etree.tostring(source, method="c14n", exclusive=True)
            after = etree.tostring(payloads[0], method="c14n", exclusive=True)
            if before != after:
                raise ValueError("Signer changed the fiscal payload")
    except Exception:
        raise FiscalValidationError("La firma XAdES es inválida o el XML fiscal fue alterado.") from None


def company_signer(company):
    from sri.services.environment_secret_provider import EnvironmentSecretProvider
    from sri.services.sri_signer_factory import SriSignerFactory
    return SriSignerFactory(secret_provider=EnvironmentSecretProvider(),
                            certificate_service=CertificateService).create_for_company(company)


def validate_document_invoice(document, *, signed=False):
    require_test_environment(document.environment)
    root = fiscal_root(document.xml)
    values = {
        "claveAcceso": document.access_key, "ambiente": document.environment,
        "tipoEmision": document.emission_type, "codDoc": document.document_type,
        "estab": document.establishment, "ptoEmi": document.emission_point,
        "secuencial": document.sequential, "ruc": document.company.person.identification,
    }
    if document.branch.company_id != document.company_id or any(
        root.findtext(f"infoTributaria/{name}") != str(value) for name, value in values.items()
    ):
        raise FiscalValidationError("La identidad fiscal del XML no coincide con el documento y su empresa.")
    if signed:
        try:
            certificate = company_signer(document.company).certificate_data.certificate
        except Exception:
            raise FiscalValidationError("Revise el certificado activo de la empresa antes de enviar.") from None
        verify_signed_invoice(document.xml, certificate=certificate)
    elif root.find(f"{DS}Signature") is not None:
        raise FiscalValidationError("El documento ya contiene una firma; no se puede volver a firmar.")
