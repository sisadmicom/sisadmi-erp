from core.exceptions import InvalidPrice
from core.validators.quantity_line_validator import QuantityLineValidator


class CommercialLineValidator:
    @staticmethod
    def validate(line):
        QuantityLineValidator.validate(line)
        if line.unit_price < 0:
            raise InvalidPrice()
