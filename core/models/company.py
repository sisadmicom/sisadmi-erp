from django.db import models
from django.db import transaction

from core.models.base import BaseModel
from people.models import Person


class Company(BaseModel):

    person = models.OneToOneField(
        Person,
        on_delete=models.CASCADE
    )

    commercial_name=models.CharField(
        max_length=200,null=True
    )

    logo=models.ImageField(
        upload_to="company",
        blank=True,
        null=True
    )


    @transaction.atomic
    def save(self, *args, **kwargs):
        creating = self._state.adding
        result = super().save(*args, **kwargs)
        if creating:
            from people.services.final_consumer import enable_for_company
            enable_for_company(self)
        return result

    def __str__(self):

        return self.commercial_name or self.person.full_name
