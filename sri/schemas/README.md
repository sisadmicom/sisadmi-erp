# Esquemas XML usados en R-04

`factura_V1.1.0.xsd` se conserva sin modificaciones desde el ZIP oficial enlazado
por [SRI — Facturación electrónica](https://www.sri.gob.ec/facturacion-electronica),
sección Esquemas XSD y XML Factura. Se eligió 1.1.0 para la factura simple sin
rubros de terceros ni sustitución de guía. `provenance.json` registra origen y hashes.

La dependencia `xmldsig-core-schema.xsd` proviene de la distribución SignXML ya
instalada. Se retienen íntegramente su copyright W3C y licencia; no se instaló una
dependencia nueva. La compilación/validación usa solo estos archivos locales.

Los mapeos se verificaron en la [ficha técnica oficial 2.34, julio 2026](https://www.sri.gob.ec/o/sri-portlet-biblioteca-alfresco-internet/descargar/f8d9bb36-5632-4f96-b463-b9265b55338c/FICHA%20TE%CC%81CNICA%20COMPROBANTES%20ELECTRO%CC%81NICOS%20ESQUEMA%20OFFLINE%20Versio%CC%81n%202.34.pdf),
tablas 16/17 (páginas impresas 29/30) y 24 (página 79). Estos códigos serializan
snapshots existentes, no determinan la tarifa vigente ni reemplazan el motor de impuestos.

Validación XSD no equivale a cumplimiento fiscal completo ni autorización.
Antes de un envío deben verificarse la firma, el ambiente, el emisor real y las
reglas aplicables a su régimen/actividad. La ficha 2.34 también incluye requisitos
condicionales como RIMPE, agentes de retención, transporte y RUC del proveedor
(anexo 26); el modelo actual no contiene todos esos datos. Su aplicabilidad y fecha
efectiva requieren revisión antes de usar un emisor real.
