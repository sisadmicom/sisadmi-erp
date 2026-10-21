# Corrección de acciones y altas relacionadas de clientes

Estado: corrección implementada y 42 pruebas aprobadas en PostgreSQL TEST.
Servidor actualizado; pendiente de validación personal del usuario.

## Implementación

- Listado de clientes: Adicionar, Editar y Borrar directamente visibles. Las
  operaciones sin permiso están deshabilitadas y explican el permiso requerido.
  Consultar se conserva; Desactivar/Reactivar no sustituyen Borrar.
- Borrar: ruta GET de confirmación, POST explícito con CSRF y permiso
  people.delete_customer. Se revalida empresa, Persona visible y cliente bajo
  bloqueo de fila. Se comprueban referencias ORM y GenericForeignKey reales;
  dependencias bloquean y muestran mensaje claro. Se conservan Persona/categoría.
- `+ Persona` en alta de cliente y `+ Categoría` en alta/edición: reutilizan las
  pantallas existentes y ui_drafts, sin otro almacén. Conservan notas, crédito,
  categoría y Persona, incluso incompletos, y retornan seleccionando el creado.
- Cancelar retorna sin perder el borrador. Se revalidan permisos/contexto, sesión,
  destino y estado antes de crear y retornar. Se conserva el retorno anidado de
  ubicación desde Persona. Repetir el POST del hijo ya consumido se rechaza.
- Se conserva la integración opcional de categoría, incluidas asignaciones
  inactivas existentes y aislamiento de empresa. Se corrigió la inicialización
  para que una categoría recién creada no sea ocultada por una antigua inactiva.
- No se cambiaron modelos ni se generaron migraciones. Proveedores y otros
  mantenimientos no se amplían; solo se integran los puntos de retorno necesarios.

## Regla aprobada y verificada

La Persona puede sustituirse únicamente sin documentos asociados. Ventas tiene
la FK directa Sale.customer; ElectronicDocument y StockMovement tienen enlaces
GenericForeignKey documentales. Se comprueban todos los estados, incluso borradores.
El servicio autoriza empresa/permisos y bloquea Customer antes de revalidar
referencias. Rechaza la sustitución con error de campo person, código
person_has_documents. Mantener la misma Persona o editar otros campos sigue
permitido. Una Persona no visible en la empresa se rechaza con identity_unavailable;
una relación duplicada con duplicate_relationship. Los documentos no se actualizan.

El selector Persona y su botón + están disponibles en edición sin documentos.
Con documentos se muestra el motivo, se deshabilita + y se rechaza cualquier
intento de sustitución, incluido POST manipulado. La categoría y los datos del
borrador se conservan al regresar desde la creación relacionada.

## Pruebas y conservación — ejecución real

Una ejecución: 42 pruebas, 42 aprobadas, 0 fallos, 0 errores (4.018 s):
14 de asignación de categorías, 16 de acciones/altas relacionadas y 12 nuevas
de sustitución de Persona. Registro completo: /tmp/customer-person-tests.log.
Se evitó recolectar por segunda vez la clase importada de pruebas de categorías.

Runner temporal limitado a esos tres módulos y Django TestCase transaccionales,
keepdb=True, parallel=1. No ejecutó flush, creación/destrucción de bases ni
migraciones. Verificó identidad test_sisadmi_erp / sisadmi_erp_test_runner /
127.0.0.1:5432. Comparó SHA-256 de todas las filas preexistentes: idénticas antes
y después. Evidencia: /tmp/sisadmi-customer-ui-actions-data-integrity.json.
No se ejecutó la suite completa porque su limpieza podría borrar los registros
humanos existentes. La suite congelada conserva contratos antiguos de Persona
inmutable; no se modificó ni ejecutó en esta tarea.

manage.py check: sin incidencias. makemigrations --check --dry-run: No changes
detected. pip check: sin dependencias rotas. git diff --check: sin incidencias.
Sin modelos ni migraciones nuevos. HEAD e índice sin cambios; siete candidatos
congelados y 1138 archivos del manifiesto CAT-05 verificados por SHA-256.

Servidor TEST actualizado: PID 1154179, 127.0.0.1:8000. Login HTTP 200 y clientes
sin sesión redirige al login. Archivo de credencial temporal retirado comprobando
su identidad original; el servidor conserva la credencial solo en su proceso.
No se conectó DEV. No stage, commit ni push.

## Rutas para revisión tras pruebas/recarga

- Listado: http://127.0.0.1:8000/people/customers/
- Alta: http://127.0.0.1:8000/people/customers/new/
- Edición: botón Editar directamente en la fila.
- Borrado: Borrar → confirmar o cancelar. Con venta u otra dependencia, se bloquea.
- Persona: escribir notas/crédito/categoría, pulsar `+` junto a Persona, registrar
  o cancelar, comprobar retorno y guardado de cliente con datos conservados.
- Categoría: usar `+` junto a su selector; comprobar retorno seleccionado.

Convenciones generales: docs/UI_CONVENCIONES.md y AGENTS.md. No continuar UI-02
ni otro trabajo tras esta corrección hasta la validación y aprobación del usuario.
