# CLIENTES-01 — Inventario Git y candidatos

Fecha: 2026-10-18. Inventario por archivo, no una reconstrucción autoritativa de autoría.
Rama `main`; HEAD `e5c4c6cec2f410772dfbe7eb434bf3932b895692`. Índice sin cambios preparados.
Inicio del cierre: **97 modificados + 282 no rastreados = 379**. Este cierre añade solo
`docs/CLIENTES01_CLOSURE.md` y este inventario: previsión final **97 + 284 = 381**.
` M` significa modificación solo en working tree; `??` archivo no rastreado.
Git diff normal no incluye archivos no rastreados; CLIENTES también se revisó por contenido/AST/JSON.
No usar `git add .` ni agregar directorios completos para materializar esta lista.

## Candidatos exactos, condicionados a integración de prerrequisitos

Estos 20 archivos son candidatos de alcance, **no un commit funcional independiente listo**.
`customer_maintenance.py` está entero sin rastrear y contiene funcionalidad previa compartida;
la corrección CLIENTES-01.3 dentro de él es el import de ObjectDoesNotExist y el override relation().
No incorporar todos sus antecedentes como si fueran una nueva modificación exclusiva.

- `config/settings_clientes013_test.py`
- `core/testing/clientes013_catalog.py`
- `core/testing/clientes013_guard.py`
- `core/testing/clientes013_runner.py`
- `core/testing/clientes013_postgresql/__init__.py`
- `core/testing/clientes013_postgresql/base.py`
- `core/testing/clientes013_postgresql/creation.py`
- `core/tests/test_clientes013_test_environment.py`
- `people/tests/clientes013_support.py`
- `people/tests/clientes013_diagnostic.py`
- `people/tests/test_customer_document_restrictions_clientes013.py`
- `people/tests/test_customer_document_concurrency_clientes013.py`
- `people/services/customer_maintenance.py`
- `core/testing/CLIENTES013_TEST_ISOLATION.md`
- `core/testing/CLIENTES013_FINAL_VALIDATION.md`
- `core/testing/clientes013_final_validation_results.json`
- `core/testing/clientes013_final_original_evidence.json`
- `core/testing/clientes013_final_revocation_evidence.json`
- `docs/CLIENTES01_CLOSURE.md`
- `docs/CLIENTES01_GIT_INVENTORY.md`

## Dependencias que bloquean independencia desde HEAD

- `config/settings_test_r01.py`, `core/testing/r01_guard.py` y backend R-01: nuevos sin integrar; el settings aislado los importa.
- `people/services/commercial_relationship_maintenance.py` y política de Personas/contexto: el servicio Customer nuevo depende de ellos.
- `Customer.company`, unicidad y `Customer.category`: cambios de modelo con migraciones `people.0005`, `.0007`, `.0008` aún sin integrar; la cadena incluye `.0006` de Proveedores.
- `IdentificationKind`, enum OTHER/PASSPORT, validadores y migraciones `.0009`–`.0011`: prerrequisitos de fixtures/modelos; no pertenecen al fix concurrente.
- Formularios/vistas/rutas y plantillas comerciales son previos y compartidos con Proveedores, Personas y GEO-01; `config/urls.py` y shell también tienen cambios mixtos.
- CreateSale/ConfirmSale y cálculo comercial tienen cambios acumulados R-04/CAT-02.3; los 66 casos validaron el working tree actual, no HEAD más estos 20 archivos.
- El lanzador de auditoría vive fuera del repositorio en `/tmp`; sus resultados persistentes se preservan en core/testing, pero no se versiona un script temporal automáticamente.

**Recomendación:** GO para cierre técnico/documental; NO-GO para presentar ahora un commit funcional autónomo desde HEAD.
Planificar primero integración de etapas previas o una separación revisada de cambios; este cierre no la ejecuta.
Un commit puramente documental es posible, indicando que sus referencias de implementación siguen pendientes de integración.

## Inventario completo clasificado

### CAT-01 / CAT-02.1: catálogo de productos

36 archivos.

