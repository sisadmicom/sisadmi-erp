import os
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from django.core.files.base import ContentFile

from core.constants.document_category import DocumentCategory
from core.constants.inventory_behavior import InventoryBehavior
from core.constants.line_behavior import LineBehavior
from core.constants.sri import SriEmissionType, SriEnvironment
from core.models.document_type import DocumentType
from sales.models import Sale
from sri.models import ElectronicDocument, SriCertificate
from sri.services.certificate_service import CertificateService
from sri.services.electronic_invoice_service import ElectronicInvoiceService
from sri.tests.helpers.invoice_factory import create_test_invoice_environment


def build_runtime_certificate(*, not_before=None, not_after=None, common_name=None):
    now = datetime.utcnow()
    not_before = not_before or (now - timedelta(minutes=2))
    not_after = not_after or (now + timedelta(days=30))
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "EC"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SISADMI C11 TEST"),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name or f"c11-{uuid4().hex}.test"),
    ])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(private_key, hashes.SHA256())
    )
    password = f"c11-{uuid4().hex}"
    p12_data = pkcs12.serialize_key_and_certificates(
        name=b"sisadmi-c11",
        key=private_key,
        cert=certificate,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode()),
    )
    return p12_data, password, certificate


def create_certificate_record(company, *, not_before=None, not_after=None, secret_key=None):
    p12_data, password, certificate = build_runtime_certificate(
        not_before=not_before,
        not_after=not_after,
    )
    secret_key = secret_key or f"C11_SECRET_{uuid4().hex.upper()}"
    os.environ[secret_key] = password
    record = SriCertificate.objects.create(
        company=company,
        secret_key=secret_key,
        is_active=True,
        is_default=True,
        serial_number=str(certificate.serial_number),
        subject=certificate.subject.rfc4514_string(),
        valid_from=certificate.not_valid_before_utc,
        valid_until=certificate.not_valid_after_utc,
    )
    record.certificate_file.save(
        f"{uuid4().hex}.p12",
        ContentFile(p12_data),
    )
    return record, password, certificate


def create_generated_document():
    expected_document_type = {
        "name": "Factura de venta",
        "category": DocumentCategory.SALES,
        "line_behavior": LineBehavior.COMMERCIAL,
        "requires_detail": True,
        "affects_inventory": True,
        "inventory_behavior": InventoryBehavior.OUT,
        "can_issue_electronic": True,
        "is_active": True,
    }
    document_type, _ = DocumentType.objects.get_or_create(
        code=Sale.DOCUMENT_TYPE_CODE,
        defaults=expected_document_type,
    )
    for field, expected in expected_document_type.items():
        actual = getattr(document_type, field)
        if actual != expected:
            raise AssertionError(
                f"DocumentType {Sale.DOCUMENT_TYPE_CODE} has incompatible "
                f"{field}: expected {expected!r}, got {actual!r}."
            )

    context = create_test_invoice_environment()
    electronic = ElectronicInvoiceService.generate(
        document=context["sale"],
        document_type="01",
        emission_point=context["emission_point"],
        environment=SriEnvironment.TEST,
        emission_type=SriEmissionType.NORMAL,
    )
    return context, electronic


def assert_certificate_self_check(certificate, password, p12_data=None):
    if p12_data is not None:
        loaded = CertificateService.load(p12_data, password)
    else:
        loaded = CertificateService.load_from_file(certificate.certificate_file.path, password)
    CertificateService.validate_certificate(loaded.certificate)
    return loaded
