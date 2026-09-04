class SriClient:
    """
    Cliente de comunicación con los servicios web del SRI.

    En esta primera etapa no realiza comunicación real.
    Su objetivo es definir la interfaz que utilizará
    SriSubmissionService.

    Posteriormente aquí implementaremos SOAP.
    """

    def send(self, xml, environment):
        """
        Envía un XML al servicio de recepción del SRI.

        Esta implementación es solamente una base para
        pruebas y desarrollo.
        """

        raise NotImplementedError(
            "El cliente SRI real todavía no está implementado."
        )
