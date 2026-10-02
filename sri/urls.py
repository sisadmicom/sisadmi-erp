from django.urls import path

from . import views


urlpatterns = [
    path(
        "electronic-documents/<int:electronic_document_id>/receive/",
        views.electronic_document_receive,
        name="electronic_document_receive",
    ),
    path(
        "electronic-documents/<int:electronic_document_id>/authorize/",
        views.electronic_document_authorize,
        name="electronic_document_authorize",
    ),
    path(
        "electronic-documents/<int:electronic_document_id>/sign/",
        views.electronic_document_sign,
        name="electronic_document_sign",
    ),
]
