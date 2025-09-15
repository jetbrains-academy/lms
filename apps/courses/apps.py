from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoursesConfig(AppConfig):
    name = 'courses'
    verbose_name = _("Courses")

    def ready(self):
        from . import signals
