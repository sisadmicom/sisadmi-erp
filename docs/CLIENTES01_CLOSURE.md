# SISADMI ERP — CLIENTES-01: cierre técnico y documental

Fecha: 2026-10-18. **Estado: validación técnica y funcional cerrada; revisión Git pendiente.**
No autoriza nuevas funcionalidades, integración Git, despliegue ni cambios en bases.

## Objetivo y alcance

Diagnosticar y validar el mantenimiento existente de Clientes y corregir su
recuperación concurrente sin rediseñar Personas, Ventas ni la arquitectura.
Se reutilizaron formularios, servicios, contexto multiempresa y navegación.
El alcance probado incluye categorías, sustitución de Persona, restricciones
documentales, permisos y concurrencia PostgreSQL. Listas de precios, SRI,
importación adicional y CLI-R01 permanecen fuera del cierre.

## Etapas y aprobación

| Etapa | Resultado y fuente |
|---|---|
| CLIENTES-01.1 | Diagnóstico READ ONLY de test_sisadmi_erp: 54 Person, 54 CompanyPersonAccess, 4 Customer activos y 4 categorías activas de la empresa 93; sin company=NULL, duplicados empresa/Persona, accesos faltantes o categorías ajenas/inactivas. Cero ventas en ese diagnóstico. |
| CLIENTES-01.2 | Validación humana 8/8 aprobada por el usuario. Es una aprobación comunicada en la sesión, no una nueva ejecución automatizada. |
| CLIENTES-01.3 | Corrección de recuperación concurrente y validación aislada. Regresión histórica 42/42; selección completa 66/66, ambas con cero fallos/errores/omisiones. |

Los conteos de datos corresponden a capturas verificadas en esas ejecuciones,
no a una consulta nueva durante este cierre. GEO-01-TEST y su validación humana
se consideran antecedentes aprobados; no se modifican ni se revalidan visualmente aquí.

## Contratos funcionales vigentes

- Person es global, con identificación única y política de identidad inmutable
  existente. Customer es una relación comercial por empresa con unicidad
  `(company, person)`; CompanyPersonAccess habilita la Persona para esa empresa.
- El mantenimiento permite Adicionar, Consultar, Editar, Borrar con confirmación,
  activar/desactivar y buscar por identificación, nombre o correo. Borrar no se
  sustituye por desactivar. Las restricciones se explican al usuario.
- El Cliente selecciona una Persona existente disponible. Los botones `+` de
  Persona y categoría respetan permisos, preservan el borrador y permiten retorno.
- Categoría opcional: asignaciones nuevas solo a categorías activas de la empresa;
  una categoría asignada que después se inactiva puede conservarse.
- Sustituir Persona solo está permitido sin documentos asociados. DRAFT,
  CONFIRMED y CANCELLED bloquean sustitución y borrado. Mantener la misma Persona
  y editar campos comerciales permitidos continúa siendo válido.
- Borrar Cliente no borra Persona ni categoría. Dependencias directas y genéricas
  detectadas bloquean la operación. No hay cambios automáticos en documentos históricos.
- El contrato de Ventas continúa validando empresa y actividad de Customer,
  sin agregar Person activa ni CompanyPersonAccess como requisitos nuevos de
  creación/confirmación. El mantenimiento sí exige disponibilidad de la Persona.
- CLI-R01 (protección específica del Cliente Consumidor Final) está pendiente;
  no se confunde con las protecciones globales de Person ya existentes.

## Autorización y aislamiento multiempresa

El middleware valida empresa/sucursal desde la sesión y membresías autorizadas;
el mantenimiento es de empresa, sin imponer una nueva obligación de sucursal.
Los servicios autorizan operador, empresa y permiso de operación antes del bloqueo.
No se confía en una empresa enviada por el navegador. Todas las búsquedas con
bloqueo de Customer incluyen simultáneamente su PK y company_id. Después se
consulta de nuevo la visibilidad de la Persona actualmente persistida, sin usar
objetos de Person cacheados antes del bloqueo. Los documentos mantienen sus
validaciones operativas y su contexto de sucursal propio.

Un Customer con Person inactiva o acceso revocado deja de estar disponible en el
mantenimiento incluso con incluir inactivos. Es comportamiento vigente, no un
rediseño resuelto por este cierre. Su coherencia de experiencia con Ventas puede
revisarse funcionalmente en una etapa autorizada.

## Defecto concurrente y corrección localizada

La evidencia instrumentada anterior demostró que `SELECT FOR UPDATE` combinado
con el filtro mutable `person_id IN (Person disponibles)` devolvía cero filas
tras esperar una sustitución confirmada, aunque consultas posteriores encontraban
el mismo Cliente autorizado. No se trataba de una eliminación real ni de un PK
inventado. No se afirmó un defecto interno de PostgreSQL sin plan de ejecución.

