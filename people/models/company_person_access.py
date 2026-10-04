"""Explicit company availability of a global Person."""

from django.db import models


class CompanyPersonAccess(models.Model):
    company = models.ForeignKey("core.Company", on_delete=models.CASCADE)
    person = models.ForeignKey("people.Person", on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("company", "person"), name="people_company_person_access_unique"
            ),
        ]
