from django.apps import AppConfig


class ContractConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.contract'
    def ready(self):
        from . import signals 

