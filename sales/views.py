from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.views.decorators.http import require_http_methods

from core.constants.document_status import DocumentStatus
from core.exceptions import InvalidPrice, InvalidQuantity
from inventory.models import Warehouse
from people.models import Customer
from sales.dto.sale_create_dto import SaleCreateDTO
from sales.dto.sale_detail_dto import SaleDetailDTO
from sales.forms import FiscalPreparationForm, SaleCreateForm, SaleDetailFormSet
from sales.models import Sale
from sales.use_cases.confirm_sale import ConfirmSale
from sales.use_cases.create_sale import CreateSale
from sri.services.fiscal_document_preparation_service import (
    FiscalDocumentPreparationService,
)


def _active_context_or_redirect(request):
    if request.active_company is None:
        return redirect("select_company")
    if request.active_branch is None:
        return redirect("select_branch")
    return None


def _login_with_path_only(view):
    """Keep caller-supplied query parameters out of the login return URL."""
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(
                request.path,
                login_url=resolve_url("login"),
            )
        return view(request, *args, **kwargs)

    return wrapped


def _sale_detail_response(
    request,
    sale,
    *,
    confirmation_error=None,
    fiscal_preparation_form=None,
):
    if fiscal_preparation_form is None:
        fiscal_preparation_form = FiscalPreparationForm(branch=request.active_branch)
    return render(
        request,
        "sales/sale_detail.html",
        {
            "sale": sale,
            "confirmation_error": confirmation_error,
            "fiscal_preparation_form": fiscal_preparation_form,
        },
    )


@_login_with_path_only
@login_required(login_url="login")
@require_http_methods(["GET", "HEAD", "POST"])
def sale_create(request):
    context_response = _active_context_or_redirect(request)
    if context_response is not None:
        return context_response

    company = request.active_company
    branch = request.active_branch
    form_kwargs = {"company": company, "branch": branch}
    if request.method == "POST":
        form = SaleCreateForm(request.POST, **form_kwargs)
        formset = SaleDetailFormSet(
            request.POST,
            prefix="details",
            form_kwargs={"company": company},
        )
        form_is_valid = form.is_valid()
        formset_is_valid = formset.is_valid()
        if form_is_valid and formset_is_valid:
            dto = SaleCreateDTO(
                company_id=company.pk,
                branch_id=branch.pk,
                customer_id=form.cleaned_data["customer_id"].pk,
                warehouse_id=form.cleaned_data["warehouse_id"].pk,
                issue_date=form.cleaned_data["issue_date"],
                notes=form.cleaned_data["notes"],
                details=[
                    SaleDetailDTO(
                        product_id=line.cleaned_data["product_id"].pk,
                        quantity=line.cleaned_data["quantity"],
                        unit_price=line.cleaned_data["unit_price"],
                        discount=line.cleaned_data["discount"],
                    )
                    for line in formset.forms
                    if line.has_changed()
                ],
            )
            try:
                sale = CreateSale.execute(dto)
            except InvalidQuantity:
                form.add_error(None, "Una de las cantidades no es válida.")
            except InvalidPrice:
                form.add_error(None, "Uno de los precios no es válido.")
            else:
                return redirect("sale_detail", sale_id=sale.pk)
    else:
        form = SaleCreateForm(**form_kwargs)
        formset = SaleDetailFormSet(
            prefix="details",
            form_kwargs={"company": company},
        )

    return render(
        request,
        "sales/sale_form.html",
        {"form": form, "formset": formset},
    )


@_login_with_path_only
@login_required(login_url="login")
@require_http_methods(["GET", "HEAD"])
def sale_detail(request, sale_id):
    context_response = _active_context_or_redirect(request)
    if context_response is not None:
        return context_response

    sale = get_object_or_404(
        Sale.objects.select_related("customer", "customer__person", "warehouse"),
        pk=sale_id,
        company=request.active_company,
        branch=request.active_branch,
    )
    return _sale_detail_response(request, sale)


@_login_with_path_only
@login_required(login_url="login")
@require_http_methods(["POST"])
def sale_prepare_fiscal(request, sale_id):
    context_response = _active_context_or_redirect(request)
    if context_response is not None:
        return context_response

    sale = get_object_or_404(
        Sale,
        pk=sale_id,
        company=request.active_company,
        branch=request.active_branch,
    )
    form = FiscalPreparationForm(request.POST, branch=request.active_branch)
    if not form.is_valid():
        return _sale_detail_response(request, sale, fiscal_preparation_form=form)

    try:
        FiscalDocumentPreparationService.prepare(
            sale=sale,
            point_of_emission=form.cleaned_data["point_of_emission"],
        )
    except ValueError:
        form.add_error(None, "La preparación fiscal no pudo completarse.")
        return _sale_detail_response(request, sale, fiscal_preparation_form=form)

    messages.success(request, "La preparación fiscal se completó.")
    return redirect("sale_detail", sale_id=sale.pk)


@_login_with_path_only
@login_required(login_url="login")
@require_http_methods(["POST"])
def sale_confirm(request, sale_id):
    context_response = _active_context_or_redirect(request)
    if context_response is not None:
        return context_response

    sale = get_object_or_404(
        Sale,
        pk=sale_id,
        company=request.active_company,
        branch=request.active_branch,
    )
    try:
        ConfirmSale.execute(sale_id=sale.pk, user=request.user)
    except ValueError:
        return _sale_detail_response(
            request,
            sale,
            confirmation_error="La venta no pudo confirmarse en su estado actual.",
        )
    return redirect("sale_detail", sale_id=sale.pk)
