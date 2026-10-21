from django import forms

from people.models import Person
from people.forms import GEOGRAPHIC_FIELDS, IDENTITY_UNAVAILABLE, PersonForm


class InitialSetupForm(forms.ModelForm):
    commercial_name = forms.CharField(max_length=200, label="Nombre comercial")
    company_address = forms.CharField(label="Dirección de la empresa", widget=forms.Textarea)
    branch_code = forms.CharField(max_length=20, label="Código de sucursal")
    branch_name = forms.CharField(max_length=100, label="Nombre de sucursal")
    branch_address = forms.CharField(label="Dirección de sucursal", widget=forms.Textarea)

    class Meta:
        model = Person
        fields = ("identification_type", "identification", "full_name", "email", "phone")
        labels = {
            "identification_type": "Tipo de identificación",
            "identification": "Identificación",
            "full_name": "Razón social",
        }

    def __init__(self, *args, **kwargs):
        # The initial profile is a legal entity; identity type remains explicit.
        super().__init__(*args, instance=Person(person_type="LEGAL"), **kwargs)
        self.fields["identification_type"].required = True


from people.identity_integrity import ImmutableIdentityFormMixin


class FoundingPersonForm(ImmutableIdentityFormMixin, forms.ModelForm):
    class Meta:
        model = Person
        fields = ("identification_type", "identification", "full_name", "email", "phone", "address")
        labels = {
            **InitialSetupForm.Meta.labels,
            "email": "Correo electrónico",
            "phone": "Teléfono",
            "address": "Dirección",
        }
        help_texts = {
            "identification_type": "Seleccione el tipo de identificación de la persona vinculada a la empresa.",
            "identification": "Identificación de la persona vinculada a la empresa.",
            "full_name": "Nombre completo o razón social de la persona vinculada a la empresa.",
            "email": "Correo de contacto de la persona vinculada a la empresa.",
            "phone": "Número de contacto. Puede dejarlo vacío.",
            "address": "Domicilio de la persona vinculada a la empresa.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["identification_type"].required = not bool(self.instance.pk)
        self.fields["address"].required = True


class SetupCompanyForm(forms.ModelForm):
    commercial_name = forms.CharField(
        max_length=200, label="Nombre comercial",
        help_text="Escriba el nombre con el que su empresa se presenta al público.",
    )

    class Meta:
        model = Person
        fields = ("identification_type", "identification", "full_name", "email", "phone")
        labels = {**InitialSetupForm.Meta.labels, "email": "Correo", "phone": "Teléfono"}
        help_texts = {
            "identification_type": "Seleccione el tipo de identificación de su empresa.",
            "identification": "Ingrese la identificación que corresponde al tipo seleccionado.",
            "full_name": "Escriba la razón social completa de su empresa.",
            "email": "Correo de contacto de la empresa. Puede dejarlo vacío.",
            "phone": "Teléfono de contacto de la empresa. Puede dejarlo vacío.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, instance=Person(person_type="LEGAL"), **kwargs)
        self.fields["identification_type"].required = True

    def validate_unique(self):
        identity = self.cleaned_data.get("identification")
        if identity and Person.objects.filter(identification=identity).exists():
            self.add_error(None, IDENTITY_UNAVAILABLE)


class SetupLocationForm(PersonForm):
    class Meta(PersonForm.Meta):
        fields = (*GEOGRAPHIC_FIELDS, "address")
        labels = {**PersonForm.Meta.labels, "address": "Dirección legal"}
        help_texts = {
            **PersonForm.Meta.help_texts,
            "country": "Seleccione el país de la dirección legal de su empresa.",
            "address": "Escriba la dirección legal completa, incluyendo calle y referencias útiles.",
        }


class SetupBranchForm(forms.Form):
    branch_code = forms.CharField(max_length=20, label="Código",
                                 help_text="Escriba un código interno para identificar esta sucursal.")
    branch_name = forms.CharField(max_length=100, label="Nombre",
                                 help_text="Escriba el nombre de su sucursal principal.")
    branch_address = forms.CharField(label="Dirección", widget=forms.Textarea(attrs={"rows": 3}),
                                    help_text="Escriba la dirección de la sucursal o use explícitamente la dirección legal.")
