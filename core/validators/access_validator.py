"""Explicit membership and activity policy for Company/Branch access context."""
from core.models import Company


def context_pk(value):
    """Reject malformed or out-of-range BigAutoField input before querying."""
    try:
        value = int(value)
        return value if 0 < value <= 9223372036854775807 else None
    except (TypeError, ValueError, OverflowError):
        return None


def authorized_companies(user):
    if not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False):
        return Company.objects.none()
    profile = getattr(user, 'profile', None)
    return profile.companies.filter(is_active=True) if profile is not None else Company.objects.none()


def authorized_branches(user, company):
    if not authorized_companies(user).filter(pk=company.pk).exists():
        return company.branch_set.none()
    profile = getattr(user, 'profile', None)
    return profile.branches.filter(company=company, is_active=True) if profile is not None else company.branch_set.none()
