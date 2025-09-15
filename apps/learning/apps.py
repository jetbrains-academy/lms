import sys

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LearningConfig(AppConfig):
    name = 'learning'
    verbose_name = _("Learning")

    def ready(self):
        # Register checks, signals, permissions and roles, tabs
        from . import (  # pylint: disable=unused-import
            checks, permissions, roles, signals, tabs
        )
        if 'manage.py' not in sys.argv or 'runserver' in sys.argv:
            # Runnning actual server
            from learning.services.jba_service import JbaService
            JbaService.schedule_update_current_assignments_progress()
