# R-03 — Regresión funcional PostgreSQL TEST

## Aislamiento acreditado

Se verificó mediante conexiones reales exclusivamente a las bases autorizadas:
`127.0.0.1:5432`, `session_user = current_user = sisadmi_erp_test_runner`.
Bootstrap: `sisadmi_erp_test_bootstrap`, `default_transaction_read_only=on`.
TEST: `test_sisadmi_erp`, `default_transaction_read_only=off`.
Se verificaron propietario TEST, cinco privilegios administrativos desactivados y
ninguna pertenencia a otros roles. La acreditación HBA/rechazo DEV procede de la
verificación administrativa comunicada por el operador; no se intentó conectar
DEV desde esta ejecución. Las guardas locales se comprobaron además con 13 tests.

La contraseña se leyó en memoria desde un archivo privado del operador (0600),
sin incorporarla a archivos del proyecto, comandos ni registros. El archivo
temporal se retiró al finalizar tras verificar identidad, propietario y permisos. Se limpiaron
variables heredadas libpq y de conexión DEV antes de configurar R-01.

## Corrección mínima realizada

La conexión de mantenimiento de Django intentaba usar `postgres`, rechazada por
HBA. Se cambió exclusivamente el backend TEST para usar bootstrap en modo solo
lectura. La guarda de mantenimiento acepta únicamente bootstrap y rechaza
`None`, `postgres` y TEST. Se ajustaron sus pruebas y documentación; no se
ampliaron permisos PostgreSQL ni se modificaron reglas de negocio.

Archivos R-02 ajustados en R-03:
- `core/testing/r01_postgresql/base.py`
- `core/testing/r01_guard.py`
- `core/tests/test_r01_test_environment.py`
- `core/testing/R01_POSTGRESQL.md`

Archivo de informe creado: `core/testing/R03_REGRESSION.md`.
No se crearon migraciones.

## Regresión solicitada

Módulos: `catalog`, `sales`, `sri`,
`core.tests.test_application_shell`, `core.tests.test_auth_navigation`,
`core.tests.test_form_ux_foundation_red`, `people.tests.test_person_form_ui`,
`people.tests.test_person_ui_navigation`.
Runner: `config.settings_test_r01`, `--keepdb --parallel=1`, sin interacción.
El runner aplicó 72 migraciones pendientes exclusivamente en TEST.

Resultado: **716 tests ejecutados, 713 aprobados, 3 tests con fallos, 0 errores**.
Django informa `failures=7`: son siete subcasos de esos tres tests.
Duración: 129.631 s; salida 1; base TEST conservada.

| Aplicación | Aprobados | Tests con fallos |
|---|---:|---:|
| catalog | 179 | 0 |
| sales | 172 | 0 |
| sri | 306 | 0 |
| core (interfaz seleccionada) | 40 | 0 |
| people (interfaz seleccionada) | 16 | 3 |

Fallos sin corrección funcional en esta etapa:
1. `PersonFormTests.test_invalid_post_preserves_values_and_accessibly_exposes_field_and_general_errors`:
   el parser de prueba observa un salto de línea inicial adicional en textarea
   `address`. Revisar semántica del parser y navegador antes de cambiar plantilla.
2. `PersonNavigationTests.test_empty_and_no_result_states_explain_next_action_without_disclosure`:
   dos subcasos rechazan el texto privado que el propio usuario ingresó como
   búsqueda y que se devuelve en el input. Esto no demuestra divulgación de datos
   consultados. Revisar el alcance de la aserción de no divulgación.
3. `PersonNavigationTests.test_known_pk_never_reveals_hidden_or_inactive_person_in_detail_or_edit`:
   cuatro subcasos POST reciben 405 frente al contrato 403/404. Revisar el orden
   de comprobación de método y visibilidad; no se observó contenido privado.

## Verificaciones

- Guardas sin conexión: 13/13 aprobadas.
- `manage.py check` con settings R-01: sin incidencias.
- `makemigrations --check --dry-run`, conexión dirigida a TEST: `No changes detected`.
- `.venv/bin/python -m pip check`: sin dependencias rotas.
- AST de los tres archivos Python ajustados: correcto.
- `git diff --check`: correcto.

## Preservación

HEAD: `e5c4c6cec2f410772dfbe7eb434bf3932b895692`; índice sin cambios.
Los 663 archivos preexistentes inventariados en `cat054_before.json` conservan
sus hashes, incluidos los siete candidatos RED congelados.
La copia sellada CAT-05 conserva los 1138 hashes de su manifiesto.
SHA-256 del manifiesto: `4ad318442979ef400db3aa8928a68c4530b505fabe618b1f2ec9ae7872f4ba74`.
Las 28 pruebas CAT-05 no se importaron ni ejecutaron. `approved=false` intacto.
No se ejecutaron operaciones Git de escritura ni conexiones DEV.

