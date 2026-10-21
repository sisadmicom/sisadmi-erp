from core.validators.access_validator import authorized_companies, authorized_branches, context_pk


class ERPContextMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.active_company = None
        request.active_branch = None
        stored_company = request.session.get("company_id")
        stored_branch = request.session.get("branch_id")
        company_id = context_pk(stored_company)
        branch_id = context_pk(stored_branch)

        if getattr(request.user, "is_authenticated", False):
            company = authorized_companies(request.user).filter(pk=company_id).first()
            if company is None:
                if stored_company or stored_branch:
                    request.session["company_id"] = None
                    request.session["branch_id"] = None
            else:
                request.active_company = company
                branch = authorized_branches(request.user, company).filter(pk=branch_id).first()
                if branch is not None:
                    request.active_branch = branch
                elif stored_branch:
                    request.session["branch_id"] = None

        request.company = request.active_company
        request.branch = request.active_branch
        return self.get_response(request)
