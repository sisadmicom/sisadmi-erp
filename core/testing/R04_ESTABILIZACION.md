# R-04 — Estabilización funcional y preparación de factura SRI

Estado: validación PostgreSQL TEST reanudada con la credencial temporal del operador.
Ejecución finalizada exclusivamente en PostgreSQL TEST. La regresión principal
aprueba 729/729; la suite completa conserva fallos funcionales/contractuales
documentados. El XML de factura simple está validado por XSD; no hay autorización SRI.

## DocumentType

La carga original reside en migraciones de datos core 0004 y 0007–0010.
`TransactionTestCase` ejecuta flush y borra los registros; al reutilizar la base,
Django conserva django_migrations y no repite los RunPython ya aplicados.

Corrección: servicio `ensure_document_types` y señal `post_migrate` de CoreConfig.
La misma carga se ejecuta tras migrate y flush. Inserta únicamente los siete códigos
canónicos faltantes, con las capacidades ya fijadas por las migraciones. Usa el alias
recibido y el registro apps del evento (o el registro actual en flush), respeta routers y omite esquemas históricos
sin line_behavior. No altera entradas existentes, actividad ni auditoría y no
reproduce migraciones históricas. No se añadieron migraciones de datos: otra migración
por sí sola volvería a perder sus datos tras flush.

Pruebas nuevas: carga desde catálogo vacío; idempotencia exacta; preservación de
entradas editadas/inactivas; flush seguido de reposición sin cambiar django_migrations.
Estas pruebas pasan en PostgreSQL TEST. La suite completa terminó sin ningún
DocumentType.DoesNotExist: los 408 errores de este tipo registrados en R-03
no reaparecen, incluso reutilizando TEST después de las ejecuciones previas.

## Personas y empresa

1. Textarea: los parsers de tests contaban el LF inicial que el navegador ignora.
   Se corrigen los dos parsers usados por la interfaz, conservando saltos reales
   adicionales. No se cambia el valor del formulario productivo para adaptar HTML
   válido a un parser defectuoso.
2. Privacidad de búsqueda: el verificador confundía el query escrito por el operador
   con datos recuperados. La excepción se limita al valor exacto del input q;
   texto, otros atributos y enlaces de la persona siguen comprobándose. Una prueba
   nueva demuestra que esas divulgaciones siguen fallando.
3. person_detail: se verifica contexto, permiso y visibilidad antes de responder por
   método no admitido. Una persona no visible devuelve 403/404 también ante POST;
   un registro visible continúa rechazando POST con 405.

El alta vigente es un wizard en cuatro pasos, con ubicación explícita. No se vuelve
al POST único antiguo ni se inventan sucursal o geografía. Se ejecutó
el contrato test_initial_company_setup_d02a_red; su única discrepancia restante
es la redirección de login: select_company frente a company_create. El segundo
destino está exigido por test_entity_company_person_d02a1_red, por lo que no se
cambió la navegación ni las aserciones para favorecer uno de los contratos. Los tests antiguos de
bootstrap que esperan company_address y todos los pasos en una página requieren
conciliarse con este contrato, sin alterar pruebas congeladas para ocultarlos.

Además se corrigió Company.__str__: cuando commercial_name es None, la etiqueta
usa person.full_name, evitando un TypeError real al mostrar formularios de venta.
Un test nuevo cubre ambas etiquetas.

## Forma de pago

SaleCreateForm ofrece PaymentMethod.choices existentes. HTTP valida la elección;
la vista la transmite al DTO; CreateSale ya la persiste. La omisión sigue siendo None
en borradores comerciales, sin asumir una forma de pago fiscal.

Pruebas nuevas sin mocks de dominio: todas las elecciones sobreviven HTTP → DTO →
servicio → Sale; elección desconocida no crea una venta; omisión conserva None;
control HTML expone las opciones existentes.

## XML de factura simple

Generador corregido a factura 1.1.0: versión, orden de nodos, dirección matriz,
identificación explícita del comprador, descuento, códigos de impuesto/porcentaje,
agrupación por código fiscal y forma de pago. Se eliminan nodos nombre no admitidos.
Importes provienen de Sale, detalles y SaleDetailTax persistidos: no se recalculan
impuestos, no se cambian tarifas ni se actualizan XML ya almacenados.

Mapeo en sri: IVA ordinario con tarifa persistida positiva usa tabla SRI; IVA cero,
exento y no sujeto requieren categoría explícita. Cero sin categoría y tarifas
no soportadas fallan; no se interpreta Tax.code como código fiscal. ICE u otros
impuestos necesitan un mapeo explícito posterior para este generador simple.

Se preservó el XSD oficial SRI 1.1.0 sin modificar y su dependencia XMLDSig ya
instalada; provenance.json contiene hashes y origen. No se instalaron paquetes.
Ver sri/schemas/README.md para referencias oficiales y límites normativos.

