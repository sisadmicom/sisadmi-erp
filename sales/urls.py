from django.urls import path

from . import views


urlpatterns = [
    path("create/", views.sale_create, name="sale_create"),
    path("<int:sale_id>/", views.sale_detail, name="sale_detail"),
    path("<int:sale_id>/confirm/", views.sale_confirm, name="sale_confirm"),
]
