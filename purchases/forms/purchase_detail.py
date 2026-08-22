from django import forms

from purchases.models import PurchaseDetail


class PurchaseDetailForm(forms.ModelForm):

    class Meta:

        model = PurchaseDetail

        exclude = (
            "purchase",
            "subtotal",
            "tax",
            "total",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "deleted_at",
            "is_active",
        )