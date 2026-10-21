# R-01 / R-02 — PostgreSQL TEST

No credentials are stored here. Nothing in this document has been executed
against PostgreSQL. The former CAT-05 policy remains unchanged.

## Operator preparation (manual, administrative approval required)

Connect from the operator's terminal to the intended Ubuntu PostgreSQL instance:

```sh
sudo -u postgres psql -X -h /var/run/postgresql -p 5432 -d postgres
```

Inspect before creating anything. If any proposed name already exists, STOP and
identify its owner/content; do not drop it or overwrite its privileges.

```sql
SELECT datname, pg_get_userbyid(datdba) AS owner FROM pg_database ORDER BY datname;
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls
FROM pg_roles WHERE rolname = 'sisadmi_erp_test_runner';
SHOW hba_file;
```

Only if all three names are unused:

```sql
CREATE ROLE sisadmi_erp_test_runner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
NOREPLICATION NOBYPASSRLS;
\password sisadmi_erp_test_runner
CREATE DATABASE sisadmi_erp_test_bootstrap OWNER postgres;
REVOKE ALL ON DATABASE sisadmi_erp_test_bootstrap FROM PUBLIC;
GRANT CONNECT ON DATABASE sisadmi_erp_test_bootstrap TO sisadmi_erp_test_runner;
CREATE DATABASE test_sisadmi_erp OWNER sisadmi_erp_test_runner;
REVOKE ALL ON DATABASE test_sisadmi_erp FROM PUBLIC;
```

The password is entered in the operator's terminal, never supplied to Codex.
No CREATEDB permission is needed: the custom creation class checks for the
precreated database and fails if it is absent. It never creates/drops/clones it.

## HBA restriction (separate administrative authorization)

Review and back up the actual hba_file. Do not replace it or change existing
rules for other users. The following dedicated rules must precede broad allows
(including any applicable include files). Inspect existing records first:

```text
local all sisadmi_erp_test_runner reject
host sisadmi_erp_test_bootstrap,test_sisadmi_erp sisadmi_erp_test_runner 127.0.0.1/32 scram-sha-256
host all sisadmi_erp_test_runner 0.0.0.0/0 reject
host all sisadmi_erp_test_runner ::/0 reject
```

Django maintenance/catalog queries use bootstrap, in read-only mode. No
connection to the administrative `postgres` database is required. All other databases
are denied for the test role, without altering DEV database privileges.

Manual inspection/reload, only after approval to modify HBA:

```sql
SELECT rule_number, file_name, line_number, type, database, user_name,
       address, auth_method, error
FROM pg_hba_file_rules ORDER BY rule_number;
SELECT pg_reload_conf();
```

There must be no parse errors and no earlier rule allowing another destination
for this role. Verify the intended instance and the TEST owner/role attributes.
Do not connect to DEV to test rejection: inspection of the effective rule order
is required. No superuser or role memberships are permitted for the test role.

## Runtime configuration

Use `.venv` and `config.settings_test_r01`. Host and port are mandatory and pinned
to 127.0.0.1:5432. User, bootstrap and TEST names cannot be overridden. DJANGO_DB_*
variables are not used; inherited PG* variables are rejected before connection.
Connection aliases, mirrors, pooling, persistent connections and alternate
libpq destinations are rejected. Django's postgres-to-first-database fallback
is disabled. The server HBA is an independent, essential protection.

Set R01_TEST_ADMIN_VERIFIED=1 **only after** the operator has completed these
checks. It is an acknowledgment, not proof of isolation by itself. Never reuse
the DEV password. Example for the operator's Bash terminal:

```sh
export R01_TEST_DB_HOST=127.0.0.1
export R01_TEST_DB_PORT=5432
read -r -s -p 'TEST password: ' R01_TEST_DB_PASSWORD
printf '\n'
export R01_TEST_DB_PASSWORD
export R01_TEST_ADMIN_VERIFIED=1
```

Clear inherited PG* options in the shell rather than disabling the guard.
Do not print passwords/environment dumps or put credentials in command arguments.

## Test execution (only after isolation is accredited)

```sh
.venv/bin/python -B manage.py test catalog sales sri \
  core.tests.test_application_shell core.tests.test_auth_navigation \
  core.tests.test_form_ux_foundation_red \
  --settings=config.settings_test_r01 --keepdb --parallel=1 --verbosity=2
```

The existing migration-isolation runner is preserved for legacy Customer tests.
The 28 CAT-05 tests are not copied into the main tree or executed: their models
and migrations are absent. Functional failures are recorded, not fixed in R-02.

Django's normal test setup applies the migration graph to TEST even with keepdb;
review the graph before the first database run. No migrations are applied to
bootstrap or DEV. The custom backend refuses CREATE/DROP DATABASE, cloning and
non-keepdb runs. TEST can still be modified/flushed by tests; it is disposable.
All media/certificates/cache/email are isolated from DEV. The guard is not a
sandbox against arbitrary Python code/direct drivers or external SRI requests:
network integration tests require their own explicit approval.

Configuration-only verification (does not connect to PostgreSQL):

```sh
.venv/bin/python -B -m unittest core.tests.test_r01_test_environment -v
```

## R-02 verification result

- 12 configuration/backend/runner unit tests passed, with no PostgreSQL connections.
- `manage.py check --settings=config.settings_test_r01`: passed, no issues.
- `python -m pip check`: passed, no broken requirements.
- `makemigrations --check --dry-run --settings=config.settings_test_r01`:
  blocked before connection by the administrative-verification guard. Django
  tries to inspect migration history; graph/model synchronization is not certified.
- Database regression for catalog/sales/sri/UI: NOT RUN. R01_TEST_DB_* variables
  and manual HBA/role/database verification were unavailable in this session.
- No functional test failures are claimed or fixed; no migrations generated/applied.
- The seven prior RED candidates, the 28 preserved CAT-05 tests and old approved=false
  artifacts were not changed. Preexisting working-tree files and Git index preserved.

Next step: the operator executes the manual preparation above and provides
non-secret evidence of role attributes, database owners and HBA order. Only then
run the selected regression; do not treat an acknowledgment variable as proof.

## R-03 compatibility correction

Maintenance connections now use only the read-only bootstrap database, never
`postgres`. The connection registry remains restricted to the single `default`
alias. Existing concurrency tests may create unregistered wrappers named
`isolation_probe` and `con532_row_probe`, only for the exact TEST database, role,
host, port and options already approved. They cannot connect to bootstrap or DEV.
