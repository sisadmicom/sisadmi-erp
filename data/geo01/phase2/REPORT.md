# GEO-01 Fase 2: importación parcial preparada

**Estado: AWAITING EXECUTION AUTHORIZATION. No se ha ejecutado carga real.**

Se utiliza el plan aprobado de Fase 1. El subconjunto canónico UTF-8 contiene
1.354 filas parroquiales con trazabilidad hacia las 1.398 filas originales.
No se modifican los CSV, REPORT.md ni los archivos de Fase 1.

## Operaciones proyectadas contra sisadmi_erp_dev

| Entidad | CREATE | REUSE | Existentes ajenos al subconjunto conservados | Total proyectado en base |
|---|---:|---:|---:|---:|
| Continent | 0 | 1 | 0 | 1 |
| Country | 0 | 1 | 0 | 1 |
| Province | 23 | 1 | 0 | 24 |
| Canton | 220 | 1 | 0 | 221 |
| Parish | 1353 | 1 | 1 | 1355 |

CREATE: **1.596 entidades**. REUSE: **5 entidades**. CONFLICT: **0**.
SKIP: **44 filas de origen**, unidad distinta de las entidades anteriores:
31 duplicados exactos, 2 equivalencias consolidadas y 11 filas pendientes.
`operations.json` enumera cada operación con entidad, nombre, ruta contextual
o referencia original de página/fila y decisión. `lineage.json` conserva cada
fila original exactamente una vez, incluyendo las filas consolidadas.

## Resoluciones conservadas

- CARCHI / ESPEJO: EL ÁNGEL.
- PICHINCHA / RUMIÑAHUI: SANGOLQUÍ.
- MANABI / PORTOVIEJO: reutilización de RIOCHICO existente, sin renombrarlo.
- Se reutilizan America y ECUADOR tal como están almacenados (código 593),
  además de MANABI y PORTOVIEJO. No se cambian sus nombres o relaciones.
- SAN ALEJO existente queda intacta, aunque no pertenece al subconjunto.

## Exclusiones temporales: 10 casos, 11 filas

| Caso | Provincia / cantón | Referencia PDF |
|---|---|---|
| TIPITINI / TIPUTINI, sin equivalencia probada | ORELLANA / AGUARICO | p19 f66 y f71 |
| GUASAGANDA, anotación truncada | COTOPAXI / LA MANÁ | p4 f31 |
| VACAS GALINDO, anotación truncada | IMBABURA / COTACACHI | p9 f71 |
| SAN FRANCISCO DE NOVILLO, anotación truncada | MANABI / FLAVIO ALFARO | p13 f12 |
| SAN ANTONIO, anotación truncada | MORONA SANTIAGO / LIMÓN INDANZA | p14 f49 |
| SAN CARLOS DE LIMÓN, anotación truncada | MORONA SANTIAGO / LIMÓN INDANZA | p14 f50 |
| NUEVO PARAÍSO, anotación truncada | ORELLANA / ORELLANA | p19 f63 |
| Código 90: LAS GOLONDRINAS | ZONAS NO DELIMITADAS | p20 f49 |
| Código 90: MANGA DEL CURA | ZONAS NO DELIMITADAS | p20 f50 |
| Código 90: EL PIEDRERO | ZONAS NO DELIMITADAS | p20 f51 |

Se conserva la evidencia de Fase 1 en `pending_exceptions.json`: sus menciones
al bloqueo global corresponden al plan original, que sigue bloqueado.
La decisión humana de Fase 2 autoriza únicamente preparar este subconjunto;
no resuelve los casos pendientes ni autoriza ejecutar la carga.

Las 24 provincias y los 221 cantones válidos de códigos 01–24 permanecen
representados. Ninguna exclusión parroquial pierde padres válidos.
Las tres agrupaciones código 90 quedan excluidas conforme a su revisión.

## Dry-run e idempotencia

Ejecución realizada exclusivamente en modo dry-run:

```bash
.venv/bin/python manage.py import_ecuador_geography \
  --csv data/geo01/phase2/ecuador_2016_partial.csv --dry-run \
  --report data/geo01/phase2/dry_run.json --simulate-repeat \
  --simulation-report data/geo01/phase2/repeat_simulation.json
```

Resultado: cero conflictos, ambigüedades o variantes pendientes en el
subconjunto. `blocked=false` significa que los datos son técnicamente aptos;
**no constituye autorización humana de ejecución**.
La segunda planificación usa exclusivamente una proyección en memoria:
CREATE = 0 en las cinco entidades. No se usa una carga real ni siquiera con
rollback para simular la idempotencia.

La futura importación reutilizará el comando ORM existente, su transacción
atómica, validación del plan aprobado y revalidación de la base. No hay
actualizaciones, eliminaciones ni escrituras en entidades operativas.
Cualquier cambio de base o nuevas discrepancias exige repetir el dry-run y
obtener autorización; no debe utilizarse un plan obsoleto.

## Integridad y verificaciones

La auditoría ORM antes/después contiene exactamente los mismos seis registros:
1 continente, 1 país, 1 provincia, 1 cantón y 2 parroquias.
SHA256 del snapshot: `e7fa0ab594e9f3d0cf0004299f1eea26aacb2e3650fcc26e02f52241f14095bd`.
`verification.json` registra ambas capturas y los hashes de todos los
artefactos protegidos de Fases 0 y 1. Escrituras reales: **0**.

SHA256 CSV parcial:
`07f80efd52a70964d2795f016d9eb3d220f7e3eaca431bda95c84e482c70f2cc`.

Tests aislados: **28/28 PASS** (15 importador, 10 decisiones, 3 subconjunto).
`manage.py check`: sin incidencias.
`makemigrations --check --dry-run`: sin cambios.
`migrate --plan`: sin operaciones pendientes.
`pip check`: sin dependencias rotas.
`git diff --check`: PASS.
No se repite la suite global: esta fase añade únicamente artefactos de
preparación y tests; el resultado global previo consta en Fase 1.

Cambios de esta fase: directorio `data/geo01/phase2/` y
`people/tests/test_geo01_partial.py`. No se modificó producción, modelos,
migraciones, permisos ni procesos operativos. El árbol conserva los cambios
anteriores del usuario. HEAD y origin/main local:
`e5c4c6cec2f410772dfbe7eb434bf3932b895692`. Sin stage, commit ni push.
