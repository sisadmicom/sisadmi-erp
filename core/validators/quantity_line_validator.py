from core.exceptions import InvalidQuantity


class QuantityLineValidator:
    @staticmethod
    def validate(line):
        if line.quantity <= 0:
            raise InvalidQuantity()
