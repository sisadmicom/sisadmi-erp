# GEO-01 — Informe para aprobación

Fuente histórica de 2016; no representa una actualización automática a la división territorial actual. No se ha ejecutado carga real.

## Archivos verificables

- `ecuador_2016.csv`: UTF-8, 1.398 filas originales; incluye repeticiones y código 90, sin correcciones de nombres.
- `source_report.json`: procedencia, duplicados, equivalencias y ambigüedades.
- `parishes_by_canton.csv`: inventario completo de parroquias distintas por provincia y cantón; incluye las tres entradas de código 90 identificadas separadamente.
- `verification.json`: contraste de 1.397 filas con cuatro celdas y una fila de celdas fusionadas; cero discrepancias finales.
- `development_dry_run.json`: plan de solo lectura vinculado a CSV, base y snapshot.
- `development_audit.json`: registros geográficos existentes, sin cambios respecto al snapshot del dry-run.
- `model_contract.json`: campos, longitudes, obligatoriedad, unicidad y relaciones reales.

## Resultado de extracción

- 20 páginas; 1.398 filas, 1.367 combinaciones distintas provincia/cantón/parroquia.
- 24 provincias; 221 cantones y 1.364 combinaciones provinciales distintas de parroquia.
- Código 90: 3 entradas adicionales de zonas no delimitadas; no se convierten automáticamente en Province.
- 31 grupos repetidos, cada uno con una fila adicional. El CSV fuente conserva ambas; la futura importación deduplica por la cadena completa.
- Longitudes máximas: Province 30, Canton 32, Parish 57; límite real 100. Cero excesos y cero campos vacíos.
- Código provincial se conserva solo en CSV: Province no tiene ese campo. Sin cambios de schema.

## Provincias encontradas

| Código | Nombre original | Cantones distintos | Parroquias distintas por cantón, sumadas |
|---|---|---:|---:|
| 01 | AZUAY | 15 | 103 |
| 02 | BOLIVAR | 7 | 32 |
| 03 | CAÑAR | 7 | 40 |
| 04 | CARCHI | 6 | 39 |
| 05 | COTOPAXI | 7 | 52 |
| 06 | CHIMBORAZO | 10 | 65 |
| 07 | EL ORO | 14 | 87 |
| 08 | ESMERALDAS | 8 | 81 |
| 09 | GUAYAS | 25 | 93 |
| 10 | IMBABURA | 6 | 52 |
| 11 | LOJA | 16 | 112 |
| 12 | LOS RIOS | 13 | 51 |
| 13 | MANABI | 22 | 109 |
| 14 | MORONA SANTIAGO | 12 | 72 |
| 15 | NAPO | 5 | 29 |
| 16 | PASTAZA | 4 | 24 |
| 17 | PICHINCHA | 8 | 103 |
| 18 | TUNGURAHUA | 9 | 64 |
| 19 | ZAMORA CHINCHIPE | 9 | 46 |
| 20 | GALAPAGOS | 3 | 8 |
| 21 | SUCUMBIOS | 7 | 38 |
| 22 | ORELLANA | 4 | 34 |
| 23 | SANTO DOMINGO DE LOS TSACHILAS | 1 | 14 |
| 24 | SANTA ELENA | 3 | 16 |

## Repeticiones exactas

