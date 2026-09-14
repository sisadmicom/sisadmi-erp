from django.db import models

from core.models.base import TimeStampedModel
from core.models.company import Company


class FiscalSequence(TimeStampedModel):
    """Next available number for one fiscal series; 1000000000 means exhausted."""

    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    establishment = models.CharField(max_length=3)
    emission_point = models.CharField(max_length=3)
    document_type = models.CharField(max_length=2)
    next_number = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'establishment', 'emission_point', 'document_type'],
                name='unique_sri_fiscal_sequence_scope',
            ),
            models.CheckConstraint(
                condition=models.Q(next_number__gte=1, next_number__lte=1000000000),
                name='sri_fiscal_sequence_next_range',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    establishment__regex=r'\A[0-9]{3}\Z',
                    emission_point__regex=r'\A[0-9]{3}\Z',
                    document_type__regex=r'\A[0-9]{2}\Z',
                ),
                name='sri_fiscal_sequence_codes_valid',
            ),
        ]
