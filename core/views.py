from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from core.validators.access_validator import authorized_companies, authorized_branches, context_pk
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponseForbidden

from core.forms import FoundingPersonForm
from core.models import Company
from django.contrib import messages
from core.services.initial_company_setup import can_configure_company


@login_required
@require_http_methods(["GET", "HEAD", "POST"])
def founding_person_edit(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("La edición administrativa requiere un superusuario.")
    company = request.active_company
    if company is None:
        return redirect("select_company")
    form = FoundingPersonForm(
        request.POST if request.method == "POST" else None,
        instance=company.person,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            person = form.save(commit=False)
            person.updated_by = request.user
            person.save(update_fields=(*form.Meta.fields, "updated_by", "updated_at"))
        messages.success(request, "Datos de la identidad legal actualizados.")
        return redirect("dashboard")
    return render(request, "core/founding_person_edit.html", {"form": form, "company": company})


@login_required
@require_http_methods(["GET", "HEAD", "POST"])
def initial_setup(request):
    from core.setup_views import wizard
    if Company.objects.exists():
        return redirect("select_company")
    return wizard(request)


@login_required
def login_view0(request):
    return render(request, "core/login.html")

def login_view(request):

    login_error = None

    if request.method == "POST":
        

        username = request.POST.get("username")
        password = request.POST.get("password")


        user = authenticate(
            request,
            username=username,
            password=password
        )


        if user is not None:

            login(request, user)


            request.session["company_id"] = None
            request.session["branch_id"] = None

            return redirect("company_create" if can_configure_company(user) else "select_company")
        

        login_error = "Usuario o contraseña incorrectos."

    return render(request, "core/login.html", {"login_error": login_error})


@login_required
@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
@require_http_methods(["GET", "HEAD", "POST"])
def select_company(request):


    if not request.user.is_authenticated:
        return redirect("login")

    companies = authorized_companies(request.user)


    if request.method == "POST":
        company_id = context_pk(request.POST.get("company_id"))
        company = authorized_companies(request.user).filter(pk=company_id).first()
        if company is None:
            return redirect("select_company")
        request.session["company_id"] = company.pk
        request.session["branch_id"] = None
        request.session.pop("pending_branch_id", None)

        return redirect("select_branch")

    return render(request, "core/select_company.html", {
        "companies": companies,
        "can_configure_company": can_configure_company(request.user),
    })

@login_required
@require_http_methods(["GET", "HEAD", "POST"])
def select_branch(request):
    if not request.user.is_authenticated:
        return redirect("login")

    company_id = context_pk(request.session.get("company_id"))
    company = authorized_companies(request.user).filter(pk=company_id).first()
    if company is None:
        request.session["company_id"] = None
        request.session["branch_id"] = None
        return redirect("select_company")

    branches = authorized_branches(request.user, company)

    if request.method == "POST":
        branch_id = context_pk(request.POST.get("branch_id"))
        branch = branches.filter(pk=branch_id).first()
        if branch is None:
            request.session["branch_id"] = None
            return redirect("select_branch")
        request.session["company_id"] = company.pk
        request.session["branch_id"] = branch.pk
        request.session.pop("pending_branch_id", None)

        return redirect("dashboard")

    selected = branches.filter(pk=context_pk(request.session.get("pending_branch_id"))).first()
    from core.services.branch_maintenance import can_create_branch
    return render(request, "core/select_branch.html", {
        "branches": branches, "company": company,
        "has_branches": company.branch_set.exists(),
        "can_add_branch": can_create_branch(request.user, company),
        "selected_branch_id": selected.pk if selected else None,
    })

@login_required
def dashboard(request):

    if not request.company:
        return redirect("select_company")

    if not request.branch:
        return redirect("select_branch")

    return render(
        request,
        "core/dashboard.html"
    )