Se añadió un override exclusivamente en `CustomerMaintenance.relation()`:

1. Las operaciones públicas ya autorizadas entran o permanecen en su transacción atómica.
2. El bloqueo recupera Customer por PK y empresa, sin subconsulta mutable.
3. Revalida la disponibilidad de `customer.person_id` obtenido después del bloqueo.
4. Conserva excepciones públicas, permisos y comprobaciones documentales existentes.

Aplica a edición, sustitución, actividad y borrado de Clientes. Las consultas sin
bloqueo delegan en la implementación anterior. Proveedores y el servicio compartido
no cambiaron por esta corrección. Una actualización SQL directa de Customer.person_id
no incorpora automáticamente estas reglas del servicio; los triggers de identidad
Person no equivalen a una restricción documental sobre esa FK.

## Entorno de validación y catálogo de pruebas

Destino exclusivo de pruebas: `test_sisadmi_clientes013`, propietario/usuario
`sisadmi_erp_test_runner`, `127.0.0.1:5432`. Base precreada manualmente; el backend
no crea, destruye ni clona bases y no conecta a bootstrap. Guardas validan parámetros,
identidad real, propietario y privilegios. Runner exige keepdb, parallel=1 y solo
los cinco módulos autorizados. Las limpiezas TransactionTestCase son exclusivas
de esa base descartable; nunca se ejecutaron en TEST poblada.

Las fixtures históricas dependían de IdentificationKind sembrado por migración.
El runner ahora registra temporalmente un inicializador People/post_migrate para
OTHER/"Otro" y PASSPORT/"Pasaporte", usando el enum oficial y get_or_create por
código único, sin PK fijas, cambios de registros existentes, reactivaciones ni
repetición de migraciones de datos. Se retira en finally y no afecta otros runners.
No se crea Consumidor Final desde este inicializador ni se implementa CLI-R01.

En la ejecución final se registraron **13 eventos**: uno inicial y doce después
de limpiezas transaccionales. Las doce limpiezas dejaron el catálogo vacío y
ambos tipos se reconstruyeron antes de las siguientes pruebas. Todos los registros
preexistentes de los eventos iniciales conservaron sus valores. El receptor quedó
desconectado después de ambas selecciones. No se introdujeron tipos inactivos
como escenario PostgreSQL adicional; ese rechazo conserva evidencia estática y
de configuración, sin atribuirle una prueba negativa real que no se ejecutó.

El lanzador externo serializa date/datetime explícitamente a ISO-8601 y rechaza
tipos desconocidos. El fallo intermedio de serialización y los errores de fixtures
se conservan en sus informes; no se reinterpretan como aprobaciones.

## Resultados finales (ejecuciones separadas)

| Selección | Ejecutadas | Aprobadas | Fallos | Errores | Omitidas | Tiempo |
|---|---:|---:|---:|---:|---:|---:|
| Históricas autorizadas | 42 | 42 | 0 | 0 | 0 | 4,564 s |
| Completa desde el inicio | 66 | 66 | 0 | 0 | 0 | 19,307 s |

Las 42 históricas están incluidas en las 66: **no son 108 casos únicos**.

| Módulo de la selección completa | Aprobadas |
|---|---:|
| test_customer_document_restrictions_clientes013 | 12 |
| test_customer_category_assignment | 14 |
| test_customer_ui_actions | 16 |
| test_customer_person_replacement | 12 |
| test_customer_document_concurrency_clientes013 | 12 |

Se comprobaron bloqueos PostgreSQL reales con PIDs independientes y
pg_blocking_pids, carreras entre venta/borrado/sustitución, rollbacks, ausencia de
efectos parciales, timeout deliberado SQLSTATE 55P03 y cierre de conexiones.
El caso original sustitución→borrado pasó conservando ambas Personas. Se verificaron
permisos antes de bloqueo, aislamiento, restricciones en los tres estados y FK real.

La prueba de revocación demuestra solamente el orden **commit de sustitución y
revocación → revalidación de borrado → rechazo**. No demuestra protección general
ante revocaciones posteriores a la revalidación ni todos los intercalados posibles.
Las referencias genéricas carecen de FK y no adquieren garantía universal por
estas pruebas. No se declara lista toda la suite ERP ni un despliegue productivo.

## Preservación de TEST poblada y cierre de ejecución

