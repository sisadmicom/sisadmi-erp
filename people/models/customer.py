from django.db import models
from django.core.exceptions import ValidationError

from people.models import Person
from core.models.base import BaseModel

class Customer(BaseModel):

    # Nullable only during the legacy classification/expansion stage.
    company = models.ForeignKey(
        "core.Company",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    person=models.ForeignKey(
        Person,
        on_delete=models.CASCADE
    )

    credit_limit=models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    notes=models.TextField(
        blank=True
    )

    category = models.ForeignKey(
        "people.CustomerCategory", on_delete=models.PROTECT,
        null=True, blank=True, related_name="customers",
        verbose_name="Categoría de cliente",
    )

    def clean(self):
        super().clean()
        if self.category_id:
            from people.models.customer_category import CustomerCategory
            if not CustomerCategory.objects.filter(pk=self.category_id, company_id=self.company_id).exists():
                raise ValidationError({"category": ValidationError(
                    "La categoría no está disponible en esta empresa.", code="invalid_category",
                )})

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("company", "person"),
                name="people_customer_company_person_unique",
            ),
        ]

    def __str__(self):
        return self.person.full_name