| Provincia | Cantón | Parroquia original | Página/fila |
|---|---|---|---|
| BOLIVAR | GUARANDA | GUANUJO | 2/37; 2/40 |
| BOLIVAR | LAS NAVES | LAS NAVES | 2/67; 2/68 |
| CAÑAR | AZOGUES | AZOGUES | 2/70; 3/2 |
| CARCHI | TULCÁN | TULCÁN | 3/40; 3/41 |
| COTOPAXI | LA MANÁ | LA MANÁ | 4/28; 4/30 |
| EL ORO | MACHALA | MACHALA | 5/56; 5/60 |
| EL ORO | MACHALA | EL CAMBIO | 5/59; 5/61 |
| EL ORO | SANTA ROSA | SANTA ROSA | 6/45; 6/50 |
| EL ORO | LAS LAJAS | LA VICTORIA | 6/68; 6/71 |
| ESMERALDAS | ESMERALDAS | ESMERALDAS | 7/6; 7/9 |
| GUAYAS | GUAYAQUIL | PASCUALES | 8/29; 8/34 |
| GUAYAS | DAULE | DAULE | 8/44; 8/52 |
| GUAYAS | DURÁN | ELOY ALFARO (DURÁN) | 8/60; 8/62 |
| GUAYAS | SAMBORONDÓN | SAMBORONDÓN | 9/11; 9/13 |
| IMBABURA | ANTONIO ANTE | ATUNTAQUI | 9/55; 9/56 |
| LOJA | CALVAS | CARIAMANGA | 10/41; 10/44 |
| LOJA | PALTAS | CATACOCHA | 11/19; 11/21 |
| LOS RIOS | QUEVEDO | QUEVEDO | 12/12; 12/22 |
| LOS RIOS | BUENA FÉ | SAN JACINTO DE BUENA FÉ | 12/40; 12/43 |
| MANABI | PORTOVIEJO | PORTOVIEJO | 12/48; 12/57 |
| MANABI | EL CARMEN | EL CARMEN | 13/6; 13/8 |
| MANABI | MANTA | MANTA | 13/29; 13/33 |
| MANABI | MONTECRISTI | MONTECRISTI | 13/37; 13/41 |
| MANABI | SUCRE | BAHÍA DE CARÁQUEZ | 13/61; 13/63 |
| MORONA SANTIAGO | GUALAQUIZA | GUALAQUIZA | 14/35; 14/37 |
| PICHINCHA | CAYAMBE | CAYAMBE | 17/4; 17/6 |
| TUNGURAHUA | SAN PEDRO DE PELILEO | PELILEO | 18/9; 18/11 |
| TUNGURAHUA | SANTIAGO DE PÍLLARO | PÍLLARO | 18/21; 18/22 |
| ZAMORA CHINCHIPE | ZAMORA | ZAMORA | 18/33; 18/34 |
| SANTO DOMINGO DE LOS TSACHILAS | SANTO DOMINGO | SANTO DOMINGO DE LOS COLORADOS | 20/22; 20/24 |
| SANTA ELENA | SANTA ELENA | SANTA ELENA | 20/33; 20/34 |

## Decisiones de datos pendientes

La carga está bloqueada hasta resolver estos hallazgos explícitamente. No se completaron nombres ni se eligió una variante automáticamente.

