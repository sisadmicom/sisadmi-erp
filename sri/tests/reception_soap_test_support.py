from dataclasses import dataclass
from types import SimpleNamespace

from core.constants.sri import SriEnvironment
from sri.services.electronic_document_reception_service import (
    SriReceptionMessageData,
    SriReceptionResult,
)


TEST_WSDL = (
    "https://celcer.sri.gob.ec/comprobantes-electronicos-ws/"
    "RecepcionComprobantesOffline?wsdl"
)
PRODUCTION_WSDL = (
    "https://cel.sri.gob.ec/comprobantes-electronicos-ws/"
    "RecepcionComprobantesOffline?wsdl"
)
CONNECT_TIMEOUT = 10
OPERATION_TIMEOUT = 60


class FakeSoapOperation:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.call_count = 0
        self.arguments = []

    def __call__(self, *, xml):
        self.call_count += 1
        self.arguments.append(xml)
        if self.error is not None:
            raise self.error
        return self.response


class FakeSoapClient:
    def __init__(self, operation):
        self.service = SimpleNamespace(validarComprobante=operation)
        self.authorization_call_count = 0

    def consultarAutorizacion(self, *args, **kwargs):
        self.authorization_call_count += 1
        raise AssertionError("C-12B no puede consultar autorización.")


class FakeClientFactory:
    def __init__(self, operation):
        self.operation = operation
        self.call_count = 0
        self.calls = []
        self.client = FakeSoapClient(operation)

    def __call__(
        self,
        *,
        wsdl,
        verify,
        connect_timeout,
        operation_timeout,
    ):
        self.call_count += 1
        self.calls.append(
            {
                "wsdl": wsdl,
                "verify": verify,
                "connect_timeout": connect_timeout,
                "operation_timeout": operation_timeout,
            }
        )
        return self.client


def response(*, state=None, comprobantes=None, omit_state=False):
    value = SimpleNamespace(comprobantes=comprobantes)
    if not omit_state:
        value.estado = state
    return value


def comprobante(*messages):
    return SimpleNamespace(
        mensajes=SimpleNamespace(mensaje=list(messages))
    )


def message(*, tipo=None, identificador=None, mensaje=None, informacion=None):
    return SimpleNamespace(
        tipo=tipo,
        identificador=identificador,
        mensaje=mensaje,
        informacionAdicional=informacion,
    )


def result(outcome, *messages):
    return SriReceptionResult(
        outcome=outcome,
        messages=tuple(messages),
    )


def message_data(*, message_type, identifier, text, additional_information):
    return SriReceptionMessageData(
        message_type=message_type,
        identifier=identifier,
        message=text,
        additional_information=additional_information,
    )


def production_adapter(factory):
    from sri.clients.sri_reception_soap_adapter import SriReceptionSoapAdapter

    return SriReceptionSoapAdapter(client_factory=factory)


def production_exceptions():
    from sri.clients.sri_reception_soap_adapter import (
        SriReceptionProtocolError,
        SriReceptionTransportError,
    )

    return SriReceptionProtocolError, SriReceptionTransportError


def assert_single_xml_argument(testcase, operation, expected):
    testcase.assertEqual(operation.call_count, 1)
    testcase.assertEqual(operation.arguments, [expected])


__all__ = [
    "CONNECT_TIMEOUT",
    "OPERATION_TIMEOUT",
    "PRODUCTION_WSDL",
    "TEST_WSDL",
    "FakeClientFactory",
    "FakeSoapOperation",
    "SriEnvironment",
    "assert_single_xml_argument",
    "comprobante",
    "message",
    "message_data",
    "production_adapter",
    "production_exceptions",
    "response",
]