| Estado | Archivo | Criterio |
|---|---|---|
| ` M` | `catalog/forms.py` | Ajeno; no agregar al cierre CLIENTES |
| ` M` | `catalog/models/product.py` | Ajeno; no agregar al cierre CLIENTES |
| ` M` | `catalog/templates/catalog/product_detail.html` | Ajeno; no agregar al cierre CLIENTES |
| ` M` | `catalog/templates/catalog/product_form.html` | Ajeno; no agregar al cierre CLIENTES |
| ` M` | `catalog/templates/catalog/unit_form.html` | Ajeno; no agregar al cierre CLIENTES |
| ` M` | `catalog/templates/catalog/unit_list.html` | Ajeno; no agregar al cierre CLIENTES |
| ` M` | `catalog/urls.py` | Ajeno; no agregar al cierre CLIENTES |
| ` M` | `catalog/views.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/group_forms.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/group_views.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/migrations/0004_alter_product_cost_price_alter_product_sale_price.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/related_fields.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/services/product_continuation.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/subgroup_forms.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/subgroup_views.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/templates/catalog/brand_detail.html` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/templates/catalog/brand_form.html` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/templates/catalog/brand_list.html` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/templates/catalog/deactivate_confirm.html` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/templates/catalog/group_detail.html` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/templates/catalog/group_form.html` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/templates/catalog/group_list.html` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/templates/catalog/product_continuation_controls.html` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/templates/catalog/product_subgroup_refresh.html` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/templates/catalog/subgroup_detail.html` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/templates/catalog/subgroup_form.html` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/templates/catalog/subgroup_list.html` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/templates/catalog/unit_detail.html` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/tests/test_brand_maintenance_cat012b_red.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/tests/test_product_form_ux_cat012f.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/tests/test_product_group_maintenance_cat012c_red.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/tests/test_product_maintenance_cat01_red.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/tests/test_product_related_continuation_cat012e_red.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/tests/test_product_subgroup_maintenance_cat012d_red.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/tests/test_unit_measure_maintenance_cat012a_red.py` | Ajeno; no agregar al cierre CLIENTES |
| `??` | `catalog/tests/test_unit_price_precision_cat021_red.py` | Ajeno; no agregar al cierre CLIENTES |

### CAT-02.2 / CAT-02.3: relaciones comerciales

13 archivos.

| Estado | Archivo | Criterio |
|---|---|---|
| ` M` | `people/models/supplier.py` | Prerrequisito; congelados CAT-02.3 no se modifican ni incorporan automáticamente |
| `??` | `people/migrations/0005_customer_company_expansion.py` | Prerrequisito; congelados CAT-02.3 no se modifican ni incorporan automáticamente |
| `??` | `people/migrations/0006_supplier_company_expansion.py` | Prerrequisito; congelados CAT-02.3 no se modifican ni incorporan automáticamente |
| `??` | `people/services/commercial_relationship_maintenance.py` | Prerrequisito; congelados CAT-02.3 no se modifican ni incorporan automáticamente |
| `??` | `people/services/customer_company_evidence.py` | Prerrequisito; congelados CAT-02.3 no se modifican ni incorporan automáticamente |
| `??` | `people/services/supplier_maintenance.py` | Prerrequisito; congelados CAT-02.3 no se modifican ni incorporan automáticamente |
| `??` | `people/tests/test_commercial_document_activity_cat023_red.py` | Prerrequisito; congelados CAT-02.3 no se modifican ni incorporan automáticamente |
| `??` | `people/tests/test_commercial_document_concurrency_cat023_red.py` | Prerrequisito; congelados CAT-02.3 no se modifican ni incorporan automáticamente |
| `??` | `people/tests/test_commercial_relationship_maintenance_cat023_red.py` | Prerrequisito; congelados CAT-02.3 no se modifican ni incorporan automáticamente |
| `??` | `people/tests/test_commercial_relationship_web_cat023_red.py` | Prerrequisito; congelados CAT-02.3 no se modifican ni incorporan automáticamente |
| `??` | `people/tests/test_customer_company_cat022a_red.py` | Prerrequisito; congelados CAT-02.3 no se modifican ni incorporan automáticamente |
| `??` | `people/tests/test_customer_company_green.py` | Prerrequisito; congelados CAT-02.3 no se modifican ni incorporan automáticamente |
| `??` | `people/tests/test_supplier_company_cat022b_red.py` | Prerrequisito; congelados CAT-02.3 no se modifican ni incorporan automáticamente |

### CLIENTES-01: candidatos condicionados

20 archivos.

| Estado | Archivo | Criterio |
|---|---|---|
| `??` | `config/settings_clientes013_test.py` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `core/testing/CLIENTES013_FINAL_VALIDATION.md` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `core/testing/CLIENTES013_TEST_ISOLATION.md` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `core/testing/clientes013_catalog.py` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `core/testing/clientes013_final_original_evidence.json` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `core/testing/clientes013_final_revocation_evidence.json` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `core/testing/clientes013_final_validation_results.json` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `core/testing/clientes013_guard.py` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `core/testing/clientes013_postgresql/__init__.py` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `core/testing/clientes013_postgresql/base.py` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `core/testing/clientes013_postgresql/creation.py` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `core/testing/clientes013_runner.py` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `core/tests/test_clientes013_test_environment.py` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `people/services/customer_maintenance.py` | Servicio mixto UI/CAT previo + corrección CLIENTES-01.3 |
| `??` | `people/tests/clientes013_diagnostic.py` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `people/tests/clientes013_support.py` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `people/tests/test_customer_document_concurrency_clientes013.py` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `people/tests/test_customer_document_restrictions_clientes013.py` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `docs/CLIENTES01_CLOSURE.md` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |
| `??` | `docs/CLIENTES01_GIT_INVENTORY.md` | Propio del cierre, pruebas o evidencia final; depende de prerrequisitos no integrados |

### CLIENTES-01: historial intermedio, fuera del commit mínimo

13 archivos.

| Estado | Archivo | Criterio |
|---|---|---|
| `??` | `core/testing/CLIENTES013_CATALOG_VALIDATION.md` | Conservar; resultados parciales/fallidos históricos, no sustituyen 66/66 final |
| `??` | `core/testing/CLIENTES013_EXECUTION.md` | Conservar; resultados parciales/fallidos históricos, no sustituyen 66/66 final |
| `??` | `core/testing/CLIENTES013_FIX_VALIDATION.md` | Conservar; resultados parciales/fallidos históricos, no sustituyen 66/66 final |
| `??` | `core/testing/CLIENTES013_INSTRUMENTED_DIAGNOSIS.md` | Conservar; resultados parciales/fallidos históricos, no sustituyen 66/66 final |
| `??` | `core/testing/CLIENTES013_REPEAT.md` | Conservar; resultados parciales/fallidos históricos, no sustituyen 66/66 final |
| `??` | `core/testing/clientes013_catalog_validation_results.json` | Conservar; resultados parciales/fallidos históricos, no sustituyen 66/66 final |
| `??` | `core/testing/clientes013_execution_results.json` | Conservar; resultados parciales/fallidos históricos, no sustituyen 66/66 final |
| `??` | `core/testing/clientes013_fix_original_evidence.json` | Conservar; resultados parciales/fallidos históricos, no sustituyen 66/66 final |
| `??` | `core/testing/clientes013_fix_revocation_evidence.json` | Conservar; resultados parciales/fallidos históricos, no sustituyen 66/66 final |
| `??` | `core/testing/clientes013_fix_validation_results.json` | Conservar; resultados parciales/fallidos históricos, no sustituyen 66/66 final |
| `??` | `core/testing/clientes013_instrumented_evidence.json` | Conservar; resultados parciales/fallidos históricos, no sustituyen 66/66 final |
| `??` | `core/testing/clientes013_instrumented_results.json` | Conservar; resultados parciales/fallidos históricos, no sustituyen 66/66 final |
| `??` | `core/testing/clientes013_repeat_results.json` | Conservar; resultados parciales/fallidos históricos, no sustituyen 66/66 final |

### Convenciones UI generales

2 archivos.

| Estado | Archivo | Criterio |
|---|---|---|
| ` M` | `AGENTS.md` | Acuerdo transversal previo; no incluir automáticamente |
| `??` | `docs/UI_CONVENCIONES.md` | Acuerdo transversal previo; no incluir automáticamente |

### GEO-01 / GEO-01-TEST

64 archivos.

| Estado | Archivo | Criterio |
|---|---|---|
| `??` | `config/settings_geo01_test.py` | Ajeno; conservar intacto |
| `??` | `core/testing/GEO01_TEST_ISOLATION.md` | Ajeno; conservar intacto |
| `??` | `core/testing/geo01_guard.py` | Ajeno; conservar intacto |
| `??` | `core/testing/geo01_postgresql/__init__.py` | Ajeno; conservar intacto |
| `??` | `core/testing/geo01_postgresql/base.py` | Ajeno; conservar intacto |
| `??` | `core/testing/geo01_postgresql/creation.py` | Ajeno; conservar intacto |
| `??` | `core/testing/geo01_runner.py` | Ajeno; conservar intacto |
| `??` | `core/testing/geo01_test_executed_operations.json` | Ajeno; conservar intacto |
| `??` | `core/testing/geo01_test_execution_results.json` | Ajeno; conservar intacto |
| `??` | `core/tests/test_geo01_test_environment.py` | Ajeno; conservar intacto |
| `??` | `data/geo01/REPORT.md` | Ajeno; conservar intacto |
| `??` | `data/geo01/development_audit.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/development_dry_run.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/ecuador_2016.csv` | Ajeno; conservar intacto |
| `??` | `data/geo01/hotfix_validation.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/model_contract.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/parishes_by_canton.csv` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase1/PLAN.md` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase1/database_before.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase1/decisions_table.csv` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase1/development_plan.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase1/entity_counts.csv` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase1/final_audit.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase1/import_decisions.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase1/original_artifact_hashes.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase1/regression_result.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase1/repeat_simulation.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase1/source_lineage.csv` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase1/source_lineage.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase2/REPORT.md` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase2/dry_run.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase2/ecuador_2016_partial.csv` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase2/lineage.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase2/operations.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase2/pending_exceptions.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase2/prepare.py` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase2/repeat_simulation.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase2/verification.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase3/apply_result.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase3/backup_manifest.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase3/before_audit.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase3/execution_report.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase3/final_geography_snapshot.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase3/geography_backup.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase3/pre_execution_dry_run.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase3/run_execution.py` | Ajeno; conservar intacto |
| `??` | `data/geo01/phase3/second_dry_run.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/source_report.json` | Ajeno; conservar intacto |
| `??` | `data/geo01/verification.json` | Ajeno; conservar intacto |
| `??` | `people/management/commands/import_ecuador_geography.py` | Ajeno; conservar intacto |
| `??` | `people/management/commands/prepare_ecuador_geography.py` | Ajeno; conservar intacto |
| `??` | `people/services/geography_catalog_import.py` | Ajeno; conservar intacto |
| `??` | `people/services/geography_catalog_parser.py` | Ajeno; conservar intacto |
| `??` | `people/services/geography_deletion.py` | Ajeno; conservar intacto |
| `??` | `people/services/geography_import_decisions.py` | Ajeno; conservar intacto |
| `??` | `people/static/people/js/geography_selects.js` | Ajeno; conservar intacto |
| `??` | `people/templates/people/geography_delete.html` | Ajeno; conservar intacto |
| `??` | `people/templates/people/geography_form.html` | Ajeno; conservar intacto |
| `??` | `people/templates/people/geography_list.html` | Ajeno; conservar intacto |
| `??` | `people/tests/test_geo01_decisions.py` | Ajeno; conservar intacto |
| `??` | `people/tests/test_geo01_import.py` | Ajeno; conservar intacto |
| `??` | `people/tests/test_geo01_partial.py` | Ajeno; conservar intacto |
| `??` | `people/tests/test_geo01_plan_comparison.py` | Ajeno; conservar intacto |
| `??` | `people/tests/test_geography_ui.py` | Ajeno; conservar intacto |

### Identificación e inmutabilidad de Personas

21 archivos.

| Estado | Archivo | Criterio |
|---|---|---|
| ` M` | `people/apps.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| ` M` | `people/constants/identification_type.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| ` M` | `people/models/person.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| ` M` | `people/test_identification_type_contract.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `core/testing/identification_regression_results.json` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `core/testing/person_identity_immutability_results.json` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `docs/IDENTIFICACION_PERSONAS.md` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `docs/INMUTABILIDAD_IDENTIDAD_PERSONAS.md` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `people/identification.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `people/identity_integrity.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `people/management/commands/audit_identification_test.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `people/migrations/0009_alter_person_identification_type_identificationkind_and_more.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `people/migrations/0010_identification_catalog_and_final_consumer.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `people/migrations/0011_person_identity_immutable.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `people/models/identification_kind.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `people/services/final_consumer.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `people/services/person_protection.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `people/static/people/js/identification.js` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `people/tests/test_identification_integration.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `people/tests/test_identification_validation.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |
| `??` | `people/tests/test_person_identity_immutability.py` | Prerrequisito; no confundir protección Person existente con CLI-R01 pendiente |

