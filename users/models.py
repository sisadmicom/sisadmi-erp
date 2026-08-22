#users/models.py
from django.db import models
from django.contrib.auth.models import User

from people.models import Person
from core.models import Company, Branch


class UserProfile(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    companies = models.ManyToManyField(
        Company,
        blank=True
    )

    branches = models.ManyToManyField(
        Branch,
        blank=True
    )

    is_supervisor = models.BooleanField(default=False)

    is_developer = models.BooleanField(default=False)

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.user.username