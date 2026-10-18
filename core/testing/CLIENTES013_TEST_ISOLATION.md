# CLIENTES-01.3 — prepared; PostgreSQL execution NOT authorized yet

## Destination and invariant

Only test_sisadmi_clientes013 / sisadmi_erp_test_runner / 127.0.0.1:5432.
No bootstrap, populated TEST, GEO-01 or DEV connection is accepted. Settings reuse
standalone R-01 configuration only; no production settings or credential fallback.
Existing settings, runners, fixtures, models, services and frozen tests unchanged.
CLI-R01 (special Final Consumer behavior) is explicitly excluded.

The custom backend checks both configured parameters and actual server identity,
owner, minimal role attributes/no memberships and CONNECT/CREATE privileges.
It rejects inherited PG* options, alternate aliases/mirrors/routers, pooling,
persistent connections, raw connection overrides and administrative connections.
The runner rejects non-whitelisted labels before importing them and requires
--keepdb --parallel=1. Each worker uses the same alias in its own thread-local
connection; no extra connection aliases are authorized.

Database creation/destruction/cloning APIs fail closed. Django can migrate only
the manually precreated disposable database after explicit future execution approval.
The backend never opens an administrative maintenance connection. TransactionTestCase
will flush that disposable database; this is expected and must NEVER run on any
populated database. No mechanism modifies the populated TEST database to test safety.

## Exact allowed modules

- people.tests.test_customer_document_restrictions_clientes013 (9 new tests)
- people.tests.test_customer_document_concurrency_clientes013 (11 new tests)
- people.tests.test_customer_category_assignment (14 existing tests)
- people.tests.test_customer_ui_actions (16 existing tests)
- people.tests.test_customer_person_replacement (12 existing tests)

Expected full selection: 62 cases; collection not yet performed against Django.
No GEO-01/CAT-02.3 modules are selected or changed. Frozen tests may be read as
reference, but their migration/concurrency runner and aliases are not adapted here.

## Prepared contracts

DRAFT, CONFIRMED and CANCELLED are produced through actual CreateSale/ConfirmSale/
CancelSale services, using deterministic stock/product/sequence/branch/company
fixtures. For each state, HTTP and services must reject person replacement and
customer deletion; full business snapshots must remain identical. Commercial
edits preserving identity remain allowed. Direct SQL FK violation asserts 23503.
Multi-company checks and current sales acceptance with inactive Person/revoked
CompanyPersonAccess are explicit; no new sales prerequisite is introduced.

Concurrent fixtures use TransactionTestCase with committed rows. Two thread-local
connections and an observer have different verified PostgreSQL PIDs. A SQL wrapper
observes the completed Customer SELECT FOR UPDATE without replacing SQL/results.
An Event holds the first transaction before business writes; pg_blocking_pids
proves the second waits on that exact PID. No arbitrary sleeps. Bounded event waits,
lock_timeout and statement_timeout prevent unbounded waits. Both orders of sale /
replace and sale / delete; rollback of first sale/replace/delete; two replacements;
both orders of delete / replace; controlled timeout 55P03. Waiters must not write
before acquiring the customer lock. Unexpected errors fail, never count as RED
success. Finally releases barriers, joins workers and closes their connections.

These are prepared contracts, NOT evidence that the services currently pass them.
The harness has not yet been exercised on PostgreSQL; timing/cleanup may need a
strictly scoped correction after a real result. No automatic business fixes.

## Manual administrative steps — NOT EXECUTED

From the administrator's PostgreSQL terminal, first inspect:

```sql
SELECT datname,pg_get_userbyid(datdba) AS owner FROM pg_database
WHERE datname IN ('test_sisadmi_clientes013','test_sisadmi_erp','test_sisadmi_geo01');
SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls
FROM pg_roles WHERE rolname='sisadmi_erp_test_runner';
SELECT parent.rolname FROM pg_auth_members m
JOIN pg_roles member ON member.oid=m.member JOIN pg_roles parent ON parent.oid=m.roleid
WHERE member.rolname='sisadmi_erp_test_runner';
```

