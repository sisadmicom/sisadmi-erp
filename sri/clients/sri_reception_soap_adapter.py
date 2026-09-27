from __future__ import annotations

from collections.abc import Iterable

import requests
from zeep import Client, Transport

from core.constants.sri import SriEnvironment
from sri.constants.reception_attempt_status import SriReceptionAttemptStatus
from sri.services.electronic_document_reception_service import (
    SriReceptionMessageData,
    SriReceptionResult,
)


TEST_RECEPTION_WSDL = (
    "https://celcer.sri.gob.ec/comprobantes-electronicos-ws/"
    "RecepcionComprobantesOffline?wsdl"
)
PRODUCTION_RECEPTION_WSDL = (
    "https://cel.sri.gob.ec/comprobantes-electronicos-ws/"
    "RecepcionComprobantesOffline?wsdl"
)
CONNECT_TIMEOUT = 10
OPERATION_TIMEOUT = 60


class SriReceptionAdapterError(RuntimeError):
    """Base error for the SRI reception transport adapter."""


class SriReceptionTransportError(SriReceptionAdapterError):
    """A transport or remote protocol failure with an ambiguous outcome."""


class SriReceptionProtocolError(SriReceptionAdapterError):
    """A response that cannot be normalized safely."""


class SriReceptionSoapAdapter:
    def __init__(self, client_factory=None):
        self.client_factory = client_factory or self._create_client

    def receive(self, *, xml, environment):
        xml_bytes = self._xml_bytes(xml)
        wsdl = self._resolve_wsdl(environment)
        try:
            client = self.client_factory(
                wsdl=wsdl,
                verify=True,
                connect_timeout=CONNECT_TIMEOUT,
                operation_timeout=OPERATION_TIMEOUT,
            )
            response = client.service.validarComprobante(xml=xml_bytes)
        except SriReceptionAdapterError:
            raise
        except Exception as exc:
            raise SriReceptionTransportError(
                "Falló el transporte de recepción SRI."
            ) from exc
        return self._normalize_response(response)

    @staticmethod
    def _xml_bytes(xml):
        if isinstance(xml, str):
            return xml.encode("utf-8")
        if isinstance(xml, bytes):
            return xml
        raise TypeError("El XML de recepción debe ser str o bytes.")

    @staticmethod
    def _resolve_wsdl(environment):
        if environment == SriEnvironment.TEST:
            return TEST_RECEPTION_WSDL
        if environment == SriEnvironment.PRODUCTION:
            return PRODUCTION_RECEPTION_WSDL
        raise ValueError("El ambiente SRI no es válido.")

    @staticmethod
    def _create_client(*, wsdl, verify, connect_timeout, operation_timeout):
        session = requests.Session()
        session.verify = verify
        transport = Transport(
            session=session,
            timeout=connect_timeout,
            operation_timeout=operation_timeout,
        )
        return Client(wsdl=wsdl, transport=transport)

    @classmethod
    def _normalize_response(cls, response):
        if response is None or not hasattr(response, "estado"):
            raise SriReceptionProtocolError(
                "La respuesta SRI no contiene estado."
            )
        state = getattr(response, "estado", None)
        if state not in {"RECIBIDA", "DEVUELTA"}:
            raise SriReceptionProtocolError(
                f"Estado de recepción SRI no reconocido: {state!r}."
            )
        messages = tuple(cls._messages(response))
        outcome = (
            SriReceptionAttemptStatus.RECEIVED
            if state == "RECIBIDA"
            else SriReceptionAttemptStatus.REJECTED
        )
        return SriReceptionResult(outcome=outcome, messages=messages)

    @classmethod
    def _messages(cls, response):
        for comprobante in cls._children(
            getattr(response, "comprobantes", None), "comprobante"
        ):
            for message in cls._children(
                getattr(comprobante, "mensajes", None), "mensaje"
            ):
                yield SriReceptionMessageData(
                    message_type=getattr(message, "tipo", None),
                    identifier=getattr(message, "identificador", None),
                    message=getattr(message, "mensaje", None) or "",
                    additional_information=getattr(
                        message, "informacionAdicional", None
                    ),
                )

    @staticmethod
    def _children(container, name):
        if container is None:
            return ()
        if isinstance(container, (list, tuple)):
            return container
        child = getattr(container, name, None)
        if child is None:
            return ()
        if isinstance(child, (list, tuple)):
            return child
        if isinstance(child, Iterable) and not isinstance(child, (str, bytes)):
            return tuple(child)
        return (child,)
