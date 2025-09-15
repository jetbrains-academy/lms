import datetime
from zoneinfo import ZoneInfo

import pytest
import pytz
from django.core import mail

from core.timezone.constants import DATE_FORMAT_RU
from core.urls import reverse
from courses.constants import AssigneeMode, AssignmentFormat
from courses.models import Assignment, CourseTeacher
from courses.tests.factories import (
    AssignmentFactory, CourseFactory, CourseNewsFactory, CourseTeacherFactory
)
from learning.models import AssignmentNotification, CourseNewsNotification, StudentAssignment, AssignmentComment
from learning.services.enrollment_service import (
    EnrollmentService, is_course_failed_by_student
)
from learning.settings import StudentStatuses
from learning.tests.factories import EnrollmentFactory, StudentAssignmentFactory, AssignmentNotificationFactory, \
    CourseNewsNotificationFactory, AssignmentCommentFactory
from notifications.tasks import get_assignment_notification_context, get_course_news_notification_context, \
    send_assignment_notifications
from users.services import get_student_profile
from users.tests.factories import TeacherFactory, StudentFactory


def _prefixed_form(form_data, prefix: str):
    return {f"{prefix}-{k}": v for k, v in form_data.items()}


def _get_unread(client, url):
    return client.get(url).wsgi_request.unread_notifications_cache


@pytest.mark.django_db
def test_view_new_assignment(client):
    teacher1 = TeacherFactory()
    teacher2 = TeacherFactory()
    course = CourseFactory(teachers=[teacher1, teacher2])
    course_teacher1, course_teacher2 = CourseTeacher.objects.filter(course=course)
    student = StudentFactory()
    EnrollmentFactory(student=student, course=course, grade=4)
    a = AssignmentFactory.build()
    form = {
        'title': a.title,
        'submission_type': AssignmentFormat.ONLINE,
        'text': a.text,
        'maximum_score': 5,
        'weight': 1,
        'time_zone': 'UTC',
        'opens_at_0': a.opens_at.strftime(DATE_FORMAT_RU),
        'opens_at_1': '00:00',
        'deadline_at_0': a.deadline_at.strftime(DATE_FORMAT_RU),
        'deadline_at_1': '00:00',
        'assignee_mode': AssigneeMode.MANUAL
    }
    form_prefixed = _prefixed_form(form, "assignment")
    form_prefixed.update({
        f'responsible-teacher-{course_teacher1.pk}-active': True,
        f'responsible-teacher-{course_teacher2.pk}-active': True
    })
    client.login(teacher1)
    response = client.post(course.get_create_assignment_url(), form_prefixed)
    assert response.status_code == 302
    assignments = course.assignment_set.all()
    assert len(assignments) == 1
    assignment = assignments[0]
    student_assignment = (StudentAssignment.objects
                          .filter(assignment=assignment, student=student)
                          .get())
    assert AssignmentNotification.objects.filter(is_about_creation=True).count() == 1
    student_url = student_assignment.get_student_url()
    student_create_comment_url = reverse("study:assignment_comment_create",
                                         kwargs={"pk": student_assignment.pk})
    student_create_solution_url = reverse("study:assignment_solution_create",
                                          kwargs={"pk": student_assignment.pk})
    teacher_create_comment_url = reverse(
        "teaching:assignment_comment_create",
        kwargs={"pk": student_assignment.pk})
    teacher_url = student_assignment.get_teacher_url()
    student_list_url = reverse('study:assignment_list', args=[])
    teacher_list_url = reverse('teaching:assignments_check_queue', args=[])
    student_comment_dict = {
        'comment-text': "Test student comment without file"
    }
    teacher_comment_dict = {
        'comment-text': "Test teacher comment without file"
    }
    # Post first comment on assignment
    AssignmentNotification.objects.all().delete()
    assert not is_course_failed_by_student(course, student)
    client.login(student)
    mail.outbox = []
    client.post(student_create_comment_url, student_comment_dict)
    assert 2 == (AssignmentNotification.objects
                 .filter(is_about_passed=False,
                         is_unread=True,
                         is_notified=True)
                 .count())
    assert len(mail.outbox) == 2
    assert len(_get_unread(client, student_list_url).assignments) == 0
    client.login(teacher1)
    assert len(_get_unread(client, teacher_list_url).assignments) == 1
    client.login(teacher2)
    assert len(_get_unread(client, teacher_list_url).assignments) == 1
    # Read message
    client.get(teacher_url)
    client.login(teacher1)
    assert len(_get_unread(client, teacher_list_url).assignments) == 1
    client.login(teacher2)
    assert len(_get_unread(client, teacher_list_url).assignments) == 0
    # Teacher left a comment
    mail.outbox = []
    client.post(teacher_create_comment_url, teacher_comment_dict)
    unread_msgs_for_student = (AssignmentNotification.objects
                               .filter(user=student,
                                       is_unread=True,
                                       is_notified=True)
                               .count())
    assert unread_msgs_for_student == 1
    assert len(mail.outbox) == 1
    client.login(student)
    assert len(_get_unread(client, student_list_url).assignments) == 1
    # Student left a comment again
    mail.outbox = []
    client.post(student_create_comment_url, student_comment_dict)
    unread_msgs_for_teacher1 = (AssignmentNotification.objects
                                .filter(is_about_passed=False,
                                        user=teacher1,
                                        is_unread=True,
                                        is_notified=True)
                                .count())
    assert unread_msgs_for_teacher1 == 2
    assert len(mail.outbox) == 2
    # Student sent a solution
    client.login(student)
    solution_form = {
        'solution-text': "Test student solution without file"
    }
    mail.outbox = []
    client.post(student_create_solution_url, solution_form)
    assert 2 == (AssignmentNotification.objects
                 .filter(is_about_passed=True,
                         is_unread=True,
                         is_notified=True)
                 .count())
    assert len(mail.outbox) == 2


