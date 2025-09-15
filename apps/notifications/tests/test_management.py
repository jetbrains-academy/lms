import pytest
import pytz
from django.core import management
from io import StringIO as OutputIO

from courses.constants import SemesterTypes
from courses.tests.factories import SemesterFactory
from courses.utils import TermPair
from learning.models import AssignmentNotification
from learning.tests.factories import (
    AssignmentNotificationFactory
)


@pytest.mark.django_db
def test_command_notification_cleanup(client, settings):
    current_term = SemesterFactory.create_current()
    semester = TermPair(year=current_term.academic_year - 1,
                        type=SemesterTypes.AUTUMN)
    notification1, notification2 = AssignmentNotificationFactory.create_batch(
        2, is_notified=True, is_unread=False)
    notification1.created = semester.starts_at(pytz.UTC)
    notification1.save()
    out = OutputIO()
    management.call_command("notification_cleanup", stdout=out)
    assert "1 AssignmentNotifications" in out.getvalue()
    assert AssignmentNotification.objects.filter(pk=notification2.pk).exists()