### Importación de Personas / auditoría CORE

10 archivos.

| Estado | Archivo | Criterio |
|---|---|---|
| ` M` | `core/models/__init__.py` | Ajeno al cierre; dependencia por acumulación del working tree |
| `??` | `core/migrations/0011_auditlog.py` | Ajeno al cierre; dependencia por acumulación del working tree |
| `??` | `core/testing/audit_enablement_preparation.json` | Ajeno al cierre; dependencia por acumulación del working tree |
| `??` | `core/testing/audit_import_execution_results.json` | Ajeno al cierre; dependencia por acumulación del working tree |
| `??` | `core/testing/controlled_person_import_final_results.json` | Ajeno al cierre; dependencia por acumulación del working tree |
| `??` | `core/testing/controlled_person_import_results.json` | Ajeno al cierre; dependencia por acumulación del working tree |
| `??` | `docs/IMPORTACION_PERSONAS_CONTROLADA.md` | Ajeno al cierre; dependencia por acumulación del working tree |
| `??` | `people/management/commands/import_approved_test_people.py` | Ajeno al cierre; dependencia por acumulación del working tree |
| `??` | `people/services/controlled_person_import.py` | Ajeno al cierre; dependencia por acumulación del working tree |
| `??` | `people/tests/test_controlled_person_import.py` | Ajeno al cierre; dependencia por acumulación del working tree |

