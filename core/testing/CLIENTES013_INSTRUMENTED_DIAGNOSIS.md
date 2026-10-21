# CLIENTES-01.3 — one instrumented execution

1 executed, 0 passed, 0 assertion failures, 1 error; 0.964 seconds.
No retry and no full suite. The original ObjectDoesNotExist remains an error.
Guarded destination test_sisadmi_clientes013 / sisadmi_erp_test_runner /
127.0.0.1:5432; owner/permissions checked. No pending migrations.

Fixture Customer 51, Company 119, original Person 230, replacement Person 231.
Observer PID 1996043, replacement PID 1996057, deletion PID 1996059.
Worker transactions READ COMMITTED. pg_blocking_pids(1996059) returned [1996057].
Replacement locking SELECT returned 1 row; commit returned successfully.
Deletion locking SELECT completed after that commit and returned 0 rows.
CommercialRelationshipMaintenance.relation line 89 raised ObjectDoesNotExist.
The DELETE operation itself was never reached.

## Actual deletion locking SQL (unmodified)

```sql
SELECT "people_customer"."id", "people_customer"."created_at", "people_customer"."updated_at", "people_customer"."created_by_id", "people_customer"."updated_by_id", "people_customer"."is_active", "people_customer"."deleted_at", "people_customer"."company_id", "people_customer"."person_id", "people_customer"."credit_limit", "people_customer"."notes", "people_customer"."category_id" FROM "people_customer" WHERE ("people_customer"."company_id" = %s AND "people_customer"."person_id" IN (SELECT U0."id" AS "pk" FROM "people_person" U0 INNER JOIN "people_companypersonaccess" U1 ON (U0."id" = U1."person_id") WHERE (U1."company_id" = %s AND U0."is_active")) AND "people_customer"."id" = %s) ORDER BY "people_customer"."id" ASC LIMIT 1 FOR UPDATE
```

Parameters: `[119, 119, 51]`.

## Final snapshot before TransactionTestCase cleanup

Taken by observer in a fresh REPEATABLE READ READ ONLY transaction after workers
closed. Both direct PK/company and availability-filtered queries returned:

```json
[
  {
    "id": 51,
    "company_id": 119,
    "person_id": 231,
    "category_id": 147,
    "is_active": true
  }
]
```

Both Person 230 and Person 231 were active. CompanyPersonAccess ID 112 existed
for Company 119 and Person 231. That association model has no activity field.
Full SQL/parameters for both queries, commit/block events and preserved traceback
are in clientes013_instrumented_evidence.json.

## Classification and proposed minimal correction

Confirmed: the locking lookup reports the existing authorized Customer as absent
when concurrent replacement changes person_id. The same row is subsequently
visible through both lookups. Wrong PK, missing replacement access, inactive
replacement and a successful competing deletion are not supported by this run.
The failing lookup combines row locking with a mutable person_id IN subquery.
This is a service lookup/concurrency defect reproduced by real PostgreSQL; it
is not the earlier identification catalog fixture defect. Exact planner/executor
mechanism (e.g. semijoin recheck) is not proven without a captured execution plan.
No claim that PostgreSQL itself is defective is made.

Proposed, NOT implemented: authorize operator/company first; lock Customer by
immutable PK and company; then revalidate current Person visibility/availability
after lock acquisition within the same transaction. Preserve all permissions
and dependency checks; do not suppress ObjectDoesNotExist or weaken assertions.
Assess shared Customer/Supplier helper impact before choosing patch location.

Expected after a separately approved correction: the exact case must observe
blocking, then delete only Customer 51 after replacement commit; both Persons
and accesses remain unchanged. Rollback/timeout and other races need separate
authorized regression; no passing result is inferred here.

## Preservation and cleanup

All populated TEST table counts/full-row hashes matched before/after (READ ONLY
separate R-01 connection): 54 Person, 54 CompanyPersonAccess, four Customers,
geography and all other tables. No other populated TEST connections were observed
at capture time; web was paused and restored afterward (login HTTP 200). Original
temporary credential removed. No service/model/form/view/migration changed.
No DEV, GEO-01, CAT-05 or CAT-02.3 changes, commit/push or automatic DB creation.
Django system check passed; no additional tests or makemigrations check after error.

Raw run: /tmp/clientes013-instrumented-once.log. Before/after integrity evidence:
/tmp/clientes013-instrumented-once/populated-before.json and failed-results.json.
Stopped for human review before any correction.
