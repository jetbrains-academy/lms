import logging
import smtplib
import time
from datetime import datetime
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import linebreaks, strip_tags
from django_rq import job
from functools import partial
from typing import Dict

from core.urls import replace_hostname
from core.utils import render_markdown, create_multipart_email
from learning.models import AssignmentNotification, CourseNewsNotification

logger = logging.getLogger(__name__)

EMAIL_TEMPLATES = {
    'new_comment_for_student': {
        'subject': "The teacher commented on the solution",
        'template_name': "emails/new_comment_for_student.html"
    },
    'assignment_passed': {
        'subject': "A student submitted their assignment",
        'template_name': "emails/assignment_passed.html"
    },
    'new_comment_for_teacher': {
        'subject': "A student commented on their assignment",
        'template_name': "emails/new_comment_for_teacher.html"
    },
    'new_course_news': {
        'subject': "Course news updated",
        'template_name': "emails/new_course_news.html"
    },
    'deadline_changed': {
        'subject': "Homework deadline updated",
        'template_name': "emails/deadline_changed.html"
    },
    'new_assignment': {
        'subject': "New assignment posted",
        'template_name': "emails/new_assignment.html"
    },
}


def send_notification(notification, template, context):
    subject = "[{}] {}".format(context['course_name'], template['subject'])
    msg = create_multipart_email(
        subject,
        template['template_name'],
        context,
        [notification.user.email],
    )
    logger.info(f"sending {notification} ({template})")
    try:
        # FIXME: use .send_messages instead to reuse connection and Keep-Alive feature
        msg.send()
    except smtplib.SMTPException as e:
        logger.exception(e)
        return
    notification.is_notified = True
    notification.save()
    time.sleep(settings.EMAIL_SEND_COOLDOWN)


def get_assignment_notification_template(notification: AssignmentNotification):
    if notification.is_about_creation:
        template_code = 'new_assignment'
    elif notification.is_about_deadline:
        template_code = 'deadline_changed'
    elif notification.is_about_passed:
        template_code = 'assignment_passed'
    elif notification.user == notification.student_assignment.student:
        template_code = 'new_comment_for_student'
    else:
        template_code = 'new_comment_for_teacher'
    return EMAIL_TEMPLATES[template_code]


def _get_abs_url_builder():
    return partial(replace_hostname, new_hostname=settings.LMS_DOMAIN)


def get_assignment_notification_context(notification: AssignmentNotification) -> Dict:
    a_s = notification.student_assignment
    tz_override = notification.user.time_zone
    abs_url_builder = _get_abs_url_builder()
    context = {
        'a_s_link_student': abs_url_builder(a_s.get_student_url()),
        'a_s_link_teacher': abs_url_builder(a_s.get_teacher_url()),
        # FIXME: rename
        'assignment_link': abs_url_builder(a_s.assignment.get_teacher_url()),
        'notification_created': notification.created_local(tz_override),
        'assignment_name': str(a_s.assignment),
        'assignment_text': render_markdown(a_s.assignment.text),
        'student_name': str(a_s.student),
        'deadline_at': a_s.assignment.deadline_at_local(tz=tz_override),
        'course_name': str(a_s.assignment.course.meta_course)
    }
    return context


@job('default')
def send_assignment_notifications(notification_ids: list[int]) -> None:
    prefetch = [
        'user__groups',
        'student_assignment',
        'student_assignment__assignment',
        'student_assignment__assignment__course',
        'student_assignment__assignment__course__meta_course',
        'student_assignment__student',
    ]
    notifications = (
        AssignmentNotification.objects
        .filter(is_unread=True,
                is_notified=False)
        .select_related("user")
        .prefetch_related(*prefetch)
        .filter(id__in=notification_ids)
        .all()
    )

    for notification in notifications:
        template = get_assignment_notification_template(notification)
        context = get_assignment_notification_context(notification)
        send_notification(notification, template, context)


def get_course_news_notification_context(notification: CourseNewsNotification) -> dict:
    abs_url_builder = _get_abs_url_builder()
    course = notification.course_offering_news.course
    return {
        'course_link': abs_url_builder(course.get_absolute_url()),
        'course_name': course.meta_course.name,
        'course_news_name': notification.course_offering_news.title,
        'course_news_text': notification.course_offering_news.text,
    }


@job('default')
def send_course_news_notifications(notification_ids: list[int]) -> None:
    prefetch = [
        'user__groups',
        'course_offering_news__course',
        'course_offering_news__course__meta_course',
        'course_offering_news__course__semester',
    ]
    notifications = (
        CourseNewsNotification.objects
        .filter(is_unread=True, is_notified=False)
        .select_related('user', 'course_offering_news')
        .prefetch_related(*prefetch)
        .filter(id__in=notification_ids)
        .all()
    )

    template = EMAIL_TEMPLATES['new_course_news']

    for notification in notifications:
        context = get_course_news_notification_context(notification)
        send_notification(notification, template, context)
