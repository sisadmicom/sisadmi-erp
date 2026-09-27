from dataclasses import dataclass
from decimal import Decimal
from threading import Lock

from django.db import connections

from core.constants.document_category import DocumentCategory
from core.constants.inventory_behavior import InventoryBehavior
from core.constants.line_behavior import LineBehavior
from core.constants.sri import SriEmissionType, SriEnvironment
from core.models.document_type import DocumentType
from sales.models import Sale
from sri.constants.document_status import SriDocumentStatus
from sri.models import ElectronicDocument
from sri.services.electronic_invoice_service import ElectronicInvoiceService
from sri.tests.helpers.invoice_factory import create_test_invoice_environment


RECEIVED = "RECEIVED"
REJECTED = "REJECTED"
IN_PROGRESS = "IN_PROGRESS"
UNCERTAIN = "UNCERTAIN"
FAILED = "FAILED"


@dataclass(frozen=True)
class ReceptionMessageData:
    message_type: str | None
    identifier: str | None
    message: str
    additional_information: str | None


@dataclass(frozen=True)
class ReceptionResult:
    outcome: str
    messages: tuple[ReceptionMessageData, ...] = ()


class AmbiguousReceptionError(RuntimeError):
    """Represents a transport result that cannot prove SRI outcome."""


class FakeReceptionAdapter:
    def __init__(self, result=None, error=None, on_receive=None):
        self.result = result
        self.error = error
        self.on_receive = on_receive
        self.calls = []
        self._lock = Lock()

    def receive(self, *, xml, environment):
        with self._lock:
            self.calls.append((xml, environment))
        if self.on_receive is not None:
            self.on_receive()
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
        actual = getattr(document_type, field)
        if actual != value:
            raise AssertionError(
                f"Incompatible official SALES_INVOICE {field}: "
                f"expected {value!r}, got {actual!r}."
            )
    return document_type


def create_signed_document():
    _ensure_sales_invoice_type()
    context = create_test_invoice_environment()
    document = ElectronicInvoiceService.generate(
        document=context["sale"],
        document_type="01",
        emission_point=context["emission_point"],
        environment=SriEnvironment.TEST,
        emission_type=SriEmissionType.NORMAL,
    )
    document.status = SriDocumentStatus.SIGNED
    document.save(update_fields=["status"])
    document.refresh_from_db()
    return context, document


def fiscal_snapshot(document):
    document.refresh_from_db()
    return {
        field: getattr(document, field)
        for field in (
            "xml", "access_key", "document_type", "environment",
            "emission_type", "establishment", "emission_point",
            "sequential", "numeric_code", "company_id", "branch_id",
            "content_type_id", "object_id", "authorization_number",
            "authorization_date",
        )
    }


def reception_models():
    try:
        from sri.models.sri_reception_attempt import SriReceptionAttempt
        from sri.models.sri_reception_message import SriReceptionMessage
    except (ImportError, ModuleNotFoundError) as error:
        raise AssertionError(
            "C-12A reception persistence models are not implemented."
        ) from error
    return SriReceptionAttempt, SriReceptionMessage


def another_db_attempt_count(document_id):
    SriReceptionAttempt, _ = reception_models()
    observer = connections["default"].copy()
    try:
        with observer.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM {SriReceptionAttempt._meta.db_table} "
                "WHERE electronic_document_id = %s",
                [document_id],
            )
            return cursor.fetchone()[0]
    finally:
        observer.close()
