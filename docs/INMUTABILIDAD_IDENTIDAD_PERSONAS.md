# Inmutabilidad de identidad de Personas

Estado: migración aplicada y 104 pruebas PostgreSQL aprobadas. Servidor TEST
actualizado; pendiente de validación humana.

## Contrato

Person.id conserva la PK BigAutoField. identification, identification_type e
identification_kind_id se congelan tras INSERT. Django rechaza cambios con
immutable_person_identity; PostgreSQL compara OLD/NEW mediante IS DISTINCT FROM.
No existe excepción para superusuarios Django, migraciones o flags de sesión.
Asignar nuevamente los mismos valores se permite en PostgreSQL y para Personas
ordinarias en Django. Consumidor Final conserva la prohibición especial Django.
Nombre, person_type, contacto y ubicación siguen editables con permisos y ámbito
vigentes, sin bloqueo por estar vinculada con Company/Customer/documentos.

El catálogo protege su code en save/clean y en PostgreSQL. Las nuevas altas deben
contener tipo y FK no NULL, con coincidencia de IdentificationKind.code; la
clasificación FINAL_CONSUMER solo corresponde al identificador reservado. Esto
no duplica el algoritmo de cédula/RUC en SQL; la validación central sigue en Django.
No se reclasifican registros históricos ni se completan NULL automáticamente.

## Migración aplicada exclusivamente en TEST

people.0011_person_identity_immutable, posterior a 0010. RunSQL reversible, sin
operaciones DML ni borrado de registros. Crea tres funciones y tres triggers:
- people_person_identity_immutable: BEFORE UPDATE OR DELETE. Inmutabilidad de
  identidad; adicionalmente bloquea modificación real y borrado del reservado.
- people_person_identity_coherent: BEFORE INSERT; exige coherencia código/FK.
- people_identification_kind_code_immutable: BEFORE UPDATE; protege code.

Errores PostgreSQL SQLSTATE 23514 y constraint_name estable; mensajes sin valores
personales. La reversión elimina exclusivamente los triggers y funciones propios,
sin tocar datos. Aplicada en TEST tras preflight con historial consistente,
plan limitado a 0011, coherencia de pares no NULL y ausencia de triggers previos
que requieran revisión. Los históricos con uno o ambos valores NULL se conservan.

Los propietarios de tablas/superusuarios PostgreSQL pueden retirar protecciones
DDL; un superusuario Django no obtiene esa capacidad por serlo. El rol operativo
no debería disponer de privilegios DDL. No se modifican roles en esta tarea.

## Django e interfaz

Guardia del modelo protege también identification_kind_id. El servicio existente
person_access_policy incorpora update_person, con permiso change_person,
empresa autorizada, Persona visible, bloqueo de fila y auditoría. La vista normal
reutiliza este servicio. La edición administrativa de Persona fundadora usa el
mismo mixin de campos disabled y rechazo explícito de POST manipulado. Los
campos omitidos conservan su valor, incluidos NULL; valores forjados (también
parámetros repetidos) producen un mensaje neutral de inmutabilidad. Detección
central y JavaScript permanecen para altas; en edición se informa inmutabilidad.

No basta con disabled en navegador: hay validación de formulario, modelo y DB.
QuerySet.update puede asignar valores iguales y expresiones; el trigger decide
atómicamente si hay cambio real. Bulk create sigue bloqueado por el contrato
previo. No se amplía la importación de clientes.

## Pruebas y evidencias reales — 17 de octubre de 2026

17 pruebas PostgreSQL nuevas en test_person_identity_immutability.py, 17 aprobadas:
alta válida, tres campos por modelo y SQL, servicio, superusuario HTTP, valores
iguales, inserción incoherente, código de catálogo, datos descriptivos/ubicación,
Company/Customer, ámbito, protección reservada, rollback y reversibilidad/NULL.

La simulación de históricos revierte explícitamente 0011 dentro de la transacción
de un TestCase, inserta una fila temporal previa a protección y reinstala 0011;
todo se revierte con rollback. No introduce excepción de ejecución en el trigger.
El test de contrato histórico previo se adapta a esa misma preparación explícita.
Regresiones de formulario se adaptan a identidad disabled y conservación del tipo,
sin modificar expectativas de seguridad ni pruebas CAT-05.

