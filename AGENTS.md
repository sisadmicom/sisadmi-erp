# SISADMI ERP — Reglas de trabajo para Codex

## Objetivo

SISADMI ERP es un ERP modular, multiempresa, multiusuario y multisucursal,
orientado a Ecuador y preparado para integración SRI.

La prioridad del proyecto es:
- arquitectura clara;
- seguridad;
- mantenibilidad;
- trazabilidad;
- pruebas;
- evolución incremental sin romper módulos existentes.

## Regla principal

Codex ejecuta tareas de implementación.

No debe rediseñar la arquitectura por iniciativa propia.

Si una tarea requiere cambiar una decisión arquitectónica existente,
debe detenerse y explicar el impacto antes de modificar código.

## Base tecnológica

- Python 3.12
- Django 5.2.x
- PostgreSQL es la base de datos oficial
- entorno virtual `.venv`
- no usar SQLite como alternativa funcional
- no agregar dependencias sin justificación técnica explícita

## Git

- rama estable: `main`
- no hacer commit automáticamente
- no hacer push automáticamente
- no modificar historial Git
- no hacer reset destructivo
- no borrar cambios del usuario
- antes de finalizar una tarea mostrar o revisar `git diff`
- mantener cambios pequeños y relacionados con la tarea solicitada

## Migraciones Django

- no borrar migraciones existentes para resolver problemas
- no recrear el historial de migraciones
- generar solo las migraciones estrictamente necesarias
- revisar las migraciones generadas antes de aplicarlas
- para cambios con datos existentes usar migraciones seguras y progresivas
- usar `apps.get_model()` en migraciones de datos
- ejecutar al finalizar:

  python manage.py makemigrations --check --dry-run

## Pruebas

Las tareas funcionales deben seguir preferentemente:

1. inspeccionar código existente
2. escribir o ajustar pruebas que expresen el contrato
3. comprobar el fallo esperado
4. implementar el cambio mínimo
5. ejecutar pruebas afectadas
6. ejecutar `python manage.py check`
7. ejecutar `python manage.py makemigrations --check --dry-run`
8. revisar `git diff`

Antes del cierre de una etapa importante:
- ejecutar la suite completa con `python manage.py test`
- ejecutar `python -m pip check`

Los tests no deben depender de datos casuales de una base de desarrollo,
IDs fijos ni del orden de ejecución.

## Arquitectura documental

Principio:

"Reutilizar lo estable y especializar lo variable."

Un Documento SISADMI es una entidad de negocio persistente,
perteneciente a una empresa y un contexto operativo,
identificable y auditable, con ciclo de vida propio
y capacidad de relacionarse con otros documentos u operaciones.

No asumir que todo documento:
- tiene productos;
- tiene cantidades;
- tiene precios;
- tiene impuestos;
- tiene totales;
- afecta inventario;
- genera contabilidad;
- genera SRI;
- tiene detalles.

`BaseDocument` debe contener solo infraestructura documental transversal.

No introducir lógica de inventario, contabilidad o SRI dentro de BaseDocument.

No crear mega-modelos ni mega-servicios con lógica de múltiples dominios.

## Estados

El estado documental transversal mínimo es:

- DRAFT
- CONFIRMED
- CANCELLED

Los estados comerciales, operativos, de inventario,
contables y SRI son responsabilidades separadas.

No mezclar estado comercial con estado fiscal.

## DocumentType

`DocumentType` es un catálogo persistente de CORE.

Define identidad y capacidades estructurales del tipo documental.

Actualmente incluye:

- code
- name
- category
- requires_detail
- affects_inventory
- inventory_behavior
- can_issue_electronic
- is_active heredado de BaseModel

`DocumentType` define qué reglas aplican.

Los servicios de dominio definen cómo se ejecutan.

El tipo documental:
- debe almacenarse en cada documento concreto;
- no debe ser seleccionable por el usuario;
- no debe venir desde DTOs;
- debe ser determinado por el modelo o servicio de dominio.

Tipos iniciales:

- SALES_INVOICE
- PURCHASE_INVOICE
- INVENTORY_TRANSFER

No dispersar strings de códigos documentales innecesariamente por el código.

## Multiempresa y sucursal

Toda operación documental nace en una Branch.

Company define el ámbito jurídico y organizacional.

Branch define el ámbito operativo.

Cuando un modelo almacena `company` y `branch`,
debe respetarse:

`branch.company == company`

No eliminar `company` de modelos existentes sin análisis previo
de aislamiento, seguridad, consultas, índices y migraciones.

## Secuencias

La numeración interna ERP y la numeración fiscal SRI
son responsabilidades distintas.

`Sequence` pertenece al mecanismo interno ERP.

Dirección arquitectónica aprobada:

una secuencia por:
- company
- branch
- document_type

No derivar numeración fiscal desde `document.number`.

No mezclar secuencias SRI dentro de CORE.

## SRI

Regla crítica:

El documento comercial NO es el documento SRI.

Flujo conceptual:

Sale / documento comercial
    -> ElectronicDocument
    -> XML
    -> firma
    -> envío
    -> autorización SRI

Toda lógica relacionada con:
- XML;
- certificados;
- PKCS#12;
- XAdES;
- claves de acceso;
- envío;
- autorización;
- estados SRI;

debe permanecer en el módulo `sri`.

Nunca introducir lógica SRI dentro de `sales`,
`purchases` o `BaseDocument`.

`can_issue_electronic` significa que un DocumentType
puede originar un ElectronicDocument emitido por SISADMI.

No significa simplemente que tenga relevancia tributaria.

## Inventario

`DocumentType.inventory_behavior` describe el efecto natural esperado:

- NONE
- IN
- OUT
- TRANSFER
- TRANSFORM

No sustituye a `MovementType`.

`MovementType` describe los movimientos reales de stock generados.

Un documento puede producir múltiples movimientos de inventario.

## Servicios

Mantener los modelos relativamente simples.

Usar servicios para lógica compleja de dominio.

Evitar lógica basada en `hasattr()` para adivinar capacidades del documento.

No convertir `DocumentService` en un mega-servicio.

## Alcance de las tareas

Modificar solo archivos necesarios para la tarea actual.

No realizar limpiezas laterales, renombrados o refactorizaciones
no solicitadas aunque se detecten problemas menores.

Si se detecta deuda técnica relevante,
informarla al final sin modificarla salvo autorización.

## Seguridad

Nunca:
- versionar secretos;
- versionar certificados privados;
- versionar claves privadas;
- guardar contraseñas de certificados en base de datos;
- imprimir secretos en logs.

## Forma de finalizar una tarea

Antes de dar una tarea por terminada, informar:

1. archivos modificados;
2. migraciones creadas;
3. pruebas ejecutadas y resultado;
4. resultado de `python manage.py check`;
5. resultado de `makemigrations --check --dry-run`;
6. riesgos o deuda técnica detectada;
7. resumen del `git diff`.

No hacer commit ni push salvo instrucción explícita.
