from importlib import import_module
from unittest import TestCase
from unittest.mock import Mock, patch

from django.db import connection
from django.test import TransactionTestCase


ENTRYPOINT_MODULE = "sri.services.electronic_document_reception_entrypoint"


def load_entrypoint(test_case):
    try:
        module = import_module(ENTRYPOINT_MODULE)
    except ModuleNotFoundError as error:
        if error.name != ENTRYPOINT_MODULE:
            raise
        test_case.fail(
            "C-14D-A reception composition entrypoint is not implemented."
        )
    function = getattr(module, "submit_electronic_document", None)
    test_case.assertTrue(
        callable(function),
        "C-14D-A submit_electronic_document is not implemented.",
    )
    return module, function


class ReceptionEntrypointREDTests(TestCase):
    def setUp(self):
        self.document = object()
        self.adapter = object()
        self.client_factory = Mock(name="client_factory")

    def test_public_module_and_function_exist(self):
        module, function = load_entrypoint(self)

        self.assertEqual(module.__name__, ENTRYPOINT_MODULE)
        self.assertEqual(function.__name__, "submit_electronic_document")

    def test_explicit_adapter_is_delegated_without_default_construction(self):
        module, submit = load_entrypoint(self)
        with (
            patch.object(module, "SriReceptionSoapAdapter") as adapter_class,
            patch.object(module, "ElectronicDocumentReceptionService") as service,
        ):
            submit(
                electronic_document=self.document,
                adapter=self.adapter,
            )

        adapter_class.assert_not_called()
        self.client_factory.assert_not_called()
        service.submit.assert_called_once_with(
            electronic_document=self.document,
            adapter=self.adapter,
        )

    def test_missing_adapter_constructs_default_adapter_once(self):
        module, submit = load_entrypoint(self)
        with (
            patch.object(module, "SriReceptionSoapAdapter") as adapter_class,
            patch.object(module, "ElectronicDocumentReceptionService") as service,
        ):
            resolved_adapter = adapter_class.return_value
            submit(electronic_document=self.document)

        adapter_class.assert_called_once_with(client_factory=None)
        service.submit.assert_called_once_with(
            electronic_document=self.document,
            adapter=resolved_adapter,
        )

    def test_client_factory_is_forwarded_without_invocation(self):
        module, submit = load_entrypoint(self)
        with (
            patch.object(module, "SriReceptionSoapAdapter") as adapter_class,
            patch.object(module, "ElectronicDocumentReceptionService") as service,
        ):
            resolved_adapter = adapter_class.return_value
            submit(
                electronic_document=self.document,
                client_factory=self.client_factory,
            )

        adapter_class.assert_called_once_with(
            client_factory=self.client_factory,
        )
        self.client_factory.assert_not_called()
        service.submit.assert_called_once_with(
            electronic_document=self.document,
            adapter=resolved_adapter,
        )

    def test_explicit_adapter_wins_when_factory_is_also_supplied(self):
        module, submit = load_entrypoint(self)
        with (
            patch.object(module, "SriReceptionSoapAdapter") as adapter_class,
            patch.object(module, "ElectronicDocumentReceptionService") as service,
        ):
            submit(
                electronic_document=self.document,
                adapter=self.adapter,
                client_factory=self.client_factory,
            )

        adapter_class.assert_not_called()
        self.client_factory.assert_not_called()
        service.submit.assert_called_once_with(
            electronic_document=self.document,
            adapter=self.adapter,
        )

    def test_exact_document_identity_and_service_return_are_preserved(self):
        module, submit = load_entrypoint(self)
        service_result = object()
        with (
            patch.object(module, "SriReceptionSoapAdapter") as adapter_class,
            patch.object(module, "ElectronicDocumentReceptionService") as service,
        ):
            service.submit.return_value = service_result
            result = submit(
                electronic_document=self.document,
                adapter=self.adapter,
            )

        self.assertIs(result, service_result)
        service.submit.assert_called_once_with(
            electronic_document=self.document,
            adapter=self.adapter,
        )
        adapter_class.assert_not_called()

    def test_service_exceptions_propagate_unchanged(self):
        module, submit = load_entrypoint(self)
        for error in (ValueError("preflight"), RuntimeError("transport")):
            with self.subTest(error_type=type(error).__name__):
                with (
                    patch.object(module, "SriReceptionSoapAdapter"),
                    patch.object(module, "ElectronicDocumentReceptionService") as service,
                ):
                    service.submit.side_effect = error
                    with self.assertRaises(type(error)) as raised:
                        submit(
                            electronic_document=self.document,
                            adapter=self.adapter,
                        )

                self.assertIs(raised.exception, error)
                service.submit.assert_called_once_with(
                    electronic_document=self.document,
                    adapter=self.adapter,
                )

    def test_document_state_is_not_read_or_prechecked(self):
        module, submit = load_entrypoint(self)

        class OpaqueDocument:
            def __getattribute__(self, name):
                raise AssertionError(f"Entrypoint inspected document.{name}")

        document = OpaqueDocument()
        with (
            patch.object(module, "SriReceptionSoapAdapter"),
            patch.object(module, "ElectronicDocumentReceptionService") as service,
        ):
            submit(electronic_document=document, adapter=self.adapter)

        service.submit.assert_called_once_with(
            electronic_document=document,
            adapter=self.adapter,
        )

    def test_one_entrypoint_call_makes_exactly_one_service_call(self):
        module, submit = load_entrypoint(self)
        with (
            patch.object(module, "SriReceptionSoapAdapter"),
            patch.object(module, "ElectronicDocumentReceptionService") as service,
        ):
            submit(electronic_document=self.document, adapter=self.adapter)

        self.assertEqual(service.submit.call_count, 1)


class ReceptionEntrypointTransactionREDTests(TransactionTestCase):
    def test_service_seam_is_outside_outer_transaction(self):
        module, submit = load_entrypoint(self)
        observed = []

        def observe(**kwargs):
            observed.append(connection.in_atomic_block)
            return kwargs["electronic_document"]

        with (
            patch.object(module, "SriReceptionSoapAdapter"),
            patch.object(module, "ElectronicDocumentReceptionService") as service,
        ):
            service.submit.side_effect = observe
            document = object()
            result = submit(electronic_document=document, adapter=object())

        self.assertIs(result, document)
        self.assertEqual(observed, [False])
        service.submit.assert_called_once()