### R-01 / R-02 / R-03 / R-04: infraestructura y regresión

18 archivos.

| Estado | Archivo | Criterio |
|---|---|---|
| ` M` | `core/apps.py` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `config/settings_test_r01.py` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/services/document_type_catalog.py` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/testing/R01_POSTGRESQL.md` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/testing/R03_REGRESSION.md` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/testing/R04_ESTABILIZACION.md` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/testing/__init__.py` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/testing/migration_isolation.py` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/testing/r01_guard.py` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/testing/r01_postgresql/__init__.py` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/testing/r01_postgresql/base.py` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/testing/r01_postgresql/creation.py` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/testing/r01_runner.py` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/testing/r04_results.json` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/testing/runner.py` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/tests/test_document_type_initialization_r04.py` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/tests/test_migration_isolation.py` | Prerrequisito o etapa ajena; sin cambios en este cierre |
| `??` | `core/tests/test_r01_test_environment.py` | Prerrequisito o etapa ajena; sin cambios en este cierre |

### R-04 / R-05 / R-06: SRI

48 archivos.

| Estado | Archivo | Criterio |
|---|---|---|
| ` M` | `sri/clients/sri_authorization_soap_adapter.py` | Ajeno; no incluir |
| ` M` | `sri/clients/sri_reception_soap_adapter.py` | Ajeno; no incluir |
| ` M` | `sri/services/electronic_document_authorization_service.py` | Ajeno; no incluir |
| ` M` | `sri/services/electronic_document_reception_service.py` | Ajeno; no incluir |
| ` M` | `sri/services/electronic_document_signing_service.py` | Ajeno; no incluir |
| ` M` | `sri/services/sri_signer_factory.py` | Ajeno; no incluir |
| ` M` | `sri/services/sri_submission_service.py` | Ajeno; no incluir |
| ` M` | `sri/services/xml_generator_service.py` | Ajeno; no incluir |
| ` M` | `sri/services/xml_signing_service.py` | Ajeno; no incluir |
| ` M` | `sri/services/xml_validation_service.py` | Ajeno; no incluir |
| ` M` | `sri/storage.py` | Ajeno; no incluir |
| ` M` | `sri/templates/sri/electronic_document_authorization.html` | Ajeno; no incluir |
| ` M` | `sri/templates/sri/electronic_document_reception.html` | Ajeno; no incluir |
| ` M` | `sri/templates/sri/electronic_document_signing.html` | Ajeno; no incluir |
| ` M` | `sri/tests/authorization_domain_test_support.py` | Ajeno; no incluir |
| ` M` | `sri/tests/helpers/electronic_document_factory.py` | Ajeno; no incluir |
| ` M` | `sri/tests/helpers/invoice_factory.py` | Ajeno; no incluir |
| ` M` | `sri/tests/reception_test_support.py` | Ajeno; no incluir |
| ` M` | `sri/tests/test_electronic_document_authorization_concurrency.py` | Ajeno; no incluir |
| ` M` | `sri/tests/test_electronic_document_authorization_entrypoint.py` | Ajeno; no incluir |
| ` M` | `sri/tests/test_electronic_document_authorization_service.py` | Ajeno; no incluir |
| ` M` | `sri/tests/test_electronic_document_authorization_trigger.py` | Ajeno; no incluir |
| ` M` | `sri/tests/test_electronic_document_reception_trigger.py` | Ajeno; no incluir |
| ` M` | `sri/tests/test_electronic_document_signing_service.py` | Ajeno; no incluir |
| ` M` | `sri/tests/test_electronic_document_signing_trigger.py` | Ajeno; no incluir |
| ` M` | `sri/tests/test_electronic_invoice_service.py` | Ajeno; no incluir |
| ` M` | `sri/tests/test_sri_authorization_soap_adapter.py` | Ajeno; no incluir |
| ` M` | `sri/tests/test_sri_reception_soap_adapter.py` | Ajeno; no incluir |
| ` M` | `sri/tests/test_sri_submission_service.py` | Ajeno; no incluir |
| ` M` | `sri/tests/test_xml_generator_service.py` | Ajeno; no incluir |
| ` M` | `sri/tests/test_xml_signing_integration.py` | Ajeno; no incluir |
| ` M` | `sri/tests/test_xml_signing_service.py` | Ajeno; no incluir |
| ` M` | `sri/views.py` | Ajeno; no incluir |
| `??` | `core/testing/R05_REGRESION.md` | Ajeno; no incluir |
| `??` | `core/testing/R05_VALIDACION_SRI.md` | Ajeno; no incluir |
| `??` | `core/testing/R06_PREPARACION_SRI.md` | Ajeno; no incluir |
| `??` | `core/testing/r05_results.json` | Ajeno; no incluir |
| `??` | `sri/schemas/README.md` | Ajeno; no incluir |
| `??` | `sri/schemas/factura_V1.1.0.xsd` | Ajeno; no incluir |
| `??` | `sri/schemas/provenance.json` | Ajeno; no incluir |
| `??` | `sri/schemas/xmldsig-core-schema.xsd` | Ajeno; no incluir |
| `??` | `sri/services/invoice_fiscal_mapping.py` | Ajeno; no incluir |
| `??` | `sri/services/invoice_validation.py` | Ajeno; no incluir |
| `??` | `sri/templates/sri/attempt_messages.html` | Ajeno; no incluir |
| `??` | `sri/tests/r05_support.py` | Ajeno; no incluir |
| `??` | `sri/tests/test_human_workflow_r05.py` | Ajeno; no incluir |
| `??` | `sri/tests/test_invoice_security_r05.py` | Ajeno; no incluir |
| `??` | `sri/tests/test_invoice_xml_r04.py` | Ajeno; no incluir |

### UI Clientes previa / componentes compartidos

18 archivos.

| Estado | Archivo | Criterio |
|---|---|---|
| ` M` | `core/services/commercial/commercial_line_calculator.py` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| ` M` | `people/models/__init__.py` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| ` M` | `people/models/customer.py` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `core/testing/UI01_CLIENTES_CATEGORIA.md` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `core/testing/UI_CLIENTES_ACCIONES.md` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `core/testing/customer_ui_actions_results.json` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `people/commercial_forms.py` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `people/commercial_views.py` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `people/services/customer_continuation.py` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `people/services/ui_drafts.py` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `people/templates/people/commercial_activity.html` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `people/templates/people/commercial_detail.html` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `people/templates/people/commercial_form.html` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `people/templates/people/commercial_list.html` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `people/templates/people/customer_delete.html` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `people/tests/test_customer_person_replacement.py` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `people/tests/test_customer_ui_actions.py` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |
| `??` | `people/urls.py` | Dependencia: categorías, Personas, Proveedores y rutas GEO; no atribuir el archivo entero a CLIENTES-01 |

### UI Personas / D-02 / shell y archivos compartidos

72 archivos.

| Estado | Archivo | Criterio |
|---|---|---|
| ` M` | `config/settings.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| ` M` | `config/urls.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| ` M` | `core/middleware.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| ` M` | `core/models/company.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| ` M` | `core/templates/core/base.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| ` M` | `core/templates/core/dashboard.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| ` M` | `core/templates/core/login.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| ` M` | `core/templates/core/select_branch.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| ` M` | `core/templates/core/select_company.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| ` M` | `core/tests/test_document_service.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| ` M` | `core/urls.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| ` M` | `core/validators/access_validator.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| ` M` | `core/views.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| ` M` | `people/services/person_access_policy.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| ` M` | `people/views.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `config/settings_ui01_test.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/action_presentation.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/branch_forms.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/branch_views.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/company_forms.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/company_views.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/forms.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/related_fields.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/services/branch_maintenance.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/services/company_maintenance.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/services/initial_company_setup.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/setup_views.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/static/core/css/erp.css` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/static/core/icons/add.svg` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/static/core/icons/delete.svg` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/static/core/icons/edit.svg` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/static/core/icons/view.svg` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/static/core/js/form_help.js` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/templates/core/branch_form.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/templates/core/company_detail.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/templates/core/company_form.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/templates/core/components/README.md` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/templates/core/components/entity_action.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/templates/core/components/entity_fields.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/templates/core/components/form_fields.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/templates/core/components/related_control.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/templates/core/entity_base.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/templates/core/founding_person_edit.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/templates/core/initial_setup.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/testing/ui01_results.json` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/tests/test_administrative_bootstrap.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/tests/test_application_shell.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/tests/test_auth_navigation.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/tests/test_entity_company_person_d02a1_red.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/tests/test_form_ux_foundation_red.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/tests/test_founding_person_data.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/tests/test_html_contract_r04.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/tests/test_initial_company_setup_d02a_red.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `core/tests/test_post_company_branch_flow_d02a1_red.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/forms.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/management/__init__.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/management/commands/__init__.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/related_fields.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/services/contextual_person_creation.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/templates/people/components/catalog_navigation.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/templates/people/components/grouped_fields.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/templates/people/denied.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/templates/people/person_detail.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/templates/people/person_form.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/templates/people/person_list.html` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/tests/person_ui_support.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/tests/test_person_form_ui.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/tests/test_person_related_data_flow.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/tests/test_person_ui_navigation.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/tests/test_related_entity_actions_d02a1_red.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/tests/test_related_entity_continuation_security.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |
| `??` | `people/tests/test_sisadmi_action_language.py` | Clasificación funcional por ruta/dependencia; confirmar integración en su etapa |

### UI-01: categorías de clientes

13 archivos.

| Estado | Archivo | Criterio |
|---|---|---|
| `??` | `core/testing/UI01_CATEGORIAS_CLIENTES.md` | Prerrequisito anterior; no modificado por CLIENTES-01 |
| `??` | `core/testing/customer_category_assignment_results.json` | Prerrequisito anterior; no modificado por CLIENTES-01 |
| `??` | `people/customer_category_forms.py` | Prerrequisito anterior; no modificado por CLIENTES-01 |
| `??` | `people/customer_category_views.py` | Prerrequisito anterior; no modificado por CLIENTES-01 |
| `??` | `people/migrations/0007_customer_category.py` | Prerrequisito anterior; no modificado por CLIENTES-01 |
| `??` | `people/migrations/0008_customer_category_assignment.py` | Prerrequisito anterior; no modificado por CLIENTES-01 |
| `??` | `people/models/customer_category.py` | Prerrequisito anterior; no modificado por CLIENTES-01 |
| `??` | `people/templates/people/customer_category_activity.html` | Prerrequisito anterior; no modificado por CLIENTES-01 |
| `??` | `people/templates/people/customer_category_detail.html` | Prerrequisito anterior; no modificado por CLIENTES-01 |
| `??` | `people/templates/people/customer_category_form.html` | Prerrequisito anterior; no modificado por CLIENTES-01 |
| `??` | `people/templates/people/customer_category_list.html` | Prerrequisito anterior; no modificado por CLIENTES-01 |
| `??` | `people/tests/test_customer_category_assignment.py` | Prerrequisito anterior; no modificado por CLIENTES-01 |
| `??` | `people/tests/test_customer_category_ui01.py` | Prerrequisito anterior; no modificado por CLIENTES-01 |

### Ventas / Compras / Inventario: R-04 y CAT-02.3 compartidos

33 archivos.

| Estado | Archivo | Criterio |
|---|---|---|
| ` M` | `inventory/models/stock_movement.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `inventory/tests/sales_return_test_support.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `inventory/tests/test_context_integrity.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `inventory/tests/test_inventory_purchase.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `inventory/tests/test_kardex.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `inventory/tests/test_stock_movement.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `purchases/services/purchase_confirmation_service.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `purchases/services/purchase_creator.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `purchases/services/purchase_service.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `purchases/tests/purchase_manifest_test_support.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `purchases/tests/purchase_return_test_support.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `purchases/tests/test_cancel_purchase.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `purchases/tests/test_confirm_purchase.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `purchases/tests/test_create_purchase.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `purchases/tests/test_inventory_receipt.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `purchases/validators/purchase_validator.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `sales/forms.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `sales/services/sale_confirmation_service.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `sales/services/sale_validator.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `sales/templates/sales/sale_detail.html` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `sales/tests/sale_manifest_test_support.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `sales/tests/test_cancel_sale.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `sales/tests/test_confirm_sale.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `sales/tests/test_create_sale.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `sales/tests/test_fiscal_workflow_navigation.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `sales/tests/test_sale_application_trigger.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `sales/tests/test_sale_detail_tax.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `sales/tests/test_sale_fiscal_preparation_trigger.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `sales/use_cases/create_sale.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| ` M` | `sales/views.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| `??` | `inventory/migrations/0012_alter_stockmovement_unit_cost.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| `??` | `purchases/tests/test_purchase_decimal_totals.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |
| `??` | `sales/tests/test_payment_method_r04.py` | Dependencias de integración; atribución funcional orientativa, revisar aparte |

