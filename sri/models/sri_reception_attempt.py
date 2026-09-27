from django.db import models
from django.db.models import Q

from sri.constants.reception_attempt_status import SriReceptionAttemptStatus
from sri.models.electronic_document import ElectronicDocument


class SriReceptionAttempt(models.Model):
    electronic_document = models.ForeignKey(ElectronicDocument, on_delete=models.PROTECT, related_name="reception_attempts")
    status = models.CharField(max_length=20, choices=SriReceptionAttemptStatus.choices, default=SriReceptionAttemptStatus.IN_PROGRESS)
    attempted_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_type = models.CharField(max_length=255, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["-attempted_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["electronic_document"], condition=Q(status__in=[SriReceptionAttemptStatus.IN_PROGRESS, SriReceptionAttemptStatus.UNCERTAIN]), name="unique_active_sri_reception_attempt")]
        indexes = [
            models.Index(fields=["electronic_document", "status"], name="sri_attempt_doc_status_idx"),
            models.Index(fields=["status", "attempted_at"], name="sri_attempt_status_time_idx"),
        ]
