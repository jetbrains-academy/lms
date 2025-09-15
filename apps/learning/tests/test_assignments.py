import datetime
from decimal import Decimal

import factory
import pytest
import pytz
from bs4 import BeautifulSoup
from django.utils.encoding import smart_bytes
from django.utils.timezone import now
from django.utils.translation import gettext as _

from auth.mixins import PermissionRequiredMixin
from core.timezone.constants import DATE_FORMAT_RU, TIME_FORMAT_RU
from core.urls import reverse
from courses.constants import AssigneeMode, AssignmentFormat
from courses.models import Assignment, AssignmentAttachment, CourseTeacher
from courses.tests.factories import (
    AssignmentAttachmentFactory, AssignmentFactory, CourseFactory, CourseTeacherFactory,
    SemesterFactory
)
from learning.models import StudentAssignment
from learning.permissions import ViewAssignmentAttachment
from learning.services.enrollment_service import is_course_failed_by_student
from learning.settings import StudentStatuses
from learning.tests.factories import (
    AssignmentCommentFactory, EnrollmentFactory, StudentAssignmentFactory
)
from users.services import get_student_profile
from users.tests.factories import (
    CuratorFactory, StudentFactory, TeacherFactory, InvitedStudentFactory
)


# TODO: assignment submission page - comments localisation, assignment created localization


@pytest.mark.django_db
def test_security_course_detail(client):
    """Student can't watch news from completed course which they failed"""
    teacher = TeacherFactory()
    student = StudentFactory()
    co = CourseFactory(teachers=[teacher], completed_at=datetime.date.today())
    enrollment = EnrollmentFactory(student=student, course=co, grade=1)
    a = AssignmentFactory(course=co)
    co.refresh_from_db()
    assert is_course_failed_by_student(co, student)
    client.login(student)
    url = co.get_absolute_url()
    response = client.get(url)
    soup = BeautifulSoup(response.content, "html.parser")
    assert soup.find(text=_("News")) is None
    # Change student co mark
    enrollment.grade = 5
    enrollment.save()
    response = client.get(url)
    assert not is_course_failed_by_student(co, student)
    # Change course offering state to not completed
    co.completed_at = now().date() + datetime.timedelta(days=1)
    co.save()
    response = client.get(url)
    assert not is_course_failed_by_student(co, student)


@pytest.mark.django_db
def test_model_student_assignment_final_score():
    assignment1 = AssignmentFactory(weight=1, maximum_score=10,
                                    submission_type=AssignmentFormat.NO_SUBMIT)
    student_assignment = StudentAssignment(assignment=assignment1,
                                           score=Decimal('2.34'))
    assert student_assignment.penalty is None
    assert student_assignment.final_score == student_assignment.score
    assert student_assignment.final_score == Decimal('2.34')
    student_assignment.penalty = Decimal('1.11')
    assert student_assignment.final_score == Decimal('3.45')
    student_assignment.score = None
    assert student_assignment.final_score == Decimal('1.11')
    student_assignment.penalty = None
    assert student_assignment.final_score is None


@pytest.mark.django_db
def test_model_student_assignment_final_score_penalty_assignment_format():
    assignment = AssignmentFactory(weight=1, maximum_score=10,
                                   submission_type=AssignmentFormat.PENALTY)
    student_assignment = StudentAssignment(assignment=assignment,
                                           score=Decimal('2.34'),
                                           penalty=Decimal('0.22'))
    assert student_assignment.final_score == -Decimal('2.34')
    # Real penalty value in a score field
    student_assignment.score = None
    student_assignment.penalty = Decimal('0.33')
    assert student_assignment.final_score is None
    student_assignment.penalty = None
    assert student_assignment.final_score is None


@pytest.mark.django_db
def test_model_student_assignment_weighted_score():
    assignment = AssignmentFactory(weight=1, maximum_score=10)
    student_assignment = StudentAssignment(assignment=assignment, score=2)
    assert student_assignment.weighted_score == 2
    assignment.weight = Decimal('.5')
    assert student_assignment.weighted_score == 1
    assignment.weight = Decimal('0.00')
    assert student_assignment.weighted_score == 0
    assignment.weight = Decimal('0.01')
    assert student_assignment.weighted_score == Decimal('0.02')
    student_assignment.score = Decimal(0)
    assert student_assignment.weighted_score == Decimal(0)


@pytest.mark.django_db
def test_model_student_assignment_weighted_final_score():
    assignment = AssignmentFactory(weight=1, maximum_score=10)
    student_assignment = StudentAssignment(assignment=assignment, score=None,
                                           penalty=None)
    assert student_assignment.final_score is None
    assert student_assignment.weighted_final_score is None
    student_assignment.score = 2
    assert student_assignment.weighted_final_score == 2
    assignment.weight = Decimal('.5')
    assert student_assignment.weighted_final_score == 1
    assignment.weight = Decimal('0.00')
    assert student_assignment.weighted_final_score == 0
    assignment.weight = Decimal('0.01')
    assert student_assignment.weighted_final_score == Decimal('0.02')
    student_assignment.score = Decimal(0)
    assert student_assignment.weighted_final_score == Decimal(0)


@pytest.mark.django_db
def test_first_comment_after_deadline(client):
    dt = datetime.datetime(2017, 1, 1, 23, 58, 0, 0, tzinfo=pytz.UTC)
    assignment = AssignmentFactory(deadline_at=dt)
    sa = StudentAssignmentFactory(assignment=assignment)
    student = sa.student
    comment = AssignmentCommentFactory(student_assignment=sa,
                                       author=student,
                                       created=dt)
    client.login(student)
    response = client.get(sa.get_student_url())
    assert response.status_code == 200
    # Consider last min in favor of student
    assert response.context['first_comment_after_deadline'] is None
    assert smart_bytes('<hr class="deadline">') not in response.content
    comment.created = dt + datetime.timedelta(minutes=1)
    comment.save()
    response = client.get(sa.get_student_url())
    assert response.context['first_comment_after_deadline'] == comment
    assert smart_bytes('<hr class="deadline">') in response.content


