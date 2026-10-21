"""Normal Branch maintenance in the selected, authorized Company."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core.branch_forms import BranchForm
from core.related_fields import field_rows
from core.services.branch_maintenance import can_create_branch, create_branch


@login_required
@require_http_methods(['GET', 'HEAD', 'POST'])
def branch_create(request):
    company = request.active_company
    if not can_create_branch(request.user, company):
        raise PermissionDenied
    if request.method == 'POST' and request.POST.get('action') == 'cancel':
        return redirect('select_branch')
    form = BranchForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        branch = create_branch(actor=request.user, company=company, data=form.cleaned_data)
        request.session['pending_branch_id'] = branch.pk
        return redirect('select_branch')
    return render(request, 'core/branch_form.html', {
        'form': form, 'company': company, 'field_rows': field_rows(form, {}, request.user),
    })
