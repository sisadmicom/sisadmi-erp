from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import requests
from zeep import Client, Transport
from zeep.exceptions import Fault

from core.constants.sri import SriEnvironment
from sri.constants.authorization_attempt_status import SriAuthorizationAttemptStatus
from sri.services.electronic_document_authorization_service import (
    SriAuthorizationMessageData,
    SriAuthorizationProtocolError,
    SriAuthorizationResult,
    SriAuthorizationTransportError,
)

TEST_AUTHORIZATION_WSDL = (
    "https://celcer.sri.gob.ec/comprobantes-electronicos-ws/"
    "AutorizacionComprobantesOffline?wsdl"
)
PRODUCTION_AUTHORIZATION_WSDL = (
    "https://cel.sri.gob.ec/comprobantes-electronicos-ws/"
    "AutorizacionComprobantesOffline?wsdl"
)
CONNECT_TIMEOUT = 10
OPERATION_TIMEOUT = 60


class SriAuthorizationSoapAdapter:
    def __init__(self, client_factory=None):
        self.client_factory = client_factory or self._create_client

    def query_authorization(self, *, access_key, environment):
        wsdl = self._resolve_wsdl(environment)
        try:
            client = self.client_factory(
                wsdl=wsdl,
                verify=True,
                connect_timeout=CONNECT_TIMEOUT,
                operation_timeout=OPERATION_TIMEOUT,
            )
            response = client.service.autorizacionComprobante(
                claveAccesoComprobante=access_key
            )
        except (SriAuthorizationProtocolError, SriAuthorizationTransportError):
            raise
        except (TimeoutError, requests.exceptions.RequestException, Fault) as exc:
            raise SriAuthorizationTransportError(
                "Falló el transporte de autorización SRI."
            ) from exc
        return self._normalize_response(response, requested_environment=environment)

    @staticmethod
    def _resolve_wsdl(environment):
        if environment == SriEnvironment.TEST:
            return TEST_AUTHORIZATION_WSDL
        if environment == SriEnvironment.PRODUCTION:
            return PRODUCTION_AUTHORIZATION_WSDL
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
    def _normalize_response(cls, response, *, requested_environment):
        if response is None or not hasattr(response, "claveAccesoConsultada"):
            raise SriAuthorizationProtocolError(
                "La respuesta no contiene claveAccesoConsultada."
            )
        key = getattr(response, "claveAccesoConsultada", None)
        cls._validate_access_key(key)

        if not hasattr(response, "autorizaciones"):
            raise SriAuthorizationProtocolError(
                "La respuesta no contiene el contenedor de autorizaciones."
            )
        items = tuple(cls._children(getattr(response, "autorizaciones"), "autorizacion"))
        count = getattr(response, "numeroComprobantes", None)
        if count is not None:
            if not isinstance(count, str) or not count.isdigit():
                raise SriAuthorizationProtocolError(
                    "numeroComprobantes no es un entero válido."
                )
            expected = int(count)
            if expected != len(items):
                raise SriAuthorizationProtocolError(
                    "numeroComprobantes no coincide con autorizaciones."
                )

        if not items:
            return SriAuthorizationResult(
                outcome=SriAuthorizationAttemptStatus.PENDING,
                access_key_consulted=key,
                environment=requested_environment,
                messages=(),
            )

        normalized = [cls._normalize_item(item, requested_environment) for item in items]
        outcomes = {item["outcome"] for item in normalized}
        if len(outcomes) != 1:
            raise SriAuthorizationProtocolError(
                "La respuesta contiene estados de autorización contradictorios."
            )
        outcome = normalized[0]["outcome"]
        if any(item["evidence"] != normalized[0]["evidence"] for item in normalized[1:]):
            raise SriAuthorizationProtocolError(
                "Las autorizaciones múltiples contienen evidencia contradictoria."
            )
        messages = tuple(message for item in normalized for message in item["messages"])
        first = normalized[0]
        return SriAuthorizationResult(
            outcome=outcome,
            access_key_consulted=key,
            authorization_number=first["authorization_number"],
            authorization_date=first["authorization_date"],
            environment=first["environment"],
            authorized_xml=first["authorized_xml"],
            messages=messages,
        )

    @classmethod
    def _normalize_item(cls, item, requested_environment):
        if item is None or not hasattr(item, "estado"):
            raise SriAuthorizationProtocolError(
                "Una autorización no contiene estado."
            )
        state = getattr(item, "estado", None)
        if not isinstance(state, str):
            raise SriAuthorizationProtocolError("Estado de autorización inválido.")
        state = state.strip()
        states = {
            "AUT": SriAuthorizationAttemptStatus.AUTHORIZED,
            "AUTORIZADO": SriAuthorizationAttemptStatus.AUTHORIZED,
            "NAT": SriAuthorizationAttemptStatus.NOT_AUTHORIZED,
            "NO AUTORIZADO": SriAuthorizationAttemptStatus.NOT_AUTHORIZED,
            "RECHAZADO": SriAuthorizationAttemptStatus.NOT_AUTHORIZED,
            "PPR": SriAuthorizationAttemptStatus.PENDING,
            "EN PROCESAMIENTO": SriAuthorizationAttemptStatus.PENDING,
        }
        if state not in states:
            raise SriAuthorizationProtocolError(f"Estado desconocido: {state!r}.")
        outcome = states[state]
        raw_environment = getattr(item, "ambiente", None)
        environment = cls._normalize_environment(raw_environment)
        if environment != requested_environment:
            raise SriAuthorizationProtocolError(
                "El ambiente retornado no coincide con el solicitado."
            )
        messages = tuple(cls._messages(item))
        if outcome == SriAuthorizationAttemptStatus.PENDING:
            return {
                "outcome": outcome, "authorization_number": None,
                "authorization_date": None, "environment": environment,
                "authorized_xml": None, "messages": messages,
                "evidence": (None, None, environment, None),
            }
        number = getattr(item, "numeroAutorizacion", None)
        date = getattr(item, "fechaAutorizacion", None)
        comprobante = getattr(item, "comprobante", None)
        if outcome == SriAuthorizationAttemptStatus.AUTHORIZED:
            if not isinstance(number, str) or not number:
                raise SriAuthorizationProtocolError("Falta numeroAutorizacion.")
            date = cls._normalize_date(date)
            if not isinstance(comprobante, str) or not comprobante:
                raise SriAuthorizationProtocolError("Falta comprobante autorizado.")
            xml = comprobante
        else:
            xml = None
            date = cls._optional_date(date)
            if number is not None and not isinstance(number, str):
                raise SriAuthorizationProtocolError("numeroAutorizacion inválido.")
        evidence = (number, date, environment, comprobante if outcome == SriAuthorizationAttemptStatus.NOT_AUTHORIZED else xml)
        return {
            "outcome": outcome, "authorization_number": number,
            "authorization_date": date, "environment": environment,
            "authorized_xml": xml, "messages": messages,
            "evidence": evidence,
        }

    @staticmethod
    def _validate_access_key(key):
        if not isinstance(key, str) or len(key) != 49 or not key.isdigit():
            raise SriAuthorizationProtocolError("claveAccesoConsultada inválida.")

    @staticmethod
    def _normalize_environment(value):
        if value == "PRUEBAS":
            return SriEnvironment.TEST
        if value == "PRODUCCIÓN":
            return SriEnvironment.PRODUCTION
        raise SriAuthorizationProtocolError("Ambiente de autorización inválido.")

    @staticmethod
    def _normalize_date(value):
        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise SriAuthorizationProtocolError("La fecha no tiene zona horaria.")
            return value
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise SriAuthorizationProtocolError("Fecha de autorización inválida.") from exc
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise SriAuthorizationProtocolError("La fecha no tiene zona horaria.")
            return parsed
        raise SriAuthorizationProtocolError("Falta fecha de autorización.")

    @classmethod
    def _optional_date(cls, value):
        if value is None:
            return None
        return cls._normalize_date(value)

    @classmethod
    def _messages(cls, item):
        container = getattr(item, "mensajes", None)
        for message in cls._children(container, "mensaje"):
            yield SriAuthorizationMessageData(
                message_type=getattr(message, "tipo", None),
                identifier=getattr(message, "identificador", None),
                message=getattr(message, "mensaje", None) or "",
                additional_information=getattr(message, "informacionAdicional", None),
            )

    @staticmethod
    def _children(container, name):
        if container is None:
            return ()
        if isinstance(container, (list, tuple)):
            return tuple(container)
        child = getattr(container, name, None)
        if child is None:
            return ()
        if isinstance(child, (list, tuple)):
            return tuple(child)
        if isinstance(child, Iterable) and not isinstance(child, (str, bytes)):
            return tuple(child)
        return (child,)
