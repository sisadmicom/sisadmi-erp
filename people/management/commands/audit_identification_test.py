"""Read-only TEST-only diagnostics; never changes historical identities."""
from collections import Counter
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.db import connection
from people.identification import detect_identification, FINAL_CONSUMER_ID


class Command(BaseCommand):
    help = 'Diagnóstico agregado de identificaciones, exclusivamente PostgreSQL TEST.'

    def handle(self, *args, **options):
        from core.testing.r01_guard import TEST_DATABASE, USER
        if connection.settings_dict['NAME'] != TEST_DATABASE or connection.settings_dict['USER'] != USER:
            raise CommandError('Solo TEST autorizado.')
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database(), current_user')
            if cursor.fetchone() != (TEST_DATABASE, USER):
                raise CommandError('Identidad de conexión no autorizada.')
            # SQL selects only columns that exist BEFORE additive migrations.
            cursor.execute('SELECT identification, identification_type FROM people_person')
            totals = Counter()
            for value, historical in cursor.fetchall():
                totals['persons'] += 1
                if value == FINAL_CONSUMER_ID:
                    totals['reserved_conflicts'] += 1
                    continue
                try:
                    detected = detect_identification(value, historical)
                except ValidationError:
                    totals['structurally_invalid'] += 1
                else:
                    if detected != historical:
                        totals['classification_differences_preserved'] += 1
            cursor.execute('SELECT count(*) FROM people_customer WHERE company_id IS NULL')
            totals['unclassified_customers'] = cursor.fetchone()[0]
        self.stdout.write(str(dict(totals)))
        if totals['reserved_conflicts']:
            raise CommandError('STOP: identificación reservada ya existente; revisar sin sobrescribir.')
