from django.urls import path
from . import views, company_views, branch_views

urlpatterns = [
    path("branches/new/", branch_views.branch_create, name="branch_create"),
    path("companies/<int:pk>/", company_views.company_detail, name="company_detail"),
    path("companies/new/", company_views.company_create, name="company_create"),
    path("founding-person/edit/", views.founding_person_edit, name="founding_person_edit"),
    path("initial-setup/", views.initial_setup, name="initial_setup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("select-company/", views.select_company, name="select_company"),
    path("select-branch/", views.select_branch, name="select_branch"),
    path("dashboard/", views.dashboard, name="dashboard"),
]
