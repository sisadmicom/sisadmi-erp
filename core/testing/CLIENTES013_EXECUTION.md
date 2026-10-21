# CLIENTES-01.3 — controlled execution stopped at first error

Representative execution: 1 test, 1 passed, 0 failures/errors; 0.307 seconds.
Separate full selection: 62 discovered, 53 executed, 52 passed, 0 failures,
1 error; 9 not executed; 8.022 seconds. The representative case also belongs
to the 62; it is not an additional unique success.

| Module | Authorized | Passed | Failures | Errors | Not run |
|---|---:|---:|---:|---:|---:|
| test_customer_document_restrictions_clientes013 | 9 | 9 | 0 | 0 | 0 |
| test_customer_category_assignment | 14 | 14 | 0 | 0 | 0 |
| test_customer_ui_actions | 16 | 16 | 0 | 0 | 0 |
| test_customer_person_replacement | 12 | 12 | 0 | 0 | 0 |
| test_customer_document_concurrency_clientes013 | 11 | 1 | 0 | 1 | 9 |

Connection verified: test_sisadmi_clientes013 / sisadmi_erp_test_runner /
127.0.0.1:5432, correct owner, CONNECT/CREATE true, no administrative role flags
or memberships; initially no tables. Dedicated backend rejects other database
names before connection. Django applied schema only in this disposable database;
no database created/dropped/cloned. Populated TEST was accessed exclusively through
a separate original R-01 wrapper in REPEATABLE READ READ ONLY transactions.
TEST server paused to exclude human editing; no other populated-DB connections
observed before/after. All table counts and full-row hashes matched exactly,
including 54 Person, 54 CompanyPersonAccess, 4 Customer and geography. No writes,
flush or migrations in populated TEST. CAT-05 hashes: 1138 files and 7 frozen
candidates unchanged. GEO-01 runner, services/models/forms/views unchanged.

Document restrictions passed for DRAFT, CONFIRMED and CANCELLED (real lifecycle),
HTTP/service errors, allowed commercial edits, company isolation and direct FK
violation (SQLSTATE 23503 plus specific actual constraint). Sales acceptance of
inactive Person/revoked CompanyPersonAccess remained unchanged and passed.

First concurrent case passed:
`test_controlled_timeout_and_holder_rollback_leave_no_changes`.
Its assertions proved distinct PostgreSQL PIDs, the exact wait edge using
pg_blocking_pids, controlled lock_timeout 1000ms with SQLSTATE 55P03, holder
rollback, complete business snapshot preservation and closed worker backends.
Worker statement_timeout was 8s; normal lock_timeout 5s. Other concurrency
scenarios remain unverified; no claim is made that all races are safe.

Next case failed during fixture setUp, before creating its workers:
`test_delete_first_replacement_reports_missing_customer`.
Trace: CustomerDocumentFixture.setUp -> person('COMPANY', 'LEGAL') -> Person.save
-> ValidationError code incoherent_person_identity. The first TransactionTestCase
flushes its disposable DB at teardown; seed data from migration 0010 is removed.
PeopleConfig does not replenish IdentificationKind on post_migrate. Subsequent
fixture assumes that seed data survives. READ ONLY confirmation afterward:
IdentificationKind count 0, people.0010 migration applied, DocumentType count 7
(its independent initializer did run), no other isolated DB connections.

Classification: test-fixture initialization defect, not a demonstrated Customer
service defect. Minimal proposed follow-up: explicitly/idempotently prepare the
identification kinds required by the test fixtures before Person creation, without
replaying migration 0010, changing business validation or implementing CLI-R01.
No correction/retry made. Further results must be established by a new execution;
this report does not assume the remaining cases will pass after that correction.

Django system checks reported no issues. No new migration was created.
makemigrations --check --dry-run and additional tests were not run after failfast.
TEST web restored (PID 1962433), login HTTP 200. Original temporary credential
removed after restart. No DEV, Git stage/commit/push or automatic repair.

Evidence:
- core/testing/clientes013_execution_results.json (per-case status and time)
- /tmp/clientes013-representative.log
- /tmp/clientes013-all.log (complete traceback)
- /tmp/clientes013-controlled-execution/populated-before.json
- /tmp/clientes013-controlled-execution/representative-results.json
- /tmp/clientes013-controlled-execution/all-results.json (post-run table hashes)
- /tmp/clientes013-controlled-execution/readonly-diagnostic.json

Awaiting human review before any fixture/service correction.
