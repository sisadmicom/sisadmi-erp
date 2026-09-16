from sales.services.sales_return_confirmation_service import SalesReturnConfirmationService
class ConfirmSalesReturn:
    @staticmethod
    def execute(sales_return_id,user=None):
        return SalesReturnConfirmationService.execute(sales_return_id,user)
