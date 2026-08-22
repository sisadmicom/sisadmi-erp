from django.db import transaction

from core.exceptions import (
    SequenceInactive,
    SequenceNotFound,
)
from core.models.sequence import Sequence


class SequenceService:
    """
    Servicio central de numeración del ERP.

    Garantiza:
    - numeración independiente por empresa y sucursal;
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
        code,
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

        try:
            sequence = (
                Sequence.objects
                .select_for_update()
                .get(
                    company=company,
                    branch=branch,
                    code=code,
                )
            )
        except Sequence.DoesNotExist:
            raise SequenceNotFound(
                f"No existe la secuencia '{code}' "
                f"para la empresa y sucursal indicadas."
            )

        if not sequence.is_active:
            raise SequenceInactive(
                f"La secuencia '{code}' está inactiva."
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