@pytest.mark.django_db
def test_assignment_attachment_permissions(curator, client, tmpdir):
    teacher = TeacherFactory()
    client.login(teacher)
    term = SemesterFactory.create_current()
    course = CourseFactory(semester=term, teachers=[teacher])
    form = factory.build(dict, FACTORY_CLASS=AssignmentFactory)
    tmp_file = tmpdir.mkdir("attachment").join("attachment.txt")
    tmp_file.write("content")
    form.update({
        'course': course.pk,
        'attachments': tmp_file.open(),
        'time_zone': 'UTC',
        'opens_at_0': form['opens_at'].strftime(DATE_FORMAT_RU),
        'opens_at_1': form['opens_at'].strftime(TIME_FORMAT_RU),
        'deadline_at_0': form['deadline_at'].strftime(DATE_FORMAT_RU),
        'deadline_at_1': form['deadline_at'].strftime(TIME_FORMAT_RU),
        "assignee_mode": AssigneeMode.DISABLED
    })
    url = course.get_create_assignment_url()

    prefixed_form = {f"assignment-{k}": v for k, v in form.items()}
    client.post(url, prefixed_form)
    assert Assignment.objects.count() == 1
    assert AssignmentAttachment.objects.count() == 1
    a_attachment = AssignmentAttachment.objects.first()
    assert a_attachment.attachment.read() == b"content"
    client.logout()
    task_attachment_url = a_attachment.get_download_url()
    response = client.get(task_attachment_url)
    assert response.status_code == 302  # redirect to login view
    student_spb = StudentFactory()
    client.login(student_spb)
    response = client.get(task_attachment_url)
    assert response.status_code == 403  # not enrolled in
    EnrollmentFactory(student=student_spb, course=course)
    response = client.get(task_attachment_url)
    assert response.status_code == 200
    # Should be the same for invited student
    invitee_spb = InvitedStudentFactory()
    client.login(invitee_spb)
    response = client.get(task_attachment_url)
    assert response.status_code == 403
    EnrollmentFactory(student=invitee_spb, course=course)
    response = client.get(task_attachment_url)
    assert response.status_code == 200
    # Check not actual teacher access
    other_teacher = TeacherFactory()
    client.login(other_teacher)
    response = client.get(task_attachment_url)
    assert response.status_code == 403  # not a course teacher (among all terms)
    client.login(teacher)
    response = client.get(task_attachment_url)
    assert response.status_code == 200
    client.login(curator)
    response = client.get(task_attachment_url)
    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("inactive_status", StudentStatuses.inactive_statuses)
def test_assignment_attachment_inactive_student(inactive_status, client,
                                                settings):
    """Inactive student can't view assignment attachments"""
    course = CourseFactory(semester=SemesterFactory.create_current())
    student_spb = StudentFactory()
    a_attachment = AssignmentAttachmentFactory(assignment__course=course)
    EnrollmentFactory(course=course, student=student_spb)
    task_attachment_url = a_attachment.get_download_url()
    client.login(student_spb)
    response = client.get(task_attachment_url)
    assert response.status_code == 200
    student_profile = get_student_profile(student_spb)
    student_profile.status = inactive_status
    student_profile.save()
    response = client.get(task_attachment_url)
    assert response.status_code == 403


@pytest.mark.django_db
def test_create_assignment_admin_form(client):
    """
    Student assignments should be generated after creating assignment.
    """
    client.login(CuratorFactory())
    enrollment = EnrollmentFactory()
    course = enrollment.course
    a = AssignmentFactory.build()
    post_data = {
        'assignment-course': course.pk,
        'assignment-title': a.title,
        "assignment-assignee_mode": AssigneeMode.STUDENT_GROUP_DEFAULT,
        'assignment-submission_type': AssignmentFormat.ONLINE,
        'assignment-text': a.text,
        'assignment-maximum_score': 5,
        'assignment-weight': 1,
        'assignment-time_zone': 'UTC',
        'assignment-opens_at_0': a.opens_at.date().strftime('%d.%m.%Y'),
        'assignment-opens_at_1': '00:00',
        'assignment-deadline_at_0': a.deadline_at.date().strftime('%d.%m.%Y'),
        'assignment-deadline_at_1': '00:00'
    }
    assert StudentAssignment.objects.count() == 0
    url = course.get_create_assignment_url()
    response = client.post(url, post_data)
    assert response.status_code == 302
    assert Assignment.objects.count() == 1
    assert StudentAssignment.objects.count() == 1


@pytest.mark.django_db
def test_download_assignment_attachment(lms_resolver):
    url = reverse('study:download_assignment_attachment',
                  kwargs={"sid": "wrongsid", "file_name": "filename.txt"})
    resolver = lms_resolver(url)
    assert issubclass(resolver.func.view_class, PermissionRequiredMixin)
    assert resolver.func.view_class.permission_required == ViewAssignmentAttachment.name


@pytest.mark.django_db
def test_view_course_assignment_add_btn_visibility(client):
    """
        The add assignment button is displayed only
        if the user has permission to do so.
    """
    teacher, spectator = TeacherFactory.create_batch(2)
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)

    def has_create_assignment_btn(user):
        client.login(user)
        url = course.get_absolute_url()
        html = client.get(url).content.decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        client.logout()
        return soup.find('a', {
            "href": course.get_create_assignment_url()
        }) is not None

    assert has_create_assignment_btn(teacher)
    assert not has_create_assignment_btn(spectator)
