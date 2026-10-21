from django.urls import path

from people import views, commercial_views, customer_category_views
from people.forms import GEOGRAPHY

urlpatterns = [
    path('persons/identification/detect/', views.person_identification_detect, name='person_identification_detect'),
    path("customers/<int:pk>/delete/", commercial_views.customer_delete, name="customer_delete"),
    path("customers/categories/", customer_category_views.category_list, name="customer_category_list"),
    path("customers/categories/new/", customer_category_views.category_form, name="customer_category_create"),
    path("customers/categories/<int:pk>/", customer_category_views.category_detail, name="customer_category_detail"),
    path("customers/categories/<int:pk>/edit/", customer_category_views.category_form, name="customer_category_update"),
    path("customers/categories/<int:pk>/deactivate/", customer_category_views.category_activity,
         {"is_active": False}, name="customer_category_deactivate"),
    path("customers/categories/<int:pk>/reactivate/", customer_category_views.category_activity,
         {"is_active": True}, name="customer_category_reactivate"),
    path("", views.person_list, name="person_list"),
    path("new/", views.person_create, name="person_create"),
    path("<int:pk>/", views.person_detail, name="person_detail"),
    path("<int:pk>/edit/", views.person_update, name="person_update"),
]
for kind in GEOGRAPHY:
    urlpatterns += [
        path(f"geography/{kind}/", views.geography_list, {"kind": kind}, name=kind + "_list"),
        path(f"geography/{kind}/new/", views.geography_edit, {"kind": kind}, name=kind + "_create"),
        path(f"geography/{kind}/<int:pk>/edit/", views.geography_edit, {"kind": kind}, name=kind + "_update"),
        path(f"geography/{kind}/<int:pk>/delete/", views.geography_delete, {"kind": kind}, name=kind + "_delete"),
    ]

for role, prefix in (('customer', 'customers'), ('supplier', 'suppliers')):
    urlpatterns += [
        path(f"{prefix}/", commercial_views.commercial_list, {"role": role}, name=role + "_list"),
        path(f"{prefix}/new/", commercial_views.commercial_form, {"role": role}, name=role + "_create"),
        path(f"{prefix}/<int:pk>/", commercial_views.commercial_detail, {"role": role}, name=role + "_detail"),
        path(f"{prefix}/<int:pk>/edit/", commercial_views.commercial_form, {"role": role}, name=role + "_update"),
        path(f"{prefix}/<int:pk>/deactivate/", commercial_views.commercial_activity,
             {"role": role, "is_active": False}, name=role + "_deactivate"),
        path(f"{prefix}/<int:pk>/reactivate/", commercial_views.commercial_activity,
             {"role": role, "is_active": True}, name=role + "_reactivate"),
    ]
