from django.db import models
from django.conf import settings


class AuditLog(models.Model):

    model_name=models.CharField(
        max_length=100
    )

    object_id=models.PositiveBigIntegerField()

    action=models.CharField(
        max_length=50
    )

    detail=models.JSONField(
        default=dict
    )

    observation=models.TextField(
        blank=True,
        null=True
    )

    requested_by=models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="requested_logs"
    )

    approved_by=models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="approved_logs"
    )

    executed_by=models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="executed_logs"
    )

    created_at=models.DateTimeField(
        auto_now_add=True,null=True
    )