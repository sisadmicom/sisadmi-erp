from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase

from requests.exceptions import ConnectionError, SSLError
from zeep.exceptions import Fault

from core.constants.sri import SriEnvironment
from sri.constants.authorization_attempt_status import SriAuthorizationAttemptStatus
from sri.services.electronic_document_authorization_service import (
    SriAuthorizationProtocolError,
    SriAuthorizationTransportError,
)
from sri.tests.authorization_soap_test_support import (
    ACCESS_KEY, AUTHORIZED_XML, CONNECT_TIMEOUT, OPERATION_TIMEOUT,
    PRODUCTION_WSDL, TEST_WSDL, FakeClientFactory, FakeSoapOperation,
    authorization, message, production_adapter, response,
)


class SriAuthorizationSoapAdapterREDTests(TestCase):
    def run_adapter(self, *, environment=SriEnvironment.TEST, response_obj=None, error=None):
        operation = FakeSoapOperation(response=response_obj, error=error)
        factory = FakeClientFactory(operation=operation)
        result = production_adapter(factory).query_authorization(
            access_key=ACCESS_KEY, environment=environment,
        )
        return result, factory, operation

    def test_test_environment_uses_official_authorization_wsdl(self):
        result, factory, _ = self.run_adapter(response_obj=response())
        self.assertEqual(factory.calls[0]["wsdl"], TEST_WSDL)

    def test_production_environment_uses_official_authorization_wsdl(self):
        _, factory, _ = self.run_adapter(environment=SriEnvironment.PRODUCTION, response_obj=response(authorizations=[authorization(environment="PRODUCCIÓN")]))
        self.assertEqual(factory.calls[0]["wsdl"], PRODUCTION_WSDL)

    def test_calls_autorizacion_comprobante_with_exact_access_key(self):
        _, _, operation = self.run_adapter(response_obj=response())
        self.assertEqual(operation.call_count, 1)
        self.assertEqual(operation.arguments, [ACCESS_KEY])

    def test_authorized_normalizes_complete_evidence(self):
        item = authorization(messages=(message(tipo="INFO", identificador="60", mensaje="ok", informacion="x"),))
        result, _, _ = self.run_adapter(response_obj=response(authorizations=[item]))
        self.assertEqual(result.outcome, SriAuthorizationAttemptStatus.AUTHORIZED)
        self.assertEqual(result.access_key_consulted, ACCESS_KEY)
        self.assertEqual(result.authorization_number, "AUTH-001")
        self.assertEqual(result.authorization_date, item.fechaAutorizacion)
        self.assertEqual(result.environment, SriEnvironment.TEST)
        self.assertEqual(result.authorized_xml, AUTHORIZED_XML)
        self.assertEqual(result.messages[0].identifier, "60")

    def test_aut_state_normalizes_authorized(self):
        result, _, _ = self.run_adapter(response_obj=response(authorizations=[authorization(state="AUT")]))
        self.assertEqual(result.outcome, SriAuthorizationAttemptStatus.AUTHORIZED)

    def test_not_authorized_values_normalize(self):
        for state in ("NAT", "NO AUTORIZADO", "RECHAZADO"):
            with self.subTest(state=state):
                result, _, _ = self.run_adapter(response_obj=response(authorizations=[authorization(state=state, number=None, date=None, comprobante=None)]))
                self.assertEqual(result.outcome, SriAuthorizationAttemptStatus.NOT_AUTHORIZED)
                self.assertIsNone(result.authorization_number)
                self.assertIsNone(result.authorized_xml)

    def test_pending_values_normalize(self):
        for state in ("PPR", "EN PROCESAMIENTO"):
            with self.subTest(state=state):
                result, _, _ = self.run_adapter(response_obj=response(authorizations=[authorization(state=state, number=None, date=None, comprobante=None)]))
                self.assertEqual(result.outcome, SriAuthorizationAttemptStatus.PENDING)
                self.assertIsNone(result.authorization_number)
                self.assertIsNone(result.authorization_date)
                self.assertIsNone(result.authorized_xml)

    def test_state_normalization_only_trims_outer_whitespace(self):
        result, _, _ = self.run_adapter(response_obj=response(authorizations=[authorization(state="  AUTORIZADO  ")]))
        self.assertEqual(result.outcome, SriAuthorizationAttemptStatus.AUTHORIZED)
        for state in ("AUTORIZ", "AUTHORIZED", "ERROR", "OK"):
            with self.subTest(state=state):
                with self.assertRaises(SriAuthorizationProtocolError):
                    self.run_adapter(response_obj=response(authorizations=[authorization(state=state)]))

    def test_zero_authorizations_is_pending(self):
        for count, items in (("0", None), ("0", [])):
            with self.subTest(count=count):
                result, _, _ = self.run_adapter(response_obj=response(count=count, authorizations=items))
                self.assertEqual(result.outcome, SriAuthorizationAttemptStatus.PENDING)

    def test_missing_count_uses_authorization_cardinality(self):
        result, _, _ = self.run_adapter(response_obj=response(count=None, authorizations=[authorization()]))
        self.assertEqual(result.outcome, SriAuthorizationAttemptStatus.AUTHORIZED)
        result, _, _ = self.run_adapter(response_obj=response(count=None, authorizations=[]))
        self.assertEqual(result.outcome, SriAuthorizationAttemptStatus.PENDING)

    def test_invalid_numero_comprobantes_is_protocol_error(self):
        for count in ("abc", "-1", "1.0", ""):
            with self.subTest(count=count):
                with self.assertRaises(SriAuthorizationProtocolError):
                    self.run_adapter(response_obj=response(count=count, authorizations=[]))

    def test_numero_comprobantes_must_match_authorization_count(self):
        with self.assertRaises(SriAuthorizationProtocolError):
            self.run_adapter(response_obj=response(count="2", authorizations=[authorization()]))

    def test_returns_clave_acceso_consultada_exactly(self):
        result, _, _ = self.run_adapter(response_obj=response(key=ACCESS_KEY))
        self.assertEqual(result.access_key_consulted, ACCESS_KEY)

    def test_invalid_access_key_shapes_are_protocol_errors(self):
        for key in (None, "", ACCESS_KEY[:-1], ACCESS_KEY + "0"):
            with self.subTest(key=key):
                with self.assertRaises(SriAuthorizationProtocolError):
                    self.run_adapter(response_obj=response(key=key))

    def test_authorized_requires_authorization_number(self):
        with self.assertRaises(SriAuthorizationProtocolError):
            self.run_adapter(response_obj=response(authorizations=[authorization(number=None)]))

    def test_authorized_accepts_aware_datetime(self):
        date = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
        result, _, _ = self.run_adapter(response_obj=response(authorizations=[authorization(date=date)]))
        self.assertEqual(result.authorization_date, date)

    def test_authorized_parses_iso_datetime_with_offset(self):
        item = authorization()
        item.fechaAutorizacion = "2025-01-02T03:04:05-05:00"
        result, _, _ = self.run_adapter(response_obj=response(authorizations=[item]))
        self.assertIsNotNone(result.authorization_date.tzinfo)

    def test_authorized_rejects_naive_datetime(self):
        item = authorization(date=datetime(2025, 1, 2, 3, 4))
        with self.assertRaises(SriAuthorizationProtocolError):
            self.run_adapter(response_obj=response(authorizations=[item]))

    def test_authorized_rejects_invalid_date(self):
        for date in (None, "invalid"):
            with self.subTest(date=date):
                item = authorization(date=date)
                with self.assertRaises(SriAuthorizationProtocolError):
                    self.run_adapter(response_obj=response(authorizations=[item]))

    def test_environment_normalization(self):
        result, _, _ = self.run_adapter(response_obj=response(authorizations=[authorization(environment="PRUEBAS")]))
        self.assertEqual(result.environment, SriEnvironment.TEST)
        result, _, _ = self.run_adapter(environment=SriEnvironment.PRODUCTION, response_obj=response(authorizations=[authorization(environment="PRODUCCIÓN")]))
        self.assertEqual(result.environment, SriEnvironment.PRODUCTION)

    def test_unknown_response_environment_is_protocol_error(self):
        with self.assertRaises(SriAuthorizationProtocolError):
            self.run_adapter(response_obj=response(authorizations=[authorization(environment="DESARROLLO")]))

    def test_request_response_environment_mismatch_is_protocol_error(self):
        with self.assertRaises(SriAuthorizationProtocolError):
            self.run_adapter(response_obj=response(authorizations=[authorization(environment="PRODUCCIÓN")]))

    def test_authorized_xml_is_preserved_exactly(self):
        result, _, _ = self.run_adapter(response_obj=response(authorizations=[authorization()]))
        self.assertEqual(result.authorized_xml, AUTHORIZED_XML)

    def test_authorized_requires_returned_xml(self):
        with self.assertRaises(SriAuthorizationProtocolError):
            self.run_adapter(response_obj=response(authorizations=[authorization(comprobante=None)]))

    def test_not_authorized_does_not_return_authorized_xml(self):
        result, _, _ = self.run_adapter(response_obj=response(authorizations=[authorization(state="NAT")]))
        self.assertIsNone(result.authorized_xml)

    def test_messages_preserve_order_and_fields(self):
        msgs = (message(tipo="E", identificador="1", mensaje="uno", informacion="a"), message(tipo="W", identificador="2", mensaje="dos", informacion="b"), message(tipo=None, identificador=None, mensaje=None, informacion=None))
        result, _, _ = self.run_adapter(response_obj=response(authorizations=[authorization(messages=msgs)]))
        self.assertEqual([m.identifier for m in result.messages], ["1", "2", None])
        self.assertEqual(result.messages[2].message, "")

    def test_duplicate_messages_are_preserved(self):
        msg = message(tipo="E", identificador="1", mensaje="dup", informacion=None)
        result, _, _ = self.run_adapter(response_obj=response(authorizations=[authorization(messages=(msg, msg))]))
        self.assertEqual(len(result.messages), 2)

    def test_multiple_authorized_equivalent_aggregates_messages(self):
        a = authorization(messages=(message(identificador="1", mensaje="a"),))
        b = authorization(messages=(message(identificador="2", mensaje="b"),))
        result, _, _ = self.run_adapter(response_obj=response(count="2", authorizations=[a, b]))
        self.assertEqual(result.outcome, SriAuthorizationAttemptStatus.AUTHORIZED)
        self.assertEqual([m.identifier for m in result.messages], ["1", "2"])

    def test_multiple_authorized_conflicting_is_protocol_error(self):
        for field, value in (("number", "OTHER"), ("date", datetime(2024, 1, 1, tzinfo=timezone.utc)), ("environment", "PRODUCCIÓN"), ("comprobante", "<other/>")):
            with self.subTest(field=field):
                a = authorization()
                kwargs = {"number": a.numeroAutorizacion, "date": a.fechaAutorizacion, "environment": a.ambiente, "comprobante": a.comprobante}
                kwargs[field] = value
                b = authorization(**kwargs)
                with self.assertRaises(SriAuthorizationProtocolError):
                    self.run_adapter(response_obj=response(count="2", authorizations=[a, b]))

    def test_multiple_not_authorized_equivalent_and_conflicting(self):
        a = authorization(state="NAT", number=None, date=None, comprobante=None)
        b = authorization(state="NAT", number=None, date=None, comprobante=None)
        result, _, _ = self.run_adapter(response_obj=response(count="2", authorizations=[a, b]))
        self.assertEqual(result.outcome, SriAuthorizationAttemptStatus.NOT_AUTHORIZED)
        b.numeroAutorizacion = "OTHER"
        with self.assertRaises(SriAuthorizationProtocolError):
            self.run_adapter(response_obj=response(count="2", authorizations=[a, b]))

    def test_pending_pending_is_pending(self):
        items = [authorization(state="PPR", number=None, date=None, comprobante=None), authorization(state="PPR", number=None, date=None, comprobante=None)]
        result, _, _ = self.run_adapter(response_obj=response(count="2", authorizations=items))
        self.assertEqual(result.outcome, SriAuthorizationAttemptStatus.PENDING)

    def test_mixed_states_are_protocol_errors(self):
        for states in (("PPR", "AUTORIZADO"), ("PPR", "NAT"), ("AUTORIZADO", "NAT")):
            with self.subTest(states=states):
                with self.assertRaises(SriAuthorizationProtocolError):
                    self.run_adapter(response_obj=response(count="2", authorizations=[authorization(state=states[0]), authorization(state=states[1])]))

    def test_first_valid_second_conflicting_is_not_first_only(self):
        with self.assertRaises(SriAuthorizationProtocolError):
            self.run_adapter(response_obj=response(count="2", authorizations=[authorization(), authorization(state="NAT", number=None, date=None, comprobante=None)]))

    def test_malformed_responses_are_protocol_errors(self):
        for malformed in (None, SimpleNamespace(claveAccesoConsultada=ACCESS_KEY, numeroComprobantes="0"), response(omit_key=True)):
            with self.subTest(malformed=malformed):
                with self.assertRaises(SriAuthorizationProtocolError):
                    self.run_adapter(response_obj=malformed)

    def test_transport_errors_are_ambiguous_and_not_retried(self):
        for error in (TimeoutError("timeout"), ConnectionError("connection"), SSLError("tls"), Fault("fault")):
            with self.subTest(error=type(error).__name__):
                operation = FakeSoapOperation(error=error)
                factory = FakeClientFactory(operation=operation)
                with self.assertRaises(SriAuthorizationTransportError) as raised:
                    production_adapter(factory).query_authorization(access_key=ACCESS_KEY, environment=SriEnvironment.TEST)
                self.assertIs(raised.exception.__cause__, error)
                self.assertEqual(operation.call_count, 1)

    def test_client_creation_failure_is_transport_error(self):
        factory = FakeClientFactory(error=ConnectionError("wsdl"))
        with self.assertRaises(SriAuthorizationTransportError):
            production_adapter(factory).query_authorization(access_key=ACCESS_KEY, environment=SriEnvironment.TEST)

    def test_invalid_environment_fails_before_factory(self):
        factory = FakeClientFactory(operation=FakeSoapOperation(response=response()))
        with self.assertRaises(ValueError):
            production_adapter(factory).query_authorization(access_key=ACCESS_KEY, environment="9")
        self.assertEqual(factory.call_count, 0)

    def test_factory_settings_and_one_call(self):
        _, factory, operation = self.run_adapter(response_obj=response())
        self.assertIs(factory.calls[0]["verify"], True)
        self.assertEqual(factory.calls[0]["connect_timeout"], CONNECT_TIMEOUT)
        self.assertEqual(factory.calls[0]["operation_timeout"], OPERATION_TIMEOUT)
        self.assertEqual(operation.call_count, 1)

    def test_adapter_does_not_persist_or_call_reception(self):
        result, factory, _ = self.run_adapter(response_obj=response())
        self.assertEqual(factory.client.reception_call_count, 0)
        self.assertEqual(result.outcome, SriAuthorizationAttemptStatus.AUTHORIZED)
