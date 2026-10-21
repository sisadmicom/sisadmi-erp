from django.urls import path

from . import group_views, subgroup_views, views


urlpatterns = [
    path("subgroups/", subgroup_views.subgroup_list, name="subgroup_list"),
    path("subgroups/<int:pk>/", subgroup_views.subgroup_detail, name="subgroup_detail"),
    path("subgroups/create/", subgroup_views.subgroup_create, name="subgroup_create"),
    path("subgroups/<int:pk>/edit/", subgroup_views.subgroup_update, name="subgroup_update"),
    path("subgroups/<int:pk>/delete/", subgroup_views.subgroup_delete, name="subgroup_delete"),
    path("groups/", group_views.group_list, name="group_list"),
    path("groups/<int:pk>/", group_views.group_detail, name="group_detail"),
    path("groups/create/", group_views.group_create, name="group_create"),
    path("groups/<int:pk>/edit/", group_views.group_update, name="group_update"),
    path("groups/<int:pk>/delete/", group_views.group_delete, name="group_delete"),
    path("units/<int:pk>/", views.unit_detail, name="unit_detail"),
    path("brands/<int:pk>/", views.brand_detail, name="brand_detail"),
    path("brands/", views.brand_list, name="brand_list"),
    path("brands/create/", views.brand_create, name="brand_create"),
    path("brands/<int:pk>/edit/", views.brand_update, name="brand_update"),
    path("brands/<int:pk>/delete/", views.brand_delete, name="brand_delete"),
    path("products/<int:pk>/", views.product_detail, name="product_detail"),

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