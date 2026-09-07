from django.db import transaction

from core.exceptions import (
    SequenceInactive,
    SequenceNotFound,
    ValidationException,
)
from core.models.sequence import Sequence


class SequenceService:
    """
    Servicio central de numeración del ERP.

    Garantiza:
    - numeración independiente por empresa, sucursal y tipo documental;
    - bloqueo de la secuencia durante la generación;
    - incremento atómico;
    - control de secuencias inexistentes;
    - control de secuencias inactivas.
    """

    @staticmethod
    @transaction.atomic
    def next_number(
        company,
        branch,
        document_type,
    ):
        """
        Obtiene y consume el siguiente número de una secuencia.

        Ejemplo:

            prefix = "VEN-"
            series = "001"
            next_number = 25
            padding = 6

        Resultado:

            VEN-001-000025
        """

        if branch.company_id != company.id:
            raise ValidationException("La sucursal no pertenece a la empresa indicada.")

        if document_type is None:
            raise SequenceNotFound("Se requiere un tipo documental para obtener la secuencia.")

        try:
            sequence = (
                Sequence.objects
                .select_for_update()
                .get(
                    company=company,
                    branch=branch,
                    document_type=document_type,
                )
            )
        except Sequence.DoesNotExist:
            raise SequenceNotFound(
                f"No existe la secuencia '{document_type}' "
                f"para la empresa y sucursal indicadas."
            )

        if not sequence.is_active:
            raise SequenceInactive(
                f"La secuencia '{document_type}' está inactiva."
            )

        number = sequence.next_number

        sequence.next_number += 1

        sequence.save(
            update_fields=[
                "next_number",
                "updated_at",
            ]
        )

        return (
            f"{sequence.prefix}"
            f"{sequence.series}-"
            f"{str(number).zfill(sequence.padding)}"
        )