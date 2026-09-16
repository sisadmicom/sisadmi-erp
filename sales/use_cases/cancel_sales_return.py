from sales.services.sales_return_cancellation_service import SalesReturnCancellationService
class CancelSalesReturn:
    @staticmethod
    def execute(sales_return_id,user=None):
        return SalesReturnCancellationService.execute(sales_return_id,user)
