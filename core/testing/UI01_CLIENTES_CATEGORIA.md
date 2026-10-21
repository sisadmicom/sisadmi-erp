# Integración de categorías en clientes

Estado: integración disponible en el servidor TEST reiniciado; migración aplicada
y 14 pruebas aprobadas. Pendiente únicamente de validación personal del usuario.

## Resultado de la ejecución autorizada

Identidad verificada: test_sisadmi_erp, sisadmi_erp_test_runner, 127.0.0.1:5432.
No se accedió a DEV. El servidor TEST propio se detuvo durante la intervención.

Primero se aplicó 0008 dentro de una transacción de prueba: las 14 pruebas
aprobaron en 1.105 s; se revirtieron esquema y registro de migración y se comprobó
igualdad de las huellas de todas las filas preexistentes. Solo después se aplicó
people.0008_customer_category_assignment definitivamente, con código 0.

Sobre el esquema definitivo se repitieron los 14 casos: 14 aprobados, cero fallos
y cero errores, 1.140 s. Son dos ejecuciones independientes, no 28 casos distintos.
No hubo creación/reconstrucción de base, flush ni eliminación de registros humanos.

Se conservaron el cliente y las cuatro categorías existentes. La comparación de
huellas también verificó las demás tablas, incluidos usuarios y sesiones, sin
persistir sus valores en informes. La migración solo añadió category_id nullable;
no asignó categorías automáticamente ni alteró los demás campos existentes.

check: sin incidencias. makemigrations --check --dry-run: No changes detected.
pip check: No broken requirements found. git diff --check: correcto.

Servidor reiniciado: PID 1085483, sesión 73156, 127.0.0.1:8000, settings_ui01_test.
Login HTTP 200; listado y alta sin autenticación HTTP 302 hacia login, como corresponde.
La prueba automatizada autenticada comprobó creación, edición y visualización;
no se usaron las sesiones del usuario para suplantarlo. La credencial temporal
se retiró verificando dispositivo/inode; el servidor conserva su configuración
solo en memoria del proceso.

Registros locales: /tmp/sisadmi-customer-category-trial.log,
/tmp/sisadmi-customer-category-migrate.log,
/tmp/sisadmi-customer-category-test.log,
/tmp/sisadmi-customer-category-checks.log y
/tmp/sisadmi-customer-category-web.log.
Resumen persistente: customer_category_assignment_results.json.

## Contrato implementado

- Se reutiliza CustomerCategory. Customer incorpora category nullable/blank,
  FK PROTECT y related_name customers. No hay clasificación automática ni
  cambio obligatorio para clientes existentes.
- Selector Categoría de cliente en alta/edición: categorías activas de la empresa
  autorizada. Campo opcional; no requiere permisos de mantenimiento de categorías,
  sí los permisos de cliente y Persona ya exigidos por el recorrido existente.
- Customer.clean valida empresa. CustomerMaintenance valida de nuevo la categoría
  y bloquea su fila durante la asignación, rechazando inexistentes, ajenas e
  inactivas nuevas con código invalid_category. Supplier conserva su contrato.
- Una actualización parcial sin category conserva la categoría. Vacío explícito
  elimina una asignación activa. Si la actual se desactivó, se muestra su estado
  y la opción Conservar categoría actual (inactiva); vacío conserva esa asignación,
  mientras elegir una activa la sustituye. La inactiva no se ofrece como nueva
  categoría seleccionable. El servicio permite conservar su ID existente.
- Listado y consulta muestran código/descripción o Sin categoría y distinguen
  asignaciones inactivas. La consulta del listado usa select_related category.
- Una categoría asociada no puede borrarse, gracias a PROTECT. La desactivación
  sigue permitida y conserva las asociaciones existentes.

## Migración

people/0008_customer_category_assignment: exclusivamente AddField nullable,
dependiente de 0007. Sin backfill, fechas inventadas ni sustitución de datos.
Generada y revisada con el grafo en disco; aplicada posteriormente solo en TEST
tras aprobar la prueba transaccional indicada arriba.

El harness histórico incorpora únicamente este nodo adicional a sus listas
explícitas y expectativas de restauración. Conserva la guarda contra reversión
cuando hay categorías. No se editó ningún archivo congelado.