- Equivalencia en 04 / CARCHI / ESPEJO: EL ANGEL ↔ EL ÁNGEL.
- Equivalencia en 17 / PICHINCHA / RUMIÑAHUI: SANGOLQUI ↔ SANGOLQUÍ.
- Posible variante tipográfica en 22 / ORELLANA / AGUARICO: TIPITINI ↔ TIPUTINI; no se presume identidad.
- unbalanced_parentheses: 05 / COTOPAXI / LA MANÁ / GUASAGANDA (CAB.EN GUASAGANDA (página 4, fila 31).
- unbalanced_parentheses: 10 / IMBABURA / COTACACHI / VACAS GALINDO (EL CHURO) (CAB.EN SAN MIGUEL ALTO (página 9, fila 71).
- unbalanced_parentheses: 13 / MANABI / FLAVIO ALFARO / SAN FRANCISCO DE NOVILLO (CAB. EN (página 13, fila 12).
- unbalanced_parentheses: 14 / MORONA SANTIAGO / LIMÓN INDANZA / SAN ANTONIO (CAB. EN SAN ANTONIO CENTRO (página 14, fila 49).
- unbalanced_parentheses: 14 / MORONA SANTIAGO / LIMÓN INDANZA / SAN CARLOS DE LIMÓN (SAN CARLOS DEL (página 14, fila 50).
- unbalanced_parentheses: 22 / ORELLANA / ORELLANA / NUEVO PARAÍSO (CAB. EN UNIÓN (página 19, fila 63).
- non_province_code: 90 / ZONAS NO DELIMITADAS / LAS GOLONDRINAS / LAS GOLONDRINAS (página 20, fila 49).
- non_province_code: 90 / ZONAS NO DELIMITADAS / MANGA DEL CURA / MANGA DEL CURA (página 20, fila 50).
- non_province_code: 90 / ZONAS NO DELIMITADAS / EL PIEDRERO / EL PIEDRERO (página 20, fila 51).

## Registros existentes y conflictos

America → ECUADOR (código 593) → MANABI → PORTOVIEJO → RIOCHICO / SAN ALEJO permanece íntegro. America/América y ECUADOR/Ecuador se reconocen como coincidencias equivalentes únicas, conservando la escritura y el código almacenados.

Conflicto: RIOCHICO (RÍO CHICO), página 12 fila 62, posiblemente corresponde al RIOCHICO existente. No se crea duplicado, no se renombra ni se asocia por suposición. SAN ALEJO, bajo PORTOVIEJO, no tiene coincidencia en esta fuente y se conserva.

## Dry-run

| Entidad | Existentes coincidentes | Proyección de nuevos | Creados realmente |
|---|---:|---:|---:|
| Continent | 1 | 0 | 0 |
| Country | 1 | 0 | 0 |
| Province | 1 | 23 | 0 |
| Canton | 1 | 220 | 0 |
| Parish | 0 | 1361 | 0 |

**Resultado: BLOQUEADO.** Las proyecciones son provisionales; no autorizan cargar filas ambiguas. Dos parroquias existentes permanecen intactas: RIOCHICO requiere resolver el posible alias; SAN ALEJO queda fuera de las coincidencias del PDF.

## Comandos e integridad

```bash
.venv/bin/python manage.py prepare_ecuador_geography --pdf /home/sisadmi/workspace/sisadmi-erp/CENSO_2016_TTHH_Listado_prov-cantones-parroquias.pdf --csv data/geo01/ecuador_2016.csv --report data/geo01/source_report.json
.venv/bin/python manage.py import_ecuador_geography --csv data/geo01/ecuador_2016.csv --dry-run --report data/geo01/development_dry_run.json
.venv/bin/python manage.py test people.tests.test_geo01_import --noinput
```

El importador exige un modo explícito. La futura opción `--apply` exige `--approved-plan` obtenido de un dry-run, sin cambios de contenido ni snapshot. Un plan bloqueado no puede aplicarse. No se ejecutó esa opción en desarrollo.

Las escrituras futuras se limitan a los cinco modelos geográficos, mediante Django ORM y una transacción atómica. Se validan nuevas instancias con full_clean; nunca se actualizan ni eliminan registros existentes. Las relaciones se resuelven por padre autorizado en el plan y nombre. No hay SQL directo, Admin ni efectos operativos.

Las tablas geográficas se bloquean en orden fijo al aplicar; Country.code único protege también la contención durante la primera creación. Province/Canton/Parish no tienen unicidad de nombre en schema: no se añaden restricciones ni migraciones. Un cambio externo invalida el plan y requiere nuevo dry-run.

La extracción usa Poppler `pdftotext`, ya instalado; no se agregaron dependencias Python. El parser está acotado a la estructura de este documento; otros formatos deben verificarse antes de reutilizarlo.

15/15 tests aislados PASS: parser, CSV UTF-8, duplicados, relaciones, conservación, colisiones, longitudes, idempotencia, aprobación obsoleta y rollback. check, makemigrations --check --dry-run, pip check y git diff --check correctos. No se ejecutó suite completa: se respetó la instrucción de tests aislados.

## Trazabilidad

- PDF SHA256: `f7cbf23e1427da5f0fae6f354abcd4d5ce75ac63c7b81e114136cb991819d617`
- CSV SHA256: `8a5ee6152635567c3cb2e7f5c6c8c0ec5e329a6ab10808376428a3190c6c5fb2`
- Base: `sisadmi_erp_dev`; snapshot sin cambios comprobado: `True`.

No se modificaron modelos, migraciones, permisos ni entidades operativas. No stage, commit ni push. La siguiente puerta es la aprobación de las decisiones de datos y del CSV preparado para una carga posterior.
