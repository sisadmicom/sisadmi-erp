from pathlib import Path
from uuid import uuid4

from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q

from core.models.base import BaseModel
from core.models.company import Company
from sri.storage import sri_certificate_storage


def sri_certificate_upload_to(
    instance,
    filename,
):
    """
    Genera una ruta privada para el certificado.

    El nombre físico no reutiliza el nombre original.
    """

    extension = (
        Path(filename)
        .suffix
        .lower()
    )

    unique_name = (
        f"{uuid4().hex}{extension}"
    )

    return (
        f"company_{instance.company_id}/"
        f"{unique_name}"
    )


class SriCertificate(BaseModel):
    """
    Certificado electrónico PKCS#12 perteneciente
    a una empresa de SISADMI.

    La contraseña no se almacena en este modelo.
    secret_key contiene únicamente la referencia
    utilizada por SecretProvider.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="sri_certificates",
    )

    certificate_file = models.FileField(
        storage=sri_certificate_storage,
        upload_to=sri_certificate_upload_to,
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    "p12",
                    "pfx",
                ]
            )
        ],
        blank=True,
    )

    original_filename = models.CharField(
        max_length=255,
        blank=True,
    )

    serial_number = models.CharField(
        max_length=200,
        blank=True,
    )

    subject = models.TextField(
        blank=True,
    )

    valid_from = models.DateTimeField(
        null=True,
        blank=True,
    )

    valid_until = models.DateTimeField(
        null=True,
        blank=True,
    )

    secret_key = models.CharField(
        max_length=255,
    )

    is_default = models.BooleanField(
        default=False,
    )

    class Meta:

        verbose_name = "Certificado SRI"
        verbose_name_plural = "Certificados SRI"

        ordering = [
            "company",
            "-is_default",
            "-valid_until",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["company"],
                condition=Q(
                    is_default=True,
                    is_active=True,
                ),
                name="unique_active_default_sri_certificate_company",
            ),
        ]

    def __str__(self):

        description = (
            self.serial_number
            or self.original_filename
            or str(self.pk)
        )

        return (
            f"{self.company} - "
            f"{description}"
        )
