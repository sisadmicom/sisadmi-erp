"""Human forms for the global catalogs and contextual Person maintenance."""

from django import forms

from people.models import Person
from people.models.geography import Canton, Continent, Country, Parish, Province

GEOGRAPHY = {
    "continent": (Continent, "Continente", "Continentes", ("name",)),
    "country": (Country, "País", "Países", ("continent", "code", "name")),
    "province": (Province, "Provincia", "Provincias", ("country", "name")),
    "canton": (Canton, "Cantón", "Cantones", ("province", "name")),
    "parish": (Parish, "Parroquia", "Parroquias", ("canton", "name")),
}
GEOGRAPHIC_FIELDS = tuple(GEOGRAPHY)
PERSON_FIELDS = (
    "person_type", "identification_type", "identification", "full_name",
    "email", "phone", "country", "province", "canton", "parish", "address",
)
IDENTITY_UNAVAILABLE = "No se puede utilizar esta identificación. Revísela o solicite ayuda a un usuario autorizado."


def valid_id(value):
    try:
        number = int(value)
        return number if 0 < number <= 9223372036854775807 else None
    except (TypeError, ValueError, OverflowError):
        return None


from people.identity_integrity import ImmutableIdentityFormMixin


class PersonForm(ImmutableIdentityFormMixin, forms.ModelForm):
    continent = forms.ModelChoiceField(
        queryset=Continent.objects.order_by("name"), label="Continente",
        help_text="Seleccione el continente para limitar los países disponibles.",
    )

    class Meta:
        model = Person
        fields = (*PERSON_FIELDS[:6], "continent", *PERSON_FIELDS[6:])
        labels = {
            "person_type": "Tipo de persona", "identification_type": "Tipo de identificación",
            "identification": "Identificación", "full_name": "Nombre / Razón social",
            "email": "Correo", "phone": "Teléfono", "address": "Dirección",
            **{kind: values[1] for kind, values in GEOGRAPHY.items()},
        }
        help_texts = {
            "person_type": "Seleccione si registra una persona natural o jurídica.",
            "identification_type": "Seleccione el tipo de identificación que corresponde a la persona.",
            "identification": "Ingrese la identificación correspondiente al tipo seleccionado.",
            "full_name": "Ingrese el nombre completo o la razón social de la persona.",
            "email": "Registre un correo válido para las comunicaciones asociadas a esta persona, incluidos los comprobantes electrónicos cuando corresponda.",
            "phone": "Registre un teléfono de contacto. Puede dejarlo vacío.",
            "country": "Seleccione el país correspondiente a la dirección de la persona.",
            "province": "Seleccione una provincia del país elegido.",
            "canton": "Seleccione un cantón de la provincia elegida.",
            "parish": "Seleccione una parroquia del cantón elegido.",
            "address": "Ingrese la dirección completa de la persona, incluyendo calle y referencias útiles.",
        }
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.country_id and "continent" not in self.initial:
            self.initial["continent"] = self.instance.country.continent_id
        for name, field in self.fields.items():
            field.required = name not in {"email", "phone", "identification_type"}
        if 'identification_type' in self.fields:
            from people.models import IdentificationKind
            kinds = IdentificationKind.objects.filter(is_active=True).exclude(code='FOREIGN_ID').order_by('name')
            self.fields['identification_type'].choices = [('', 'Detección automática'), *kinds.values_list('code', 'name')]
            if self.instance.pk and self.instance.identification_type == 'FOREIGN_ID':
                self.fields['identification_type'].choices.append(('FOREIGN_ID', 'Identificación del exterior (histórico)'))
            self.fields['identification_type'].help_text = 'Se detecta desde la identificación. Pasaporte no permite omitir la validación de Cédula o RUC.'
        if self.instance.pk:
            for name in ('identification', 'identification_type'):
                if name in self.fields:
                    self.fields[name].disabled = True
                    self.fields[name].required = False
        values = self.data if self.is_bound else self.initial
        for index, child in enumerate(GEOGRAPHIC_FIELDS[1:], 1):
            parent = GEOGRAPHIC_FIELDS[index - 1]
            self.fields[child].queryset = GEOGRAPHY[child][0].objects.filter(
                **{parent + "_id": valid_id(values.get(parent))}
            ).order_by("name")
            self.fields[child].error_messages["invalid_choice"] = "Seleccione una opción que corresponda al dato anterior."

    def clean(self):
        data = super().clean()
        if 'identification' in self.fields and data.get('identification'):
            from people.identification import detect_identification
            from django.core.exceptions import ValidationError
            unchanged = self.instance.pk and data['identification'] == self.instance.identification and data.get('identification_type') == self.instance.identification_type
            if not unchanged:
                try:
                    data['identification_type'] = detect_identification(data['identification'], data.get('identification_type'))
                    if data['identification_type'] == 'FINAL_CONSUMER':
                        from people.services.final_consumer import PROTECTED_MESSAGE
                        self.add_error('identification', PROTECTED_MESSAGE)
                except ValidationError as error:
                    for field, errors in error.error_dict.items():
                        self.add_error(field, errors)
        for parent, child in zip(GEOGRAPHIC_FIELDS, GEOGRAPHIC_FIELDS[1:]):
            if data.get(parent) and data.get(child) and getattr(data[child], parent + "_id") != data[parent].pk:
                self.add_error(child, "La opción seleccionada no corresponde al dato anterior.")
        return data

    def validate_unique(self):
        # Never render Django's global identifying uniqueness message.
        identity = self.cleaned_data.get("identification")
        if identity and Person.objects.filter(identification=identity).exclude(pk=self.instance.pk).exists():
            self.add_error(None, IDENTITY_UNAVAILABLE)


def geography_form(kind):
    model, label, _, fields = GEOGRAPHY[kind]
    parent = fields[0] if fields[0] in GEOGRAPHY else None
    help_texts = {
        "name": f"Ingrese el nombre del {label.lower()}." if kind != "province" and kind != "parish" else f"Ingrese el nombre de la {label.lower()}.",
        "code": "Ingrese un código corto y único para identificar el país, por ejemplo EC.",
    }
    if parent:
        help_texts[parent] = "Seleccione " + GEOGRAPHY[parent][1].lower() + " al que pertenece este dato."
    return forms.modelform_factory(
        model, fields=fields,
        labels={"name": "Nombre", "code": "Código", **{key: item[1] for key, item in GEOGRAPHY.items()}},
        help_texts=help_texts,
    )