## Protección de los datos humanos en TEST

El usuario ya registró categorías en test_sisadmi_erp. No se ejecutará allí una
suite que use flush, TransactionTestCase o transiciones históricas.
Para los nuevos casos se preparó un lanzador temporal que:

1. Exige la credencial privada y el destino/rol R-01 exactos; valida propietario
   y privilegios usando el bootstrap de solo lectura.
2. Exige detener antes el servidor local de revisión y rechaza otras transacciones
   activas/no verificables en TEST.
3. Admite para migración solo 0008 hacia delante y compara hashes de filas antes y
   después, excluyendo únicamente la columna nueva en esa comparación inicial.
4. Admite solo el módulo nuevo y Django TestCase con transacciones/savepoints y
   rollback; rechaza TransactionTestCase puro y serialized_rollback.
5. No crea bases, no hace setup/migrate/serialize/flush de la base desde el runner.
   Verifica que no haya migraciones pendientes y usa la TEST existente.
6. Compara después todas las filas preexistentes, incluida category_id, mediante
   hashes; no escribe datos empresariales, certificados ni contraseñas en logs.

Las secuencias pueden avanzar por inserts revertidos; eso no borra ni modifica
filas humanas. Una discrepancia detiene la secuencia sin reparación automática.
Después se ejecutan checks y se recarga únicamente el servidor TEST propio.

La suite completa queda pendiente para una TEST desechable separada; no se
ejecuta sobre la base que ahora contiene datos humanos de revisión. Esta
restricción de conservación prevalece sobre vaciar TEST para una regresión.

## Pruebas preparadas

people/tests/test_customer_category_assignment.py contiene 14 Django TestCase:

- Selector activo por empresa.
- Alta con categoría y visualización en listado/consulta.
- Alta opcional sin categoría.
- Inicialización y cambio en edición.
- Conservación al editar otros datos, incluida omisión del campo.
- Limpieza explícita de una asignación activa.
- Conservación/reemplazo de una asignación que pasó a inactiva.
- Rechazo HTTP de ajena/inactiva/inexistente.
- Rechazo en servicio con rollback sin cambiar cliente.
- Rechazo de alta en servicio con ajena/inactiva.
- Validación multiempresa del modelo.
- Protección contra borrado de categoría asociada.
- Conservación de permisos de edición.
- Formulario de proveedor sin campo de categoría de cliente.

Las 14 pruebas se ejecutaron y aprobaron; la credencial temporal se retiró.
AST, manage.py check, compilación de plantillas, comparación offline de
modelos/grafo, pip check y git diff --check: correctos.
makemigrations --check --dry-run con historial TEST: aprobado.

Compatibilidad detectada por inspección: las pruebas congeladas de formulario
Customer en test_commercial_relationship_web_cat023_red exigen conjuntos exactos
de campos anteriores (persona/notas/crédito). El nuevo selector aprobado amplía
ese contrato; no se editaron esas aserciones ni se oculta el campo para aparentar
compatibilidad. La regresión congelada completa deberá registrar esa discrepancia
cuando se ejecute en una base desechable, además de validar los contratos nuevos.

## Archivos

people/models/customer.py; commercial_forms.py; commercial_views.py;
services/customer_maintenance.py; services/commercial_relationship_maintenance.py;
templates/people/commercial_form.html, commercial_list.html y commercial_detail.html;
migrations/0008_customer_category_assignment.py;
tests/test_customer_category_assignment.py;
core/testing/migration_isolation.py y core/tests/test_migration_isolation.py.

## Revisión humana posterior

- Clientes: http://127.0.0.1:8000/people/customers/
- Alta: http://127.0.0.1:8000/people/customers/new/
- Edición: Consultar → Editar en el cliente correspondiente.

Tras aplicar migración y recargar: elegir categoría activa, guardar, consultar,
editar notas sin cambiar categoría, recargar y comprobar persistencia. Repetir
con cliente sin categoría. No continuar UI-02 hasta comprobar esta integración.
No se accedió a DEV, no hubo envío SRI ni commits/push.
