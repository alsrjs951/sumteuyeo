from django.apps import AppConfig


class ItemsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.items'

    def ready(self):
        from . import signals  # noqa
