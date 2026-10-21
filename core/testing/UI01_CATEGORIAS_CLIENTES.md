# UI-01 — Categorías de clientes

Estado: pruebas UI-01 aprobadas, migración aplicada exclusivamente a PostgreSQL
TEST y servidor local iniciado. Pendientes la creación de usuario/contexto humano
y la validación personal del usuario. No se declara validada la interfaz.

## Ejecución con credencial TEST

| Ejecución independiente | Pruebas | Aprobadas | Métodos con fallo | Métodos con error |
|---|---:|---:|---:|---:|
| Afectadas, primer intento | 46 | 31 | 0 | 15 |
| Afectadas, corregido fixture de sesión | 46 | 46 | 0 | 0 |
| Completa, antes del ajuste Supplier | 1777 | 1737 | 36 | 4 |
| Afectadas más compatibilidad Supplier | 53 | 53 | 0 | 0 |
| Tres clases históricas Customer/Supplier | 16 | 16 | 0 | 0 |

No se suman ejecuciones. La completa registra failures=81, errors=4 por subcasos.
El primer intento falló por SessionBase.update utilizado con argumentos nombrados
en el fixture nuevo; se corrigió a un diccionario, sin alterar aserciones.
Las 15 pruebas de categorías aprobaron en las ejecuciones corregidas.

De los 36 métodos con fallo de la completa, seis eran de SupplierMigrationRedTests:
su transición congelada no admite la nueva migración 0007. El runner ahora retira
temporalmente solo 0007 alrededor de esa clase, protege la tabla si contiene datos
y restaura exactamente el esquema. Se preservaron sus archivos y aserciones.
Los seis aprobaron en las dos últimas ejecuciones. La suite completa no se repitió
tras este ajuste; no se presenta un conteo completo inferido de esos resultados.

Los otros 30 métodos con fallo y cuatro con error son los pendientes generales
ya documentados: bootstrap, navegación de alta, texto 403 geográfico y acciones
Borrar. No son fallos de categorías; véase R05_REGRESION.md.

check y makemigrations --check --dry-run posteriores al ajuste: código 0,
sin incidencias y No changes detected. migrate: código 0, No migrations to apply
porque 0007 ya se aplicó en la preparación de tests. pip check: correcto.

Identidad comprobada: test_sisadmi_erp, sisadmi_erp_test_runner, 127.0.0.1:5432;
sin privilegios administrativos del rol. No se accedió a DEV.
Los conteos posteriores muestran cero usuarios activos y cero empresas en TEST.

Servidor original: PID 862160, sesión de ejecución 93488, solo 127.0.0.1:8000.
Fue reemplazado al integrar categorías en clientes; estado actual en
UI01_CLIENTES_CATEGORIA.md. No utilizar el PID antiguo para detener el servidor actual.
Login y CSS: HTTP 200. Categorías anónimas: HTTP 302 al login.
Log original: /tmp/sisadmi-ui01-web.log. Para detener el proceso actual, identificar
primero su PID/comando y utilizar únicamente el proceso TEST propio.
La credencial temporal fue retirada verificando dispositivo/inode; la conexión
del servidor utiliza la credencial en memoria del proceso, sin archivo secreto
rastreado. Para comandos administrativos propios, configurar variables según
las instrucciones siguientes. No ejecutar la suite mientras se usan datos humanos.

## Acceso y operaciones

- Login: http://127.0.0.1:8000/core/login/
- Pantalla: http://127.0.0.1:8000/people/customers/categories/
- Menú: Clientes → Categorías de clientes.
- Operaciones: listar activos/inactivos, buscar código/descripción, adicionar,
  consultar, editar, desactivar y activar. Listado paginado de 25 filas.
- Campos: código obligatorio (32 caracteres; entrada normalizada a mayúsculas),
  descripción obligatoria (150) y estado controlado por acciones POST.
- Unicidad: empresa + código, incluidos inactivos; restricción PostgreSQL protege
  escrituras concurrentes. El formulario presenta el conflicto en el campo código.
- No hay ruta de eliminación. La desactivación conserva registro y auditoría.

## Usuario y permisos

Usuario activo y autenticado con membresía explícita en empresa activa y sucursal
activa de esa empresa. Los permisos Django son:

```
people.view_customercategory
people.add_customercategory
people.change_customercategory
```

Solo consulta requiere view; mantenimiento completo requiere los tres.
Ni superusuario evita la membresía de empresa/sucursal. No se creó una cuenta
ni se inspeccionaron cuentas DEV. El contexto se toma de la sesión validada por
el middleware y se revalida; campos company enviados por navegador se ignoran.
Objetos de otra empresa devuelven 404 al actor con permiso. Mutaciones llevan
CSRF. GET/HEAD no cambian estado. No se ofrece permiso de borrado en la UI.

## Arranque local exclusivo TEST — instrucciones para la terminal del usuario

Usar la instancia TEST existente y sus credenciales, nunca las DEV. La acreditación
administrativa R-01 de rol/HBA debe seguir vigente. En una terminal propia:

```bash
cd /home/sisadmi/workspace/sisadmi-erp/sisadmi-erp
source .venv/bin/activate
export R01_TEST_DB_HOST=127.0.0.1
export R01_TEST_DB_PORT=5432
read -r -s -p 'Contraseña PostgreSQL TEST: ' R01_TEST_DB_PASSWORD
printf '\n'
export R01_TEST_DB_PASSWORD
export R01_TEST_ADMIN_VERIFIED=1
```

No heredar variables PG*; las guardas las rechazan. No mostrar el entorno.
No colocar contraseña en comandos, archivos rastreados ni chat.