@pytest.mark.django_db
def test_assignment_setup_assignees_public_form(client):
    """
    Make sure `Assignment.assignees` are populated by the course
    homework reviewers on adding new assignment.
    """
    student = StudentFactory()
    t1, t2, t3, t4 = TeacherFactory.create_batch(4)
    course = CourseFactory.create(teachers=[t1, t2, t3, t4])
    course_teachers = list(CourseTeacher.objects.filter(course=course))
    for course_teacher in course_teachers:
        course_teacher.roles = CourseTeacher.roles.reviewer
        course_teacher.save()
    course_teacher1 = CourseTeacher.objects.get(course=course, teacher=t1)
    course_teacher1.notify_by_default = False
    course_teacher1.roles = None
    course_teacher1.save()
    course_teacher2 = CourseTeacher.objects.get(course=course, teacher=t2)
    EnrollmentFactory.create(student=student, course=course, grade=4)
    # Create first assignment
    client.login(t1)
    a = AssignmentFactory.build()
    form = {
        'title': a.title,
        'submission_type': AssignmentFormat.ONLINE,
        'text': a.text,
        'maximum_score': 5,
        'weight': '1.00',
        'time_zone': 'UTC',
        'opens_at_0': a.opens_at.strftime(DATE_FORMAT_RU),
        'opens_at_1': '00:00',
        'deadline_at_0': a.deadline_at.strftime(DATE_FORMAT_RU),
        'deadline_at_1': '00:00',
        'assignee_mode': AssigneeMode.MANUAL,
    }
    form_prefixed = _prefixed_form(form, "assignment")
    form_prefixed.update({
        f'responsible-teacher-{course_teacher1.pk}-active': True,
        f'responsible-teacher-{course_teacher2.pk}-active': True,
    })
    url = course.get_create_assignment_url()
    response = client.post(url, form_prefixed, follow=True)
    assert response.status_code == 200
    assignments = course.assignment_set.all()
    assert len(assignments) == 1
    assignment = assignments[0]
    assert len(assignment.assignees.all()) == 2
    # Update assignment and check, that assignees are not changed
    form_prefixed['maximum_score'] = 10
    url = assignment.get_update_url()
    response = client.post(url, form_prefixed)
    assert response.status_code == 302
    assigned_teachers = list(assignment.assignees.all())
    assert len(assigned_teachers) == 2
    assert course_teacher1 in assigned_teachers
    assert course_teacher2 in assigned_teachers