STOP if the dedicated database exists: inspect contents, do not repurpose/drop it.
Role attributes must all be false; no memberships. Only after explicit approval
and if the name is unused, outside a transaction:

```sql
CREATE DATABASE test_sisadmi_clientes013 OWNER sisadmi_erp_test_runner TEMPLATE template0;
REVOKE ALL ON DATABASE test_sisadmi_clientes013 FROM PUBLIC;
```

Do not grant CREATEDB or change existing database/role privileges. Inspect SHOW
hba_file and pg_hba_file_rules (including include files/order). Add ONLY this
administratively approved line before this role's broad rejects, retaining others:

```text
host test_sisadmi_clientes013 sisadmi_erp_test_runner 127.0.0.1/32 scram-sha-256
```

Verify no parse/order errors then manually SELECT pg_reload_conf(). Verify using
the following command in the operator terminal (password entered interactively):

```sh
psql -X -W "host=127.0.0.1 port=5432 dbname=test_sisadmi_clientes013 user=sisadmi_erp_test_runner sslmode=disable connect_timeout=5"
```

Then verify:

```sql
SELECT current_database(),current_user,inet_server_addr(),inet_server_port();
SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database();
SELECT has_database_privilege(current_user,current_database(),'CONNECT'),
       has_schema_privilege(current_user,'public','CREATE');
SELECT tablename FROM pg_tables WHERE schemaname='public';
```

Only the dedicated name/role/address, both permissions true, initially zero
application tables. Never probe DEV. Shared role still has its previously approved
TEST/GEO-01 access: application guards restrict this runner; HBA cannot distinguish
programs sharing credentials. A new dedicated role is not silently introduced.

## Future execution — separate approval required

Use the habitual private 0600 credential file. A reviewed launcher must load it
into memory, never argv/logs/tracked files; clear PG*, DJANGO_DB_* and DATABASE_URL.
Set R01_TEST_DB_HOST=127.0.0.1, R01_TEST_DB_PORT=5432, R01_TEST_DB_PASSWORD from that
file. Only after administrative evidence and explicit execution authorization,
set CLIENTES013_ALLOW_TEST_EXECUTION=1 in that process (not a tracked file).
No connection is allowed by default. This switch does not alter old CAT-05 flags.

Representative then restrictions, then concurrency, then regressions; STOP on
first error, preserve evidence and do not fix business logic automatically:

```sh
.venv/bin/python -B manage.py test \
 people.tests.test_customer_document_restrictions_clientes013.CustomerDocumentRestrictionTests.test_draft_blocks_replacement_and_deletion \
 --settings=config.settings_clientes013_test --keepdb --parallel=1 --failfast
```

Full whitelist command, only after the preceding stages succeed:

```sh
.venv/bin/python -B manage.py test \
 people.tests.test_customer_document_restrictions_clientes013 \
 people.tests.test_customer_document_concurrency_clientes013 \
 people.tests.test_customer_category_assignment \
 people.tests.test_customer_ui_actions \
 people.tests.test_customer_person_replacement \
 --settings=config.settings_clientes013_test --keepdb --parallel=1 --failfast
```

Do not invoke GEO-01 runner or run an unrestricted suite with these settings.
Only the disposable DB may receive migrations/transaction-test cleanup.

## Populated TEST preservation and recovery

Before/after any future PostgreSQL run, use a SEPARATE original R-01 guarded
connection to test_sisadmi_erp, within REPEATABLE READ READ ONLY transactions.
Do not add that database as a runner alias. Record actual identity and per-table
sorted full-row SHA-256 plus counts, especially 54 Person, 54 CompanyPersonAccess,
4 original Customer with their IDs and every geographic PK/reference. Compare
all tables, not merely counts. Coordinate a window without human writes: otherwise
fingerprint differences cannot be attributed solely to tests. Reads and their
credential availability require their own valid authorization at execution time.

