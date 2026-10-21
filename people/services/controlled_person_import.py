"""One explicitly authorized TEST-only batch. No general-purpose import API."""
import csv
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor

from core.models import Company
from people.identification import detect_identification
from people.models import CompanyPersonAccess, IdentificationKind, Person
from people.services import person_access_policy as policy


@dataclass(frozen=True)
class Authorization:
    source: Path
    manifest: Path
    source_sha256: str
    manifest_sha256: str
    validator_sha256: str
    company_id: int
    company_name: str = 'SISADMI'
    count: int = 49


APPROVED = Authorization(
    source=Path('/home/sisadmi/workspace/sisadmi-erp/fv_cliente.txt'),
    manifest=Path('/tmp/sisadmi-personas-preview-xsaxce4s/revision-3-lectura-eqs1gs_4/previsualizacion.json'),
    source_sha256='0a8102213be8e3f912e8e443d0fb2954a4f9daba229769fe2651f16a1d15c0b3',
    manifest_sha256='2d93b15c3d6603de8f6dfaadf4bdc2721f0a8b83b4ad11de537e81b86817a1ab',
    validator_sha256='a1ce4a01ca0214b54509f550accf6de54c9524cbff64ae6bfa92f00a4387456b',
    company_id=93,
)
ACTION = 'CONTROLLED_PERSON_IMPORT'


def stop(message):
    raise ValidationError(message, code='controlled_import_stopped')


def digest(content):
    return hashlib.sha256(content).hexdigest()


def _read_authorization(spec):
    source = spec.source.read_bytes()
    manifest = spec.manifest.read_bytes()
    if digest(source) != spec.source_sha256 or digest(manifest) != spec.manifest_sha256:
        stop('Los hashes de la fuente o del manifiesto cambiaron. Se requiere nueva autorización.')
    if digest((Path(__file__).resolve().parents[1] / 'identification.py').read_bytes()) != spec.validator_sha256:
        stop('Cambió el validador aprobado.')
    document = json.loads(manifest)
    if document['resumen']['source_sha256'] != spec.source_sha256:
        stop('El manifiesto no corresponde a la fuente autorizada.')
    all_rows = document['filas']
    if len(all_rows) != 100 or len({row['linea'] for row in all_rows}) != 100:
        stop('La muestra autorizada debe contener las mismas 100 líneas distintas.')
    selected = [row for row in all_rows if row['accion_propuesta'] == 'CREAR']
    if len(selected) != spec.count or Counter(row['person_type_propuesto'] for row in selected) != {'NATURAL': 48, 'LEGAL': 1}:
        stop('El lote debe contener exactamente 49 Personas: 48 NATURAL y 1 LEGAL.')
    if len({row['identificacion'] for row in selected}) != spec.count:
        stop('El lote contiene identificaciones duplicadas.')
    lines = source.decode('utf-8').splitlines()
    # Verify every sample row, including excluded rows; never import the exclusions.
    for row in all_rows:
        number = row['linea']
        if not isinstance(number, int) or not 1 <= number <= len(lines):
            stop('Referencia de línea inválida.')
        line = lines[number - 1]
        fields = next(csv.reader([line], delimiter=',', quotechar="'", strict=True))
        if (len(fields) != 35 or digest(line.encode()) != row['sha256_linea']
                or fields[0] != row['identificador_original'] or fields[5] != row['identificacion']
                or fields[2] != row['nombre_columna_3'] or fields[6] != row['nombre_columna_7']):
            stop('La trazabilidad de una fila ya no coincide con el manifiesto.')
    for row in selected:
        if row['company_id_verificada'] != spec.company_id or row['resultado_cruce'] != 'PERSONA_NUEVA_ASOCIACION_NUEVA':
            stop('La empresa o la acción de una candidata no corresponde a la autorización.')
        if not row['nombre_propuesto'] or row['nombre_propuesto'] != row['nombre_columna_3'] or row['nombre_propuesto'] != row['nombre_columna_7']:
            stop('El nombre autorizado no es común y no vacío.')
        if detect_identification(row['identificacion']) != row['tipo_detectado']:
            stop('La validación actual difiere de la previsualización.')
        natural = row['tipo_detectado'] == 'CEDULA' or (row['tipo_detectado'] == 'RUC' and row['identificacion'][2] in '012345')
        if not natural and not (row['tipo_detectado'] == 'RUC' and row['identificacion'][2] == '6'):
            stop('Clasificación no autorizada para esta muestra.')
        if row['person_type_propuesto'] != ('NATURAL' if natural else 'LEGAL'):
            stop('Clasificación NATURAL/LEGAL incompatible con el lote aprobado.')
    return selected


def _require_test():
    from core.testing.r01_guard import HOST, PORT, TEST_DATABASE, USER
    cfg = connection.settings_dict
    if (connection.vendor != 'postgresql' or cfg['NAME'] != TEST_DATABASE or cfg['USER'] != USER
            or cfg['HOST'] != HOST or str(cfg['PORT']) != str(PORT)):
        stop('La importación está permitida exclusivamente en PostgreSQL TEST autorizado.')
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database(),current_user,inet_server_addr()::text,inet_server_port()')
        if cursor.fetchone() != (TEST_DATABASE, USER, HOST + '/32', int(PORT)):
            stop('La identidad real de la conexión TEST no coincide.')