## Seguridad y artefactos

Comprobación estática por patrones y estructuras, sin imprimir valores: no se detectaron
archivos de credenciales/certificados privados, bloques PEM privados, URLs autenticadas
ni campos JSON de secretos no vacíos en los candidatos CLIENTES. Los literales de contraseña
localizados en el inventario corresponden a fixtures/placeholders de pruebas; no son la credencial temporal.
Esto no sustituye una auditoría exhaustiva de todos los secretos posibles.
Las constantes sensibles compartidas de config/settings.py no cambian respecto de HEAD.
Las evidencias finales contienen SQL, PIDs, fechas, PK internas y huellas, sin nombres o identificaciones personales reales.
No se copian .env, certificados, .pgpass, bases, .venv, logs de ejecución o credenciales de /run/user.
Los informes intermedios fallidos se conservan aparte y se excluyen del commit mínimo propuesto; no se eliminan.
Los CSV/PDF y respaldos geográficos de otras etapas no se incorporan a CLIENTES.
Las referencias `/tmp` de los informes son evidencia auxiliar efímera, no garantía de conservación a largo plazo.
El artefacto final persistente y el cierre tienen precedencia al interpretar resultados actuales.

## Mensajes propuestos (no ejecutados)

Funcional, solo después de integrar prerrequisitos:

`fix(clientes): serializar mantenimiento y aislar regresión PostgreSQL`

Cierre documental independiente:

`docs(clientes): cerrar CLIENTES-01 con evidencia de 66 pruebas aprobadas`

No hubo stage, commit, push, cambio de rama, reset, limpieza ni alteración de otros archivos.
