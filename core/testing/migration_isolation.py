"""Aislamiento limitado al contrato histórico Customer en PostgreSQL TEST.

MigrationExecutor garantiza atomicidad por migración, no por plan. Validamos
el plan completo antes de ejecutar y restauramos el registro capturado, sin
fake, borrados, backfill ni aplicación indiscriminada de hojas del disco.
"""
from contextlib import contextmanager

from django.db.migrations.executor import MigrationExecutor

CUSTOMER = ("people", "0005_customer_company_expansion")
SUPPLIER = ("people", "0006_supplier_company_expansion")
CATEGORY = ("people", "0007_customer_category")
CATEGORY_ASSIGNMENT = ("people", "0008_customer_category_assignment")


class MigrationIsolationError(RuntimeError):
    """El aislamiento no puede garantizar un estado seguro."""


def require_test_connection(connection):
    name = str(connection.settings_dict["NAME"])
    if (connection.vendor != "postgresql" or not name.startswith("test_")
            or name == "sisadmi_erp_dev"
            or connection.settings_dict.get("TEST", {}).get("MIRROR")):
        raise MigrationIsolationError("Solo PostgreSQL TEST independiente; DEV rechazado.")
    if connection.in_atomic_block or not connection.get_autocommit():
        raise MigrationIsolationError("Se requiere teardown completo, sin transacciones activas.")
    connection.ensure_connection()
    if connection.connection.info.transaction_status != 0:
        raise MigrationIsolationError("La conexión PostgreSQL tiene una transacción activa.")
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        actual = cursor.fetchone()[0]
    if actual != name:
        raise MigrationIsolationError("La identidad real de PostgreSQL no coincide con TEST.")
    with connection.cursor() as cursor:
        cursor.execute("""SELECT pid FROM pg_stat_activity
            WHERE datname=current_database() AND pid<>pg_backend_pid()
              AND (xact_start IS NOT NULL OR state='active' OR state IS NULL)""")
        if cursor.fetchall():
            raise MigrationIsolationError("Existen otras transacciones activas o conexiones no verificables en TEST.")


def schema_snapshot(connection):
    """Definiciones, índices y estado de FK/triggers; no datos de negocio."""
    queries = (
        """SELECT table_name, column_name, data_type, udt_name, is_nullable,
                  column_default FROM information_schema.columns
           WHERE table_schema = 'public' ORDER BY table_name, ordinal_position""",
        """SELECT c.relname, x.conname, pg_get_constraintdef(x.oid), x.convalidated
           FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid
           JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' ORDER BY c.relname,x.conname""",
        "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname",
        """SELECT c.relname,t.tgname,t.tgenabled FROM pg_trigger t
           JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
           WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY c.relname,t.tgname""",
    )
    result = []
    with connection.cursor() as cursor:
        for query in queries:
            cursor.execute(query)
            result.append(tuple(cursor.fetchall()))
    return tuple(result)


def applied_targets(executor, applied):
    """Frontera del conjunto aplicado, incluidas aplicaciones no relacionadas."""
    graph = executor.loader.graph
    return sorted(node for node in applied
                  if not any(child.key in applied for child in graph.node_map[node].children))


def validate_plan(plan, allowed, backwards):
    for migration, reverse in plan:
        node = (migration.app_label, migration.name)
        if node not in allowed or reverse != backwards:
            raise MigrationIsolationError(f"Descendiente o dependencia no autorizada: {node}, reverse={reverse}.")


@contextmanager
def _historical_migration_state(connection, target, removable):
    require_test_connection(connection)
    executor = MigrationExecutor(connection)
    executor.loader.check_consistent_history(connection)
    initial = set(executor.loader.applied_migrations)
    if target not in initial or not initial <= set(executor.loader.graph.nodes):
        raise MigrationIsolationError("Estado inicial no permitido: se requiere la migración objetivo y un grafo conocido.")
    plan = executor.migration_plan([target])
    reversible = removable & initial
    validate_plan(plan, reversible, True)
    if CATEGORY in reversible:
        with connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS(SELECT 1 FROM people_customercategory)")
            if cursor.fetchone()[0]:
                raise MigrationIsolationError("Categorías existentes: no se permite revertir su tabla TEST.")
    targets = applied_targets(executor, initial)
    schema = schema_snapshot(connection)

    def restore():
        require_test_connection(connection)
        restoring = MigrationExecutor(connection)
        restoring.loader.check_consistent_history(connection)
        current = set(restoring.loader.applied_migrations)
        if current - initial:
            raise MigrationIsolationError("Restauración rechazada: aparecieron migraciones ajenas al estado inicial.")
        restore_plan = restoring.migration_plan(targets)
        validate_plan(restore_plan, ({target} | removable) & initial, False)
        restoring.migrate(targets)
        actual = set(MigrationExecutor(connection).loader.applied_migrations)
        if actual != initial or schema_snapshot(connection) != schema:
            raise MigrationIsolationError("Restauración TEST incompleta: registro o esquema distinto al inicial.")

    try:
        executor.migrate([target])
        if set(MigrationExecutor(connection).loader.applied_migrations) != initial - reversible:
            raise MigrationIsolationError("La preparación no produjo el estado histórico esperado.")
        yield
    except BaseException as original:
        try:
            restore()
        except BaseException as cleanup:
            raise BaseExceptionGroup("Falló aislamiento y restauración TEST", [original, cleanup]) from None
        raise
    else:
        restore()


def customer_migration_state(connection):
    return _historical_migration_state(connection, CUSTOMER, {SUPPLIER, CATEGORY, CATEGORY_ASSIGNMENT})


def supplier_migration_state(connection):
    return _historical_migration_state(connection, SUPPLIER, {CATEGORY, CATEGORY_ASSIGNMENT})
