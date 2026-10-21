# CLIENTES-01.3 — catalog validation stopped on evidence serialization error

Only the historical category case was executed:
CustomerCategoryAssignmentTests.test_active_category_can_be_explicitly_cleared.
Result: 1 passed, 0 failures, 0 test errors, 0.139s. The 42-case historical
selection and the full 66-case selection were NOT executed. No retry.

Destination/owner/permissions verified through the dedicated backend:
test_sisadmi_clientes013, sisadmi_erp_test_runner, 127.0.0.1:5432. No pending
migrations; no database creation/destruction/cloning or application code change.
Django system check passed. No further tests/makemigrations check after stop.

post_migrate event before the historical case: catalog empty before, then
OTHER/"Otro" ID 43 and PASSPORT/"Pasaporte" ID 44 present and active. Observer
registered before the scoped initializer captured before values; a second
observer registered after it captured after values. Receiver disconnected when
the runner finished. The seed therefore resolved the previously failing case.
No existing kinds were present in this run, so unchanged-existing/inactive-kind
behavior was not exercised against actual data. Unit/static checks from the
previous phase remain separate evidence. No TransactionTestCase was executed in
this run; post-flush reseeding still requires the authorized full suite.

A separate external launcher error occurred AFTER the successful test and after
runner disconnect/preservation assertions: /tmp/clientes013-catalog-validation.py
line 154 attempted json.dumps of per-test catalog snapshots containing datetime
objects, without a converter. TypeError: Object of type datetime is not JSON
serializable. This is an evidence-writing defect, not a test failure or catalog
initializer failure. All later test stages were stopped. No code corrected.

Proposed minimal next action, subject to review: normalize datetime/date fields
to ISO-8601 when saving external diagnostic output, without changing tests,
services or the catalog initializer; then repeat the approved staged validation.
No claim that the remaining tests will pass is made.

Post-run READ ONLY verification confirmed every populated TEST table's full-row
hash/count identical to its pre-run capture, including 54 Person, 54 accesses,
four Customers and full geography. No other populated connections at capture.
No residual isolated test connections. TEST web restored, login HTTP 200, exact
temporary credential removed. No DEV, CAT-05/GEO-01/CAT-02.3 changes, flush on
populated TEST, Git stage/commit/push or CLI-R01 work.

Evidence:
- core/testing/clientes013_catalog_validation_results.json
- /tmp/clientes013-catalog-failed.log (test OK plus separate full launcher traceback)
- /tmp/clientes013-catalog-validation/failed-catalog-events.json
- /tmp/clientes013-catalog-validation/populated-before.json
- /tmp/clientes013-catalog-validation/populated-after.json

Stopped for human review before further changes or executions.
