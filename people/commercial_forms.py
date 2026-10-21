"""Local commercial fields; global identity is selected, never edited here."""
from django import forms
from django.core.exceptions import ValidationError

from people.services import person_access_policy
from people.models import CustomerCategory


class CustomerCategoryChoice(forms.ModelChoiceField):
    def __init__(self, *args, current=None, **kwargs):
        self.current = current
        super().__init__(*args, **kwargs)

    def clean(self, value):
        # Keeping an existing inactive assignment is not a new assignment.
        if self.current is not None and not self.current.is_active and str(value) == str(self.current.pk):
            return self.current
        return super().clean(value)


class CommercialRelationshipForm(forms.Form):
    def __init__(self, *args, actor, company, model, editing=False, existing_category=None, existing_customer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.customer_mode = model._meta.model_name == 'customer'
        self.existing_customer = existing_customer
        if not editing or self.customer_mode:
            self.fields['person'] = forms.ModelChoiceField(
                label='Persona', required=not editing,
                queryset=person_access_policy.visible_people(actor=actor, company=company).order_by('full_name', 'pk'),
                error_messages={'invalid_choice': 'La identidad no está disponible.'},
            )
        for name in ('credit_limit', 'notes') if model._meta.model_name == 'customer' else ('notes',):
            field = model._meta.get_field(name).formfield()
            if name == 'credit_limit':
                field = forms.DecimalField(label='Límite de crédito', min_value=0,
                    max_digits=field.max_digits, decimal_places=field.decimal_places)
            else:
                field.label = 'Notas'
                field.widget = forms.Textarea(attrs={'rows': 3})
            self.fields[name] = field
        self.current_category = None
        if model._meta.model_name == 'customer':
            if existing_category is not None and existing_category.company_id == company.pk:
                self.current_category = existing_category
            inactive = self.current_category is not None and not self.current_category.is_active
            self.fields['category'] = CustomerCategoryChoice(
                label='Categoría de cliente', required=False,
                queryset=CustomerCategory.objects.filter(company=company, is_active=True).order_by('code', 'pk'),
                current=self.current_category,
                empty_label='Conservar categoría actual (inactiva)' if inactive else 'Sin categoría',
                error_messages={'invalid_choice': 'Seleccione una categoría activa de esta empresa.'},
            )
            initial_category = self.initial.get('category')
            if isinstance(initial_category, CustomerCategory):
                initial_category = initial_category.pk
            if inactive and (initial_category in (None, '') or str(initial_category) == str(self.current_category.pk)):
                self.initial['category'] = None

    def clean(self):
        values = super().clean()
        controls = {'csrfmiddlewaretoken', 'draft', 'related'} if self.customer_mode else {'csrfmiddlewaretoken'}
        if set(self.data) - set(self.fields) - controls:
            raise ValidationError('Se enviaron campos no permitidos.', code='invalid_fields')
        if self.existing_customer is not None:
            from people.services import customer_maintenance
            person = values.get('person')
            if 'person' in self.data and not self.data.get('person'):
                self.add_error('person', ValidationError('Seleccione una Persona.', code='required'))
            elif person is not None and person.pk != self.existing_customer.person_id and customer_maintenance.has_documents(self.existing_customer):
                self.add_error('person', ValidationError(customer_maintenance.PERSON_DOCUMENTS_MESSAGE, code='person_has_documents'))
        return values

    def commercial_data(self):
        data = {name: value for name, value in self.cleaned_data.items() if name != 'person'}
        if self.existing_customer is not None and 'person' in self.data and 'person' in self.cleaned_data:
            data['person'] = self.cleaned_data['person']
        if 'category' in data and ('category' not in self.data or (
                self.current_category is not None and not self.current_category.is_active
                and data['category'] is None)):
            data.pop('category')
        return data