## Evidencias locales

- `/tmp/sisadmi-r03-regression.log`: salida completa de regresión seleccionada.
- `/tmp/sisadmi-r03-checks.log`: identidad TEST, check y comprobación de migraciones.
- `/tmp/sisadmi-r03-full.log`: suite completa exigida por AGENTS.md.
Estas rutas son temporales; este informe conserva el resumen reproducible.

## Próximo trabajo hacia factura SRI

El flujo SRI de generación, firma, recepción y autorización ya tiene servicios y
vistas; los 306 tests SRI seleccionados pasan. Esto no acredita una autorización
real: no se envió una factura al SRI ni se probó un certificado real.
La interfaz de nueva venta no transmite `payment_method` al DTO, aunque
`CreateSale` lo persiste. Preparar un caso de factura desde interfaz que cubra
forma de pago, confirmación y preparación electrónica; revisar después XML
contra el esquema fiscal aplicable antes de usar certificado y SRI pruebas.
No se alteraron cálculos tributarios para conseguir resultados favorables.

## Suite completa (antes del ajuste de conexiones auxiliares)

Ejecutada con el mismo runner, `--keepdb --parallel=1`: **1723 tests** en
517.680 s. **1243 aprobados, 41 métodos con fallos, 439 métodos con errores**.
Django registra `failures=95, errors=443` porque incluye subcasos y errores
adicionales asociados a un mismo método. No hubo skips. Salida 1, base conservada.

Clasificación de los 443 errores registrados:
- 408: `DocumentType.DoesNotExist`. La segunda ejecución usa una TEST ya migrada
  pero sin los registros sembrados por migraciones. Los tests de transacción
  realizan flush y `--keepdb` no vuelve a ejecutar migraciones ya aplicadas.
  Las pruebas afectadas no construyen todas sus precondiciones de catálogo.
  No se borró ni recreó la base y no se reejecutaron migraciones de datos a ciegas.
- 31: guarda rechazaba wrappers auxiliares de concurrencia. Corregido después
  de esta ejecución, limitando dos nombres de wrapper existentes al destino TEST.
  Se mantiene una sola entrada `DATABASES.default`, sin routers ni mirrors.
- 4: `Person.DoesNotExist` / `Company.DoesNotExist` en pruebas de bootstrap que
  esperaban entidades no creadas; revisar con sus fallos de formulario relacionados.

Los 95 fallos incluyen contratos de bootstrap desalineados (campos de empresa y
sucursal), validación documental, controles Borrar, mensajes de autorización,
textareas y los casos de interfaz Personas ya descritos. No se modificaron pruebas funcionales,
modelos ni formularios para silenciarlos. La suite general **no está verde**.

Corrección adicional R-03: wrappers `isolation_probe` / `con532_row_probe` solo
pueden usar `test_sisadmi_erp`. Un test de guarda adicional comprueba esta condición
además del rechazo de su registro como aliases configurados: 13/13 aprobados.

Próxima corrección de pruebas: proporcionar precondiciones deterministas de
DocumentType en las pruebas que las requieren, reutilizando contratos existentes,
sin modificar reglas tributarias, sin alterar congelados y sin recrear bases.
Esto debe separarse de los fallos funcionales reales de interfaz/bootstrap.

## Reejecución tras corregir la guarda

`core.tests.test_migration_isolation` y
`people.tests.test_commercial_document_concurrency_cat023_red`:
**44 tests ejecutados y aprobados, 0 fallos, 0 errores**, 60.049 s, salida 0.
Incluye adquisición/espera de bloqueos, rollback, timeout y cierre de workers.
Los errores de configuración en wrappers auxiliares quedaron corregidos.
No se reejecutó la suite completa después de este ajuste: sus conteos anteriores
se conservan como evidencia y no se presentan como resultado del código final.

Checks finales repetidos sobre TEST: sin incidencias y sin cambios de migraciones.
Logs adicionales: `/tmp/sisadmi-r03-concurrency.log` y
`/tmp/sisadmi-r03-checks-final.log`.

**GO para continuar desarrollo con PostgreSQL TEST. NO-GO para declarar regresión
completa satisfactoria o una factura real autorizada.** No hacen falta nuevas
fases de virtualización ni permisos administrativos para los próximos cambios.