Una ejecución PostgreSQL: 104 pruebas, 104 aprobadas, 0 fallos, 0 errores,
12.483 s. Incluye 17 nuevas de inmutabilidad y las 87 regresiones de identificación,
clientes, categorías, formularios, navegación y retornos relacionados de Personas.
La ejecución usó failfast; no apareció ningún error ni se hicieron correcciones
automáticas de datos o código durante esta validación.

Por separado: 24 pruebas unitarias del validador, 24 OK. No sumar ejecuciones.
manage.py check: sin incidencias. makemigrations --check --dry-run con conexión e
historial real TEST: No changes detected. pip check y git diff --check OK.
No se ejecutó la suite completa porque se conserva la base con registros humanos.

## Preflight, conservación y postflight

Identidad acreditada: test_sisadmi_erp / sisadmi_erp_test_runner / 127.0.0.1:5432.
Historial consistente; único pendiente people.0011_person_identity_immutable.
Esquema id bigint PK, identificación no NULL, tipo y FK nullable. Cero conflictos
entre tipo/catálogo, cero triggers de usuario previos y cero funciones en conflicto.
Había 1 Persona histórica con clasificación NULL.

Se pausó únicamente el servidor TEST. Aplicación de 0011 correcta. Comparación de
huellas SHA-256 de todas las filas y todas sus columnas antes/después: idénticas,
exceptuando únicamente el registro de historial de migraciones esperado. Las
pruebas también conservaron todas las filas mediante TestCase rollback; sin flush,
creación/destrucción de bases ni borrado persistente de registros.

Postflight de solo lectura: migración aplicada una vez y los tres triggers activos
(tgenabled=O). La Persona histórica NULL permanece intacta; se conservó el mismo
conteo 1. Pruebas de SQL directo verificaron SQLSTATE 23514 y constraint_name
para los tres campos de identidad, catálogo, coherencia y protección reservada.
Los valores idénticos se permitieron. La reversión/reinstalación técnica se probó
en una transacción de test, sin excepción en la función de protección.

Siete candidatos congelados y 1138 archivos sellados CAT-05 verificados SHA-256
sin cambios. No DEV, flush, stage, commit ni push. HEAD e índice se compararon
con la captura al inicio de esta validación, sin cambios.

Servidor TEST actualizado: PID 1492750, 127.0.0.1:8000. Login y JavaScript HTTP 200;
creación sin sesión redirige a login. La credencial temporal original fue retirada
tras verificar inode, dispositivo, propietario, permisos 0600 y enlace único.
El servidor conserva su conexión configurada únicamente en el proceso.

## Evidencias

- core/testing/person_identity_immutability_results.json
- core/testing/person_identity_immutability_validation.log
- /tmp/person-identity-immutable-preflight.json
- /tmp/person-identity-immutable-migration-integrity.json
- /tmp/person-identity-immutable-test-integrity.json
- /tmp/person-identity-immutable-postflight.json

## Validación humana

- Adicionar: http://127.0.0.1:8000/people/new/
- Listado: http://127.0.0.1:8000/people/
- Editar: botón de la Persona, /people/<id>/edit/.

Comprobar detección en alta; en edición identificación/tipo aparecen deshabilitados.
Cambiar nombre, contacto, dirección y ubicación, guardar y comprobar persistencia.
Consumidor Final sigue protegido. No continuar importación ni otros módulos hasta
aprobación del usuario.

## Archivos relacionados

people/identity_integrity.py; people/models/person.py;
people/models/identification_kind.py; people/services/person_protection.py;
people/services/person_access_policy.py; people/forms.py; core/forms.py;
people/views.py; people/static/people/js/identification.js;
people/migrations/0011_person_identity_immutable.py;
people/tests/test_person_identity_immutability.py;
people/test_identification_type_contract.py; people/tests/test_person_form_ui.py.

Validación automatizada completada; falta aprobación humana. No DEV, flush,
commit ni push.
