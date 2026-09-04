from xml.etree import ElementTree as ET


class XmlValidationService:
    """
    Servicio encargado de validar la estructura básica
    del XML de comprobantes electrónicos SRI.

    En esta fase:
    - No valida XSD oficial SRI.
    - No valida firma electrónica.
    - No envía al SRI.

    Solo verifica estructura mínima.
    """

    REQUIRED_TAGS = [
        "infoTributaria",
        "infoFactura",
        "detalles",
    ]

    @staticmethod
    def validate(xml_content):
        """
        Recibe XML como string.

        Retorna True si cumple estructura mínima.
        Caso contrario lanza ValueError.
        """

        try:
            root = ET.fromstring(xml_content)

        except ET.ParseError:
            raise ValueError(
                "El contenido recibido no es un XML válido."
            )

        if root.tag != "factura":
            raise ValueError(
                "El XML debe tener nodo raíz factura."
            )

        for tag in XmlValidationService.REQUIRED_TAGS:

            if root.find(tag) is None:
                raise ValueError(
                    f"Falta nodo requerido: {tag}"
                )

        detalles = root.find("detalles")

        if len(detalles.findall("detalle")) == 0:
            raise ValueError(
                "La factura debe contener al menos un detalle."
            )

        return True
