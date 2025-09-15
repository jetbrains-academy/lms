from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AlumniConfig(AppConfig):
    name = 'alumni'
    verbose_name = _('Alumni')

    def ready(self):
        # noinspection PyUnresolvedReferences
        from . import permissions
