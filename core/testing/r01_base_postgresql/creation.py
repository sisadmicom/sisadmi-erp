"""Isolated lifecycle and exact, protected-row-aware Django snapshot restoration."""
import json
import math
import re

from django.apps import apps
from django.db import models, transaction
from django.db.models import Q
from django.utils.timezone import is_aware

from core.testing.r01_base_json import Deserializer

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.backends.postgresql.creation import DatabaseCreation as PostgreSQLCreation

from core.testing.r01_base_guard import (
    DATABASE, reject, require_execution, validate_connections, validate_database,
    verify_identity,
)


class DatabaseCreation(PostgreSQLCreation):
    def serialize_db_to_string(self):
        # Use Django's exact model selection, routing, reads and JSON serializer.
        snapshot = super().serialize_db_to_string()
        return self._order_identification_catalog(snapshot)

    @staticmethod
    def _order_identification_catalog(snapshot):
        """Stable movement of catalog rows only; never query or rebuild data."""
        def invalid():
            # No snapshot values in errors: they may contain personal data.
            raise ImproperlyConfigured("R-01 Base rejected an unexpected Django snapshot format.")

        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    invalid()
                result[key] = value
            return result

        def finite_float(value):
            result = float(value)
            if not math.isfinite(result):
                invalid()
            return result

        def invalid_constant(value):
            invalid()

        if not isinstance(snapshot, str):
            invalid()
        try:
            rows = json.loads(snapshot, object_pairs_hook=unique_object,
                              parse_float=finite_float, parse_constant=invalid_constant)
        except (ValueError, TypeError, RecursionError):
            invalid()
        if not isinstance(rows, list):
            invalid()
        for row in rows:
            if (not isinstance(row, dict) or set(row) != {"model", "pk", "fields"}
                    or not isinstance(row["model"], str) or row["model"].count(".") != 1
                    or not all(row["model"].split(".")) or not isinstance(row["fields"], dict)
                    or isinstance(row["pk"], (list, dict))):
                invalid()
        kinds = [i for i, row in enumerate(rows) if row["model"] == "people.identificationkind"]
        persons = [i for i, row in enumerate(rows) if row["model"] == "people.person"]
        if not kinds or not persons or max(kinds) < min(persons):
            return snapshot
        catalog = [row for row in rows if row["model"] == "people.identificationkind"]
        others = [row for row in rows if row["model"] != "people.identificationkind"]
        first_person = next(i for i, row in enumerate(others) if row["model"] == "people.person")
        reordered = others[:first_person] + catalog + others[first_person:]
        return json.dumps(reordered, ensure_ascii=True, allow_nan=False)

    @staticmethod
    def _restore_reject(fields=()):
        # Only model field names may be included; never values or server errors.
        suffix = ": " + ",".join(sorted(fields)) if fields else ""
        raise ImproperlyConfigured("R-01 Base rejected snapshot restoration" + suffix) from None

    @classmethod
    def _typed_snapshot(cls, snapshot):
        """Validate every record before any database read/write or model save."""
        ordered = cls._order_identification_catalog(snapshot)
        rows = json.loads(ordered)
        seen = set()
        for row in rows:
            try:
                model = apps.get_model(row["model"])
                if (model is None or model._meta.proxy or model._meta.abstract
                        or row["model"] != model._meta.label_lower):
                    cls._restore_reject()
                pk = row["pk"]
                if isinstance(pk, bool) or not isinstance(pk, int) or pk <= 0:
                    cls._restore_reject()
                key = (model._meta.label_lower, pk)
                if key in seen:
                    cls._restore_reject()
                seen.add(key)
                fields = {f.name: f for f in model._meta.local_fields
                          if f.serialize and not f.primary_key}
                fields.update({f.name: f for f in model._meta.local_many_to_many
                               if f.serialize and f.remote_field.through._meta.auto_created})
                if set(row["fields"]) != set(fields):
                    cls._restore_reject()
                for name, value in row["fields"].items():
                    field = fields[name]
                    if value is None:
                        if not field.null:
                            cls._restore_reject((name,))
                    elif isinstance(field, (models.DateTimeField, models.TimeField)):
                        # Old/truncated snapshots cannot prove exact equivalence.
                        if (not isinstance(value, str)
                                or not re.search(r"\.\d{6}(?:Z|[+-]\d{2}:\d{2})?$", value)):
                            cls._restore_reject((name,))
                        typed = field.to_python(value)
                        if isinstance(field, models.DateTimeField) and not is_aware(typed):
                            cls._restore_reject((name,))
                        if isinstance(field, models.TimeField) and re.search(r"(?:Z|[+-]\d{2}:\d{2})$", value):
                            cls._restore_reject((name,))
                    elif field.many_to_many:
                        if not isinstance(value, list) or any(
                            isinstance(pk, bool) or not isinstance(pk, int) or pk <= 0 for pk in value
                        ) or len(set(value)) != len(value):
                            cls._restore_reject((name,))
                    elif field.is_relation:
                        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                            cls._restore_reject((name,))
                    else:
                        if isinstance(field, models.BooleanField) and type(value) is not bool:
                            cls._restore_reject((name,))
                        if isinstance(field, models.IntegerField) and (
                            isinstance(value, bool) or not isinstance(value, int)
                        ):
                            cls._restore_reject((name,))
                        if isinstance(field, (models.CharField, models.TextField)) and not isinstance(value, str):
                            cls._restore_reject((name,))
                        field.to_python(value)
            except Exception:
                cls._restore_reject()
        try:
            objects = list(Deserializer(ordered, using="default"))
        except Exception:
            cls._restore_reject()
        return rows, objects

    @staticmethod
    def _different_fields(expected, actual):
        """Compare typed concrete values, including audit dates and FK attnames."""
        if type(expected) is not type(actual):
            return {"model"}
        return {field.name for field in expected._meta.concrete_fields
                if getattr(expected, field.attname) != getattr(actual, field.attname)}

    def deserialize_db_from_string(self, data):
        from people.identification import FINAL_CONSUMER_ID
        from people.models import IdentificationKind, Person

        validate_connections(settings.DATABASES, settings.DATABASE_ROUTERS)
        validate_database(self.connection.settings_dict, self.connection.alias)
        require_execution()
        rows, objects = self._typed_snapshot(data)
        reserved = [obj.object for obj in objects if isinstance(obj.object, Person)
                    and obj.object.identification == FINAL_CONSUMER_ID]
        if len(reserved) != 1:
            self._restore_reject()
        expected = reserved[0]
        if (expected.identification_type != "FINAL_CONSUMER"
                or expected._meta.many_to_many):
            self._restore_reject()
        catalogs = [obj.object for obj in objects if isinstance(obj.object, IdentificationKind)]
        kinds = [kind for kind in catalogs if kind.pk == expected.identification_kind_id]
        if (len(kinds) != 1 or kinds[0].code != "FINAL_CONSUMER"
                or sum(kind.code == "FINAL_CONSUMER" for kind in catalogs) != 1):
            self._restore_reject()
        kind = kinds[0]
        alias = self.connection.alias
        with transaction.atomic(using=alias):
            # No writes occur until both identity/PK conflict checks have passed.
            existing = list(Person._base_manager.using(alias).select_for_update().filter(
                Q(pk=expected.pk) | Q(identification=FINAL_CONSUMER_ID)
            ))
            skip = False
            if existing:
                if len(existing) != 1:
                    self._restore_reject()
                differences = self._different_fields(expected, existing[0])
                if differences:
                    self._restore_reject(differences)
                skip = True
            existing_kinds = list(IdentificationKind._base_manager.using(alias).select_for_update().filter(
                Q(pk=kind.pk) | Q(code="FINAL_CONSUMER")
            ))
            if existing_kinds:
                if len(existing_kinds) != 1:
                    self._restore_reject()
                differences = self._different_fields(kind, existing_kinds[0])
                if differences:
                    self._restore_reject(differences)
            elif skip:
                self._restore_reject()
            remaining = [row for row in rows if not (
                skip and row["model"] == expected._meta.label_lower and row["pk"] == expected.pk
            )]
            # Delegate saving, FK handling and M2M handling to Django unchanged.
            # Only this temporary input is filtered; data/_test_serialized_contents stay intact.
            super().deserialize_db_from_string(json.dumps(remaining, allow_nan=False))
            tables = set()
            for deserialized in objects:
                obj = deserialized.object
                actual = type(obj)._base_manager.using(alias).get(pk=obj.pk)
                differences = self._different_fields(obj, actual)
                if differences:
                    self._restore_reject(differences)
                for name, pks in (deserialized.m2m_data or {}).items():
                    if set(getattr(actual, name).using(alias).values_list("pk", flat=True)) != set(pks):
                        self._restore_reject((name,))
                tables.add(obj._meta.db_table)
            self.connection.check_constraints(table_names=tables)

    def _create_test_db(self, verbosity, autoclobber, keepdb=False):
        validate_connections(settings.DATABASES, settings.DATABASE_ROUTERS)
        validate_database(self.connection.settings_dict, self.connection.alias)
        require_execution()
        if not keepdb:
            reject()
        # No parent _create_test_db: that path may issue CREATE/DROP DATABASE.
        # Parent create_test_db still performs normal migrate, serialization,
        # cache-table setup and connection initialization.
        with self.connection.cursor() as cursor:
            verify_identity(cursor)
        return DATABASE

    def _execute_create_test_db(self, *args, **kwargs):
        reject()

    def _destroy_test_db(self, *args, **kwargs):
        reject()

    def _clone_test_db(self, *args, **kwargs):
        reject()

    def clone_test_db(self, *args, **kwargs):
        reject()

    def get_test_db_clone_settings(self, *args, **kwargs):
        reject()

    def set_as_test_mirror(self, *args, **kwargs):
        reject()

    def destroy_test_db(self, old_database_name=None, verbosity=1, keepdb=False, suffix=None):
        validate_connections(settings.DATABASES, settings.DATABASE_ROUTERS)
        validate_database(self.connection.settings_dict, self.connection.alias)
        require_execution()
        if not keepdb or suffix is not None or old_database_name not in (None, DATABASE):
            reject()
        self.connection.close()
