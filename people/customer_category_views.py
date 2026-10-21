from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from core.validators.access_validator import authorized_companies, authorized_branches
from people.customer_category_forms import CustomerCategoryForm
from people.models import CustomerCategory
from people.services import customer_continuation


def context(request, operation):
    company, branch = request.active_company, request.active_branch
    if (company is None or branch is None
            or not authorized_companies(request.user).filter(pk=company.pk).exists()
            or not authorized_branches(request.user, company).filter(pk=branch.pk).exists()
            or not request.user.has_perm(f"people.{operation}_customercategory")):
        raise PermissionDenied("Seleccione una empresa y sucursal autorizadas y compruebe sus permisos.")
    return CustomerCategory.objects.filter(company=company)


@login_required
@require_safe
def category_list(request):
    categories = context(request, "view")
    query = request.GET.get("q", "").strip()[:150]
    if query:
        categories = categories.filter(Q(code__icontains=query) | Q(name__icontains=query))
    return render(request, "people/customer_category_list.html", {
        "page": Paginator(categories, 25).get_page(request.GET.get("page")), "query": query,
    })


@login_required
@require_safe
def category_detail(request, pk):
    return render(request, "people/customer_category_detail.html", {
        "category": get_object_or_404(context(request, "view"), pk=pk),
    })


@login_required
@require_http_methods(["GET", "HEAD", "POST"])
def category_form(request, pk=None):
    categories = context(request, "change" if pk is not None else "add")
    token = request.POST.get('draft') if request.method == 'POST' else request.GET.get('draft')
    if token:
        if pk is not None:
            raise PermissionDenied
        customer_continuation.read(request, token, state='waiting', field='category')
        if request.method == 'POST' and request.POST.get('action') == 'cancel':
            return redirect(customer_continuation.finish(request, token))
    obj = get_object_or_404(categories, pk=pk) if pk is not None else None
    form = CustomerCategoryForm(request.POST if request.method == "POST" else None,
                                company=request.active_company, instance=obj)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                if obj is not None:
                    locked = get_object_or_404(categories.select_for_update(), pk=pk)
                    locked.code, locked.name = form.cleaned_data["code"], form.cleaned_data["name"]
                    locked.updated_by = request.user
                    locked.save(update_fields=["code", "name", "updated_by", "updated_at"])
                    obj = locked
                else:
                    obj = form.save(commit=False)
                    obj.created_by = obj.updated_by = request.user
                    obj.save()
                if token:
                    destination = customer_continuation.finish(request, token, obj)
        except IntegrityError as error:
            cause = error.__cause__
            if (getattr(cause, "sqlstate", None) != "23505" or
                    getattr(getattr(cause, "diag", None), "constraint_name", None) !=
                    "people_customer_category_company_code_unique"):
                raise
            form.add_error("code", "Ya existe una categoría con este código en la empresa.")
        else:
            messages.success(request, "Categoría guardada correctamente.")
            if token:
                return redirect(destination)
            return redirect("customer_category_detail", pk=obj.pk)
    return render(request, "people/customer_category_form.html", {"form": form, "editing": pk is not None, 'draft_token': token or ''})


@login_required
@require_POST
def category_activity(request, pk, is_active):
    with transaction.atomic():
        category = get_object_or_404(context(request, "change").select_for_update(), pk=pk)
        category.is_active = is_active
        category.updated_by = request.user
        category.save(update_fields=["is_active", "updated_by", "updated_at"])
    messages.success(request, "Categoría activada." if is_active else "Categoría desactivada.")
    return redirect("customer_category_detail", pk=category.pk)
