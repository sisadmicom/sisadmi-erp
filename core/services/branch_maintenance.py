"""Scoped initial administrative Branch creation, without operational activation."""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from core.models import Branch, Company
from users.models import UserProfile
from core.validators.access_validator import authorized_companies


def can_create_branch(actor, company):
    # Initial administrative authority is explicit; superuser never replaces scope.
    # General delegated/multi-company Branch administration is a later slice.
    return bool(actor.is_authenticated and actor.is_active and actor.is_superuser
                and getattr(actor, 'profile', None) is not None
                and actor.has_perm('core.add_branch') and company and company.is_active
                and authorized_companies(actor).filter(pk=company.pk).exists())


@transaction.atomic
def create_branch(*, actor, company, data):
    profile = UserProfile.objects.select_for_update().filter(user=actor).first()
    company = Company.objects.select_for_update().filter(pk=company.pk).first()
    if profile is None or not can_create_branch(actor, company):
        raise PermissionDenied
    branch = Branch(company=company, created_by=actor, updated_by=actor,
                    **{field: data[field] for field in ('code', 'name', 'address', 'is_main')})
    branch.full_clean()
    branch.save()
    profile.branches.add(branch)
    return branch
