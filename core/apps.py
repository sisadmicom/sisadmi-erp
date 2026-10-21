from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from django.db.models.signals import post_migrate
        from core.services.document_type_catalog import initialize_document_types

        post_migrate.connect(
            initialize_document_types, sender=self,
            dispatch_uid="core.initialize_document_types",
        )
