from django.urls import path

from . import views


urlpatterns = [

    path(
        "units/",
        views.unit_list,
        name="unit_list"
    ),

    path(
        "units/create/",
        views.unit_create,
        name="unit_create"
    ),

    path(
        "units/<int:pk>/edit/",
        views.unit_update,
        name="unit_update"
    ),

    path(
        "units/<int:pk>/delete/",
        views.unit_delete,
        name="unit_delete"
    ),
    
    path(
        "products/",
        views.product_list,
        name="product_list"
    ),

    path(
        "products/create/",
        views.product_create,
        name="product_create"
    ),

    path(
        "products/<int:pk>/edit/",
        views.product_update,
        name="product_update"
    ),

    path(
        "products/<int:pk>/delete/",
        views.product_delete,
        name="product_delete"
    ),

]