Se pausó el servidor TEST durante la ventana de pruebas. Conexión separada R-01
exclusivamente READ ONLY a `test_sisadmi_erp`, sin añadirla como alias del runner.
Se compararon conteos y SHA-256 de filas completas ordenadas en **todas las tablas**,
antes/después de ambas ejecuciones, incluidos 54 Person, 54 accesos, cuatro Customer,
claves y referencias geográficas. Coincidencia completa; sin otras conexiones
observadas en las capturas. No hubo migraciones, flush ni escrituras en esa base.

La base aislada quedó sin conexiones residuales. Se restableció el servidor TEST,
login HTTP 200 y se retiró la credencial temporal original. No se reutilizaron
credenciales del servidor web. No se abrió DEV. CAT-05 conservó 1138 hashes de
archivos preservados y siete candidatos congelados. Los cambios acumulados de
otras etapas visibles en Git no fueron introducidos ni corregidos por CLIENTES-01.

En la validación final: manage.py check, makemigrations --check --dry-run (READ ONLY),
pip check y git diff --check satisfactorios, sin migraciones nuevas ni pendientes.
**Este cierre solo ejecuta comprobaciones estáticas; no repite esos comandos que
requieren conexión ni las pruebas PostgreSQL.**

## Control de versiones y decisión de cierre

Rama `main`; HEAD `e5c4c6cec2f410772dfbe7eb434bf3932b895692`. Índice sin stage.
Inventario inicial: 97 archivos modificados y 282 sin rastrear. Este cierre añade
únicamente dos documentos: este y [el inventario completo](CLIENTES01_GIT_INVENTORY.md).
No se modificó código, pruebas, informes anteriores ni artefactos de otras etapas.

**GO para cierre técnico/documental. NO-GO para un commit funcional independiente
desde HEAD sin integrar o separar antes los prerrequisitos.** El working tree
validado incluye infraestructura R-01, modelos/migraciones de Personas/categorías,
UI compartida, relaciones CAT-02.3 y cambios documentales aún sin integrar.
El servicio Customer completo está sin rastrear; no representa solo el pequeño
fix de bloqueo. Un commit parcial presentado como autónomo sería incompleto.

El inventario contiene la lista exacta de 20 candidatos condicionados, las
dependencias, los 381 archivos finales clasificados y los mensajes propuestos.
No se ejecuta ninguna operación Git que modifique índice/historial. Un commit
solo documental puede revisarse por separado, explicando las dependencias pendientes.

## Seguridad, limitaciones y próximos trabajos

La revisión estática de candidatos no detectó secretos reales, claves/certificados
privados ni URLs con credenciales. Los literales localizados son placeholders o
fixtures de pruebas. Las evidencias contienen códigos de catálogo, SQL, PIDs, PK
internas y huellas; no exportaciones de nombres o identificaciones personales.
No es una garantía absoluta contra todo patrón posible de secreto. No se incorporan
.env, credenciales de /run/user, certificados, .venv, bases, backups DEV ni logs
externos. El manifiesto de candidatos excluye etapas ajenas e informes intermedios.

Pendientes, sin implementación ni autorización implícita:
- CLI-R01: protección especial del Customer Consumidor Final.
- Integrar/separar etapas previas para preparar commits coherentes y reproducibles.
- Si se requiere, aprobar mayor cobertura de revocaciones concurrentes y referencias genéricas.
- Búsqueda/paginación del selector de Personas y demás mejoras UI futuras requieren acuerdo.
- No avanzar automáticamente a listas de precios, otros módulos ni SRI.
- Los lanzadores y logs de /tmp son efímeros; no se copian a Git automáticamente.
  La evidencia final persistente está en core/testing; una futura formalización
  del lanzador requiere revisión propia y no forma parte de este cierre.

## Referencias persistentes

- [Validación final 42/42 y 66/66](../core/testing/CLIENTES013_FINAL_VALIDATION.md).
- [Resultados por caso, señales y huellas](../core/testing/clientes013_final_validation_results.json).
- [Caso concurrente original corregido](../core/testing/clientes013_final_original_evidence.json).
- [Revocación concurrente: orden específico](../core/testing/clientes013_final_revocation_evidence.json).
- [Aislamiento, administración y recuperación](../core/testing/CLIENTES013_TEST_ISOLATION.md).
- [Convenciones UI acordadas](UI_CONVENCIONES.md).
- [Inventario y candidatos Git](CLIENTES01_GIT_INVENTORY.md).

Historial de errores y avances: CLIENTES013_EXECUTION, REPEAT, INSTRUMENTED_DIAGNOSIS,
FIX_VALIDATION y CATALOG_VALIDATION en core/testing. Se conservan como historial,
no reemplazan los resultados finales. CLIENTES-01.2 queda sustentada por aprobación
humana 8/8 de la sesión; no se inventa un acta de pruebas adicional.

**Detenido para revisión humana antes de stage, commit, push o nuevas modificaciones.**
