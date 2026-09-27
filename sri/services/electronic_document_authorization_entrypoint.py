from sri.clients.sri_authorization_soap_adapter import SriAuthorizationSoapAdapter
from sri.services.electronic_document_authorization_service import (
    ElectronicDocumentAuthorizationService,
)


def authorize_electronic_document(*, electronic_document, adapter=None, client_factory=None):
    resolved_adapter = adapter
    if resolved_adapter is None:
        resolved_adapter = SriAuthorizationSoapAdapter(client_factory=client_factory)
    return ElectronicDocumentAuthorizationService.authorize(
        electronic_document=electronic_document,
        adapter=resolved_adapter,
    )
