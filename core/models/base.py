#core/models/base.py
from django.db import models
from django.conf import settings


class TimeStampedModel(models.Model):

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        abstract = True


class UserTrackingModel(models.Model):

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_%(class)s"
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_%(class)s"
    )

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):

    is_active = models.BooleanField(
        default=True
    )

    deleted_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        abstract = True


class BaseModel(
    TimeStampedModel,UserTrackingModel,SoftDeleteModel):
    class Meta:
        abstract = True