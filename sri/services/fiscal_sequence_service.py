import re

from django.db import transaction

from sri.models import FiscalSequence


class FiscalSequenceService:
    @staticmethod
    @transaction.atomic
    def next_number(company, establishment, emission_point, document_type):
        """Reserve inside the caller's emission transaction so failures roll back."""
        for field, value, width in (
            ('establishment', establishment, 3),
            ('emission_point', emission_point, 3),
            ('document_type', document_type, 2),
        ):
            if not isinstance(value, str) or re.fullmatch(r'[0-9]{%d}' % width, value) is None:
                raise ValueError(f'Código fiscal inválido: {field}.')

        sequence, _ = FiscalSequence.objects.get_or_create(
            company=company, establishment=establishment,
            emission_point=emission_point, document_type=document_type,
            defaults={'next_number': 1},
        )
        sequence = FiscalSequence.objects.select_for_update().get(pk=sequence.pk)
        reserved = sequence.next_number
        if not 1 <= reserved <= 999999999:
            raise ValueError('La secuencia fiscal está agotada o fuera de rango.')
        sequence.next_number = reserved + 1
        sequence.save(update_fields=['next_number', 'updated_at'])
        return f'{reserved:09d}'
