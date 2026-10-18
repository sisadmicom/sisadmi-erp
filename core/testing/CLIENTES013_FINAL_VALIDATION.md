# CLIENTES-01.3 — final controlled PostgreSQL validation

## Real results: two separate runs

| Selection | Executed | Passed | Failures | Errors | Skipped | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| Historical regressions | 42 | 42 | 0 | 0 | 0 | 4.564 |
| Full authorized suite, from beginning | 66 | 66 | 0 | 0 | 0 | 19.307 |

The 42 cases recur within the 66. Do not present 108 unique cases or combine older
partial executions with these counts. No test was retried after a failure: neither
run failed. The corrected external serializer produced valid JSON with dates in
ISO-8601; unsupported types remain explicit errors. Earlier evidence retained in
its original directories/files; this run used fresh /tmp/clientes013-final-regression-20261018.

| Module (full suite) | Passed |
|---|---:|
| people.tests.test_customer_document_restrictions_clientes013 | 12 |
| people.tests.test_customer_category_assignment | 14 |
| people.tests.test_customer_ui_actions | 16 |
| people.tests.test_customer_person_replacement | 12 |
| people.tests.test_customer_document_concurrency_clientes013 | 12 |

## Verified isolation and unchanged code

Dedicated connection identity/owner/privileges checked by CLIENTES013 guard:
test_sisadmi_clientes013, sisadmi_erp_test_runner, 127.0.0.1:5432. Exact five-module
whitelist preserved. Forbidden names rejected without connecting. Existing migration
history consistent with no pending migrations; no migration applied. No automatic
CREATE/DROP/clone. Django TransactionTestCase cleanup ran only in disposable DB.

All 420 inventoried project files retained their pre-run SHA-256 through execution.
No models, services, migrations, historical tests, GEO-01/CAT-02.3 files or runners
changed. CLI-R01 untouched. No Git stage, commit or push. CAT-05 final verification:
1138 preserved file hashes plus seven frozen candidates unchanged.

## Catalog lifecycle evidence

External signal observers were registered before/after the runner's existing
scoped initializer; they did not replace SQL, models, signal receiver or results.
Historical run: one initial post_migrate; existing OTHER/PASSPORT records unchanged.
Full run: 13 post_migrate events, comprising initial migration-command emission
(no pending migration applied) and 12 after TransactionTestCase cleanups. All 12
cleanup events observed empty catalog before and active OTHER/"Otro" and
PASSPORT/"Pasaporte" afterward. Every test's start recorded both required codes.
All preexisting kind rows compared completely equal before/after initialization;
no PK was fixed, no existing record renamed/reactivated and no data migration replayed.
Scoped receiver absence outside runner checked after both runs, including removal
of external observers. Actual inactive preexisting types were not introduced as
an extra negative scenario; fail-closed inactive behavior remains code/static
validation evidence rather than a new PostgreSQL rejection test in these runs.

## Document and concurrency evidence

Real DRAFT, CONFIRMED and CANCELLED flows: deletion/person substitution rejected;
permitted commercial edits succeed; original person/document references preserved.
Company isolation, HTTP permissions/CSRF, category behavior, duplicate prevention,
SQL FK SQLSTATE 23503 and original public error contracts passed. Sales acceptance
of inactive Person/revoked CompanyPersonAccess remained unchanged.

All 12 concurrent tests observed actual blocking with independent PostgreSQL
connections and pg_blocking_pids. Tests covered sale vs deletion/replacement,
rollback of first transaction, two replacements, delete vs replace, controlled
1000ms lock_timeout (55P03), normal lock_timeout 5s, statement_timeout 8s, absence
of partial effects and worker closure. The original replacement-first/delete-second
case passed and recorded final snapshot before cleanup: Customer removed and both
Persons retained. No unexpected exception/timeouts were hidden as success.

Revocation ordering in the full run: replacement PID 2172540, delete PID 2172542,
observer PID 2172538; READ COMMITTED workers. Customer 164 / company 381 changed
Person 745 -> 746. Delete waited on replacement; replacement plus access revocation
committed, then delete queried visibility of Person 746 and found zero rows. It
rejected without deleting Customer. Final snapshot before cleanup retained the
Customer with Person 746, both Persons active, and no replacement access. This
proves only that committed-revocation-before-revalidation ordering. It does NOT
prove protection if an independent revocation occurs after successful validation
or all possible interleavings. No general claim of access-revocation serialization.

## Populated TEST preservation and cleanup

TEST web paused during both selections. A separate original R-01 connection read
only test_sisadmi_erp in REPEATABLE READ READ ONLY transactions. Every table's sorted
full-row SHA-256 and count matched before/after both selections, including 54 Person,
54 CompanyPersonAccess, four original Customer (IDs/references captured), geography
and other tables. No other populated DB connections observed at capture points.
No populated writes, migration, flush or deletion. No DEV connection was opened.

Final READ ONLY check: no other isolated test connections remained. manage.py check,
makemigrations --check --dry-run (READ ONLY), pip check and git diff --check passed;
no new migrations. TEST web restored, login HTTP 200; original temporary credential
identity verified and file removed after restart. No PostgreSQL DB was destroyed.

## Artifacts and remaining limits

- core/testing/clientes013_final_validation_results.json: all cases/times, catalog
  snapshots per start, signal events, preserved table hashes and connection evidence.
- core/testing/clientes013_final_revocation_evidence.json: ordered reads/commits,
  wait edge and final snapshot for the specific revoked-access scenario.
- core/testing/clientes013_final_original_evidence.json: original corrected race.
- /tmp/clientes013-final-historical.log and /tmp/clientes013-final-all.log.
- /tmp/clientes013-final-regression-20261018/: fresh raw evidence, before/after.

No anomalies in these two runs. This validates the authorized five-module selection,
not the whole ERP or untested concurrency schedules. Runtime disconnect verified
on success here; exception cleanup had separate configuration-test coverage.
No extra PostgreSQL negative test of an existing inactive kind was added.

Stopped for human review; no further functional work initiated.
