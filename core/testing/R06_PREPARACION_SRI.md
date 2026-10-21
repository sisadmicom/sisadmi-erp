# R-06 — Correcciones y preparación, validación PostgreSQL pendiente

## Cambios implementados

- sri/tests/test_electronic_invoice_service.py: el caso positivo configura el
  certificado de empresa con el helper PKCS#12 sintético existente, resuelve su
  firmador y verifica XAdES contra ese certificado y el XML original. Conserva
  expectativas de estado, contenido de firma y propiedades firmadas. La prueba
  de firma falsa ahora exige rechazo fiscal específico y conservación de XML y
  estado: su expectativa anterior de aceptación contradice el contrato R-05.
  Los secretos sintéticos del fixture se retiran con addCleanup.
- sri/tests/reception_test_support.py: fiscal_snapshot incluye error_message;
  la aserción existente compara el valor realmente capturado antes/después.
  No se normalizan vacío y None ni se altera el servicio de recepción.
- sales/tests/test_fiscal_workflow_navigation.py: el operador autorizado recibe
  explícitamente permisos SRI de consulta y operación. Se mantienen las
  expectativas de navegación, 404 entre empresas y ausencia de mutaciones GET.
- sri/tests/test_human_workflow_r05.py: dos casos HTTP adicionales recorren los
  servicios reales con SOAP simulado: rechazo de autorización y timeout. Exigen
  ausencia de autorización/XML autorizado, estado correcto, intento único,
  mensajes seguros y ausencia de presentación de éxito.

Clasificación: certificado ausente, snapshot incompleto y permisos omitidos son
errores de fixtures; aceptación del firmador falso es un contrato desactualizado.
No se identificó todavía un defecto productivo que justifique cambiar servicios.
La regresión puede revelar discrepancias ocultas previamente por el 403.
No se tocaron modelos, migraciones, tarifas ni servicios productivos.

## Resultados comprobados

Ejecución independiente sin base de datos: 69 pruebas aprobadas, 0 fallos,
0 errores, 0.412 segundos. Módulos: test_invoice_security_r05,
test_sri_reception_soap_adapter, test_sri_authorization_soap_adapter.
Registro local: /tmp/sisadmi-r06-offline.log.
System check: sin incidencias. AST de los cuatro archivos modificados: correcto.
pip check: No broken requirements found. git diff --check: correcto.

Pruebas afectadas, HTTP PostgreSQL, principal, completa y
makemigrations --check --dry-run: PENDIENTES en R-06. No se reutilizan los conteos
R-05 como validación de estas correcciones.

Bloqueo: no existe /run/user/1000/sisadmi-r01-test-password. Se solicitó su
preparación privada al usuario; no se consultaron credenciales DEV ni se abrió
conexión PostgreSQL. No hay credencial temporal que retirar en esta ejecución.
El runner R-01 existente será reutilizado con --keepdb --parallel=1; no se
requiere otra fase de infraestructura. Selección afectada preparada:

```
sri.tests.test_electronic_invoice_service
sri.tests.test_electronic_document_reception_service
sales.tests.test_fiscal_workflow_navigation
sri.tests.test_human_workflow_r05
```

Los 34 métodos pendientes no fiscales de R-04/R-05 se mantienen documentados en
R05_REGRESION.md: bootstrap/navegación, texto 403 geográfico y acciones Borrar.
No se alteran pruebas congeladas para resolverlos.

## Configuración del emisor: interfaz y administración

| Dato | Modelo/campo existente | Entrada actual |
|---|---|---|
| RUC y razón social | Company.person → Person.identification_type, identification, full_name | Wizard inicial / formulario de Persona; elegir RUC |
| Dirección matriz | Person.address | Paso de ubicación / edición de Persona fundadora |
| Nombre comercial | Company.commercial_name | Formulario de empresa |
| Establecimiento | Branch.code, address, company | Alta de sucursal autorizada; autoridad administrativa inicial según servicio existente |
| Punto de emisión | PointOfEmission.branch, code, is_active | Provisión administrativa; el formulario de preparación fiscal solo selecciona puntos existentes |
| Ambiente | SriConfiguration.environment="1", emission_type="1" | Provisión administrativa; no hay formulario específico registrado |
| Datos fiscales adicionales | accounting_required, special_taxpayer_number | Provisión administrativa con valores reales |
| Certificado | SriCertificate.company, certificate_file, is_active, is_default | Provisión administrativa privada; no hay formulario de carga SRI ni registro de ese modelo en sri/admin.py |
| Contraseña PKCS#12 | Variable referenciada por SriCertificate.secret_key | Secreto del proceso web vía EnvironmentSecretProvider; no se guarda como dato del modelo |
| Operador | UserProfile.companies, branches; permisos SRI view/change_electronicdocument | Provisión administrativa; no hay pantalla de delegación específica para este recorrido |

Branch.code permite códigos internos más amplios: para el ensayo debe corresponder
al establecimiento fiscal real de tres dígitos. PointOfEmission.code también debe
ser el código real de tres dígitos, perteneciente a esa sucursal. No derivar la
numeración fiscal del número ERP ni inventar códigos o secuencias.

La operación cotidiana de la factura utiliza las pantallas de venta y SRI,
sin Django Admin. La provisión inicial de los datos indicados sigue siendo
administrativa; no se añadieron pantallas ni se rediseñó ese mecanismo.

## Datos pendientes y ensayo local sin envío

No se recibieron datos reales del emisor ni disponibilidad/localización autorizada
de su certificado. No se creó una factura con identidad inventada para suplirlos.
El usuario debe proporcionar por los canales adecuados:

1. RUC y razón social reales, dirección matriz, establecimiento y punto de
   emisión, obligación contable y condición de contribuyente especial si aplica.
   Revisar régimen/actividad y requisitos condicionales frente al generador simple.
2. PKCS#12 real y vigente correspondiente al emisor, en almacenamiento privado
   persistente fuera del repositorio. Su contraseña se configura privadamente
   en el entorno del proceso web; nunca en chat ni en informes.
3. Operador, empresa y sucursal autorizados; comprador, producto, cantidades,
   precio, impuestos resueltos y pago reales para la única factura propuesta.
4. Configuración web exclusivamente TEST, con certificado y secreto accesibles
   al proceso. Los settings automatizados R-01 usan rutas privadas efímeras y no
   sirven por sí solos como provisión persistente de un certificado real.

Después de aprobar la regresión y provisionar datos autorizados exclusivamente
en TEST: crear venta por interfaz, confirmar, preparar XML y firmar; comprobar
XSD oficial, identidad/clave y dígito verificador, totales, IVA y pago, ambiente 1,
integridad XAdES con el certificado del emisor, estado SIGNED y ausencia de
intentos de recepción/autorización. Detener ahí; no pulsar envío ni consulta.
La vigencia y verificación criptográfica local no acreditan confianza del emisor
ni aceptación del perfil por el SRI; esos extremos deben verificarse con el
certificado real. No se registran certificados ni secretos en este documento.

Estado actual: NO-GO para solicitar el primer envío. Faltan ejecución PostgreSQL
R-06 y prevalidación local con datos/certificado reales. No se contactaron
servicios SRI ni se enviaron comprobantes. El envío posterior requiere una
autorización expresa adicional para una sola factura.