@pytest.mark.django_db
def test_assignment_submission_notifications_for_teacher(client):
    course = CourseFactory()
    course_teacher1, *rest_course_teachers = CourseTeacherFactory.create_batch(4,
                                                                               course=course,
                                                                               roles=CourseTeacher.roles.reviewer)
    course_teacher1.notify_by_default = False
    course_teacher1.save()
    # Leave a comment from student
    student = StudentFactory()
    assert not is_course_failed_by_student(course, student)
    client.login(student)
    assert Assignment.objects.count() == 0
    assignment = AssignmentFactory(course=course,
                                   assignee_mode=AssigneeMode.MANUAL,
                                   assignees=rest_course_teachers)
    student_assignment = StudentAssignmentFactory(student=student, assignment=assignment)
    student_create_comment_url = reverse("study:assignment_comment_create",
                                         kwargs={"pk": student_assignment.pk})
    client.post(student_create_comment_url,
                {'comment-text': 'test first comment'})
    notifications = [n.user.pk for n in AssignmentNotification.objects.all()]
    assert len(notifications) == 3
    assert course_teacher1.teacher_id not in notifications


@pytest.mark.django_db
def test_new_assignment_generate_notifications(settings):
    """Generate notifications for students about new assignment"""
    course = CourseFactory()
    enrollments = EnrollmentFactory.create_batch(5, course=course)
    assignment = AssignmentFactory(course=course)
    assert AssignmentNotification.objects.count() == 5
    # Dont' send notification to the students who left the course
    AssignmentNotification.objects.all().delete()
    assert AssignmentNotification.objects.count() == 0
    enrollment = enrollments[0]
    enrollment.is_deleted = True
    enrollment.save()
    assignment = AssignmentFactory(course=course)
    assert AssignmentNotification.objects.count() == 4
    # Don't create new assignment for expelled students
    AssignmentNotification.objects.all().delete()
    student = enrollments[1].student
    student_profile = get_student_profile(student)
    student_profile.status = StudentStatuses.EXPELLED
    student_profile.save()
    assignment = AssignmentFactory(course=course)
    assert AssignmentNotification.objects.count() == 3


def build_absolute_url(relative_url, settings):
    return f'https://{settings.LMS_DOMAIN}{relative_url}'


@pytest.mark.django_db
def test_new_assignment_notification_context(settings):
    settings.DEFAULT_URL_SCHEME = 'https'  # http by default in tests
    course = CourseFactory()
    enrollment = EnrollmentFactory(course=course)
    student = enrollment.student
    assignment = AssignmentFactory(course=course)
    assert AssignmentNotification.objects.count() == 1
    an = AssignmentNotification.objects.first()
    context = get_assignment_notification_context(an)
    student_url = build_absolute_url(an.student_assignment.get_student_url(), settings)
    assert context['a_s_link_student'] == student_url
    teacher_url = build_absolute_url(an.student_assignment.get_teacher_url(), settings)
    assert context['a_s_link_teacher'] == teacher_url
    assignment_link = build_absolute_url(an.student_assignment.assignment.get_teacher_url(), settings)
    assert context['assignment_link'] == assignment_link
    assert context['course_name'] == str(course.meta_course)
    assert context['student_name'] == str(student)


@pytest.mark.django_db
def test_new_assignment_notification_context_timezone():
    msk_tz = ZoneInfo('Europe/Moscow')
    nsk_tz = ZoneInfo('Asia/Novosibirsk')
    dt = datetime.datetime(2017, 2, 4, 15, 0, 0, 0, tzinfo=pytz.UTC)
    assignment = AssignmentFactory(time_zone=pytz.timezone('Europe/Moscow'),
                                   deadline_at=dt)
    student = StudentFactory(time_zone=msk_tz)
    sa = StudentAssignmentFactory(assignment=assignment, student=student)
    dt_local = assignment.deadline_at_local()
    assert dt_local.hour == 18
    notification = AssignmentNotificationFactory(is_about_creation=True, user=student,
                                                 student_assignment=sa)
    mail.outbox = []
    send_assignment_notifications.delay([notification.pk])
    assert len(mail.outbox) == 1
    assert "04 February" in mail.outbox[0].body
    assert "18:00" in mail.outbox[0].body
    # If student is enrolled in the course, show assignments in the
    # timezone of the student.
    student.time_zone = nsk_tz
    student.save()
    notification = AssignmentNotificationFactory(is_about_creation=True, user=student,
                                                 student_assignment=sa)
    mail.outbox = []
    send_assignment_notifications.delay([notification.pk])
    assert len(mail.outbox) == 1
    assert "04 February" in mail.outbox[0].body
    assert "22:00" in mail.outbox[0].body


@pytest.mark.django_db
def test_new_course_news_notification_context(settings):
    settings.DEFAULT_URL_SCHEME = 'https'  # http by default in tests
    course = CourseFactory()
    student = StudentFactory()
    enrollment = EnrollmentFactory(course=course, student=student)
    cn = CourseNewsNotificationFactory(course_offering_news__course=course,
                                       user=student)
    context = get_course_news_notification_context(cn)
    assert context['course_link'] == build_absolute_url(course.get_absolute_url(), settings)


