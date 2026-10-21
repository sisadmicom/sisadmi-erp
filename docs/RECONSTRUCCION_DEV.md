# Reconstrucción propuesta de sisadmi_erp_dev

Pendiente de autorización humana. Ningún comando de este procedimiento se ha
ejecutado. Detener el servidor y los procesos que utilicen DEV antes de empezar.
No usar `--force`, `flush`, `--fake`, ni restaurar un dump antiguo encima del
esquema nuevo. No modificar migraciones ni las bases TEST.

## Inicialización

`people.0010` crea el catálogo y la Persona Consumidor Final incluso sin empresas,
usando modelos históricos. `people.0011` instala las protecciones PostgreSQL.
Se conservan ambas migraciones sin cambios. No se hacen consultas en `ready()`
ni se añade un receptor post_migrate que pueda utilizar un esquema incompleto.

El guardado ordinario de una Company nueva habilita el cliente y su acceso dentro
de la misma transacción: si falla la habilitación, se revierte el alta de empresa.
Se reutiliza la Persona global; las restricciones únicas y el bloqueo de empresa
evitan duplicados. `initialize_final_consumer` permite repetir explícitamente la
inicialización y completar relaciones de empresas existentes después de migrar.
Una identidad reservada incoherente se rechaza sin intentar corregirla.

La creación normal de Person conserva la validación existente que detecta el tipo
y asigna su IdentificationKind coherente; no se deshabilitan triggers ni guardas.
Las cargas por SQL, bulk_create o fixtures no sustituyen esta ruta validada.
Company.bulk_create tampoco ejecuta save: una carga de empresas debe usar save
individual o completar sus relaciones mediante initialize_final_consumer.

## Comandos propuestos, exclusivamente para DEV

Ejecutar desde la raíz del repositorio, en bash, después de autorización. Se usan
las credenciales existentes mediante variables de entorno o .pgpass. El usuario
PostgreSQL debe tener permisos de respaldo, eliminación y creación; si no los
tiene, debe realizar esta etapa el administrador, sin cambiar credenciales.

```bash
set -euo pipefail
export DJANGO_SETTINGS_MODULE=config.settings
export DJANGO_DB_NAME=sisadmi_erp_dev
export PGHOST="${DJANGO_DB_HOST:-127.0.0.1}"
export PGPORT="${DJANGO_DB_PORT:-5432}"
export PGUSER="${DJANGO_DB_USER:-sisadmi_erp}"
if [ -n "${DJANGO_DB_PASSWORD:-}" ]; then
    export PGPASSWORD="$DJANGO_DB_PASSWORD"
fi

# Respaldo exclusivo de DEV; no sobrescribe archivos anteriores.
rebuild_dir=$(mktemp -d /tmp/sisadmi-dev-rebuild.XXXXXXXX)
pg_dump --format=custom --file="$rebuild_dir/sisadmi_erp_dev.dump" --dbname=sisadmi_erp_dev
pg_restore --list "$rebuild_dir/sisadmi_erp_dev.dump" > "$rebuild_dir/backup-index.txt"
sha256sum "$rebuild_dir/sisadmi_erp_dev.dump" > "$rebuild_dir/backup.sha256"

# DESTRUCTIVO: solo ejecutar con autorización explícita posterior.
# Sin --force: las conexiones activas deben bloquear la eliminación.
dropdb --maintenance-db=postgres sisadmi_erp_dev
createdb --maintenance-db=postgres --owner="$PGUSER" sisadmi_erp_dev
.venv/bin/python manage.py migrate --database=default --noinput
.venv/bin/python manage.py initialize_final_consumer
.venv/bin/python manage.py initialize_final_consumer
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python -m pip check

# Comprobación de la instalación antes de crear empresas.
.venv/bin/python manage.py shell -c 'from core.models import Company; from people.models import Person, Customer; p = Person.objects.get(identification="9999999999999"); assert p.identification_type == p.identification_kind.code == "FINAL_CONSUMER"; assert p.person_type == "NATURAL" and p.is_active; assert not Company.objects.exists(); assert not Customer.objects.exists()'
```

Guardar el respaldo fuera de `/tmp` según la política local antes de reiniciar
el equipo. `pg_restore --list` comprueba el índice, no una restauración completa.

## Carga progresiva

Primero generar un plan geográfico nuevo contra DEV vacío; no reutilizar planes
anteriores porque dependen de la instantánea y los IDs de otra base.

```bash
.venv/bin/python manage.py import_ecuador_geography --csv data/geo01/ecuador_2016.csv --country-code EC --dry-run --report "$rebuild_dir/geografia-plan.json"
```

Revisar conflictos y ambigüedades, resolverlos con el mecanismo de decisiones
existente y aprobar el plan antes de aplicar. Si el plan está desbloqueado y se
aprueba sin decisiones adicionales, el comando exacto es:

```bash
.venv/bin/python manage.py import_ecuador_geography --csv data/geo01/ecuador_2016.csv --country-code EC --apply --approved-plan "$rebuild_dir/geografia-plan.json"
.venv/bin/python manage.py createsuperuser
```

Crear la primera empresa y sucursal mediante el asistente existente. La empresa
recibirá automáticamente su Customer Consumidor Final. Repetir
`initialize_final_consumer` no duplicará Persona, acceso ni Customer.

El archivo original `/home/sisadmi/workspace/sisadmi-erp/fv_cliente.txt` se conserva
intacto. **No ejecutar import_approved_test_people en DEV**: su autorización,
hashes, manifiesto, empresa e IDs están ligados a TEST. No existe actualmente un
comando autorizado para cargar ese archivo en DEV. Esta etapa requiere preparar
y revisar un nuevo plan de importación con tipos detectados y catálogo resuelto
por código, sin IDs heredados. No se debe restaurar un dump de personas antiguas
ni relajar la identidad inmutable para completar esta etapa.

## Verificaciones de esta preparación

`check`: sin problemas. `makemigrations --check --dry-run`: sin cambios, con acceso
a conexiones bloqueado mediante mock de ensure_connection; por tanto no se
verificó el historial aplicado. `pip check`: sin dependencias rotas.
Se prepararon pruebas PostgreSQL para inicialización sin empresas, repetición y
alta automática de dos empresas, pero no se ejecutaron porque crear o utilizar
bases de pruebas no está autorizado en esta tarea. No se ejecutó la suite completa.
