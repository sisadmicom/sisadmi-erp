from dataclasses import dataclass
from datetime import datetime
from threading import Lock

from core.constants.document_category import DocumentCategory
from core.constants.inventory_behavior import InventoryBehavior
from core.constants.line_behavior import LineBehavior
from core.constants.sri import SriEnvironment
from core.models.document_type import DocumentType
from sales.models import Sale
from django.utils import timezone
from sri.constants.document_status import SriDocumentStatus
from sri.services.electronic_invoice_service import ElectronicInvoiceService
from sri.tests.helpers.invoice_factory import create_test_invoice_environment


AUTHORIZED = "AUTHORIZED"
NOT_AUTHORIZED = "NOT_AUTHORIZED"
PENDING = "PENDING"
IN_PROGRESS = "IN_PROGRESS"
UNCERTAIN = "UNCERTAIN"
PROTOCOL_ERROR = "PROTOCOL_ERROR"


@dataclass(frozen=True)
class AuthorizationMessageData:
    message_type: str | None
    identifier: str | None
    message: str
    additional_information: str | None


@dataclass(frozen=True)
class AuthorizationResultData:
    outcome: str
    access_key_consulted: str
    authorization_number: str | None = None
    authorization_date: datetime | None = None
    environment: str | None = None
    authorized_xml: str | None = None
    messages: tuple[AuthorizationMessageData, ...] = ()


class FakeAuthorizationAdapter:
    def __init__(self, result=None, error=None, on_query=None):
        self.result = result
        self.error = error
        self.on_query = on_query
        self.calls = []
        self._lock = Lock()

    def query_authorization(self, *, access_key, environment):
        with self._lock:
            self.calls.append((access_key, environment))
        if self.on_query is not None:
            self.on_query()
        if self.error is not None:
            raise self.error
        return self.result


def _ensure_sales_invoice_type():
    expected = {
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
        defaults=expected,
    )
    for field, value in expected.items():
        if getattr(document_type, field) != value:
            raise AssertionError(
                f"Incompatible official SALES_INVOICE {field}: "
                f"expected {value!r}, got {getattr(document_type, field)!r}."
            )


def create_received_document():
    _ensure_sales_invoice_type()
    context = create_test_invoice_environment()
    document = ElectronicInvoiceService.generate(
        document=context["sale"],
        document_type="01",
        emission_point=context["emission_point"],
        environment=SriEnvironment.TEST,
        emission_type="1",
    )
    document.status = SriDocumentStatus.RECEIVED
    document.save(update_fields=["status"])
    document.refresh_from_db()
    return context, document


def create_authorized_document():
    context, document = create_received_document()
    document.status = SriDocumentStatus.AUTHORIZED
    document.authorization_number = document.access_key
    document.authorization_date = timezone.now()
    document.authorized_xml = "<authorized/>"
    document.save(
        update_fields=[
            "status",
            "authorization_number",
            "authorization_date",
            "authorized_xml",
        ]
    )
    document.refresh_from_db()
    return context, document


def authorization_models():
    from sri.models import SriAuthorizationAttempt, SriAuthorizationMessage

    return SriAuthorizationAttempt, SriAuthorizationMessage


def fiscal_snapshot(document):
    document.refresh_from_db()
    return {
        field: getattr(document, field)
        for field in (
            "xml",
            "access_key",
            "environment",
            "authorization_number",
            "authorization_date",
            "authorized_xml",
            "status",
        )
    }
