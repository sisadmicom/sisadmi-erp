# CLIENTES-01.3 — controlled repetition; stopped on new error

No correction or test retry after the error. No business code or test code changed.

| Execution | Selected | Executed | Passed | Failures | Errors | Not executed |
|---|---:|---:|---:|---:|---:|---:|
| Previously failing concurrent case | 1 | 1 | 1 | 0 | 0 | 0 |
| Concurrent module | 11 | 5 | 4 | 0 | 1 | 6 |
| Document restriction module | 9 | 0 | 0 | 0 | 0 | 9 |
| Full whitelist suite | 62 | 0 | 0 | 0 | 0 | 62 |

Separate runs: first 0.736s; concurrent run 5.002s. The first case repeats in the
module run; these results are not combined with older runs into a 62-test claim.

Connection verified by strict CLIENTES013 backend: test_sisadmi_clientes013,
sisadmi_erp_test_runner, owner matches, 127.0.0.1:5432, correct privileges and no
administrative role flags/memberships. Reused existing database, no pending
migration plan; none created/destroyed/cloned. Guard checks rejected populated
TEST, GEO-01, DEV and bootstrap destinations without connecting to them.
Django system checks passed. No new migration. Database/schema maintenance was
limited to the isolated DB and its ordinary TransactionTestCase cleanup.

Passed concurrent cases:
- controlled timeout + holder rollback, SQLSTATE 55P03, identical business snapshot;
- delete first / replacement second -> expected missing relationship;
- delete first / sale second -> expected missing customer and no partial writes;
- delete rollback / waiting sale -> sale succeeds after rollback.

The approved kind fixture fix eliminated the previously observed missing catalog
error in these runs. Every case reached its synchronization instead of failing
Person creation. This does not prove the remaining scenarios will pass.

New error: test_replacement_first_delete_removes_only_customer.
Replacement holder PID 1985985 completed without error. Delete waiter PID 1985987
was observed blocked on that holder via pg_blocking_pids, then raised
ObjectDoesNotExist('Commercial relationship unavailable.') at
CommercialRelationshipMaintenance.relation, called by customer_maintenance.delete.
Expected contract was serialized replacement followed by deletion of Customer.
Both worker connections closed and neither retained an atomic transaction.
No timeout or 55P03 occurred in this case. The exact underlying cause of the
post-wait unavailable query is NOT established; further SQL/query/visibility
analysis is required before classifying it as a fixture or business-service defect.
Do not weaken the expectation or modify a service based solely on this result.

Per-case blocking edges, PIDs, SQLSTATEs, times and worker cleanup are in
core/testing/clientes013_repeat_results.json. No residual isolated DB connections
were found by a post-run READ ONLY query. Frozen CAT-05: 1138 file hashes and
7 frozen candidates verified unchanged; GEO-01 code/tests not modified.

Preservation: populated TEST accessed through a separate R-01 connection, only
REPEATABLE READ READ ONLY transactions. TEST web was paused; no other connections
observed at snapshots. Every populated table's full-row SHA256 and count identical
before/after both runs: 54 Person, 54 CompanyPersonAccess, 4 original Customer,
and all geographic records/references. No populated TEST flush/migrations/writes.
Web restored, login HTTP 200. Original temporary credential removed after restart.
No DEV, CAT-05 flag changes, stage, commit or push. CLI-R01 untouched.
makemigrations --check --dry-run and later tests not run after the failfast stop.

Evidence (previous execution artifacts retained separately):
- /tmp/clientes013-repeat-failed.log
- /tmp/clientes013-repeat-concurrency.log
- /tmp/clientes013-repeat-controlled/populated-before.json
- /tmp/clientes013-repeat-controlled/failed-results.json
- /tmp/clientes013-repeat-controlled/concurrency-results.json

Awaiting human review before further diagnosis/reproduction or correction.
