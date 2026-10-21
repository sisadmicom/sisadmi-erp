from django.db import models

from core.models.base import BaseModel


class CustomerCategory(BaseModel):
    company = models.ForeignKey("core.Company", on_delete=models.PROTECT)
    code = models.CharField("Código", max_length=32)
    name = models.CharField("Descripción", max_length=150)

    class Meta:
        ordering = ("code", "pk")
        verbose_name = "categoría de cliente"
        verbose_name_plural = "categorías de clientes"
        constraints = [models.UniqueConstraint(
            fields=("company", "code"), name="people_customer_category_company_code_unique",
        )]

    def __str__(self):
        return f"{self.code} — {self.name}"
