# R-01 Base — PostgreSQL descartable independiente

Estado: implementación local, sin integración Git ni validación PostgreSQL real.
No se ha creado la base ni se han ejecutado migraciones con este paquete.

## Contrato cerrado

- Settings: `config.settings_r01_base_test`.
- Backend: `core.testing.r01_base_postgresql`.
- Alias único: `default`; sin routers, mirrors ni aliases auxiliares.
- NAME y TEST.NAME: `test_sisadmi_r01`.
- Usuario y propietario: `sisadmi_erp_test_runner`.
- Servidor TCP: `127.0.0.1:5432`.
- Contraseña obligatoria: `R01_BASE_TEST_DB_PASSWORD`; sin fallback.
- Autorización de ejecución: `R01_BASE_ALLOW_TEST_EXECUTION=1`, que no sustituye
  identidad, permisos, autorización humana ni HBA.
- No se admite bootstrap ni conexión administrativa alternativa.
- Solo `--keepdb --parallel=1`.

Cualquier otro destino se rechaza, incluidos TEST poblada `test_sisadmi_erp`,
DEV, GEO-01, CLIENTES-01.3, CAT-05 y nombres de clones. No se consultan esas bases.

## Comprobaciones y ciclo de Django

Antes de cada conexión se validan configuración, alias, parámetros efectivos y
variables PG* heredadas. Estas últimas se rechazan, incluso si están vacías.
Se prohíben pooling, conexiones persistentes y opciones libpq alternativas.

Después de abrir cada conexión física, antes de entregarla a Django, se consulta
base, session_user, current_user, dirección y puerto reales, propietario, atributos
administrativos, membresías, CONNECT y CREATE sobre public. Solo se ejecutan SELECT.
Si falla una comprobación o una consulta, se cierra la conexión y se propaga el error.
Si aprueba, rollback finaliza la transacción de comprobación antes de inicializarla.
La identidad real requiere abrir una conexión; no puede acreditarse antes de abrirla.

El runner hereda directamente DiscoverRunner. No importa runners históricos.
La preparación conserva create_test_db de Django y sustituye _create_test_db por
una comprobación de la base precreada. Se preservan migrate, serialización inicial,
createcachetable e inicialización normal. No se omite serialized_rollback.
No se llama al código que crea bases. Se rechazan los métodos de creación SQL,
destrucción, clonación, generación de configuración de clones y mirrors.
El teardown válido solo cierra la conexión; mantiene la base.

Las migraciones y limpiezas normales de TestCase/TransactionTestCase escribirán
exclusivamente en la base descartable cuando se autorice ejecutar PostgreSQL.
--keepdb preserva la base, no sus datos. Nunca utilizar datos humanos en esta base.
El paquete no convierte las pruebas históricas de migración en pruebas compatibles:
su runner y dependencias people.0005–0008 quedan fuera y requieren revisión posterior.

## Compatibilidad

Se mantienen intactos settings_test_r01, r01_guard, r01_runner, r01_postgresql,
runner.py, migration_isolation.py, GEO-01 y CLIENTES-01.3. Esos componentes conservan
sus imports anteriores. El runner R-01 antiguo NO debe ejecutarse sobre TEST poblada.
R-01 Base no modifica config/settings.py ni el código funcional.
Las aplicaciones y URL del ERP se cargan normalmente en una futura ejecución:
el grafo funcional debe revisarse antes de autorizar migraciones en la base nueva.

## Validación local sin PostgreSQL

```sh
.venv/bin/python -B -m unittest core.tests.test_r01_base_test_environment -v
```

33 pruebas unitarias aprobadas en la ejecución final local: 0 fallos, 0 errores.
Se conservan los 26 casos anteriores y se añaden siete contratos del ordenamiento.
Se usan conexiones y comandos de migración simulados, con bloqueo adicional de
socket.connect, get_new_connection y ensure_connection. El test de preparación
verifica que Django solicita migrate/createcachetable y serializa mediante mocks:
NO es evidencia de una migración PostgreSQL real ni de rollback real.
Se comprueban destinos, aliases, mirrors, credencial propia, PG*, identidad,
privilegios, cierre al rechazar, keepdb, paralelismo y ausencia de imports históricos.
En la primera ejecución hubo dos errores de preparación de mocks (NUL en os.environ
real y cursor sin protocolo de contexto); se corrigieron únicamente en este archivo
nuevo de pruebas antes de repetir los 24 casos satisfactoriamente.

## Preparación administrativa futura — NO EJECUTADA

Requiere autorización independiente. Un administrador opera su terminal; no entrega
contraseñas al asistente. No se emplea la credencial DEV.

1. Inspeccionar la instancia y archivos HBA efectivos, incluidas reglas incorporadas:

```sql
SELECT datname, pg_get_userbyid(datdba) AS owner FROM pg_database ORDER BY datname;
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
FROM pg_roles WHERE rolname='sisadmi_erp_test_runner';
SELECT parent.rolname FROM pg_auth_members m
JOIN pg_roles member ON member.oid=m.member
JOIN pg_roles parent ON parent.oid=m.roleid
WHERE member.rolname='sisadmi_erp_test_runner';
SHOW hba_file;
SELECT rule_number,file_name,line_number,type,database,user_name,address,auth_method,error
FROM pg_hba_file_rules ORDER BY rule_number;
```

Si test_sisadmi_r01 ya existe, DETENERSE: no vaciarla, borrarla ni reutilizarla sin
identificar su contenido y una autorización nueva. El rol existente debe ser login,
sin atributos administrativos ni membresías. Si falta o no coincide, detenerse:
crear o alterar roles requiere autorización adicional.

