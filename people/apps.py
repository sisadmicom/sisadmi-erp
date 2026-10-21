from django.apps import AppConfig


class PeopleConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'people'

    def ready(self):
        from people.services.person_protection import register
        register()
