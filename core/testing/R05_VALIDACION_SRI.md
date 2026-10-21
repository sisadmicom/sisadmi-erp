# R-05 — Implementación y validación parcial

Estado: regresión PostgreSQL TEST ejecutada con fallos pendientes; ensayo real
no realizado ni autorizado. Resultados posteriores en R05_REGRESION.md y
r05_results.json. La sección de resultados parciales de este documento conserva
la evidencia de la primera ejecución sin credencial.

## Componentes reutilizados y correcciones

Se reutilizan el XSD oficial local de factura 1.1.0 y XmlValidationService,
XmlGeneratorService, SriSignerFactory, CertificateService, Pkcs12XmlSigner,
los servicios de documentos electrónicos, adaptadores SOAP y pantallas existentes.

- Nueva guarda fiscal compartida: XSD obligatorio, coherencia con el documento
  persistido, ambiente TEST y verificación criptográfica XAdES contra el certificado
  configurado. Compara el contenido fiscal original y firmado sin reescribirlo.
- Firma: errores sanitizados, XML original y estado GENERATED preservados ante
  fallo; certificado vigente y fuera del repositorio. Almacenamiento privado
  con permisos de archivo 0600 y directorio 0700.
- Recepción: XML firmado válido antes de registrar/intentar transmisión; conserva
  los mecanismos existentes de exclusión de envíos concurrentes e inciertos.
- Autorización: evidencia firmada y coincidente; guarda XML autorizado separado.
- SOAP: destinos TEST exactos, TLS obligatorio y sin redirecciones; bloqueo de
  producción antes de construir el cliente.
- Interfaz: permisos explícitos de lectura/operación, ámbito empresa/sucursal,
  mensajes de intentos escapados y distinción RECIBIDA, DEVUELTA, AUTORIZADO y
  NO AUTORIZADO. Reintento de consulta disponible según estado existente.

No se modificaron modelos ni se crearon migraciones. No se cambiaron tarifas.
Los fixtures existentes se completaron para satisfacer el contrato fiscal real;
certificados y respuestas sintéticos se usan exclusivamente en pruebas.

## Archivos

Producción modificada: ambos adaptadores en sri/clients; servicios de firma,
recepción, autorización, SriSignerFactory, SriSubmissionService y
XmlSigningService; sri/storage.py, sri/views.py y las tres pantallas de operación.

Nuevos: sri/services/invoice_validation.py,
sri/templates/sri/attempt_messages.html, sri/tests/r05_support.py,
sri/tests/test_invoice_security_r05.py y sri/tests/test_human_workflow_r05.py.

Se ajustaron los helpers y pruebas SRI afectados y los permisos del fixture de
core/tests/test_application_shell.py. Los cambios anteriores a R-05 se preservan;
el diff Git agregado también contiene trabajo de etapas anteriores.

## Resultados reales, sin combinar ejecuciones

Última ejecución conjunta sin acceso a base de datos:

```
69 pruebas ejecutadas; 69 aprobadas; 0 fallos; 0 errores; 0.321 segundos.
System check identified no issues (0 silenced).
```

Incluye test_invoice_security_r05, test_sri_reception_soap_adapter y
test_sri_authorization_soap_adapter. Registro:
/tmp/sisadmi-r05-offline-checked.log.

Otra ejecución independiente: 13 pruebas de guardas aprobadas.
pip check: No broken requirements found. git diff --check: sin incidencias.
Compilación estática Python: correcta.

Pruebas HTTP con PostgreSQL, módulo SRI completo, regresión principal, suite
completa y makemigrations --check --dry-run: NO ejecutados en R-05.
Bloqueo: falta /run/user/1000/sisadmi-r01-test-password. No se utilizaron
credenciales DEV ni se abrió conexión PostgreSQL. No hay credencial temporal
presente que retirar. La preparación PostgreSQL existente no requiere repetirse.

## Comunicación y evidencia

GET público de ambos WSDL TEST: correcto; direcciones SOAP coinciden con las
permitidas. El WSDL define numeroComprobantes como xs:string, compatible con
el adaptador. No se invocaron operaciones de recepción ni autorización.

No existe evidencia de autorización real. La verificación criptográfica local
con certificado sintético no acredita aceptación del perfil XAdES por el SRI.

## Preservación

HEAD e índice coinciden con el inventario inicial R-05.
Los 1138 archivos del manifiesto CAT-05 sellado mantienen sus hashes.
Las 28 pruebas CAT-05 no se ejecutaron ni modificaron. Sin commit ni push.

## Pendientes para continuar

1. Disponibilidad de la credencial privada TEST con permisos 0600 para ejecutar
   los tests HTTP, SRI, regresión principal, checks y suite completa. Corregir
   cualquier regresión que resulte; los resultados anteriores no la predicen.
2. Emisor real de pruebas: RUC, razón social, dirección, establecimiento/punto,
   régimen y datos fiscales aplicables; comprador, producto, pago y ambiente TEST.
3. PKCS#12 válido reconocido para el emisor fuera del repositorio; contraseña
   por mecanismo privado existente, nunca en chat ni archivos rastreados.
4. Revisar requisitos fiscales condicionales del emisor y perfil de firma.
5. Autorización expresa adicional para un único envío desde la interfaz, después
   de comprobar configuración, XML y firma. Registrar respuesta efectiva del SRI.

NO-GO para un ensayo real ahora. La siguiente acción es ejecutar la regresión
pendiente con la credencial TEST; no abrir otra fase de infraestructura.
