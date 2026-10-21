from django import forms
from django.db.models import Q

from .models import (
    UnitMeasure,
    Brand,
    ProductGroup,
    ProductSubGroup,
    Product,
    Tax,
)


class UnitMeasureForm(forms.ModelForm):

    class Meta:

        model = UnitMeasure
        labels = {"code": "Código", "name": "Nombre"}

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
        labels = {"name": "Nombre"}

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



class ProductForm(forms.ModelForm):

    class Meta:

        model = Product
        labels = {
            'code': 'Código', 'barcode': 'Código de barras', 'name': 'Nombre',
            'description': 'Descripción', 'group': 'Grupo', 'subgroup': 'Subgrupo',
            'brand': 'Marca', 'unit_measure': 'Unidad de medida',
            'taxes': 'Impuestos específicos del producto',
            'cost_price': 'Precio de costo', 'sale_price': 'Precio de venta',
            'is_service': 'Es servicio', 'stock_control': 'Control de existencias',
        }
        widgets = {'taxes': forms.CheckboxSelectMultiple}

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
        self.company_id = kwargs.pop("company_id", None)
        super().__init__(*args, **kwargs)
        # Company is supplied by the validated server context, never a form field.
        self.instance.company_id = self.company_id
        for field_name, model in (("group", ProductGroup), ("subgroup", ProductSubGroup),
                                  ("brand", Brand), ("unit_measure", UnitMeasure), ("taxes", Tax)):
            queryset = model.objects.all()
            if field_name in ("group", "subgroup", "taxes"):
                queryset = queryset.filter(company_id=self.company_id) if self.company_id else model.objects.none()
            permitted = Q(is_active=True)
            if not self.instance._state.adding:
                # Only this product's existing assignments may remain inactive.
                if field_name == "taxes":
                    permitted |= Q(pk__in=self.instance.taxes.values_list("pk", flat=True))
                else:
                    permitted |= Q(pk=getattr(self.instance, field_name + "_id"))
            self.fields[field_name].queryset = queryset.filter(permitted)

        # Dependent options are resolved on GET and POST without JavaScript.
        from core.validators.access_validator import context_pk
        selected_group = self.data.get('group') if self.is_bound else self.initial.get('group')
        self.fields['subgroup'].queryset = self.fields['subgroup'].queryset.filter(
            group_id=context_pk(selected_group))

    def clean_code(self):
        code = self.cleaned_data["code"]
        duplicates = Product.objects.filter(company_id=self.company_id, code=code)
        if not self.instance._state.adding:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError("Ya existe un producto con este código en la empresa.")
        return code

    def clean(self):
        cleaned = super().clean()
        if not self.company_id:
            raise forms.ValidationError("Seleccione una empresa disponible antes de guardar.")
        for field in ("cost_price", "sale_price"):
            value = cleaned.get(field)
            if value is not None and value < 0:
                self.add_error(field, "El precio no puede ser negativo.")
        group, subgroup = cleaned.get("group"), cleaned.get("subgroup")
        if subgroup and (not group or subgroup.group_id != group.pk):
            self.add_error("subgroup", "Seleccione un subgrupo del grupo indicado.")
        return cleaned
