# CLIENTES-01.3 — validation of stable Customer row locking

No application/test code changed during execution. Stopped at first error; no retries.

| Separate execution | Discovered | Executed | Passed | Failures | Errors | Not run | Seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original replacement -> deletion | 1 | 1 | 1 | 0 | 0 | 0 | 0.792 |
| Four new tests | 4 | 4 | 4 | 0 | 0 | 0 | 1.578 |
| Full concurrency module | 12 | 12 | 12 | 0 | 0 | 0 | 13.914 |
| Full authorized selection | 66 | 13 | 12 | 0 | 1 | 53 | 2.203 |

These runs overlap; do not combine them into a passing 66-test claim.

## Full selection by module

| Module | Passed | Errors | Not run |
|---|---:|---:|---:|
| customer_document_restrictions_clientes013 | 12 | 0 | 0 |
| customer_category_assignment | 0 | 1 | 13 |
| customer_ui_actions | 0 | 0 | 16 |
| customer_person_replacement | 0 | 0 | 12 |
| customer_document_concurrency_clientes013 | 0 | 0 | 12 |

The concurrency module independently passed all 12 earlier in this same controlled
sequence, but was not reached in the final full selection because of failfast.

## Preconditions and preservation

Identity, owner, role privileges/no memberships and CONNECT/CREATE verified through
CLIENTES013 backend: test_sisadmi_clientes013 / sisadmi_erp_test_runner /
127.0.0.1:5432. Exactly five authorized modules; dedicated guard rejects other
names. Existing schema consistent, no pending migration plan, no migration applied.
No database creation/destruction/cloning. Populated TEST separate R-01 connection
used only REPEATABLE READ READ ONLY transactions. Web paused; no other populated
connections observed at captures. Every table's full-row SHA256/count matched
before/after each of the four stages: 54 Person, 54 CompanyPersonAccess, four
Customer, all geographic rows and other data intact. No populated flush/writes.

## Functional conclusions supported by this execution

Original defective scenario now passes: stable company/PK SELECT FOR UPDATE,
replacement commits, waiting deletion proceeds, only Customer deleted, both
Persons preserved. Its instrumented final snapshot and SQL are saved separately.
Four new tests passed: revoked replacement access blocks mutations; inactive
replacement blocks mutations; missing permission rejected before FOR UPDATE;
waiting deletion revalidates revoked access after replacement commit.
DRAFT/CONFIRMED/CANCELLED restrictions, allowed commercial edits, cross-company
checks and direct FK enforcement passed in the 12-case restriction module.
Sales contract accepting inactive Person/revoked access remained unchanged.

All 12 concurrency tests passed with distinct verified connection PIDs and real
pg_blocking_pids edges, rollback cases, normal lock_timeout 5s, deliberate timeout
1000ms with SQLSTATE 55P03, statement_timeout 8s and worker connection cleanup.
No other isolated DB connections remained at final READ ONLY inspection.

## Scope of concurrent revocation proof

Recorded in concurrency run: Customer 61, Company 139, Person 280 -> 281.
Replacement PID 2005143 and deletion PID 2005147, both READ COMMITTED.
Observer PID 2005135 confirmed deletion waiting on replacement.
Replacement first revalidated Person 280 (one row), selected Person 281 (one row),
then committed replacement plus access revocation together. Its commit returned
before deletion revalidated Person 281. That revalidation returned zero rows;
delete rejected with ObjectDoesNotExist. Final snapshot BEFORE transaction-test
cleanup: Customer 61 still active with Person 281; both Persons active, no access
for replacement, availability-filtered Customer query empty, direct PK/company
query finds the Customer. The deleting transaction did not commit a deletion.

This proves this specific ordering only. It does NOT establish general immunity
to independent revocation committed after availability revalidation or every
possible concurrent history. No additional access-row locks were introduced.
Evidence was collected by the external launcher using existing diagnostic hooks;
repository test/service code was not modified during execution.

## New blocker in full selection

After 12 passing restriction tests, the first legacy category test failed in
CustomerCategoryAssignmentTests.setUp at test_customer_category_assignment.py:15,
creating its company Person. ValidationError: incoherent_person_identity.
Readonly isolated diagnosis confirmed IdentificationKind count=0. The preceding
TransactionTestCase stage had legitimately flushed the disposable database;
old category fixtures assume the migration-seeded catalog remains. The new
CLIENTES013 fixture initializes OTHER within each test but its TestCase writes
roll back and do not initialize unrelated legacy fixtures permanently.

Classification: legacy fixture seed dependency; no new Customer service failure
shown by this error. Proposed next correction requires approval: explicitly
prepare the official identification types needed by legacy Customer regression
fixtures (including PASSPORT for related Person flows), without replaying data
migrations, changing validators, or weakening existing assertions. Reexecute
failed test then approved full selection; no success is assumed in advance.
No correction performed here.

## Completion and evidence

TEST web restored; login HTTP 200. Original temporary credential removed. No DEV,
CAT-02.3/GEO-01 code/test changes or CAT-05 flag changes, Git stage/commit/push.
CAT-05 1138 preserved hashes and 7 frozen candidates verified intact.
Django system checks passed during runs; no additional tests/makemigrations checks
after the failfast error. CLI-R01 untouched.

- core/testing/clientes013_fix_validation_results.json (all runs/cases/PIDs)
- core/testing/clientes013_fix_original_evidence.json (original case)
- core/testing/clientes013_fix_revocation_evidence.json (ordered revocation reads)
- /tmp/clientes013-fix-{original,new,concurrency,all}.log
- /tmp/clientes013-fix-validation/populated-before.json
- /tmp/clientes013-fix-validation/{failed,new,concurrency,all}-results.json

Awaiting human review before any new correction.
