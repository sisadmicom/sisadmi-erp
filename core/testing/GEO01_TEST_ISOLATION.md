# GEO-01: regression isolation

## Diagnosis and scope

R-01 uses a precreated keepdb database named test_sisadmi_erp; it does not provide
an empty database per run. The preservation runner used previously deliberately
bypasses database setup. TestCase rolls back each test's own writes but does not
hide existing rows. Geo01DecisionTests.setUp and Geo01ImportTests create Country
code 593; tests also assert empty catalogs, create competing continents/parents,
and delete their own countries. Changing code 593 alone would not solve isolation.
None of the 37 tests or their assertions have been changed.

New settings config.settings_geo01_test reuse only standalone TEST settings,
never config.settings. Backend/guards restrict the single default alias to the
read-only bootstrap and test_sisadmi_geo01. No populated TEST or DEV destination,
mirrors or extra aliases. The backend preserves the existing no-fallback bootstrap
maintenance connection, requires an owner-matched precreated database, rejects
privileged role attributes/memberships and refuses CREATE/DROP/clone operations.
Django sets up migrations only in the dedicated disposable database with keepdb.
The runner permits only the four GEO-01 modules, TestCase rollback or no-DB cases,
parallel=1, and forbids serialized rollback. R-01 files are unchanged.

## Manual administrative preparation: NOT EXECUTED

Use the administrator's own PostgreSQL terminal. No password is given to Codex.
First inspect; if test_sisadmi_geo01 already exists, STOP and identify its contents
and owner. Never drop or repurpose an existing database automatically.

```sql
SELECT datname, pg_get_userbyid(datdba) AS owner
FROM pg_database WHERE datname IN
 ('test_sisadmi_geo01','test_sisadmi_erp','sisadmi_erp_test_bootstrap');
SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls
FROM pg_roles WHERE rolname='sisadmi_erp_test_runner';
```

Only when the dedicated name is unused (CREATE DATABASE outside a transaction):

```sql
CREATE DATABASE test_sisadmi_geo01 OWNER sisadmi_erp_test_runner TEMPLATE template0;
REVOKE ALL ON DATABASE test_sisadmi_geo01 FROM PUBLIC;
```

Do not grant CREATEDB or change existing database privileges. Administrative HBA
change is manual: insert only the following allow before this role's broad reject,
preserving all other rules and verifying ordering/includes:

```text
host test_sisadmi_geo01 sisadmi_erp_test_runner 127.0.0.1/32 scram-sha-256
```

Inspect pg_hba_file_rules for errors, then manually reload configuration and verify
the effective rule ordering. Do not connect to DEV as a probe. The dedicated allow
must not enable other databases or addresses. This permission is not inferred from
the earlier R-01 setup. Prepare the habitual temporary credential afterward.

## Subsequent execution (not yet performed)

Secure launcher must read the temporary 0600 credential into process memory,
clear inherited PG*/DJANGO_DB_*/DATABASE_URL, set R01_TEST_DB_HOST=127.0.0.1,
R01_TEST_DB_PORT=5432 and R01_TEST_DB_PASSWORD, and acknowledge administrative
verification only after evidence is checked. Never put the password in argv/logs.
Commands below assume that secure environment, not a credential in a tracked file.

```sh
.venv/bin/python -B manage.py test \
 people.tests.test_geo01_import.Geo01ImportTests.test_existing_equivalent_names_and_country_code_are_preserved \
 --settings=config.settings_geo01_test --keepdb --parallel=1 --failfast
```

Only after success:

```sh
.venv/bin/python -B manage.py test \
 people.tests.test_geo01_import people.tests.test_geo01_decisions \
 people.tests.test_geo01_partial people.tests.test_geo01_plan_comparison \
 --settings=config.settings_geo01_test --keepdb --parallel=1 --failfast
```

Capture populated TEST geography, all Person and CompanyPersonAccess fingerprints
in READ ONLY before/after via its separate original guarded connection. Do not
apply migrations or invoke flush there. Stop on any failure. Only after 37 passes
and all import preconditions, continue the existing approved TEST import.
Use an explicit geography-write exclusion window/table locks and revalidate the
TEST-specific plan after acquiring locks. Never use the historical DEV plan.
Remove the temporary credential after use. No database destruction is automatic.

## Current verification

Five no-connection configuration tests passed. These are additional tests, not
part of the 37 GEO-01 tests. PostgreSQL tests and import have NOT been executed.
No temporary credential exists. No databases, roles, HBA or existing records changed.

## Executed result (supersedes earlier pending status)

Dedicated database identity, owner, CONNECT/CREATE and initially empty schema
verified. Representative test: 1/1 passed. Full GEO-01 suite: 37/37 passed,
zero failures/errors (the representative test is included in those 37). Django
created the schema only in test_sisadmi_geo01. No flush, database drop or migration
on populated TEST. Every populated TEST table had identical fingerprints
before/after both test runs. Existing fixtures/assertions were unchanged.

Concurrency verified on the disposable DB using two independent connections:
SHARE ROW EXCLUSIVE versus NOWAIT produced the expected SQLSTATE 55P03; both
transactions rolled back. Existing suite also verified full import rollback.

Source/PDF hashes, original GEO-01 artifacts, exclusions, geographic snapshot
and 54 Person/54 CompanyPersonAccess fingerprints revalidated. TEST web paused.
Main import acquired SHARE ROW EXCLUSIVE locks in sorted table order on all
geographic tables plus Person/access/customer; current approved plan rechecked
under locks. One atomic transaction created 23 provinces, 220 cantons, 1353
parishes, reused 5 original objects unchanged. Final counts 1/1/24/221/1354.
No normalized duplicates or broken parent links. All preexisting rows and all
non-geographic tables unchanged. Four Person geographic references unchanged.
Repeated planner: zero additional creations. No SAN ALEJO added artificially;
10 excluded cases/11 source rows remain excluded.

check, makemigrations --check --dry-run, pip check, git diff --check passed.
CAT-05: 1138 preserved hashes and 7 frozen candidates verified. TEST web restarted
on http://127.0.0.1:8000/ ; original temporary credential removed.
No DEV, commit or push. Awaiting human validation.

Evidence: core/testing/geo01_test_execution_results.json and
core/testing/geo01_test_executed_operations.json (actual allocated primary keys).
Logs: /tmp/geo01-representative.log and /tmp/geo01-all-tests.log; full receipt:
/tmp/geo01-controlled-execution/import-receipt.json.
