from django import forms
from django.forms import formset_factory

from catalog.models import Product
from core.models import PointOfEmission
from inventory.models import Warehouse
from people.models import Customer


class SaleCreateForm(forms.Form):
    customer_id = forms.ModelChoiceField(
        queryset=Customer.objects.none(),
        label="Cliente",
    )
    warehouse_id = forms.ModelChoiceField(
        queryset=Warehouse.objects.none(),
        label="Bodega",
    )
    issue_date = forms.DateField(
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Fecha",
    )
    notes = forms.CharField(required=False, label="Notas")

    def __init__(self, *args, company, branch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer_id"].queryset = Customer.objects.filter(is_active=True)
        self.fields["warehouse_id"].queryset = Warehouse.objects.filter(
            company=company,
            branch=branch,
            is_active=True,
        )


class SaleDetailForm(forms.Form):
    product_id = forms.ModelChoiceField(
        queryset=Product.objects.none(),
        label="Producto",
    )
    quantity = forms.DecimalField(
        max_digits=18,
        decimal_places=6,
        label="Cantidad",
    )
    unit_price = forms.DecimalField(
        max_digits=18,
        decimal_places=6,
        label="Precio unitario",
    )
    discount = forms.DecimalField(
        max_digits=18,
        decimal_places=2,
        initial=0,
        label="Descuento",
    )

    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product_id"].queryset = Product.objects.filter(
            company=company,
            is_active=True,
        )


SaleDetailFormSet = formset_factory(
    SaleDetailForm,
    extra=5,
    min_num=1,
    validate_min=True,
    max_num=1000,
    validate_max=True,
)


class FiscalPreparationForm(forms.Form):
    point_of_emission = forms.ModelChoiceField(
        queryset=PointOfEmission.objects.none(),
        label="Punto de emisión",
    )

    def __init__(self, *args, branch, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["point_of_emission"].queryset = PointOfEmission.objects.filter(
            branch=branch,
            is_active=True,
        )
