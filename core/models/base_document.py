#from datetime import timezone
from django.utils import timezone
from django.conf import settings
from django.db import models

from core.models.base import BaseModel
from core.models.company import Company
from core.models.branch import Branch

from core.constants.document_status import DocumentStatus


class BaseDocument(BaseModel):
    """
    Clase base para todos los documentos del ERP.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="%(class)s_documents"
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="%(class)s_documents"
    )

    document_type = models.ForeignKey(
        "core.DocumentType",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_documents",
        editable=False,
    )

    number = models.CharField(
        max_length=30,
        db_index=True,
        blank=True,
        default=""
    )

    issue_date = models.DateField(default=timezone.localdate)

    status = models.CharField(
        max_length=20,
        choices=DocumentStatus.choices,
        default=DocumentStatus.DRAFT
    )

    notes = models.TextField(
        blank=True,
        default=""
    )

    confirmed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_%(class)s"
    )

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True
    )

    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cancelled_%(class)s"
    )

    class Meta:
        abstract = True

    def is_draft(self):
        return self.status == DocumentStatus.DRAFT

    def is_confirmed(self):
        return self.status == DocumentStatus.CONFIRMED

    def is_cancelled(self):
        return self.status == DocumentStatus.CANCELLED