On failure, release all Events, await workers, close owned connections; do not
flush or repair any populated database. Do not terminate unrelated backends. The
precreated disposable database is retained for evidence; no automatic DROP. Any
recreation/destruction requires explicit approval, identity/content inspection,
zero other sessions and no FORCE. Never restore a DEV backup or alter role-wide
privileges. Remove only the exact temporary credential used after approved runs.

## Current verification

No PostgreSQL connections, migrations or Django database tests executed. Only
configuration unit tests, AST/inventory, Django system checks without connection,
pip check and diff/hash review are permitted in this phase. No credentials used.

Verification completed in this preparation phase: 16/16 standalone configuration
unit tests passed (no Django database tests). All 10 new Python files passed AST;
the two new database-test modules imported with psycopg.Connection.connect blocked
and zero connection attempts. Django check: no issues. pip check and diff check:
passed. SHA-256 comparison confirms all 609 preexisting Python files unchanged.
No migrations created. makemigrations --check --dry-run and full database suite
were NOT run because PostgreSQL execution/history inspection is prohibited now.
The 20 new PostgreSQL tests are prepared, not claimed as passing.

## Catalog seed correction — prepared, PostgreSQL repetition pending approval

Current whitelist contains 66 cases (12 restriction + 12 concurrency + 14 category
+ 16 UI actions + 12 person replacement), with all test bodies/assertions unchanged
by this infrastructure correction. Earlier counts/statuses above are historical.

Exact legacy dependency: CustomerCategoryAssignmentTests.setUp creates nonnumeric
Person identities which central detection classifies as OTHER. CustomerUIActions
also creates PASSPORT identities, as does CustomerPersonReplacementTests. They
assume migration 0010 seeded IdentificationKind; TransactionTestCase legitimately
flushes that seed data. No historical test file is modified.

core/testing/clientes013_catalog.py registers a People-only post_migrate receiver
ONLY inside Clientes013TestRunner.run_tests, removing it in finally even on errors.
At initial Django test schema preparation (migrate emits post_migrate even when no
migrations are pending), and again after ordinary TransactionTestCase flush, it
prepares ONLY IdentificationType.OTHER ('Otro') and PASSPORT ('Pasaporte'). Before
writing it requires explicit execution approval, validates exact settings/alias,
and checks actual database/role/host/port/owner/privileges. It uses an atomic
get_or_create by unique code, defaults from the canonical enum, no fixed PK,
no update/rename, and refuses inactive existing kinds without activating them.
No data migration is replayed and no Person/Customer/Final Consumer is created.
The existing new-fixture OTHER initializer remains harmlessly idempotent.

TestCase cases roll back to their initial seeded catalog. TransactionTestCase
cleanup recreates required kinds via the temporarily registered receiver before
the next test. This preserves independence from execution order for the approved
modules; no arbitrary global monkeypatch or app registration is installed.
The runner rejects available_apps subsets, in addition to serialized rollback,
because either can suppress the cleanup post_migrate signal. Should a future test
explicitly suppress signals/delete masters, review its fixture rather than assume
this mechanism covers it. The raw kind initializer is guarded and is not connected
by importing its module, using another runner or starting the application.

Static/configuration validation: 21/21 standalone unit tests passed; AST/imports
passed with psycopg.Connection.connect blocked; manage.py check passed. Actual
signal registration/removal verified without sending the signal or connecting;
66 cases collected but NOT executed. pip check and diff checks passed. Preserved
hashes confirm historical tests, models, services, migrations, GEO-01 artifacts
and other inventoried files unchanged. No PostgreSQL, credentials, schema/data
changes, flush, database creation/destruction, commit or push in this phase.
makemigrations --check --dry-run remains pending because it inspects migration
history via a connection. No migrations have been created.

Next proposed controlled validation, after separate execution approval: failing
legacy category case first; then the legacy category/UI/person-replacement modules;
then all 66 in the same reusable isolated database, stopping at the first error.
Use the existing READ ONLY populated TEST before/after fingerprint procedure and
remove the exact temporary credential afterward. Do not infer all 66 will pass
from the configuration checks; the actual post-flush writes are not validated yet.
