from django.db import models

from sri.models.sri_reception_attempt import SriReceptionAttempt


class SriReceptionMessage(models.Model):
    attempt = models.ForeignKey(SriReceptionAttempt, on_delete=models.CASCADE, related_name="messages")
    message_type = models.CharField(max_length=100, null=True, blank=True)
    identifier = models.CharField(max_length=100, null=True, blank=True)
    message = models.TextField()
    additional_information = models.TextField(null=True, blank=True)