`validate_for_sri` es una validación explícita offline: XSD, DTD/entidades rechazadas,
clave de acceso/checksum y correspondencia con cabecera, códigos IVA, pagos, sumas
y precisión monetaria. No sustituye al validador básico validate de llamadores
históricos. El flujo antiguo todavía no exige esta validación estricta en todos
los puntos de firma/envío: ese cierre debe hacerse antes de un envío real.

Pasan los tests de venta desde HTTP, confirmación real con inventario/secuencia,
preparación electrónica y validación XSD, junto con rechazo de XML inconsistente
y preservación de snapshots tributarios tras editar el catálogo. No hay mocks del
servicio de venta ni del servicio fiscal: solo se prohíbe el transporte HTTP externo.

Riesgos antes de autorizar SRI: certificado y firma real; configuración de emisor y
ambiente; condición tributaria/RIMPE/retenciones; aplicabilidad de anexo 26 de la
ficha 2.34; mapeos fuera de IVA simple. La validación XSD no garantiza autorización.
El cálculo tributario actual utiliza el contexto Decimal; no se cambió para elegir
otra regla en empates de medio centavo. El validador comprueba precisión sin decidir
una nueva política de redondeo tributario.

## Resultados R-04 ejecutados

| Ejecución independiente | Ejecutados | Aprobados | Fallos | Errores |
|---|---:|---:|---:|---:|
| Pruebas afectadas (último ensayo) | 89 | 88 | 1 | 0 |
| Regresión principal final | 729 | 729 | 0 | 0 |
| Suite completa | 1743 | 1709 | 30 | 4 |
| Guardas R-01 (unittest sin conexión) | 13 | 13 | 0 | 0 |

El primer ensayo del mapeo fiscal mostró el RED esperado: módulo inexistente
(dos errores). Después de implementar, las siete comprobaciones sin DB de ese ensayo pasaron;
los tests adicionales posteriores se incluyen en las ejecuciones de la tabla.
Las ejecuciones siguientes se registran por separado; no se suman sus conteos.

check: sin incidencias en la ejecución sin DB de los siete tests.
pip check: sin dependencias rotas. AST: correcto. git diff --check: correcto.
makemigrations --check --dry-run sobre TEST: No changes detected, salida 0.
Pruebas afectadas finales: 89 ejecutadas, 88 aprobadas, 1 fallo, 0 errores; 41.007 s.
Regresión principal final: 729 ejecutadas y aprobadas, 0 fallos/errores,
128.795 s, salida 0. Suite completa: 1743 ejecutadas; 1709 aprobadas, 30 métodos con fallos y
4 métodos con errores; 577.296 s. Django informa failures=75/errors=4 al contar
subcasos. Salida 1; base conservada.

El runner temporal /tmp/sisadmi-r04-run.py reutiliza settings_test_r01,
--keepdb --parallel=1 y las guardas ya acreditadas. No crea roles, bases ni otra
infraestructura. Modos: affected, principal, full, checks. Lee solo el archivo
privado /run/user/1000/sisadmi-r01-test-password y oculta su contenido en errores.

## Archivos R-04

Modificados:
- core/models/company.py (etiqueta válida sin nombre comercial opcional)
- core/apps.py
- core/tests/test_form_ux_foundation_red.py (parser HTML; no aserciones de datos maestros)
- people/views.py
- people/tests/person_ui_support.py
- sales/forms.py
- sales/views.py
- sri/services/xml_generator_service.py
- sri/services/xml_validation_service.py
- sri/tests/test_xml_generator_service.py (aserción de códigos XSD, en lugar de nombre)
- sri/tests/helpers/electronic_document_factory.py (snapshot de prueba explícito IVA 15%)

Creados:
- core/services/document_type_catalog.py
- core/tests/test_document_type_initialization_r04.py
- core/tests/test_html_contract_r04.py
- sales/tests/test_payment_method_r04.py
- sri/services/invoice_fiscal_mapping.py
- sri/tests/test_invoice_xml_r04.py
- sri/schemas/{factura_V1.1.0.xsd,xmldsig-core-schema.xsd,provenance.json,README.md}
- core/testing/r04_results.json (conteos, identificadores de fallos y hashes de logs por ejecución)
- este informe.

No se crearon migraciones. HEAD e índice conservados. Los cambios ajenos a R-04
permanecen intactos. Los siete candidatos RED y los 1138 hashes de la copia CAT-05
sellada se verificaron sin diferencias; sus 28 pruebas no se ejecutaron. Sin DEV,
QEMU, VM, commits ni push. No se firmaron ni enviaron comprobantes al SRI.

## Correcciones durante la ejecución PostgreSQL

Primer ensayo afectado: 88 tests, failures=1/errors=21, 37.786 s, salida 1.
Se corrigió el receptor de post_migrate: flush no proporciona apps. Los fixtures
HTTP nuevos ahora pasan un diccionario a SessionBase.update, según su API.
Segundo ensayo: 88 tests, failures=1/errors=3, 42.298 s, salida 1. Se corrigió el
TypeError real de Company.__str__ y la aserción del test nuevo que usaba un campo
signed_xml inexistente; la ausencia de firma ahora se comprueba en el propio XML.
Ensayo afectado final: 89 tests, 88 aprobados, 1 fallo/0 errores; incluye la nueva
regresión de etiqueta Company. Ninguna de estas correcciones modifica impuestos.

