from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from core.models import Company, Branch
from django.contrib.auth.decorators import login_required

@login_required
def login_view0(request):

    if request.method == "POST":
        print("POST RECIBIDO")

    return render(request, "core/login.html")

@login_required
def login_view(request):

    if request.method == "POST":
        
        print("METHOD:", request.method)

        username = request.POST.get("username")
        password = request.POST.get("password")

        print("USERNAME:", username)

        user = authenticate(
            request,
            username=username,
            password=password
        )

        print("USER:", user)

        if user is not None:

            login(request, user)

            print("LOGIN OK")

            request.session["company_id"] = None
            request.session["branch_id"] = None

            return redirect("select_company")
        
        print("LOGIN FAILED")

    return render(request, "core/login.html")

@login_required
def select_company(request):

    print("ENTRO A SELECT COMPANY")
    print("USER:", request.user)

    if not request.user.is_authenticated:
        return redirect("login")

    companies = request.user.profile.companies.all()

    print("COMPANIES:", companies)

    if request.method == "POST":
        company_id = request.POST.get("company_id")
        request.session["company_id"] = company_id

        return redirect("select_branch")

    return render(request, "core/select_company.html", {
        "companies": companies
    })

@login_required
def select_branch(request):
    if not request.user.is_authenticated:
        return redirect("login")

    company_id = request.session.get("company_id")

    branches = Branch.objects.filter(company_id=company_id)

    if request.method == "POST":
        branch_id = request.POST.get("branch_id")
        request.session["branch_id"] = branch_id

        return redirect("dashboard")

    return render(request, "core/select_branch.html", {
        "branches": branches
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