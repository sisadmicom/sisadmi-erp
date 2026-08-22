from django.db import transaction

from core.models import DocumentSequence


class NumberingService:


    @staticmethod
    @transaction.atomic
    def next_number(
        company,
        branch,
        document_type
    ):


        sequence, created = (
            DocumentSequence.objects
            .select_for_update()
            .get_or_create(

                company=company,

                branch=branch,

                document_type=document_type,

                defaults={
                    "current_number":0
                }

            )
        )


        sequence.current_number += 1

        sequence.save()


        prefix = sequence.prefix


        return (
            f"{prefix}"
            f"{sequence.current_number:06d}"
        )