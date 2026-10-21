# Primera importación controlada — auditoría aplicada; detenida por error de fixture

Autorización: 49 Person nuevas, 48 NATURAL y 1 LEGAL, más 49 accesos para
SISADMI ID 93, únicamente test_sisadmi_erp. Sin Customer, contactos o geografía.
Fuente y manifiesto de revisión 3 verificados con los hashes autorizados. Las
49 identificaciones siguen ausentes. Migraciones al día y tres triggers activos.
Operador existente autorizado para Personas: sisadmi, ID 66. No se crearon usuarios
ni permisos. El permiso Django superuser devuelve True incluso para un nombre
de permiso no registrado; eso no acredita la disponibilidad real de auditoría.

## Diagnóstico anterior, previo a la autorización de habilitar auditoría

core/models/audit.py contiene AuditLog, pero core/models/__init__.py no lo registra
y no existe migración que lo cree. Consulta READ ONLY a TEST confirmó:
- to_regclass('public.core_auditlog') = NULL.
- ContentType core/auditlog = 0.
- Permiso add_auditlog para core/auditlog = 0.

La primera recolección de pruebas se bloqueó por ImportError del modelo, antes de
ejecutar casos. No se ejecutaron tests ni importación, y no se escribió ningún
registro. No se creó ni aplicó migración. No se resolvió el bloqueo modificando
esquemas o prescindiendo de auditoría. El servicio ahora obtiene el modelo por el
registro de apps y falla con un mensaje explícito antes de crear cualquier fila.

## Código preparado, pendiente de validación

- people/services/controlled_person_import.py: autorización fija de archivo,
  manifiesto, hashes, empresa y filas. Guarda TEST antes de transacción/conexión
  no autorizada. Reutiliza person_access_policy.create_person; transacción única,
  bloqueo de Company, revisión de identidades existentes y AuditLog por fila.
  No admite sustitución de archivos/filas/empresa desde CLI.
- people/management/commands/import_approved_test_people.py: entrada con actor
  existente obligatorio, sin contraseñas ni parámetros para ampliar el lote.
- people/tests/test_controlled_person_import.py: 12 pruebas preparadas, no
  ejecutadas. Fixtures deterministas y modelos reales, archivos temporales propios;
  rollback sin flush. Lote exacto, repetición, hashes, exclusiones, duplicados,
  fallo de auditoría y colisión simulada a mitad de lote, permisos, aislamiento,
  identidad inmutable, búsqueda HTTP y selector sin Customer.

Idempotencia propuesta: solo un lote completo con 49 Personas, accesos y auditorías
exactamente coincidentes puede devolver ALREADY_IMPORTED sin nuevas escrituras.
Cualquier estado parcial, identidad ajena o diferencia requiere nueva revisión.
requested_by/executed_by registran al operador; approved_by queda NULL porque la
autorización conversacional no debe atribuirse a un usuario Django inventado.

Check Django y comparación offline modelo/migraciones: OK; AST y diff check OK.
La comparación actual no incluye AuditLog porque todavía no está registrado.
No afirmar que el importador está probado o listo para ejecutar.

## Estado al detenerse

0 Person, 0 CompanyPersonAccess, 0 Customer y 0 AuditLog creados por esta tarea.
Consultas reales exclusivamente READ ONLY TEST. No DEV, flush, stage, commit ni
push. Siete candidatos y 1138 archivos CAT-05 verificados SHA-256 sin cambios.
Servidor TEST restablecido, PID 1691550; login HTTP 200. Credencial temporal
retirada comprobando la identidad original del archivo. El servidor conserva
su configuración exclusivamente en el proceso.

## Autorización adicional necesaria

Registrar el modelo AuditLog ya existente, crear/revisar su migración aditiva y
aplicarla solo a TEST, junto con sus ContentType/permisos. No duplicar auditoría,
no introducir un modelo nuevo alternativo y no deshabilitar triggers de identidad.
Después: nueva credencial, revalidar lote y esquema, ejecutar pruebas y regresión;
solo si pasan, ejecutar las 49 altas en la transacción auditada y verificar las
huellas de todas las filas preexistentes. La aprobación actual no se utilizó para
crear silenciosamente la infraestructura de auditoría faltante.

Evidencias: core/testing/controlled_person_import_results.json,
/tmp/person-import-preflight.json, /tmp/person-import-audit-blocker.json y
/tmp/person-import-tests.log (recolección fallida; cero pruebas ejecutadas).


## Habilitación autorizada de auditoría — estado actual

Se registró el modelo existente mediante core/models/__init__.py. No se cambió
su esquema, relaciones ni reglas generales, ni se creó un modelo duplicado.
Nueva migración core.0011_auditlog depende de core.0010 y del modelo de usuario
configurado. Crea únicamente AuditLog, sus FK e índices propios. post_migrate
creará ContentType y los cuatro permisos estándar de Django. No crea usuarios
ni concede permisos. La reversión técnica de tabla vacía es posible; con
registros se rechaza para no eliminar evidencia histórica. Guarda de reversión
usa apps.get_model y el alias de schema_editor.

Comprobaciones sin conexión: 12 pruebas de importador recolectadas correctamente;
manage.py check sin incidencias; makemigrations --check --dry-run offline sin
diferencias (historial DB no inspeccionado); pip check y diff check correctos.

