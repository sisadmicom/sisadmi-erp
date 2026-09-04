import secrets


class AccessKeyService:
    """
    Servicio responsable de generar la clave de acceso SRI.
    """

    @staticmethod
    def generate_numeric_code():
        """
        Genera un código numérico de exactamente 8 dígitos.
        """

        return f"{secrets.randbelow(100_000_000):08d}"


    @staticmethod
    def calculate_mod11(value):
        """
        Calcula el dígito verificador utilizando el algoritmo
        módulo 11 utilizado por el SRI.
        """

        total = 0
        factor = 2

        for digit in reversed(value):

            total += int(digit) * factor

            factor += 1

            if factor > 7:
                factor = 2

        remainder = total % 11

        verifier = 11 - remainder

        if verifier == 11:
            return "0"

        if verifier == 10:
            return "1"

        return str(verifier)


    @staticmethod
    def generate(
        issue_date,
        document_type,
        ruc,
        environment,
        establishment,
        emission_point,
        sequential,
        numeric_code,
        emission_type,
    ):
        """
        Genera una clave de acceso SRI de 49 dígitos.

        Estructura:

        Fecha                 8
        Tipo comprobante     2
        RUC                  13
        Ambiente              1
        Serie                 6
        Secuencial            9
        Código numérico       8
        Tipo emisión          1
        Dígito verificador    1
        """

        issue_date = issue_date.strftime("%d%m%Y")

        document_type = str(
            document_type
        ).zfill(2)

        ruc = str(
            ruc
        ).zfill(13)

        environment = str(
            environment
        )

        establishment = str(
            establishment
        ).zfill(3)

        emission_point = str(
            emission_point
        ).zfill(3)

        sequential = str(
            sequential
        ).zfill(9)

        numeric_code = str(
            numeric_code
        ).zfill(8)

        emission_type = str(
            emission_type
        )


        base = (
            issue_date
            + document_type
            + ruc
            + environment
            + establishment
            + emission_point
            + sequential
            + numeric_code
            + emission_type
        )


        if len(base) != 48:

            raise ValueError(
                "La base de la clave de acceso debe "
                "tener exactamente 48 dígitos."
            )


        verifier = AccessKeyService.calculate_mod11(
            base
        )


        return base + verifier



    @staticmethod
    def generate_from_document(
        electronic_document,
    ):
        """
        Genera la clave de acceso directamente
        desde un ElectronicDocument.
        """

        return AccessKeyService.generate(

            issue_date=(
                electronic_document
                .document
                .issue_date
            ),

            document_type=(
                electronic_document
                .document_type
            ),

            ruc=(
                electronic_document
                .company
                .person
                .identification
            ),

            environment=(
                electronic_document
                .environment
            ),

            establishment=(
                electronic_document
                .establishment
            ),

            emission_point=(
                electronic_document
                .emission_point
            ),

            sequential=(
                electronic_document
                .sequential
            ),

            numeric_code=(
                electronic_document
                .numeric_code
            ),

            emission_type=(
                electronic_document
                .emission_type
            ),
        )