Logs independientes: /tmp/sisadmi-r04-affected.log,
/tmp/sisadmi-r04-affected-final.log, /tmp/sisadmi-r04-affected-verified.log,
/tmp/sisadmi-r04-principal.log, /tmp/sisadmi-r04-checks.log.

## Regresión principal

Primer ensayo: 728 tests, 726 aprobados, 0 fallos y 2 errores, 127.632 s.
Ambos errores eran del fixture electronic_document_factory: definía IVA 15%
pero omitía tax_type y tax_name del snapshot. Se completaron tipo, categoría
y nombre explícitos en Tax/SaleDetailTax, sin cambiar base, tarifa ni importe.
No se añadió un fallback fiscal a producción. Un test nuevo verifica que un
snapshot sin tax_type sigue siendo rechazado aunque el código interno sea 2
y el nombre sea IVA.

Ensayo principal final: **729 tests ejecutados y aprobados**, 0 fallos, 0 errores;
128.795 s. Log: /tmp/sisadmi-r04-principal-final.log. SHA-256:
`a1d19f32df8180f9d64fc9221aac582e7e2c928feeb3c3d25d74bd496493fd2b`.
Se ejecutó con la misma base conservada después de los ensayos anteriores.

## Suite completa y comparación con R-03

La tabla cuenta métodos de prueba. La suite completa registra 75 incidencias de
aserción en 30 métodos y 4 excepciones en otros 4 métodos; no hubo errores de
setUpClass ni skips. Los resultados de diferentes ensayos no se suman.

| Ejecución completa | Tests | Aprobados | Métodos con fallo | Métodos con error | Incidencias Django |
|---|---:|---:|---:|---:|---|
| R-03 | 1723 | 1243 | 41 | 439 | failures=95, errors=443 |
| R-04 | 1743 | 1709 | 30 | 4 | failures=75, errors=4 |

El tamaño cambió al incorporar nuevas regresiones. De los errores anteriores:
408 DocumentType.DoesNotExist desaparecen con la carga idempotente; 31 rechazos
por conexiones auxiliares ya habían sido corregidos al finalizar R-03 y tampoco
reaparecen. No se atribuyen esos 31 a la nueva corrección de datos maestros.

Errores actuales: dos Person.DoesNotExist y dos Company.DoesNotExist. Los cuatro
son de AdministrativeBootstrapPersistenceTests, que envían el POST único antiguo
y luego esperan entidades no creadas por el wizard vigente. Identificadores y
causas exactas: core/testing/r04_results.json, ejecución /tmp/sisadmi-r04-full.log.

Fallos pendientes por módulo (métodos, no subcasos):
- test_administrative_bootstrap: 6; contrato antiguo de formulario/POST y redirección.
- test_founding_person_data: 11; fixtures basados en el bootstrap antiguo, campos,
  validaciones y expectativas de persistencia/rollback que requieren conciliación.
- test_initial_company_setup_d02a_red: 1; login espera select_company, mientras
  test_entity_company_person_d02a1_red exige company_create.
- test_entity_company_person_d02a1_red: 1; espera company_detail tras guardar y
  el flujo posterior de sucursal dirige a select_branch. No se alteró la navegación.
- test_geography_ui: 1 con 20 subcasos; se deniega acceso con 403, pero falta el
  mensaje de permiso/autorización/acceso esperado por la interfaz.
- test_related_entity_actions_d02a1_red: 10; controles nativos Borrar ausentes o
  no reconocidos por los contratos. Incluye un candidato congelado, intacto.

No se debilitaron aserciones ni reglas tributarias para eliminar estos resultados.
La siguiente corrección debe conciliar los contratos de alta/navegación vigentes,
mejorar los mensajes 403 y resolver el mantenimiento de acciones relacionadas.

Antes de enviar SRI: integrar la validación fiscal estricta como condición obligatoria
antes de firma/envío, revisar régimen/configuración y certificado real del emisor,
verificar la firma y obtener autorización efectiva en el ambiente de pruebas.
Los tests HTTP generan y preparan XML con IVA y forma de pago; no certifican
usabilidad humana manual, firma real ni autorización de una factura.

Checks finales: check sin incidencias; makemigrations --check --dry-run con
No changes detected; pip check sin dependencias rotas. Ninguna migración creada.
Logs: /tmp/sisadmi-r04-full.log y /tmp/sisadmi-r04-checks-final.log.
SHA-256 suite completa: fab2de485571db5478107d14974b3b14a9ada253dada6d3cc4d3806c131b8675.

GO para continuar desarrollo de la factura simple. NO-GO para declarar la suite
completa verde o el ambiente SRI autorizado. No se requiere otra fase de infraestructura.

Credencial temporal retirada al finalizar, tras verificar identidad, propietario y
permisos del archivo original. HEAD, índice, archivos ajenos al alcance y congelados
verificados sin cambios no autorizados. Sin commit ni push.
