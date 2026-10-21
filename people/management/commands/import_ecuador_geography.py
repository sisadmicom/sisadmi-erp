"""Plan first; a future write requires an explicitly approved, unchanged plan."""
import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from people.services.geography_catalog_import import plan_import, apply_import, simulate_repeat
from people.services.geography_catalog_parser import read_csv, sha256


class Command(BaseCommand):
    help = 'GEO-01: planificación geográfica; use --dry-run antes de solicitar aprobación.'

    def add_arguments(self, parser):
        parser.add_argument('--csv', required=True)
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument('--dry-run', action='store_true')
        mode.add_argument('--apply', action='store_true')
        parser.add_argument('--decisions', help='Decisiones GEO-01 vinculadas al CSV original.')
        parser.add_argument('--simulate-repeat', action='store_true', help='Segunda planificación sobre proyección en memoria; solo dry-run.')
        parser.add_argument('--simulation-report', help='Informe JSON de simulación, sin escrituras ORM.')
        parser.add_argument('--country-code', help='Solo necesario al crear Ecuador; conserva el código existente.')
        parser.add_argument('--report', help='Informe JSON UTF-8 del dry-run.')
        parser.add_argument('--approved-plan', help='Informe de dry-run aprobado; obligatorio con --apply.')

    def handle(self, *args, **options):
        if not options['dry_run'] and not options['apply']:
            raise CommandError('La primera ejecución requiere --dry-run.')
        if options['apply'] and not options['approved_plan']:
            raise CommandError('--apply requiere un informe --approved-plan generado por --dry-run.')
        if options['simulate_repeat'] and not options['dry_run']:
            raise CommandError('La simulación solo puede ejecutarse con --dry-run.')
        if options['simulation_report'] and not options['simulate_repeat']:
            raise CommandError('--simulation-report requiere --simulate-repeat.')
        inputs = [Path(options['csv']).resolve()]
        if options['decisions']:
            inputs.append(Path(options['decisions']).resolve())
        if options['approved_plan']:
            inputs.append(Path(options['approved_plan']).resolve())
        outputs = [Path(options[key]).resolve() for key in ('report','simulation_report') if options[key]]
        if any(path in inputs for path in outputs) or len(set(outputs)) != len(outputs):
            raise CommandError('Los informes no pueden sobrescribir entradas ni compartir el mismo archivo.')
        try:
            rows = read_csv(options['csv'])
            decisions = None
            if options['decisions']:
                decisions = json.loads(Path(options['decisions']).read_text(encoding='utf-8'))
                if not isinstance(decisions, dict) or decisions.get('source_csv_sha256') != sha256(options['csv']):
                    raise ValueError('Las decisiones no corresponden a los bytes del CSV original.')
            if options['dry_run']:
                report, _ = plan_import(rows, country_code=options['country_code'], decisions=decisions)
            else:
                approved = json.loads(Path(options['approved_plan']).read_text(encoding='utf-8'))
                report = apply_import(rows, approved, country_code=options['country_code'], decisions=decisions)
            if options['simulate_repeat']:
                simulation = simulate_repeat(rows, country_code=options['country_code'], decisions=decisions)
                if simulation['database_before_sha256'] != report['database_snapshot_sha256']:
                    raise ValueError('La base cambió durante el dry-run. Genere nuevamente el plan.')
                if options['simulation_report']:
                    Path(options['simulation_report']).write_text(json.dumps(simulation, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                self.stdout.write(json.dumps({'simulation':simulation}, ensure_ascii=False))
            if options['report']:
                Path(options['report']).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        except (ValueError, OSError, ValidationError, IntegrityError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps({'dry_run': report['dry_run'], 'rows': report['source']['rows'],
                          'would_create': report['would_create'], 'existing': report['existing'],
                          'created': report['created'], 'conflicts': len(report['conflicts']),
                          'ambiguities': len(report['source']['ambiguities']),
                          'equivalent_groups': len(report['source']['equivalent_names']),
                          'typographical_candidates': len(report['source']['possible_typographical_variants']),
                          'pending_cases': report.get('resolution',{}).get('counts',{}).get('pending_cases',0),
                          'blocked': report['blocked']}, ensure_ascii=False))
