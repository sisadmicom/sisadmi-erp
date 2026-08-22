from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("select-company/", views.select_company, name="select_company"),
    path("select-branch/", views.select_branch, name="select_branch"),
    path("dashboard/", views.dashboard, name="dashboard"),
]