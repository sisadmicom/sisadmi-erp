from catalog.models import Product


class TaxResolver:

    @staticmethod
    def resolve(product: Product):
        """
        Resuelve los impuestos efectivos de un producto.

        Prioridad:

        1. Impuestos del producto
        2. Impuestos del subgrupo
        3. Impuestos del grupo
        4. Impuestos globales de la empresa

        Si un nivel tiene impuestos configurados,
        no continúa buscando en niveles inferiores.
        """

        # 1. Producto
        taxes = product.taxes.filter(
            is_active=True
        )

        if taxes.exists():
            return taxes

        # 2. Subgrupo
        if product.subgroup_id:

            taxes = product.subgroup.taxes.filter(
                is_active=True
            )

            if taxes.exists():
                return taxes

        # 3. Grupo
        if product.group_id:

            taxes = product.group.taxes.filter(
                is_active=True
            )

            if taxes.exists():
                return taxes

        # 4. Configuración global de la empresa
        try:
            configuration = product.company.tax_configuration
        except Exception:
            return product.taxes.none()

        return configuration.taxes.filter(
            is_active=True
        )
