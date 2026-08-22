from core.models import Company, Branch


class ERPContextMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        request.company = None
        request.branch = None

        company_id = request.session.get("company_id")
        branch_id = request.session.get("branch_id")

        if company_id:
            request.company = Company.objects.filter(
                pk=company_id
            ).first()

        if branch_id:
            request.branch = Branch.objects.filter(
                pk=branch_id
            ).first()

        response = self.get_response(request)

        return response
    
    """from core.models import Company, Branch


class ERPContextMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        request.company = None
        request.branch = None

        company_id = request.session.get("company_id")
        branch_id = request.session.get("branch_id")

        if company_id:
            try:
                request.company = Company.objects.get(pk=company_id)
            except Company.DoesNotExist:
                pass

        if branch_id:
            try:
                request.branch = Branch.objects.get(pk=branch_id)
            except Branch.DoesNotExist:
                pass

        response = self.get_response(request)

        return response"""