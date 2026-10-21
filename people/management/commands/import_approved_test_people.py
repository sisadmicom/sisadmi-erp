"""Execute only the explicitly authorized 49-row TEST batch."""
import json
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from people.services.controlled_person_import import import_approved_people, _require_test
from people.services.person_access_policy import IdentityUnavailable


class Command(BaseCommand):
    help = 'Importación fija de 49 Personas autorizadas, únicamente TEST; sin Customer.'

    def add_arguments(self, parser):
        parser.add_argument('--actor-id', type=int, required=True)

    def handle(self, *args, **options):
        _require_test()
        actor = get_user_model().objects.filter(pk=options['actor_id'], is_active=True).first()
        if actor is None:
            raise CommandError('Operador activo no disponible.')
        try:
            result = import_approved_people(actor=actor)
        except (ValidationError, PermissionDenied, IdentityUnavailable, IntegrityError) as error:
            raise CommandError('Lote no ejecutado: validación, permisos o estado cambiaron; transacción revertida. Revisar sin reintentar automáticamente.') from None
        self.stdout.write(json.dumps(result, ensure_ascii=False))
