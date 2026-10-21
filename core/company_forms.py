"""Normal Company maintenance; Person selection is supplied by authority."""
from django import forms

from core.models import Company
from people.models import Person


class CompanyNameInput(forms.TextInput):
    """Keep an explicit empty value when restoring an incomplete Company draft."""
    def format_value(self, value):
        formatted = super().format_value(value)
        return "" if formatted is None else formatted


class CompanyForm(forms.ModelForm):
    commercial_name = forms.CharField(max_length=200, label="Nombre comercial", widget=CompanyNameInput)

    class Meta:
        model = Company
        fields = ("person", "commercial_name", "logo")
        labels = {"person": "Persona", "logo": "Logo"}

    def __init__(self, *args, people=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["person"].queryset = people if people is not None else Person.objects.none()
        self.fields["person"].empty_label = "Buscar o seleccionar persona..."
