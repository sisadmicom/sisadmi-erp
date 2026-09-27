from types import SimpleNamespace
from unittest import TestCase

from core.constants.sri import SriEnvironment
from sri.constants.reception_attempt_status import SriReceptionAttemptStatus
from sri.tests.reception_soap_test_support import (
    CONNECT_TIMEOUT,
    OPERATION_TIMEOUT,
    PRODUCTION_WSDL,
    TEST_WSDL,
    FakeClientFactory,
    FakeSoapOperation,
    assert_single_xml_argument,
    comprobante,
    message,
    production_adapter,
    production_exceptions,
    response,
)


class SriReceptionSoapAdapterREDTests(TestCase):
    def _run(self, *, xml, environment, response=None, error=None):
        operation = FakeSoapOperation(response=response, error=error)
        factory = FakeClientFactory(operation)
        adapter = production_adapter(factory)
        result = adapter.receive(xml=xml, environment=environment)
        return result, factory, operation

    def test_test_environment_resolves_official_reception_wsdl(self):
        result, factory, operation = self._run(
            xml="<factura/>", environment=SriEnvironment.TEST,
            response=response(state="RECIBIDA"),
        )
        self.assertEqual(factory.calls[0]["wsdl"], TEST_WSDL)
        self.assertEqual(operation.call_count, 1)

    def test_production_environment_resolves_official_reception_wsdl(self):
        result, factory, operation = self._run(
            xml="<factura/>", environment=SriEnvironment.PRODUCTION,
            response=response(state="RECIBIDA"),
        )
        self.assertEqual(factory.calls[0]["wsdl"], PRODUCTION_WSDL)

    def test_unknown_environment_fails_before_client_creation(self):
        operation = FakeSoapOperation(response=response(state="RECIBIDA"))
        factory = FakeClientFactory(operation)
        adapter = production_adapter(factory)
        with self.assertRaises(ValueError):
            adapter.receive(xml="<factura/>", environment="9")
        self.assertEqual(factory.call_count, 0)
        self.assertEqual(operation.call_count, 0)

    def test_string_xml_is_encoded_utf8_once(self):
        xml = "<factura>áé—</factura>"
        _, factory, operation = self._run(
            xml=xml, environment=SriEnvironment.TEST,
            response=response(state="RECIBIDA"),
        )
        assert_single_xml_argument(self, operation, xml.encode("utf-8"))

    def test_bytes_xml_are_preserved_exactly(self):
        xml = b"<factura>\x00signed</factura>"
        _, _, operation = self._run(
            xml=xml, environment=SriEnvironment.TEST,
            response=response(state="RECIBIDA"),
        )
        assert_single_xml_argument(self, operation, xml)

    def test_adapter_does_not_pre_base64_encode_xml(self):
        xml = b"<factura>raw-bytes</factura>"
        _, _, operation = self._run(
            xml=xml, environment=SriEnvironment.TEST,
            response=response(state="RECIBIDA"),
        )
        self.assertEqual(operation.arguments[0], xml)
        self.assertNotEqual(operation.arguments[0], b"PGZhY3R1cmE+cmF3LWJ5dGVzPC9mYWN0dXJhPg==")

    def test_recibida_normalizes_to_received_with_empty_messages(self):
        result, _, _ = self._run(
            xml="<factura/>", environment=SriEnvironment.TEST,
            response=response(state="RECIBIDA", comprobantes=None),
        )
        self.assertEqual(result.outcome, SriReceptionAttemptStatus.RECEIVED)
        self.assertEqual(result.messages, ())

    def test_devuelta_normalizes_all_messages_from_all_comprobantes(self):
        first = comprobante(
            message(tipo="ERROR", identificador="35", mensaje="Uno", informacion="A"),
            message(tipo="ERROR", identificador="36", mensaje="Dos", informacion="B"),
        )
        second = comprobante(
            message(tipo="ERROR", identificador="48", mensaje="Tres", informacion="C"),
            message(tipo="ERROR", identificador="50", mensaje="Cuatro", informacion="D"),
        )
        result, _, _ = self._run(
            xml="<factura/>", environment=SriEnvironment.TEST,
            response=response(state="DEVUELTA", comprobantes=[first, second]),
        )
        self.assertEqual(result.outcome, SriReceptionAttemptStatus.REJECTED)
        self.assertEqual(len(result.messages), 4)
        self.assertEqual(
            {(m.message_type, m.identifier, m.message, m.additional_information) for m in result.messages},
            {("ERROR", "35", "Uno", "A"), ("ERROR", "36", "Dos", "B"),
             ("ERROR", "48", "Tres", "C"), ("ERROR", "50", "Cuatro", "D")},
        )

    def test_optional_message_fields_follow_closed_policy(self):
        result, _, _ = self._run(
            xml="<factura/>", environment=SriEnvironment.TEST,
            response=response(state="DEVUELTA", comprobantes=[comprobante(message())]),
        )
        item = result.messages[0]
        self.assertIsNone(item.message_type)
        self.assertIsNone(item.identifier)
        self.assertEqual(item.message, "")
        self.assertIsNone(item.additional_information)

    def test_unknown_external_state_raises_protocol_error(self):
        ProtocolError, _ = production_exceptions()
        operation = FakeSoapOperation(response=response(state="PROCESANDO"))
        factory = FakeClientFactory(operation)
        with self.assertRaises(ProtocolError):
            production_adapter(factory).receive(xml="<factura/>", environment="1")

    def test_missing_estado_raises_protocol_error(self):
        ProtocolError, _ = production_exceptions()
        operation = FakeSoapOperation(response=response(omit_state=True))
        factory = FakeClientFactory(operation)
        with self.assertRaises(ProtocolError):
            production_adapter(factory).receive(xml="<factura/>", environment="1")

    def test_soap_fault_raises_ambiguous_adapter_error(self):
        _, TransportError = production_exceptions()
        operation = FakeSoapOperation(error=RuntimeError("SOAP Fault"))
        factory = FakeClientFactory(operation)
        with self.assertRaises(TransportError):
            production_adapter(factory).receive(xml="<factura/>", environment="1")

    def test_read_timeout_raises_ambiguous_transport_error(self):
        _, TransportError = production_exceptions()
        operation = FakeSoapOperation(error=TimeoutError("read timeout"))
        factory = FakeClientFactory(operation)
        with self.assertRaises(TransportError):
            production_adapter(factory).receive(xml="<factura/>", environment="1")

    def test_connection_failure_raises_ambiguous_transport_error(self):
        _, TransportError = production_exceptions()
        operation = FakeSoapOperation(error=ConnectionError("connection refused"))
        factory = FakeClientFactory(operation)
        with self.assertRaises(TransportError):
            production_adapter(factory).receive(xml="<factura/>", environment="1")

    def test_tls_verification_is_enabled(self):
        _, factory, _ = self._run(
            xml="<factura/>", environment=SriEnvironment.TEST,
            response=response(state="RECIBIDA"),
        )
        self.assertIs(factory.calls[0]["verify"], True)

    def test_transport_uses_configured_timeouts(self):
        _, factory, _ = self._run(
            xml="<factura/>", environment=SriEnvironment.TEST,
            response=response(state="RECIBIDA"),
        )
        self.assertEqual(factory.calls[0]["connect_timeout"], CONNECT_TIMEOUT)
        self.assertEqual(factory.calls[0]["operation_timeout"], OPERATION_TIMEOUT)

    def test_transport_failure_is_not_retried(self):
        operation = FakeSoapOperation(error=TimeoutError("read timeout"))
        factory = FakeClientFactory(operation)
        _, TransportError = production_exceptions()
        with self.assertRaises(TransportError):
            production_adapter(factory).receive(xml="<factura/>", environment="1")
        self.assertEqual(operation.call_count, 1)

    def test_adapter_never_calls_authorization_service(self):
        result, factory, _ = self._run(
            xml="<factura/>", environment=SriEnvironment.TEST,
            response=response(state="RECIBIDA"),
        )
        self.assertEqual(factory.client.authorization_call_count, 0)
        self.assertEqual(result.outcome, SriReceptionAttemptStatus.RECEIVED)

    def test_adapter_does_not_modify_xml(self):
        xml = "  <factura xmlns='urn:test'>é<Signature> x </Signature>\n</factura>  "
        _, _, operation = self._run(
            xml=xml, environment=SriEnvironment.TEST,
            response=response(state="RECIBIDA"),
        )
        self.assertEqual(operation.arguments[0], xml.encode("utf-8"))

    def test_devuelta_error_70_follows_rejected_policy(self):
        result, _, operation = self._run(
            xml="<factura/>", environment=SriEnvironment.TEST,
            response=response(
                state="DEVUELTA",
                comprobantes=[comprobante(message(
                    tipo="ERROR", identificador="70",
                    mensaje="CLAVE DE ACCESO EN PROCESAMIENTO",
                    informacion=None,
                ))],
            ),
        )
        self.assertEqual(result.outcome, SriReceptionAttemptStatus.REJECTED)
        self.assertEqual(result.messages[0].identifier, "70")
        self.assertEqual(operation.call_count, 1)

    def test_invalid_xml_type_fails_before_client_creation(self):
        operation = FakeSoapOperation(response=response(state="RECIBIDA"))
        factory = FakeClientFactory(operation)
        with self.assertRaises((TypeError, ValueError)):
            production_adapter(factory).receive(xml=object(), environment="1")
        self.assertEqual(factory.call_count, 0)
        self.assertEqual(operation.call_count, 0)
