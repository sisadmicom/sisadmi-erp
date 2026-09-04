from xml.etree.ElementTree import fromstring, tostring

from sri.services.xml_signer import XmlSigner


class TestXmlSigner(XmlSigner):
    """
    Firmador falso utilizado exclusivamente para pruebas.

    No realiza una firma criptográfica real.
    """

    def sign(self, xml):

        root = fromstring(xml)

        root.set(
            "firma",
            "TEST-SIGNATURE",
        )

        return tostring(
            root,
            encoding="unicode",
        )