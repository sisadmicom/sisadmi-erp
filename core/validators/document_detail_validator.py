from core.exceptions import EmptyDocument


class DocumentDetailValidator:
    @staticmethod
    def validate_required(has_details):
        if not has_details:
            raise EmptyDocument()
