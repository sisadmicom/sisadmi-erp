from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from core.models import BaseModel
from core.models.company import Company
from core.models.branch import Branch

from core.constants.sri import SriEnvironment, SriEmissionType
from sri.constants.document_status import SriDocumentStatus


class ElectronicDocument(BaseModel):

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="electronic_documents",
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="electronic_documents",
    )

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        related_name="sri_electronic_documents",
    )

    object_id = models.PositiveBigIntegerField()

    document = GenericForeignKey(
        "content_type",
        "object_id",
    )

    document_type = models.CharField(
        max_length=2,
    )

    environment = models.CharField(
        max_length=1,
        choices=SriEnvironment.CHOICES,
        default=SriEnvironment.TEST,
    )

    emission_type = models.CharField(
        max_length=1,
        choices=SriEmissionType.CHOICES,
        default=SriEmissionType.NORMAL,
    )

    establishment = models.CharField(
        max_length=3,
    )

    emission_point = models.CharField(
        max_length=3,
    )

    sequential = models.CharField(
        max_length=9,
    )

    numeric_code = models.CharField(
        max_length=8,
    )

    access_key = models.CharField(
        max_length=49,
        blank=True,
        null=True,
        unique=True,
    )

    status = models.CharField(
        max_length=20,
        choices=SriDocumentStatus.choices,
        default=SriDocumentStatus.DRAFT,
    )

    xml = models.TextField(
        blank=True,
        null=True,
    )

    authorization_number = models.CharField(
        max_length=49,
        blank=True,
        null=True,
    )

    authorization_date = models.DateTimeField(
        blank=True,
        null=True,
    )

    error_message = models.TextField(
        blank=True,
        null=True,
    )

    class Meta:

        verbose_name = "Documento electrónico"
        verbose_name_plural = "Documentos electrónicos"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "company",
                    "document_type",
                    "establishment",
                    "emission_point",
                    "sequential",
                ],
                name="unique_sri_electronic_document_number",
            ),
        ]

        ordering = ["-id"]

    def __str__(self):

        return (
            f"{self.establishment}-"
            f"{self.emission_point}-"
            f"{self.sequential}"
        )