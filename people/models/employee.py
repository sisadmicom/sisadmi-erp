from django.db import models

from people.models import Person


class Employee(models.Model):

    person=models.OneToOneField(
        Person,
        on_delete=models.CASCADE
    )

    salary=models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    hire_date=models.DateField(
        null=True
    )

    def __str__(self):
        return self.person.full_name