def _require_protection():
    executor = MigrationExecutor(connection)
    executor.loader.check_consistent_history(connection)
    if ('people', '0011_person_identity_immutable') not in executor.loader.applied_migrations or executor.migration_plan(executor.loader.graph.leaf_nodes()):
        stop('El historial de migraciones TEST difiere del aprobado.')
    migration = Path(__file__).resolve().parents[1] / 'migrations/0011_person_identity_immutable.py'
    bodies = dict(re.findall(r'CREATE FUNCTION public\.(\w+)\(\) RETURNS trigger\s+LANGUAGE plpgsql AS \$\$(.*?)\$\$;', migration.read_text(), re.S))
    expected = {'people_person_identity_immutable': ('sisadmi_person_identity_guard', 27),
                'people_person_identity_coherent': ('sisadmi_person_identity_insert_guard', 7),
                'people_identification_kind_code_immutable': ('sisadmi_identification_kind_code_guard', 19)}
    with connection.cursor() as cursor:
        cursor.execute("SELECT t.tgname,t.tgenabled,t.tgtype,p.proname,p.prosrc FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid WHERE NOT t.tgisinternal AND t.tgrelid IN ('public.people_person'::regclass,'public.people_identificationkind'::regclass)")
        rows = cursor.fetchall()
    if len(rows) != 3 or any(enabled != 'O' or expected.get(name) != (function, flags) or bodies.get(function) != body
                             for name, enabled, flags, function, body in rows):
        stop('Los triggers de identidad no coinciden con la protección aprobada.')


def _audit_model():
    try:
        return apps.get_model('core', 'AuditLog')
    except LookupError:
        stop('La auditoría CORE no está registrada ni preparada. No se permite importar sin auditoría transaccional.')


def _audit_detail(spec, row, person, access):
    return {'batch_manifest_sha256': spec.manifest_sha256, 'source_sha256': spec.source_sha256,
            'line': row['linea'], 'source_id': row['identificador_original'], 'identification': row['identificacion'],
            'person_id': person.pk, 'company_id': spec.company_id, 'access_id': access.pk,
            'result': 'CREATED', 'authorization': 'Explicit user approval of 49 new Persons; no Customer/contact/geography'}


def _execute(*, actor, spec):
    # Reject forbidden connection parameters BEFORE entering a DB transaction.
    _require_test()
    return _execute_atomic(actor=actor, spec=spec)


@transaction.atomic
def _execute_atomic(*, actor, spec):
    _require_test()
    AuditLog = _audit_model()
    rows = _read_authorization(spec)
    _require_protection()
    company = Company.objects.select_for_update().get(pk=spec.company_id)
    matches = Company.objects.filter(person__full_name__iexact=spec.company_name) | Company.objects.filter(commercial_name__iexact=spec.company_name)
    if set(matches.values_list('pk', flat=True)) != {company.pk} or not company.is_active or not company.person.is_active:
        stop('La empresa SISADMI dejó de ser inequívoca o está inactiva.')
    if not policy.can_create_person(actor=actor, company=company) or not actor.has_perm('people.view_person') or not actor.has_perm('core.add_auditlog'):
        raise PermissionDenied('Se requieren permisos de Personas, auditoría y empresa autorizada.')
    people = {p.identification: p for p in Person.objects.filter(identification__in=[r['identificacion'] for r in rows]).select_for_update()}
    logs = list(AuditLog.objects.filter(action=ACTION, detail__batch_manifest_sha256=spec.manifest_sha256).select_for_update())
    if people or logs:
        # A second execution is a no-op ONLY for the fully proven original batch.
        if len(people) != spec.count or len(logs) != spec.count:
            stop('Hay Personas o auditorías previas ajenas o parciales. No se escribieron cambios.')
        by_person = {log.object_id: log for log in logs}
        for row in rows:
            person = people[row['identificacion']]
            access = CompanyPersonAccess.objects.filter(company=company, person=person).first()
            log = by_person.get(person.pk)
            if (not access or not log or log.model_name != 'people.Person'
                    or person.full_name != row['nombre_propuesto'] or person.person_type != row['person_type_propuesto']
                    or person.identification_type != row['tipo_detectado']
                    or person.identification_kind_id != row['identification_kind_id_propuesto']
                    or not person.is_active or log.detail != _audit_detail(spec, row, person, access)):
                stop('El lote previo difiere de su auditoría. Se requiere revisión.')
        return {'status': 'ALREADY_IMPORTED', 'created_persons': 0, 'created_accesses': 0, 'created_audits': 0,
                'person_ids': sorted(p.pk for p in people.values()), 'manifest_sha256': spec.manifest_sha256}
    for row in rows:
        if not IdentificationKind.objects.filter(pk=row['identification_kind_id_propuesto'], code=row['tipo_detectado'], is_active=True).exists():
            stop('El catálogo difiere de la previsualización autorizada.')
    created = []
    for row in rows:
        person = policy.create_person(actor=actor, company=company, data={
            'identification': row['identificacion'], 'identification_type': row['tipo_detectado'],
            'person_type': row['person_type_propuesto'], 'full_name': row['nombre_propuesto']})
        access = CompanyPersonAccess.objects.get(company=company, person=person)
        AuditLog.objects.create(model_name='people.Person', object_id=person.pk, action=ACTION,
            detail=_audit_detail(spec, row, person, access), requested_by=actor, executed_by=actor,
            observation='Lote autorizado por el usuario; creación exclusivamente en TEST para SISADMI.')
        created.append(person.pk)
    return {'status': 'IMPORTED', 'created_persons': len(created), 'created_accesses': len(created),
            'created_audits': len(created), 'person_ids': created, 'manifest_sha256': spec.manifest_sha256}


def import_approved_people(*, actor):
    """The only production entry point: fixed source, digest, company and 49 rows."""
    return _execute(actor=actor, spec=APPROVED)
