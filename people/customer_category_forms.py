from django import forms

from people.models import CustomerCategory


class CustomerCategoryForm(forms.ModelForm):
    class Meta:
        model = CustomerCategory
        fields = ("code", "name")

    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.company = company
        self.fields["code"].help_text = "Código único dentro de esta empresa. Se guarda en mayúsculas."

    def clean_code(self):
        code = self.cleaned_data["code"].upper()
        if CustomerCategory.objects.filter(company=self.instance.company, code=code).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe una categoría con este código en la empresa.", code="duplicate_code")
        return code
