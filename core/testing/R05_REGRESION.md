# R-05 — Regresión PostgreSQL TEST

## Ejecución e aislamiento

Se utilizó exclusivamente config.settings_test_r01, R01TestRunner y el backend
protegido existente. Todos los tests se ejecutaron con keepdb=True, parallel=1
e interactive=False; equivalen a --keepdb --parallel=1 --noinput.
La configuración no hereda credenciales DEV. El lanzador temporal eliminó
variables PG*, DJANGO_DB_* y DATABASE_URL antes de cargar Django.

El preflight del runner comprobó propietario de TEST, ausencia de membresías
del rol y privilegios administrativos. No creó, clonó ni borró bases.
La preparación Django informó «No migrations to apply»; las pruebas históricas
de migraciones operaron únicamente en TEST mediante el runner existente.

Consulta final de identidad:

```
database: test_sisadmi_erp
user: sisadmi_erp_test_runner
server: 127.0.0.1:5432
rolsuper / rolcreatedb / rolcreaterole / rolreplication / rolbypassrls: false
```

Se usó bootstrap exclusivamente para las comprobaciones de mantenimiento
protegidas y en modo de solo lectura. No se conectó ni migró DEV.
No hubo recepción ni autorización reales SRI: las pruebas utilizan dobles SOAP.

## Resultados independientes

| Ejecución | Métodos ejecutados | Aprobados | Con fallo | Con error | Segundos |
|---|---:|---:|---:|---:|---:|
| Módulo SRI | 331 | 328 | 1 | 2 | 74.905 |
| HTTP fiscal | 10 | 10 | 0 | 0 | 3.517 |
| Regresión principal | 745 | 728 | 15 | 2 | 148.636 |
| Suite completa | 1759 | 1708 | 45 | 6 | 587.950 |

No se suman ejecuciones: incluyen casos compartidos. No hubo skips.
Los conteos de fallos de Django incluyen subcasos: SRI failures=1, errors=2;
principal failures=38, errors=2; completa failures=113, errors=6.
La tabla cuenta métodos únicos afectados, para evitar restar varias veces un
método con varios subcasos fallidos. No hubo errores de colección ni de clase.

HTTP fiscal seleccionó HumanInvoiceWorkflowTests y InvoiceXMLFromHTTPTests:
alta de venta, confirmación, preparación, XSD, firma local PKCS#12, recepción y
autorización simuladas, idempotencia, XML alterado, errores seguros, CSRF,
permisos, multiempresa y conservación de snapshots.

Principal seleccionó catalog, sales, sri, core.tests.test_application_shell,
core.tests.test_auth_navigation, core.tests.test_form_ux_foundation_red,
people.tests.test_person_form_ui y people.tests.test_person_ui_navigation.
Completa usó el descubrimiento estándar del proyecto; las 28 CAT-05 externas
no se copiaron ni ejecutaron.

check: sin incidencias. makemigrations --check --dry-run: No changes detected,
código 0. No migraciones creadas. pip check: No broken requirements found.
AST de archivos Python SRI y git diff --check: correctos.

## Fallos pendientes y corrección mínima propuesta

Los 17 métodos no aprobados de la regresión principal se descomponen en:

1. Catorce métodos de sales.tests.test_fiscal_workflow_navigation: el fixture
   c14e-operator no concede sri.view_electronicdocument; GET devuelve 403 antes
   de verificar navegación/empresa, en lugar del 200/404 esperado. Conceder
   explícitamente el permiso de lectura al actor autorizado del fixture y
   mantener las pruebas de denegación. Reejecutar: puede revelar discrepancias
   posteriores ocultas por el 403. No retirar permisos de producción.
2. Un método de recepción: fiscal_snapshot no incluye error_message; la prueba
   compara el valor persistido vacío con dict.get devolviendo None. Capturar el
   campo antes de enviar y comprobar su conservación exacta; no normalizar la
   aserción de forma que esconda cambios.
3. Dos errores ElectronicInvoiceServiceTest: los tests históricos de firma no
   configuran el certificado confiable de empresa. El firmador falso además
   produce una firma sin validez criptográfica. Separar el rechazo de firma falsa
   del caso positivo, que debe usar un certificado sintético configurado y su
   clave correspondiente. No aceptar XML sin firma válida para obtener verde.

La suite completa reproduce además los 34 métodos pendientes de R-04:

