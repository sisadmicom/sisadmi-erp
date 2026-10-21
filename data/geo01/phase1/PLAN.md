# GEO-01 FASE 1 — Plan definitivo para aprobación

**Preparación completa; importación real no autorizada. El plan sigue bloqueado por 10 casos pendientes que abarcan 11 filas.**

## Fuente y conservación

Los ocho archivos de Fase 0, incluidos ambos CSV y REPORT.md, permanecen byte por byte intactos. Sus SHA256 se conservan en `original_artifact_hashes.json`. Este plan utiliza el CSV original y un archivo separado de decisiones; no genera ni carga una copia silenciosamente corregida.

- PDF SHA256: `f7cbf23e1427da5f0fae6f354abcd4d5ce75ac63c7b81e114136cb991819d617`.
- CSV original SHA256: `8a5ee6152635567c3cb2e7f5c6c8c0ec5e329a6ab10808376428a3190c6c5fb2`.
- Base del dry-run: `sisadmi_erp_dev`.

## Resoluciones verificadas

| Caso | Contexto confirmado | Decisión | Evidencia |
|---|---|---|---|
| EL ANGEL / EL ÁNGEL | 04 · CARCHI · ESPEJO | Consolidar como EL ÁNGEL para el registro nuevo | PDF página 3, filas 59 y 61; imagen y celdas verificadas. Solo cambia la tilde; la grafía elegida ya está en la fuente. |
| SANGOLQUI / SANGOLQUÍ | 17 · PICHINCHA · RUMIÑAHUI | Consolidar como SANGOLQUÍ para el registro nuevo | PDF página 17, filas 25 y 28; imagen y celdas verificadas. Solo cambia la tilde; la grafía elegida ya está en la fuente. |
| RIOCHICO (RÍO CHICO) / RIOCHICO | 13 · MANABI · PORTOVIEJO · ECUADOR (593) · America | Reutilizar Parish existente, conservando RIOCHICO | PDF página 12, fila 62, y auditoría ORM del objeto y toda su cadena. Nombre base coincidente y alias explícito en la fuente. |

Las equivalencias son identidades nominales bajo el mismo padre dentro del modelo actual. El PDF no aporta un código parroquial; se conserva cada fila original para mantener su contexto y evitar perder información del listado histórico. No se renombra ningún registro existente.

## Excepciones que requieren decisión humana

Las filas se excluyen temporalmente del subconjunto candidato, pero permanecen en revisión. Esta exclusión no resuelve el conflicto ni autoriza una carga parcial. El bloqueo global se conserva en la primera y la segunda planificación.

