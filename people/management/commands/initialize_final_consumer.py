"""Repeatable provisioning after the complete migration sequence."""
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = 'Inicializa Consumidor Final global y sus relaciones por empresa.'
    requires_migrations_checks = True

    @transaction.atomic
    def handle(self, *args, **options):
        from core.models import Company
        from people.services.final_consumer import ensure_person, enable_for_company

        ensure_person()
        for company in Company.objects.order_by('pk').iterator():
            enable_for_company(company)
        self.stdout.write(self.style.SUCCESS('Consumidor Final inicializado sin duplicados.'))
