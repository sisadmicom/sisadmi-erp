# Identificación central de Personas — lista para validación humana en TEST

## Contrato aprobado

Person sigue global. IdentificationKind es un catálogo global de códigos estables.
Se añade Person.identification_kind nullable; identification_type se conserva como
código compatible. No se enlazan/reclasifican automáticamente Personas históricas.
Las altas y cambios de identidad detectan y validan el código; las ediciones que
no cambian identificación ni tipo conservan su clasificación histórica, incluso
NULL. Las diferencias de datos existentes requieren diagnóstico y decisión.

- 10 dígitos ASCII: Cédula, provincia 01–24, tercer dígito 0–5 y módulo 10.
- 13 dígitos ASCII: RUC; provincia 01–24, terminación 001. Si se basa en cédula,
  validar los primeros diez dígitos; clases asignadas 6/9 sin módulo 11 universal.
- 9999999999999: exclusivamente FINAL_CONSUMER, nunca RUC.
- Otros formatos: OTHER; PASSPORT es opción manual. Ambas opciones siguen las
  comprobaciones numéricas obligatorias. Rechazar controles, longitud >20,
  espacios extremos, solo puntuación y dígitos Unicode que simulen números ASCII.
- FOREIGN_ID se conserva por compatibilidad histórica; altas nuevas se detectan
  como OTHER, salvo selección PASSPORT.

No se consulta existencia, vigencia ni estado del contribuyente ante el SRI.
No se garantiza existencia real de una Cédula por cumplir su checksum.

Fuentes consultadas:
- https://www.sri.gob.ec/facturacion-electronica — advertencia expresa de no exigir
  algoritmo universal a RUC de sociedades y extranjeros sin cédula.
- https://www.sri.gob.ec/o/sri-portlet-biblioteca-alfresco-internet/descargar/f3844306-7d35-406a-b4bf-55bbc8c0b72c/Reglamento_Ley_RUC.pdf
  — RUC de cédula +001 y numeración asignada por SRI.
- https://www.sri.gob.ec/o/sri-portlet-biblioteca-alfresco-internet/descargar/128d9357-9043-41ce-833b-885da7a34a7f/TALLER_SOCIALIZACIÓN_MARZO_2019_v2.pdf
  — estructura y ejemplo de verificación de cédula.

## Consumidor Final

Sistema crea una Persona global CONSUMIDOR FINAL, activa, tipo NATURAL, código
FINAL_CONSUMER. Usuario ordinario no puede crearla, editarla, desactivarla ni
eliminarla. Guardas en modelo, queryset, servicios y señal de borrado (incluidas
cascadas ORM); usos como Company, Supplier o Employee bloqueados por pre_save.
No reemplazan permisos PostgreSQL: SQL directo puede eludir lógica de aplicación.
Bulk create/update de identidades no está permitido; futura importación masiva
requiere usar validación central, fuera del alcance de esta entrega.

Servicio enable_for_company: transacción, bloqueo de Company, get_or_create de
Person, CompanyPersonAccess y Customer. Unicidades existentes protegen carreras.
Invocado desde ambos servicios autorizados de creación de Company. No cambia
notas, categoría, crédito ni actividad de Customers existentes. Revocar acceso
empresarial a la Persona reservada desde servicio se rechaza.

## Migraciones revisadas y aplicadas exclusivamente en TEST

0009: catálogo, opciones adicionales y FK nullable, sin reclasificar datos.
0010: catálogo inicial y Persona reservada; disponibilidad y Customer por empresa
existente. Es irreversible deliberadamente: no borrar Personas/clientes al volver.
Se ejecutó el diagnóstico de solo lectura TEST antes de aplicarla; no hubo
conflictos. La migración aborta si la identificación reservada ya existe. No adopta
ni sobrescribe registros ni modifica documentos históricos.

Comando audit_identification_test verifica nombre/usuario TEST y consulta solo
columnas previas a 0009. Informa conteos agregados de conflictos y diferencias,
sin imprimir identificaciones. El diagnóstico de esta ejecución usó las mismas
reglas y la transacción READ ONLY del lanzador controlado.

## Evidencia de ejecución — 17 de octubre de 2026

Conexión acreditada: test_sisadmi_erp / sisadmi_erp_test_runner / 127.0.0.1:5432.
Historial consistente; solo estaban pendientes 0009 y 0010. Diagnóstico mediante
transacción READ ONLY: 2 Personas revisadas, sin identificaciones inválidas,
sin identificación reservada existente, sin diferencias de clasificación y sin
clientes con company NULL. No hubo conflictos que requiriesen modificar datos.

