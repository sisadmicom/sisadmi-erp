"""Company-scoped maintenance; tax associations remain outside this form."""
from django import forms
from django.db.models import Q

from .models import ProductGroup, ProductSubGroup


class ProductSubGroupMaintenanceForm(forms.ModelForm):
    class Meta:
        model = ProductSubGroup
        fields = ('group', 'name')
        labels = {'group': 'Grupo', 'name': 'Nombre'}

    def __init__(self, *args, company, related_group_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        self.related_group_id = related_group_id if self.instance._state.adding else None
        if self.related_group_id is not None:
            self.initial['group'] = self.related_group_id
        self.original_group_id = self.instance.group_id if not self.instance._state.adding else None
        self.instance.company = company
        self.fields['group'].queryset = ProductGroup.objects.filter(
            Q(company=company) | Q(company__isnull=True)
        ).filter(Q(is_active=True) | Q(pk=self.original_group_id))

        if self.related_group_id is not None:
            self.fields['group'].queryset = self.fields['group'].queryset.filter(pk=self.related_group_id)

    def clean_group(self):
        selected = self.cleaned_data['group']
        # Revalidate the persisted parent; browser options do not grant authority.
        parent = ProductGroup.objects.filter(
            Q(company=self.company) | Q(company__isnull=True), pk=selected.pk
        ).first()
        if parent is None or (not parent.is_active and parent.pk != self.original_group_id):
            raise forms.ValidationError('Seleccione un grupo disponible.')
        if self.related_group_id is not None and str(parent.pk) != str(self.related_group_id):
            raise forms.ValidationError('Conserve el grupo seleccionado en el producto.')
        return parent

    def clean_name(self):
        name = self.cleaned_data['name']
        parent = self.cleaned_data.get('group')
        if parent is not None:
            duplicates = ProductSubGroup.objects.filter(company=self.company, group=parent, name=name)
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise forms.ValidationError('Ya existe un subgrupo con este nombre en el grupo seleccionado.')
        return name