@pytest.mark.django_db
def test_change_assignment_comment(settings):
    """Don't send notification on editing assignment comment"""
    teacher = TeacherFactory()
    course = CourseFactory(teachers=[teacher])
    enrollment = EnrollmentFactory(course=course)
    student = enrollment.student
    student_profile = enrollment.student_profile
    assignment = AssignmentFactory(course=course)
    student_assignment = StudentAssignment.objects.get(student=student,
                                                       assignment=assignment)
    assert AssignmentNotification.objects.count() == 1
    comment = AssignmentCommentFactory(student_assignment=student_assignment,
                                       author=teacher)
    assert AssignmentNotification.objects.count() == 2
    comment.text = 'New Content'
    comment.save()
    assert AssignmentNotification.objects.count() == 2
    # Get comment from db
    comment = AssignmentComment.objects.get(pk=comment.pk)
    comment.text = 'Updated Comment'
    comment.save()
    assert AssignmentNotification.objects.count() == 2


@pytest.mark.django_db
def test_changed_assignment_deadline_generate_notifications(settings):
    co = CourseFactory()
    e1, e2 = EnrollmentFactory.create_batch(2, course=co)
    s1 = e1.student
    s1_profile = get_student_profile(e1.student)
    s1_profile.status = StudentStatuses.EXPELLED
    s1_profile.save()
    a = AssignmentFactory(course=co)
    assert AssignmentNotification.objects.count() == 1
    dt = datetime.datetime(2017, 2, 4, 15, 0, 0, 0, tzinfo=pytz.UTC)
    a.deadline_at = dt
    a.save()
    assert AssignmentNotification.objects.count() == 2


@pytest.mark.django_db
def test_changed_assignment_deadline_notifications_timezone():
    msk_tz = ZoneInfo('Europe/Moscow')
    nsk_tz = ZoneInfo('Asia/Novosibirsk')
    student = StudentFactory(time_zone=nsk_tz)
    dt = datetime.datetime(2017, 2, 4, 15, 0, 0, 0, tzinfo=pytz.UTC)
    assignment = AssignmentFactory(time_zone=pytz.timezone('Asia/Novosibirsk'),
                                   deadline_at=dt)
    sa = StudentAssignmentFactory(assignment=assignment, student=student)
    dt_local = assignment.deadline_at_local()
    assert dt_local.hour == 22
    # Shows deadline in the time zone of the student
    notification = AssignmentNotificationFactory(is_about_deadline=True, user=sa.student,
                                                 student_assignment=sa)
    mail.outbox = []
    send_assignment_notifications.delay([notification.pk])
    assert len(mail.outbox) == 1
    assert "22:00" in mail.outbox[0].body
    assert "04 February" in mail.outbox[0].body
    # Change student time zone
    student.time_zone = msk_tz
    student.save()
    notification = AssignmentNotificationFactory(is_about_deadline=True, user=sa.student,
                                                 student_assignment=sa)
    mail.outbox = []
    send_assignment_notifications.delay([notification.pk])
    assert len(mail.outbox) == 1
    assert "04 February" in mail.outbox[0].body
    assert "18:00" in mail.outbox[0].body


@pytest.mark.django_db
def test_remove_assignment_notifications_on_leaving_course(settings):
    course = CourseFactory()
    other_course = CourseFactory()
    enrollment = EnrollmentFactory(course=course)
    AssignmentFactory(course=course)
    an = AssignmentNotificationFactory(student_assignment__assignment__course=other_course)
    assert AssignmentNotification.objects.count() == 2
    EnrollmentService.leave(enrollment)
    assert AssignmentNotification.objects.count() == 1
    assert AssignmentNotification.objects.get() == an


@pytest.mark.django_db
def test_remove_course_news_notifications_on_leaving_course(settings):
    course = CourseFactory()
    other_course = CourseFactory()
    enrollment = EnrollmentFactory(course=course)
    CourseNewsFactory(course=course)
    cn = CourseNewsNotificationFactory(course_offering_news__course=other_course)
    assert CourseNewsNotification.objects.count() == 2
    EnrollmentService.leave(enrollment)
    assert CourseNewsNotification.objects.count() == 1
    assert CourseNewsNotification.objects.get() == cn
