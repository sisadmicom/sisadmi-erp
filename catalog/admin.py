from django.contrib import admin

from .models import (
    Brand,
    ProductGroup,
    ProductSubGroup,
    UnitMeasure,
    Product,
)


admin.site.register(Brand)

admin.site.register(ProductGroup)

admin.site.register(ProductSubGroup)

admin.site.register(UnitMeasure)

admin.site.register(Product)