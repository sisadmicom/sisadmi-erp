class SriEnvironment:
    TEST = "1"
    PRODUCTION = "2"

    CHOICES = (
        (TEST, "Pruebas"),
        (PRODUCTION, "Producción"),
    )


class SriEmissionType:
    NORMAL = "1"

    CHOICES = (
        (NORMAL, "Emisión normal"),
    )