La credencial temporal no está disponible. NO se aplicó core.0011_auditlog, NO
se ejecutaron casos PostgreSQL y NO se importó ningún registro. El servidor no
se reinició con el modelo todavía sin tabla. No hubo conexión a DEV ni cambios
CAT-05. Se solicitó preparar la credencial por el mecanismo habitual.

Pendiente: preflight real TEST, migración revisada y verificación de conservación
de todas las filas previas; tabla, ContentType y permisos; 12 pruebas y regresión
transaccional sin flush. Solo con todo satisfactorio se revalida el manifiesto
inmutable y se ejecutan las 49 altas autorizadas con 49 accesos y 49 auditorías,
en una transacción, conservando todos los demás registros. Cualquier fallo
impide importar y requiere diagnóstico antes de continuar.


## Ejecución autorizada: auditoría aplicada, importación NO ejecutada

Conexión real test_sisadmi_erp / sisadmi_erp_test_runner / 127.0.0.1:5432.
Preflight READ ONLY: único pendiente core.0011_auditlog; sin tabla previa en
conflicto; hashes y 49 identidades ausentes confirmados; SISADMI ID 93 y tres
triggers de identidad activos. Se pausó exclusivamente el servidor TEST.

core.0011_auditlog aplicada correctamente. Nueva tabla vacía core_auditlog,
ContentType ID 2358 y permisos add/change/delete/view_auditlog presentes. Todas
las filas preexistentes conservadas; únicas adiciones en tablas anteriores:
1 ContentType y 4 permisos. No hubo otra modificación ni eliminación de filas.

Pruebas: 116 casos descubiertos; ejecución failfast. Se ejecutó 1 prueba, con
0 aprobadas, 0 fallos y 1 error; 115 no ejecutadas. Error en fixture de
people/tests/test_controlled_person_import.py:158: SessionBase.update no acepta
company_id/branch_id como argumentos con nombre; requiere un diccionario.
No se corrigió ni reintentó tras el error, conforme a la orden de detenerse.

El primer test creó su lote únicamente dentro de TestCase y el rollback lo
revirtió por completo, incluida la auditoría. Huellas completas antes/después
idénticas. Consulta posterior READ ONLY confirmó 0 de las 49 identidades presentes
y core_auditlog con 0 filas. No se ejecutó la importación real, no Customer ni
asociaciones persistentes. La migración autorizada permanece aplicada.

Servidor TEST restablecido PID 1699840, login HTTP 200. Credencial temporal
original retirada. CAT-05 (7 candidatos y 1138 archivos) e índice/HEAD intactos;
no DEV, flush, stage, commit ni push. Próxima corrección mínima: fixture de sesión;
después nueva ejecución completa y revalidación antes de considerar importación.

Evidencias actuales: core/testing/audit_import_execution_results.json y
core/testing/audit_import_execution_tests.log. Los estados anteriores de este
informe corresponden a etapas previas y no sustituyen este resultado.


## Cierre: importación ejecutada tras corrección autorizada de fixture

La fixture usa session.update con un diccionario de company_id y branch_id
reales y guarda la sesión. No se cambiaron reglas de permisos ni autenticación.

Ejecuciones separadas: prueba HTTP anteriormente fallida 1/1; importador 12/12;
regresiones relacionadas 104/104. Todas con cero fallos y errores, rollback de
TestCase y huellas completas antes/después idénticas; sin flush ni reconstrucción.
La prueba individual se repite dentro de las 12, no constituye un caso adicional.

Se revalidaron hashes, las 100 líneas del manifiesto, 49 candidatas ausentes,
empresa SISADMI ID 93, auditoría, catálogo y los tres triggers de identidad.
Una transacción creó exactamente 49 Person (48 NATURAL y 1 LEGAL),
49 CompanyPersonAccess para SISADMI y 49 AuditLog con trazabilidad por fila.
Person: 5 → 54; asociaciones: 5 → 54; auditorías: 0 → 49; Customer: 3 → 3.
La comparación de todas las tablas dentro de la transacción confirmó que no se
modificó ni eliminó ninguna fila preexistente y solo cambiaron esas tres tablas.
Se preservó la Persona excluida y no se importaron las otras 51 filas.
Sin contactos, geografía ni accesos a otras empresas. Las 49 Personas están
visibles y seleccionables por la política y el formulario existentes.

check sin incidencias; makemigrations --check --dry-run sin cambios; pip check
sin dependencias rotas. Ninguna migración nueva en esta ejecución; core.0011_auditlog
ya estaba aplicada. CAT-05: 1138 hashes y 7 candidatos congelados verificados.
Servidor TEST restablecido, PID 1713355: http://127.0.0.1:8000/people/.
Login y recurso JS responden 200; Personas exige autenticación. Credencial
temporal original retirada después del arranque del servidor. Sin DEV, commit
ni push. Detenido para validación humana.

Evidencia agregada: core/testing/controlled_person_import_final_results.json;
logs separados controlled_person_import_{failed-test,importer-tests,regression}.log.
Trazabilidad completa en AuditLog y recibo local privado
/tmp/person-import-final-execution.json. Los resultados anteriores de este
documento son históricos y no describen el estado final de este lote.