Ejecutar primero la regresión, antes de ingresar datos humanos: Django puede
vaciar TEST durante las pruebas. No usar runserver al mismo tiempo que la suite.

```bash
python -B manage.py test people.tests.test_customer_category_ui01 \
  core.tests.test_migration_isolation core.tests.test_application_shell \
  core.tests.test_auth_navigation \
  --settings=config.settings_test_r01 --keepdb --parallel=1
python -B manage.py check --settings=config.settings_ui01_test
python -B manage.py makemigrations --check --dry-run --settings=config.settings_ui01_test
```

Revisada la migración 0007, aplicar únicamente a TEST:

```bash
python -B manage.py migrate --settings=config.settings_ui01_test
```

Si TEST no tiene un usuario habilitado, crear uno interactivo en TEST:

```bash
python -B manage.py createsuperuser --settings=config.settings_ui01_test
python -B manage.py runserver 127.0.0.1:8000 --settings=config.settings_ui01_test
```

El servidor anterior ya está iniciado: ahora solo hace falta createsuperuser
si no se dispone de cuenta TEST. No iniciar un segundo servidor en el mismo puerto.
Elegir usuario y contraseña interactivos en la terminal propia, no en el chat.

En instalación vacía, el superusuario puede seguir el alta inicial existente de
empresa/persona y sucursal desde la interfaz; luego selecciona empresa y sucursal.
Si ya hay empresas, necesita una membresía autorizada existente. Para un operador
normal, el administrador asigna las membresías y los tres permisos indicados.
La gestión cotidiana de categorías no utiliza Django Admin.

settings_ui01_test hereda solo los settings TEST independientes, fija el alias
default a test_sisadmi_erp y conserva rol/host/puerto/guardas existentes. DEBUG se
habilita para servir los estáticos en el servidor local, enlazado a 127.0.0.1.
No usar estos settings para producción. Al cerrar el servidor:

```bash
unset R01_TEST_DB_PASSWORD R01_TEST_ADMIN_VERIFIED
```

## Validación humana propuesta

1. Iniciar sesión, seleccionar empresa y sucursal, abrir Clientes → Categorías.
2. Adicionar código MAYORISTA, descripción Clientes mayoristas; guardar y consultar.
3. Editar descripción, guardar, recargar y comprobar persistencia.
4. Buscar por código y por parte de la descripción.
5. Desactivar; verificar que sigue listada como inactiva y puede activarse.
6. Intentar código duplicado y campos vacíos; verificar mensajes sin perder datos.
7. Con otra empresa autorizada, comprobar aislamiento del listado y objetos.

Estos valores son ejemplos de catálogo para revisión, no datos tributarios.
La validación corresponde al usuario; no se simula su aprobación.

## Componentes y cambios

No había modelo equivalente. Se añade CustomerCategory en Personas, reutilizando
BaseModel (fechas, actor, actividad), FK protegida a Company y permiso Django.
No se añade relación a Customer todavía: queda para UI-03, mediante FK opcional
aditiva, PROTECT y validación de empresa/actividad; no clasificar clientes existentes
automáticamente. UI-02 deberá definir listas de precios, su propiedad empresarial
y valores por producto; no se encontró un modelo de listas de precios actual.
Productos/impuestos/precios y SRI se conservan fuera de UI-01.

Archivos:

- people/models/customer_category.py y export en people/models/__init__.py.
- people/migrations/0007_customer_category.py: solo CreateModel, sin tocar datos.
- people/customer_category_forms.py y people/customer_category_views.py.
- people/urls.py y cuatro templates customer_category_*.html.
- core/templates/core/base.html: submenú Clientes.
- config/settings_ui01_test.py: arranque web local en TEST.
- people/tests/test_customer_category_ui01.py: 15 métodos preparados.
- core/testing/migration_isolation.py y core/tests/test_migration_isolation.py:
  compatibilidad explícita con 0007, preservando rechazo de migraciones desconocidas,
  restauración exacta y bloqueo de reversión si la tabla contiene categorías.
  Se añade una prueba de conservación de esos datos.
- core/testing/runner.py: aislamiento explícito de SupplierMigrationRedTests,
  sin editar la prueba congelada; nueva prueba de restauración del ámbito Supplier.

## Evidencias iniciales sin credencial (anteriores a la ejecución)

- manage.py check con settings_ui01_test: aprobado, sin conexión a base.
- Cinco MigrationIsolationSafetyTests: aprobados, sin conexión.
- Modelos/grafo en disco: sin cambios pendientes tras generar 0007; cuatro
  plantillas compiladas; AST de archivos modificados correcto.
- pip check y git diff --check: correctos.
- No existe la credencial temporal TEST solicitada. No se ejecutaron los 15 tests
  UI, las transiciones PostgreSQL del harness, regresión principal ni suite completa.
- makemigrations --check --dry-run: intentado con la guarda administrativa
  cerrada; código 1 antes de conectar, porque falta la acreditación de ejecución
  con credencial TEST. Registro /tmp/sisadmi-ui01-makemigrations-check.log.
  La comparación offline aprobada no sustituye su ejecución con historial TEST.
- Migración 0007 revisada y no aplicada a TEST ni DEV. No se inició servidor ni se
  creó usuario. Sin migración aplicada, la pantalla aún no puede guardar categorías.
- Validación humana pendiente. No se modificó SRI ni el trabajo R-04/R-05/R-06.

Los bloqueos por credencial y migración de esta sección inicial fueron resueltos
en la ejecución descrita al principio. Pendiente actual: crear cuenta TEST desde
terminal propia, completar empresa/sucursal y realizar la revisión humana.
UI-02 comienza tras esa validación.