| Caso | Contexto | Filas | Motivo |
|---|---|---|---|
| TIPITINI / TIPUTINI | 22 · ORELLANA · AGUARICO | 19/66, 19/71 | PDF página 19 filas 66 y 71, ORELLANA / AGUARICO. Difieren en una vocal; no hay código parroquial ni evidencia suficiente para afirmar identidad. Ambas filas quedan fuera del subconjunto elegible y mantienen el bloqueo global. |
| GUASAGANDA (CAB.EN GUASAGANDA | 05 · COTOPAXI · LA MANÁ | 4/31 | Anotación truncada en la fuente; no se completa ni se inventa el nombre. |
| VACAS GALINDO (EL CHURO) (CAB.EN SAN MIGUEL ALTO | 10 · IMBABURA · COTACACHI | 9/71 | Anotación truncada en la fuente; no se completa ni se inventa el nombre. |
| SAN FRANCISCO DE NOVILLO (CAB. EN | 13 · MANABI · FLAVIO ALFARO | 13/12 | Anotación truncada en la fuente; no se completa ni se inventa el nombre. |
| SAN ANTONIO (CAB. EN SAN ANTONIO CENTRO | 14 · MORONA SANTIAGO · LIMÓN INDANZA | 14/49 | Anotación truncada en la fuente; no se completa ni se inventa el nombre. |
| SAN CARLOS DE LIMÓN (SAN CARLOS DEL | 14 · MORONA SANTIAGO · LIMÓN INDANZA | 14/50 | Anotación truncada en la fuente; no se completa ni se inventa el nombre. |
| NUEVO PARAÍSO (CAB. EN UNIÓN | 22 · ORELLANA · ORELLANA | 19/63 | Anotación truncada en la fuente; no se completa ni se inventa el nombre. |
| LAS GOLONDRINAS | 90 · ZONAS NO DELIMITADAS · LAS GOLONDRINAS | 20/49 | Código 90 ZONAS NO DELIMITADAS; no se convierte en provincia ni se asigna territorio sin decisión humana. |
| MANGA DEL CURA | 90 · ZONAS NO DELIMITADAS · MANGA DEL CURA | 20/50 | Código 90 ZONAS NO DELIMITADAS; no se convierte en provincia ni se asigna territorio sin decisión humana. |
| EL PIEDRERO | 90 · ZONAS NO DELIMITADAS · EL PIEDRERO | 20/51 | Código 90 ZONAS NO DELIMITADAS; no se convierte en provincia ni se asigna territorio sin decisión humana. |

El usuario debe decidir sobre TIPITINI/TIPUTINI, las seis anotaciones truncadas y las tres entradas de código 90. No se completa texto faltante, no se infiere equivalencia entre vocales distintas y no se asignan zonas no delimitadas a provincias.

## Cantidades exactas del subconjunto elegible

| Entidad | Existentes reutilizados | Registros nuevos propuestos | Creados realmente |
|---|---:|---:|---:|
| Continent | 1 | 0 | 0 |
| Country | 1 | 0 | 0 |
| Province | 1 | 23 | 0 |
| Canton | 1 | 220 | 0 |
| Parish | 1 | 1353 | 0 |
| **TOTAL** | **5** | **1596** | **0** |

- Filas originales: **1.398**.
- Repeticiones exactas consolidadas: **31**; todas sus referencias se conservan.
- Filas adicionales consolidadas por equivalencias verificadas: **2**.
- Filas excluidas temporalmente del subconjunto: **11**, en **10 casos pendientes**.
- Identidades parroquiales elegibles: **1.354** = 1.398 − 31 − 2 − 11.
- Conflictos de identidad con registros existentes después de resolver RIOCHICO: **0**.
- Análisis del subconjunto elegible: cero ambigüedades, cero equivalencias pendientes y cero variantes tipográficas pendientes. Las revisiones se registran aparte y siguen bloqueando la carga.

SAN ALEJO permanece intacta en PORTOVIEJO, aunque no se utiliza en el listado fuente. La proyección completa conserva esa parroquia adicional: Province 24, Canton 221 y Parish 1.355, con Continent 1 y Country 1. Estas son cifras hipotéticas, no registros cargados.

## Trazabilidad

`source_lineage.csv` y `source_lineage.json` relacionan las 1.398 filas originales con su identidad elegible o caso en revisión. No falta ni se repite ninguna referencia página/fila. `decisions_table.csv` contiene 44 entradas: las 13 decisiones explícitas y las 31 consolidaciones exactas. `entity_counts.csv` separa reutilizados, nuevos, existentes no involucrados y creados realmente.

## Dry-run e idempotencia

```bash
.venv/bin/python manage.py import_ecuador_geography --csv data/geo01/ecuador_2016.csv --decisions data/geo01/phase1/import_decisions.json --dry-run --simulate-repeat --report data/geo01/phase1/development_plan.json --simulation-report data/geo01/phase1/repeat_simulation.json
```

El primer dry-run propone 23 provincias, 220 cantones y 1.353 parroquias; reutiliza cinco registros. No realizó escrituras ORM.

La segunda planificación utiliza una proyección exclusivamente en memoria del subconjunto elegible. Propone **0 nuevos registros en las cinco entidades**. Mantiene `blocked: true` por las diez revisiones. La simulación no ejecuta INSERT/UPDATE/DELETE, no utiliza transacciones con rollback para escribir en desarrollo y no reserva IDs de PostgreSQL.

## Garantías de futura ejecución

- Se mantienen la transacción atómica y los bloqueos ORM de la infraestructura de Fase 0.
- La aplicación exige el mismo plan previo, los mismos datos y decisiones y el mismo snapshot. Cambios invalidan la aprobación anterior.
- Las decisiones equivalentes requieren código, provincia y cantón idénticos y una grafía ya presente.
- La reutilización verifica ID, nombre y cadena completa del objeto existente, además de nombre base, provincia y cantón de origen. No puede sustituirse por otro objeto o ubicación.
- Una revisión pendiente sigue bloqueando toda aplicación; quitarla sin resolver el dato deja el conflicto detectable en el análisis del subconjunto.
- Los nombres y relaciones existentes no se actualizan ni se eliminan. No hay cambios de modelos, migraciones, permisos ni entidades operativas.

## Archivos de implementación y pruebas

- Adaptados: `people/services/geography_catalog_import.py` y `people/management/commands/import_ecuador_geography.py`.
- Nuevos: `people/services/geography_import_decisions.py`, `people/tests/test_geo01_decisions.py` y los artefactos de `data/geo01/phase1/`.
- Tests específicos: **25/25 PASS** (15 de Fase 0 y 10 nuevos).
- `manage.py check`, `makemigrations --check --dry-run`, `migrate --plan`, `pip check` y `git diff --check`: correctos; sin cambios ni migraciones pendientes.
- Suite completa: **1.213 tests; 89 fallos y 4 errores conocidos**, idénticos a la línea base. **Cero regresiones inesperadas**.
- Base geográfica y ocho archivos originales: **intactos**; auditoría final verificada.
- La auditoría final y la clasificación de regresión se conservan en `final_audit.json` y `regression_result.json`.

No stage, commit ni push. La siguiente puerta es la decisión humana sobre las diez revisiones y la autorización explícita de una importación posterior.
