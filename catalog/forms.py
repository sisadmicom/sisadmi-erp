from django import forms

from .models import (
    UnitMeasure,
    Brand,
    ProductGroup,
    ProductSubGroup,
    Product,
)


class UnitMeasureForm(forms.ModelForm):

    class Meta:

        model = UnitMeasure

        exclude = (
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "deleted_at",
            "is_active",
        )


class BrandForm(forms.ModelForm):

    class Meta:

        model = Brand

        exclude = (
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "deleted_at",
            "is_active",
        )


class ProductGroupForm(forms.ModelForm):

    class Meta:

        model = ProductGroup

        exclude = (
            "company",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "deleted_at",
            "is_active",
        )


class ProductSubGroupForm(forms.ModelForm):

    class Meta:

        model = ProductSubGroup

        exclude = (
            "company",
            "created_at",
            "updated_at",
            "updated_by",
            "created_by",
            "deleted_at",
            "is_active",
        )
        
from django import forms

from .models import Product


class ProductForm(forms.ModelForm):

    class Meta:

        model = Product

        exclude = (

            "company",

            "created_at",

            "updated_at",

            "created_by",

            "updated_by",

            "deleted_at",

            "is_active",

        )

    def __init__(self, *args, **kwargs):

        company_id = kwargs.pop(
            "company_id",
            None
        )

        super().__init__(
            *args,
            **kwargs
        )

        if company_id:

            self.fields[
                "group"
            ].queryset = ProductGroup.objects.filter(

                company_id=company_id,

                is_active=True

            )

            self.fields[
                "subgroup"
            ].queryset = ProductSubGroup.objects.filter(

                company_id=company_id,

                is_active=True

            )