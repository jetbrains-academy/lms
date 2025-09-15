import pytest
from django.core import mail

from learning.models import AssignmentNotification
from learning.tests.factories import AssignmentNotificationFactory, CourseNewsNotificationFactory
from notifications.tasks import send_assignment_notifications, send_course_news_notifications
from users.tests.factories import StudentFactory


@pytest.mark.django_db
def test_notify(settings):
    settings.DEFAULT_URL_SCHEME = 'https'

    mail.outbox = []
    student = StudentFactory()
    an = AssignmentNotificationFactory(is_about_passed=True,
                                       user=student)
    send_assignment_notifications.delay([an.pk])
    assert len(mail.outbox) == 1
    assert AssignmentNotification.objects.get(pk=an.pk).is_notified

    mail.outbox = []
    send_assignment_notifications.delay([])
    assert len(mail.outbox) == 0

    mail.outbox = []
    student = StudentFactory()
    conn = CourseNewsNotificationFactory.create(user=student)
    send_course_news_notifications.delay([conn.pk])
    assert len(mail.outbox) == 1
    conn.refresh_from_db()
    assert conn.is_notified