| Grupo | Métodos con fallo | Métodos con error | Diagnóstico |
|---|---:|---:|---|
| test_administrative_bootstrap | 6 | 4 | POST antiguo de alta; dos Person.DoesNotExist y dos Company.DoesNotExist |
| test_founding_person_data | 11 | 0 | Contratos/fixtures de alta anteriores al wizard vigente |
| test_initial_company_setup_d02a_red | 1 | 0 | Destino de navegación tras login |
| test_entity_company_person_d02a1_red | 1 | 0 | Destino de navegación tras alta de empresa |
| test_geography_ui | 1 | 0 | Texto esperado en denegación 403 |
| test_related_entity_actions_d02a1_red | 10 | 0 | Controles Borrar; incluye candidato congelado, no modificado |

No se corrigieron reglas de negocio ni tests en esta continuación de ejecución.
Los identificadores exactos están en r05_results.json. Las correcciones de
contratos congelados requieren respetar su protección, no editar sus aserciones.

## Requisitos concretos del único ensayo posterior

Los conteos finales en TEST fueron cero para empresas, configuraciones SRI TEST,
certificados activos predeterminados y puntos de emisión activos. Las entidades
de fixtures no constituyen un emisor real y los archivos privados de cada proceso
se eliminan al salir. Se requiere preparar el siguiente contexto de ensayo, sin
ejecutar después una suite que pueda vaciarlo:

- Company ligada a Person con RUC real del emisor, identificación RUC, razón
  social y dirección matriz; nombre comercial cuando corresponda. Verificar
  habilitación del emisor para pruebas y los datos fiscales aplicables.
- Branch de esa empresa con código de establecimiento de tres dígitos y dirección;
  PointOfEmission activo de esa sucursal con código de tres dígitos. Secuencia ERP
  y secuencia fiscal independientes, sin reutilizar una identidad ya emitida.
- SriConfiguration de la empresa: environment="1", emission_type="1",
  accounting_required correcto y special_taxpayer_number si corresponde.
  Revisar requisitos adicionales de régimen/actividad (por ejemplo RIMPE o
  retención); el generador simple actual no cubre todos los casos condicionales.
- SriCertificate de la misma empresa activo y predeterminado; PKCS#12 real .p12
  o .pfx con clave privada y certificado vigente, en almacenamiento privado
  persistente fuera del repositorio. Verificar titular/RUC, confianza/cadena y
  perfil XAdES aceptado por SRI; la comprobación local no acredita esos extremos.
- secret_key debe identificar la variable que EnvironmentSecretProvider obtiene
  en el proceso web. El usuario configura su valor por canal privado; no entregar
  contraseñas en chat, base de datos o archivos rastreados. El proceso necesita
  acceso de lectura privado al archivo y al secreto, sin URL pública.
- Comprador con tipo e identificación reales compatibles, nombre y datos
  requeridos; producto, existencias/almacén, IVA persistido y forma de pago
  apropiados; fecha de emisión y totales revisados. No inventar tasas ni códigos.
- Usuario con acceso a empresa y sucursal y permisos SRI view_electronicdocument
  y change_electronicdocument. Ejecutar alta, confirmación, preparación, firma,
  envío y consulta desde las pantallas existentes.
- Proceso web apuntando expresamente a TEST y almacenamiento privado persistente.
  El settings automático actual usa rutas efímeras y no es por sí solo una
  configuración web persistente para certificados reales. No reutilizar DEV.
- Recepción y autorización solo en celcer.sri.gob.ec, TLS verificado. Revisar XML
  con XSD oficial y firma antes del envío; no reescribir el XML firmado.
- Autorización expresa adicional para enviar una sola factura. Registrar clave,
  intentos, mensajes y respuesta efectiva; RECIBIDA no equivale a AUTORIZADO.
  Un resultado incierto no autoriza reenviar automáticamente.

NO-GO para un envío ahora: regresión con fallos y emisor/certificado real ausentes.
Siguiente corrección: conciliar los tres grupos de fixtures SRI/navegación y
reejecutar pruebas afectadas/principal, conservando las guardas fiscales.

## Evidencias y preservación

Registros locales: /tmp/sisadmi-r05-db-affected.log,
/tmp/sisadmi-r05-db-http.log, /tmp/sisadmi-r05-db-principal.log,
/tmp/sisadmi-r05-db-full.log, /tmp/sisadmi-r05-db-checks.log y
/tmp/sisadmi-r05-db-identity.log. Resumen persistente: r05_results.json.

Credencial temporal: verificados propietario, archivo regular, modo 0600 y
enlace único; retirada al finalizar comprobando dispositivo e inode originales.
No se registra su valor. No quedó archivo temporal de credencial.
HEAD e índice preservados, siete candidatos congelados intactos y 1138 archivos
sellados con hashes coincidentes. Sin stage, commit ni push. En esta continuación
solo se actualiza la documentación R-05 y se agrega su resumen de resultados.
