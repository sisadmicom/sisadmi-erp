# Convenciones de interfaces SISADMI

Acuerdo obligatorio del usuario para los mantenimientos, aplicado dentro del
alcance de cada tarea. No autoriza extender trabajo a otros módulos.

1. Presentar Adicionar, Editar y Borrar de forma visible. Editar debe estar en
   el listado; no esconderlo detrás de Consultar.
2. Borrar es distinto de Desactivar. Requiere confirmación explícita, permiso
   y validación de dependencias en el servidor; un bloqueo debe explicarse sin
   borrar registros relacionados por cascada. Cancelar no cambia datos.
3. Junto a cada selector de otro modelo, ofrecer Adicionar mediante `+`, con
   nombre accesible. Validar los permisos del registro relacionado.
4. La creación relacionada conserva todo el borrador, incluidos datos todavía
   incompletos, y retorna con el nuevo registro seleccionado. Cancelar conserva
   los datos originales. Usar el almacén de borradores existente.
5. El retorno está vinculado a usuario, sesión, empresa y formulario de origen;
   no aceptar URLs arbitrarias ni confiar en IDs de empresa del navegador.
6. Las opciones no autorizadas son identificables pero no ejecutables. Ocultar
   una opción no reemplaza la autorización en servidor, CSRF ni el aislamiento.
7. Excepciones de diseño, identidad o integridad requieren análisis y acuerdo
   expreso. No inventar una excepción para eludir el estándar.
8. El usuario valida personalmente la interfaz. Detenerse después de la entrega;
   no continuar listas de precios ni otro módulo sin aprobación.

Regla aprobada: la Persona del cliente puede sustituirse únicamente mientras no
tenga documentos asociados, incluidos borradores. El formulario y el servicio
validan esta condición; los documentos históricos conservan sus referencias.
