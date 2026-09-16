from sales.services.sales_return_creator import SalesReturnCreator
class CreateSalesReturn:
    @staticmethod
    def execute(dto):
        return SalesReturnCreator.execute(dto)
