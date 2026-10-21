"""Required test-only master data, scoped to one CLIENTES-01.3 runner invocation."""
from contextlib import contextmanager
from django.apps import apps
from django.conf import settings
from django.db import connections, transaction
from django.db.models.signals import post_migrate
from people.constants.identification_type import IdentificationType
from core.testing.clientes013_guard import (
    require_execution, validate_connections, validate_database, verify_identity, reject,
)

REQUIRED_KINDS = (IdentificationType.OTHER, IdentificationType.PASSPORT)


def initialize_required_kinds(sender, *, using, **kwargs):
    # Guard the alias/destination before opening a transaction or touching data.
    require_execution()
    if using != 'default':
        reject()
    validate_connections(settings.DATABASES, settings.DATABASE_ROUTERS)
    validate_database(connections[using].settings_dict, using)
    Kind = apps.get_model('people', 'IdentificationKind')
    with transaction.atomic(using=using):
        with connections[using].cursor() as cursor:
            verify_identity(cursor)
        for value in REQUIRED_KINDS:
            kind, _ = Kind.objects.using(using).get_or_create(
                code=value.value, defaults={'name': value.label, 'is_active': True},
            )
            if not kind.is_active:
                reject()  # Never reactivate or overwrite existing data silently.


@contextmanager
def scoped_identification_catalog():
    require_execution()
    validate_connections(settings.DATABASES, settings.DATABASE_ROUTERS)
    sender = apps.get_app_config('people')
    token = object()
    post_migrate.connect(initialize_required_kinds, sender=sender, dispatch_uid=token, weak=False)
    try:
        # migrate emits post_migrate even with no pending migrations; ordinary
        # TransactionTestCase flush emits it again. No migration is replayed.
        yield
    finally:
        post_migrate.disconnect(sender=sender, dispatch_uid=token)