2. Solo con nombre disponible, rol conforme y autorización administrativa:

```sql
CREATE DATABASE test_sisadmi_r01 OWNER sisadmi_erp_test_runner TEMPLATE template0;
REVOKE ALL ON DATABASE test_sisadmi_r01 FROM PUBLIC;
```

3. Proponer únicamente esta nueva regla HBA, antes de rechazos aplicables al rol,
sin reemplazar reglas existentes ni alterar destinos protegidos:

```text
host test_sisadmi_r01 sisadmi_erp_test_runner 127.0.0.1/32 scram-sha-256
```

Verificar precedencia y errores mediante pg_hba_file_rules. Solo después de aprobar
el cambio, el administrador recarga con SELECT pg_reload_conf(). No añadir permisos
al rol sobre DEV ni sobre otras bases. No retirar restricciones anteriores.

4. Tras autorización de conexión, consultar exclusivamente la nueva base y comprobar:

```sql
SELECT current_database(),session_user,current_user,inet_server_addr(),inet_server_port();
SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database();
SELECT has_database_privilege(current_user,current_database(),'CONNECT'),
       has_schema_privilege(current_user,'public','CREATE');
SELECT count(*) FROM information_schema.tables
WHERE table_schema='public' AND table_type='BASE TABLE';
```

Resultados iniciales exigidos: identidad exacta, propietario del contrato,
CONNECT y CREATE true, cero tablas de aplicación. No conceder automáticamente
privilegios adicionales si falla: informar el diagnóstico.

5. Únicamente con nueva autorización para pruebas: preparar la contraseña mediante
entrada oculta en la terminal, exportar las dos variables propias y ejecutar módulos
expresamente revisados con los settings nuevos y --keepdb --parallel=1. No hay
comando de suite completa aprobado en este documento. Retirar la credencial al final.

## Límites, incidentes y recuperación

- Las guardas no sustituyen HBA/privilegios ni aíslan código Python arbitrario,
  conexiones directas por otros drivers o llamadas SRI externas.
- Una identidad por nombre/dirección/puerto no es una huella criptográfica del cluster.
- La comprobación de privilegios es puntual: no blinda cambios administrativos posteriores.
- Es responsabilidad del operador reservar esta base exclusivamente para pruebas.
- Los paths de media, static y certificados son únicos por importación de settings,
  fuera de DEV; no se crean al importar. Futuros archivos runtime deben inspeccionarse
  antes de retirarlos; no hay eliminación automática de directorios.
- Ante error real, detener el runner, cerrar conexiones y conservar evidencias sin
  secretos. No reparar migraciones, borrar bases ni limpiar datos automáticamente.
- La retirada futura de base/regla HBA requiere autorización separada y comprobación
  de identidad y contenido. No se incluye DROP DATABASE en esta preparación.
- Pendientes: prueba real de identidad/HBA, migraciones, serialización/restauración,
  limpieza y permisos en PostgreSQL. Ningún resultado unitario acredita estos puntos.


## Snapshot ordenado para serialized_rollback — exclusivo R-01 Base

Django 5.2.17 recorre el registro de modelos: Person precede a IdentificationKind.
Su deserializador mantiene el orden del snapshot. El trigger de people.0011 exige
que el catálogo ya exista al insertar Person; las FK diferidas no difieren el trigger.

El backend obtiene primero el snapshot con super().serialize_db_to_string():
conserva selección de modelos, routers, consultas y serializador estándar de Django.
Después valida en memoria el formato JSON de Django (lista de registros con model,
pk y fields). Solo si hay un catálogo posterior a Person, extrae los registros
people.identificationkind y los inserta inmediatamente antes de la primera Person.
El orden relativo de los registros de catálogo y de todos los demás se conserva.
No hay consultas adicionales, escrituras, reconstrucción ni señales post_migrate.
La deserialización no se sobreescribe: sigue siendo la implementación de Django.

La transformación conserva todos los registros, PK, tipos JSON, campos, relaciones
y valores; puede cambiar espacios o escapes JSON, no los datos. Si el snapshot está
vacío, falta cualquiera de los dos modelos o ya está ordenado, devuelve el texto
original. Los registros JSON se validan incluso cuando no necesitan ordenamiento.
Formatos inesperados, claves duplicadas y números no finitos se rechazan explícitamente
sin incluir contenido del snapshot en el error. No se corrige ni adopta un formato
nuevo automáticamente: cambios futuros de Django requieren revisar estos contratos.
El parseo y la nueva cadena aumentan el consumo de memoria proporcional al snapshot.

Las siete pruebas adicionales cubren orden, conservación de datos/PK/tipos, orden de
otros modelos, snapshot vacío, ausencia de cualquiera de los modelos, idempotencia,
rechazo de formatos inesperados y uso del deserializador estándar. La prueba con
modelos reales usa el serializer y deserializer de Django, con consultas y guardados
sustituidos por mocks; no demuestra ejecución PostgreSQL de triggers.
Las dos caracterizaciones anteriores siguen comprobando la ruta estándar original.

Limitación: clasificaciones históricas NULL o referencias incoherentes no se reparan.
El ordenamiento no permite que el trigger de INSERT acepte esos registros. No se
modifican identidades ni se deshabilitan protecciones para restaurar snapshots.

Pendiente, previa autorización de PostgreSQL real: migrar solo la nueva base vacía,
verificar triggers activos, ejecutar un TransactionTestCase con serialized_rollback,
comprobar la restauración de catálogo/Consumidor Final con PK y relaciones originales,
repetir limpieza/restauración y verificar rechazo de inserciones incoherentes.
GEO-01, CLIENTES-01.3 y R-01 histórico conservan sus implementaciones sin cambios.
