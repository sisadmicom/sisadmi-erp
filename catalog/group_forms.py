"""Company-scoped group maintenance without editing historical tax assignments."""
from django import forms

from .models import ProductGroup


class ProductGroupMaintenanceForm(forms.ModelForm):
    class Meta:
        model = ProductGroup
        fields = ('name',)
        labels = {'name': 'Nombre'}

    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.instance.company = company

    def clean_name(self):
        name = self.cleaned_data['name']
        duplicates = ProductGroup.objects.filter(company=self.company, name=name)
        if not self.instance._state.adding:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError('Ya existe un grupo con este nombre en la empresa.')
        return name
