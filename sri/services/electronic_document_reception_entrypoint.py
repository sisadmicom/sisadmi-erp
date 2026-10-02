from sri.clients.sri_reception_soap_adapter import SriReceptionSoapAdapter
from sri.services.electronic_document_reception_service import (
    ElectronicDocumentReceptionService,
)


def submit_electronic_document(
    *,
    electronic_document,
    adapter=None,
    client_factory=None,
):
    resolved_adapter = adapter
    if resolved_adapter is None:
        resolved_adapter = SriReceptionSoapAdapter(
            client_factory=client_factory,
        )
    return ElectronicDocumentReceptionService.submit(
        electronic_document=electronic_document,
        adapter=resolved_adapter,
    )
