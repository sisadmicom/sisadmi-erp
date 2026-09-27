from datetime import datetime, timezone
from types import SimpleNamespace

from core.constants.sri import SriEnvironment

TEST_WSDL = (
    "https://celcer.sri.gob.ec/comprobantes-electronicos-ws/"
    "AutorizacionComprobantesOffline?wsdl"
)
PRODUCTION_WSDL = (
    "https://cel.sri.gob.ec/comprobantes-electronicos-ws/"
    "AutorizacionComprobantesOffline?wsdl"
)
CONNECT_TIMEOUT = 10
OPERATION_TIMEOUT = 60
ACCESS_KEY = "1234567890123456789012345678901234567890123456789"
AUTHORIZED_XML = "<?xml version=\"1.0\"?>\n  <autorizado>á</autorizado>  "
_UNSET = object()


class FakeSoapOperation:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.call_count = 0
        self.arguments = []

    def __call__(self, *, claveAccesoComprobante):
        self.call_count += 1
        self.arguments.append(claveAccesoComprobante)
        if self.error is not None:
            raise self.error
        return self.response


class FakeSoapClient:
    def __init__(self, operation):
        self.service = SimpleNamespace(autorizacionComprobante=operation)
        self.reception_call_count = 0

    def validarComprobante(self, *args, **kwargs):
        self.reception_call_count += 1
        raise AssertionError("C-13B no puede llamar recepción.")


class FakeClientFactory:
    def __init__(self, operation=None, error=None):
        self.operation = operation or FakeSoapOperation()
        self.error = error
        self.call_count = 0
        self.calls = []
        self.client = FakeSoapClient(self.operation)

    def __call__(self, *, wsdl, verify, connect_timeout, operation_timeout):
        self.call_count += 1
        self.calls.append({
            "wsdl": wsdl,
            "verify": verify,
            "connect_timeout": connect_timeout,
            "operation_timeout": operation_timeout,
        })
        if self.error is not None:
            raise self.error
        return self.client


def message(*, tipo=None, identificador=None, mensaje=None, informacion=None):
    return SimpleNamespace(
        tipo=tipo,
        identificador=identificador,
        mensaje=mensaje,
        informacionAdicional=informacion,
    )


def authorization(*, state="AUTORIZADO", number="AUTH-001", date=_UNSET,
                   environment="PRUEBAS", comprobante=AUTHORIZED_XML,
                   messages=()):
    if date is _UNSET:
        date = datetime(2026, 9, 27, 15, 30, tzinfo=timezone.utc)
    return SimpleNamespace(
        estado=state,
        numeroAutorizacion=number,
        fechaAutorizacion=date,
        ambiente=environment,
        comprobante=comprobante,
        mensajes=SimpleNamespace(mensaje=list(messages)),
    )


def response(*, key=ACCESS_KEY, count="1", authorizations=_UNSET,
             omit_key=False, omit_count=False, omit_authorizations=False):
    value = SimpleNamespace()
    if not omit_key:
        value.claveAccesoConsultada = key
    if not omit_count:
        value.numeroComprobantes = count
    if not omit_authorizations:
        if authorizations is _UNSET:
            authorizations = [authorization()]
        value.autorizaciones = SimpleNamespace(
            autorizacion=list(authorizations or [])
        )
    return value


def production_adapter(factory):
    from sri.clients.sri_authorization_soap_adapter import SriAuthorizationSoapAdapter
    return SriAuthorizationSoapAdapter(client_factory=factory)


def production_exceptions():
    from sri.services.electronic_document_authorization_service import (
        SriAuthorizationProtocolError,
        SriAuthorizationTransportError,
    )
    return SriAuthorizationProtocolError, SriAuthorizationTransportError
