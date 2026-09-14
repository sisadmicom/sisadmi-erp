"""Small, explicit access policy for the active company context."""


def authorized_companies(user):
    if not getattr(user, "is_authenticated", False):
        return []
    profile = getattr(user, "profile", None)
    return profile.companies.all() if profile is not None else []


def authorized_branches(user, company):
    if not getattr(user, "is_authenticated", False):
        return company.branch_set.none()
    companies = authorized_companies(user)
    if not companies.filter(pk=company.pk).exists():
        return company.branch_set.none()
    profile = getattr(user, "profile", None)
    return profile.branches.filter(company=company) if profile is not None else company.branch_set.none()
