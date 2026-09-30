from django.urls import path

from . import views


urlpatterns = [
    path(
        "electronic-documents/<int:electronic_document_id>/authorize/",
        views.electronic_document_authorize,
        name="electronic_document_authorize",
    ),
]
