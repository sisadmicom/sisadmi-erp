from xml.etree.ElementTree import (
    Element,
    SubElement,
    tostring,
)

from xml.dom import minidom


class XmlGeneratorService:
    """
    Generador de XML para comprobantes electrónicos SRI.

    Primera versión:
    - Factura electrónica
    - Sin firma
    - Sin envío al SRI
    """

    @staticmethod
    def generate_invoice(electronic_document):

        sale = electronic_document.document

        factura = Element(
            "factura",
            {
                "id": "comprobante",
            },
        )

        # -----------------------------
        # Información tributaria
        # -----------------------------

        info_tributaria = SubElement(
            factura,
            "infoTributaria",
        )

        XmlGeneratorService._add(
            info_tributaria,
            "ambiente",
            electronic_document.environment,
        )

        XmlGeneratorService._add(
            info_tributaria,
            "tipoEmision",
            electronic_document.emission_type,
        )

        XmlGeneratorService._add(
            info_tributaria,
            "razonSocial",
            electronic_document.company.person.full_name,
        )

        XmlGeneratorService._add(
            info_tributaria,
            "ruc",
            electronic_document.company.person.identification,
        )

        XmlGeneratorService._add(
            info_tributaria,
            "claveAcceso",
            electronic_document.access_key,
        )

        XmlGeneratorService._add(
            info_tributaria,
            "codDoc",
            electronic_document.document_type,
        )

        XmlGeneratorService._add(
            info_tributaria,
            "estab",
            electronic_document.establishment,
        )

        XmlGeneratorService._add(
            info_tributaria,
            "ptoEmi",
            electronic_document.emission_point,
        )

        XmlGeneratorService._add(
            info_tributaria,
            "secuencial",
            electronic_document.sequential,
        )


        # -----------------------------
        # Información factura
        # -----------------------------

        info_factura = SubElement(
            factura,
            "infoFactura",
        )

        XmlGeneratorService._add(
            info_factura,
            "fechaEmision",
            sale.issue_date.strftime("%d/%m/%Y"),
        )

        XmlGeneratorService._add(
            info_factura,
            "identificacionComprador",
            sale.customer.person.identification,
        )

        XmlGeneratorService._add(
            info_factura,
            "razonSocialComprador",
            sale.customer.person.full_name,
        )

        XmlGeneratorService._add(
            info_factura,
            "totalSinImpuestos",
            sale.subtotal,
        )

        XmlGeneratorService._add(
            info_factura,
            "importeTotal",
            sale.total,
        )

        # -----------------------------
        # Totales de impuestos
        # -----------------------------

        total_impuestos = SubElement(
            info_factura,
            "totalConImpuestos",
        )

        taxes = {}

        for detail in sale.details.all():

            for applied_tax in detail.applied_taxes.all():

                key = (
                    applied_tax.tax_code,
                    applied_tax.tax_name,
                )

                if key not in taxes:
                    taxes[key] = {
                        "base": 0,
                        "amount": 0,
                        "rate": applied_tax.rate,
                    }

                taxes[key]["base"] += applied_tax.base
                taxes[key]["amount"] += applied_tax.amount


        for key, values in taxes.items():

            tax_code, tax_name = key

            total_impuesto = SubElement(
                total_impuestos,
                "totalImpuesto",
            )

            XmlGeneratorService._add(
                total_impuesto,
                "codigo",
                tax_code,
            )

            XmlGeneratorService._add(
                total_impuesto,
                "nombre",
                tax_name,
            )

            XmlGeneratorService._add(
                total_impuesto,
                "tarifa",
                values["rate"],
            )

            XmlGeneratorService._add(
                total_impuesto,
                "baseImponible",
                values["base"],
            )

            XmlGeneratorService._add(
                total_impuesto,
                "valor",
                values["amount"],
            )


        # -----------------------------
        # Detalles
        # -----------------------------

        detalles = SubElement(
            factura,
            "detalles",
        )


        for detail in sale.details.all():

            detalle = SubElement(
                detalles,
                "detalle",
            )

            XmlGeneratorService._add(
                detalle,
                "codigoPrincipal",
                detail.product.code,
            )

            XmlGeneratorService._add(
                detalle,
                "descripcion",
                detail.product.name,
            )

            XmlGeneratorService._add(
                detalle,
                "cantidad",
                detail.quantity,
            )

            XmlGeneratorService._add(
                detalle,
                "precioUnitario",
                detail.unit_price,
            )

            XmlGeneratorService._add(
                detalle,
                "descuento",
                detail.discount,
            )

            XmlGeneratorService._add(
                detalle,
                "precioTotalSinImpuesto",
                detail.subtotal,
            )


            # -----------------------------
            # Impuestos del detalle
            # -----------------------------

            impuestos = SubElement(
                detalle,
                "impuestos",
            )

            for applied_tax in detail.applied_taxes.all():

                impuesto = SubElement(
                    impuestos,
                    "impuesto",
                )

                XmlGeneratorService._add(
                    impuesto,
                    "codigo",
                    applied_tax.tax_code,
                )

                XmlGeneratorService._add(
                    impuesto,
                    "nombre",
                    applied_tax.tax_name,
                )

                XmlGeneratorService._add(
                    impuesto,
                    "codigoPorcentaje",
                    applied_tax.tax_code,
                )

                XmlGeneratorService._add(
                    impuesto,
                    "tarifa",
                    applied_tax.rate,
                )

                XmlGeneratorService._add(
                    impuesto,
                    "baseImponible",
                    applied_tax.base,
                )

                XmlGeneratorService._add(
                    impuesto,
                    "valor",
                    applied_tax.amount,
                )


        xml = tostring(
            factura,
            encoding="utf-8",
        )

        return minidom.parseString(
            xml
        ).toprettyxml(
            indent="  ",
            encoding="utf-8",
        ).decode("utf-8")


    @staticmethod
    def _add(parent, name, value):

        node = SubElement(
            parent,
            name,
        )

        node.text = str(
            value
        )

        return node
