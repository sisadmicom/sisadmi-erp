from django.apps import apps
from django.db import connection
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase

from core.models import DocumentType


class DocumentTypeInitializationTests(TestCase):
    def test_explicit_load_restores_missing_catalog_idempotently(self):
        from core.services.document_type_catalog import ensure_document_types
        DocumentType.objects.all().delete()
        self.assertEqual(ensure_document_types(using="default", apps=apps), 7)
        before = list(DocumentType.objects.order_by("code").values())
        self.assertEqual(ensure_document_types(using="default", apps=apps), 0)
        self.assertEqual(list(DocumentType.objects.order_by("code").values()), before)
        self.assertEqual(DocumentType.objects.get(code="SALES_INVOICE").line_behavior, "COMMERCIAL")

    def test_loading_never_overwrites_an_existing_catalog_entry(self):
        from core.services.document_type_catalog import ensure_document_types
        DocumentType.objects.filter(code="SALES_INVOICE").update(name="Configured name", is_active=False)
        ensure_document_types(using="default", apps=apps)
        value = DocumentType.objects.get(code="SALES_INVOICE")
        self.assertEqual(value.name, "Configured name")
        self.assertFalse(value.is_active)


class DocumentTypeFlushTests(TransactionTestCase):
    def test_flush_repopulates_master_catalog_without_replaying_migrations(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT app, name FROM django_migrations ORDER BY app,name")
            before = cursor.fetchall()
        call_command("flush", interactive=False, verbosity=0)
        self.assertEqual(DocumentType.objects.count(), 7)
        with connection.cursor() as cursor:
            cursor.execute("SELECT app, name FROM django_migrations ORDER BY app,name")
            self.assertEqual(cursor.fetchall(), before)
