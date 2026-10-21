from django.db import models
from people.models import Person
from core.models.base import BaseModel

class Supplier(BaseModel):

    # Expansión: los legados siguen pendientes de clasificación explícita.
    company = models.ForeignKey(
        "core.Company", on_delete=models.PROTECT, null=True, blank=True,
    )

    person=models.ForeignKey(
        Person,
        on_delete=models.CASCADE
    )

    notes=models.TextField(
        blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("company", "person"),
                                    name="people_supplier_company_person_unique"),
        ]

    def __str__(self):
        return self.person.full_name