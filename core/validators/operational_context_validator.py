from django.core.exceptions import ValidationError


class OperationalContextValidator:
    """Valida pertenencia empresarial de documentos y efectos de inventario."""

    @staticmethod
    def validate_company_branch(company, branch):
        if branch.company_id != company.pk:
            raise ValidationError("La sucursal no pertenece a la empresa indicada.")

    @staticmethod
    def validate_warehouse(company, branch, warehouse):
        if warehouse.company_id != company.pk:
            raise ValidationError("La bodega no pertenece a la empresa indicada.")
        if warehouse.branch_id != branch.pk:
            raise ValidationError("La bodega no pertenece a la sucursal indicada.")

    @staticmethod
    def validate_product(company, product):
        if product.company_id != company.pk:
            raise ValidationError("El producto no pertenece a la empresa indicada.")

    @classmethod
    def validate_inventory(cls, company, branch, warehouse, product):
        cls.validate_company_branch(company, branch)
        cls.validate_warehouse(company, branch, warehouse)
        cls.validate_product(company, product)
