"""Normal Branch fields; Company is resolved by the server."""
from django import forms
from core.models import Branch


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ('code', 'name', 'address', 'is_main')
        labels = {'code': 'Código', 'name': 'Nombre', 'address': 'Dirección', 'is_main': 'Es matriz'}
        widgets = {'address': forms.Textarea(attrs={'rows': 3})}
