"""Extract source rows without consulting or changing the database."""
import json
import subprocess
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from people.services.geography_catalog_parser import extract_pdf, write_csv, analyze, sha256


class Command(BaseCommand):
    help = 'Extrae el PDF GEO-01 a CSV UTF-8 con página y fila de origen; no importa datos.'

    def add_arguments(self, parser):
        parser.add_argument('--pdf', required=True)
        parser.add_argument('--csv', required=True)
        parser.add_argument('--report', required=True)

    def handle(self, *args, **options):
        paths = [Path(options[k]).resolve() for k in ('pdf', 'csv', 'report')]
        if len(set(paths)) != 3:
            raise CommandError('PDF, CSV e informe deben ser archivos distintos.')
        try:
            rows = extract_pdf(paths[0])
            write_csv(rows, paths[1])
            report = {'source_pdf': paths[0].name, 'source_pdf_sha256': sha256(paths[0]),
                      'csv_sha256': sha256(paths[1]), 'extraction': 'Poppler pdftotext -bbox-layout; cell lines; row tolerance 2pt; separated-gap split for merged cells',
                      'analysis': analyze(rows)}
            paths[2].write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        except (ValueError, OSError, subprocess.CalledProcessError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Extraídas {len(rows)} filas; base de datos sin cambios.")