0009 y 0010 aplicadas exclusivamente en TEST. Huellas de todas las filas previas
comparadas antes/después: ninguna modificada ni borrada (excluida únicamente la
nueva columna nullable al comparar el esquema anterior). Cambios aditivos:
Person 2→3; Customer 2→3; categorías 4→4; accesos 2→3; catálogo 0→6.
Se inicializaron permisos/content types del nuevo modelo por post_migrate.

Regresión final, una ejecución: 87 pruebas, 87 OK, 0 fallos, 0 errores, 13.552 s.
Incluye 13 de integración de identificación, 7 del contrato de identificación,
14 categorías, 16 acciones de clientes, 12 sustitución de Persona y 25 de
formularios/navegación/retornos relacionados de Personas. Cada TestCase usa
rollback; runner keepdb=True, parallel=1, sin flush ni reconstrucción de base.
Comparación de todas las filas antes/después: idénticas.

Ejecuciones diagnósticas previas (no sumadas al resultado final):
- 62 pruebas: 60 OK y 2 errores; permiso add_person ausente en fixture y borrado
  queryset bloqueado por PROTECT antes de dar el error de dominio.
- Tras corrección: 62/62 OK.
- Ampliación a Personas: 87 pruebas con 4 fallos de aserción/subtest derivados
  del requisito antiguo de tipo obligatorio. Se adaptó REQUIRED_FIELDS a la
  detección automática aprobada. No se modificaron CAT-05 ni sus expectativas.

Correcciones de esta ejecución: permiso explícito en fixture; guardia de borrado
queryset antes del recolector; contrato de formulario permite tipo vacío. La
prueba de integración comprueba alta HTTP real sin tipo manual y vínculo CEDULA
al catálogo, sin JavaScript. Se conserva la validación estricta en servidor.

Pruebas unitarias separadas: 24/24 OK. No sumar ejecuciones diferentes.
manage.py check: sin incidencias. makemigrations --check --dry-run con historial
TEST: No changes detected. pip check y git diff --check: OK. No nuevas migraciones
por estas correcciones. Suite completa no ejecutada para preservar datos humanos.

Siete candidatos congelados y 1138 archivos sellados CAT-05 verificados por SHA-256.
No DEV, flush, commit ni push. Credencial temporal retirada verificando su identidad.
Servidor TEST actualizado: PID 1381776, 127.0.0.1:8000; login y JavaScript HTTP 200,
Personas sin autenticación redirige al login. Pendiente de validación humana.

Evidencias completas: core/testing/identification_regression_results.json y
core/testing/identification_regression_final.log. Evidencias detalladas de huellas:
/tmp/person-identification-migration-integrity.json,
/tmp/person-identification-test-integrity.json y /tmp/person-identification-preflight.json.

## Validación humana y límites

- Listado: http://127.0.0.1:8000/people/
- Adicionar: http://127.0.0.1:8000/people/new/
- Ingresar identificación sin elegir tipo y comprobar el resultado dinámico.
- Cédula/RUC incorrectos se rechazan incluso seleccionando Pasaporte/Otro.
- Consumidor Final aparece habilitado; editarlo muestra el bloqueo del sistema.
- Los registros históricos permanecen sin reclasificar.

Mapeo fiscal de FINAL_CONSUMER y OTHER sigue pendiente en SRI: no se modificó
XML, impuestos ni envíos, ni se acredita emisión fiscal. No continuar importación
masiva ni otros módulos hasta decisión del usuario. La importación futura deberá
usar validación central; bulk create/update de identidad sigue bloqueado.

## Archivos de esta implementación

- people/identification.py; people/constants/identification_type.py.
- people/models/person.py; people/models/identification_kind.py;
  people/models/__init__.py; people/apps.py.
- people/services/final_consumer.py; people/services/person_protection.py;
  people/services/person_access_policy.py.
- core/services/initial_company_setup.py; core/services/company_maintenance.py.
- people/forms.py; people/views.py; people/urls.py;
  people/templates/people/person_form.html; people/static/people/js/identification.js.
- people/management/commands/audit_identification_test.py.
- people/migrations/0009_alter_person_identification_type_identificationkind_and_more.py;
  people/migrations/0010_identification_catalog_and_final_consumer.py.
- people/tests/test_identification_validation.py;
  people/tests/test_identification_integration.py;
  people/test_identification_type_contract.py.

Revisión Git: HEAD sigue e5c4c6cec2f410772dfbe7eb434bf3932b895692. El hash binario
del índice difiere de la referencia temporal de la tarea anterior; esa referencia
no permite atribuir el cambio a esta tarea ni acreditar identidad byte a byte.
No se ejecutaron operaciones Git de stage, commit, reset ni push.
