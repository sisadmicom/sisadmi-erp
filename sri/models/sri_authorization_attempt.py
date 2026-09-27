from django.db import models
from django.db.models import Q

from core.constants.sri import SriEnvironment
from sri.constants.authorization_attempt_status import SriAuthorizationAttemptStatus
from sri.models.electronic_document import ElectronicDocument


class SriAuthorizationAttempt(models.Model):
    electronic_document = models.ForeignKey(
        ElectronicDocument,
        on_delete=models.PROTECT,
        related_name="authorization_attempts",
    )
    status = models.CharField(
        max_length=20,
        choices=SriAuthorizationAttemptStatus.choices,
        default=SriAuthorizationAttemptStatus.IN_PROGRESS,
    )
    access_key = models.CharField(max_length=49)
    environment = models.CharField(
        max_length=1,
        choices=SriEnvironment.CHOICES,
    )
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    authorization_number = models.CharField(max_length=49, null=True, blank=True)
    authorization_date = models.DateTimeField(null=True, blank=True)
    response_environment = models.CharField(max_length=32, null=True, blank=True)
    error_type = models.CharField(max_length=255, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["electronic_document"],
                condition=Q(status=SriAuthorizationAttemptStatus.IN_PROGRESS),
                name="unique_active_sri_authorization_attempt",
            ),
        ]
        indexes = [
            models.Index(
                fields=["electronic_document", "status"],
                name="sri_auth_doc_status_idx",
            ),
            models.Index(
                fields=["status", "started_at"],
                name="sri_auth_status_time_idx",
            ),
        ]
