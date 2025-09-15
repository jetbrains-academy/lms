import datetime
from decimal import Decimal

import factory
import pytest
import pytz
from bs4 import BeautifulSoup
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import formats
from django.utils.encoding import smart_bytes

from core.timezone import UTC
from core.timezone.constants import DATE_FORMAT_RU
from core.urls import reverse
from courses.constants import AssigneeMode, AssignmentFormat, AssignmentStatus
from courses.models import Assignment, CourseTeacher, CourseGroupModes
from courses.tests.factories import (
    AssignmentFactory, CourseFactory, CourseNewsFactory, CourseTeacherFactory,
    SemesterFactory, CourseProgramBindingFactory
)
from learning.models import (
    AssignmentComment, AssignmentNotification, CourseNewsNotification, Enrollment,
    StudentAssignment, StudentGroup
)
from learning.services.personal_assignment_service import create_assignment_solution
from learning.tests.factories import (
    AssignmentCommentFactory, EnrollmentFactory, StudentAssignmentFactory
)
from users.tests.factories import StudentFactory, StudentProfileFactory, TeacherFactory, CuratorFactory


def prefixed_form(form_data, prefix: str):
    return {f"{prefix}-{k}": v for k, v in form_data.items()}


@pytest.mark.django_db
def test_create_assignment_conflict_opens_at_deadline(client):
    """
    Deadline should be later than the opening date
    """
    client.login(CuratorFactory())
    course = CourseFactory()
    today = datetime.datetime.now(UTC)
    form = factory.build(dict, FACTORY_CLASS=AssignmentFactory)
    form.update({
        'opens_at_0': today.strftime(DATE_FORMAT_RU),
        'opens_at_1': '01:00',
        'deadline_at_0': today.strftime(DATE_FORMAT_RU),
        'deadline_at_1': '00:00',
        'time_zone': 'UTC',
    })
    url = course.get_create_assignment_url()
    response = client.post(url, prefixed_form(form, "assignment"))
    assert response.status_code == 200
    assert 'deadline_at' in response.context_data['assignment_form'].errors


@pytest.mark.django_db
def test_assignment_public_form(settings, client):
    settings.LANGUAGE_CODE = 'ru'  # formatting depends on locale
    teacher = TeacherFactory()
    course_spb = CourseFactory(teachers=[teacher])
    client.login(teacher)
    form_data = {
        "submission_type": AssignmentFormat.ONLINE,
        "title": "title",
        "text": "text",
        "time_zone": "UTC",
        "opens_at_0": "29.06.2010",
        "opens_at_1": "00:00",
        "deadline_at_0": "29.06.2017",
        "deadline_at_1": "00:00",
        "maximum_score": "5",
        "weight": "1.00",
        "assignee_mode": AssigneeMode.DISABLED
    }
    add_url = course_spb.get_create_assignment_url()
    form_prefixed = prefixed_form(form_data, "assignment")
    response = client.post(add_url, form_prefixed)
    assert response.status_code == 302
    assert Assignment.objects.count() == 1
    assignment = Assignment.objects.first()
    # DB stores datetime values in UTC
    assert assignment.deadline_at.day == 29
    assert assignment.deadline_at.hour == 0
    assert assignment.deadline_at.minute == 0
    assert assignment.course_id == course_spb.pk

    response = client.get(assignment.get_update_url())
    widget_html = response.context_data['assignment_form']['deadline_at'].as_widget()
    widget = BeautifulSoup(widget_html, "html.parser")
    time_input = widget.find('input', {"name": 'assignment-deadline_at_1'})
    assert time_input.get('value') == '00:00'


@pytest.mark.django_db
def test_assignment_detail_deadline_l10n(settings, client):
    settings.LANGUAGE_CODE = 'ru'  # formatting depends on locale
    dt = datetime.datetime(2017, 1, 1, 15, 0, 0, 0, tzinfo=pytz.UTC)
    teacher = TeacherFactory()
    assignment = AssignmentFactory(deadline_at=dt,
                                   time_zone=pytz.timezone('Europe/Moscow'),
                                   course__teachers=[teacher])
    url_for_teacher = assignment.get_teacher_url()
    client.login(teacher)
    response = client.get(url_for_teacher)
    html = BeautifulSoup(response.content, "html.parser")
    # Note: On this page used `naturalday` filter, so use passed datetime
    deadline_str = formats.date_format(assignment.deadline_at_local(),
                                       'd E Y H:i')
    assert deadline_str == "01 января 2017 18:00"
    assert any(deadline_str in s.string for s in html.find_all('p'))
    # Test student submission page
    sa = StudentAssignmentFactory(assignment=assignment)
    response = client.get(sa.get_teacher_url())
    html = BeautifulSoup(response.content, "html.parser")
    # Note: On this page used `naturalday` filter, so use passed datetime
    deadline_str = formats.date_format(assignment.deadline_at_local(),
                                       'd E Y H:i')
    assert deadline_str == "01 января 2017 18:00"
    assert any(
        deadline_str in s.string
        for s in html.find_all('div', {"class": "info-panel-row-value"})
        if s.string
    )


@pytest.mark.django_db
def test_view_student_assignment_detail_update_score(client):
    """
    Make sure we can remove zeroed grade for student assignment and use both
    1.23 and 1,23 formats
    """
    sa = StudentAssignmentFactory()
    teacher = TeacherFactory.create()
    CourseTeacherFactory(course=sa.assignment.course,
                         teacher=teacher)
    sa.assignment.maximum_score = 10
    sa.assignment.save()
    assert sa.score is None
    form = {"review-score": 0,
            "review-score_old": "",
            "review-status": sa.status,
            "review-status_old": sa.status}
    client.login(teacher)
    response = client.post(sa.get_teacher_url(), form, follow=True)
    assert response.status_code == 200
    sa.refresh_from_db()
    assert sa.score == 0
    form = {"review-score": "",
            "review-score_old": 0,
            "review-status": sa.status,
            "review-status_old": sa.status}
    response = client.post(sa.get_teacher_url(), form, follow=True)
    assert response.status_code == 200
    sa.refresh_from_db()
    assert sa.score is None
    form = {"review-score": "1.22",
            "review-score_old": "",
            "review-status": sa.status,
            "review-status_old": sa.status}
    client.post(sa.get_teacher_url(), form, follow=True)
    sa.refresh_from_db()
    assert sa.score == Decimal("1.22")
    form = {"review-score": "2,34",
            "review-score_old": 1.22,
            "review-status": sa.status,
            "review-status_old": sa.status}
    client.post(sa.get_teacher_url(), form, follow=True)
    sa.refresh_from_db()
    assert sa.score == Decimal("2.34")


@pytest.mark.django_db
def test_create_assignment_public_form(client):
    """Create assignments for active enrollments only"""
    ss = StudentFactory.create_batch(3)
    current_semester = SemesterFactory.create_current()
    co = CourseFactory.create(semester=current_semester)
    for student in ss:
        enrollment = EnrollmentFactory.create(student=student, course=co)
    assert Enrollment.objects.count() == 3
    assert StudentAssignment.objects.count() == 0
    assignment = AssignmentFactory.create(course=co)
    assert StudentAssignment.objects.count() == 3
    enrollment.is_deleted = True
    enrollment.save()
    assignment = AssignmentFactory.create(course=co)
    assert StudentAssignment.objects.count() == 5
    assert StudentAssignment.objects.filter(student=enrollment.student,
                                            assignment=assignment).count() == 0
    # Check deadline notifications sent for active enrollments only
    AssignmentNotification.objects.all().delete()
    assignment.deadline_at = assignment.deadline_at - datetime.timedelta(days=1)
    assignment.save()
    enrolled_students = Enrollment.active.count()
    assert enrolled_students == 2
    assert AssignmentNotification.objects.count() == enrolled_students
    CourseNewsNotification.objects.all().delete()
    assert CourseNewsNotification.objects.count() == 0
    CourseNewsFactory.create(course=co)
    assert CourseNewsNotification.objects.count() == enrolled_students


@pytest.mark.django_db
def test_create_assignment_public_form_restricted_to_settings(client, program_cub001, program_nup001):
    teacher = TeacherFactory()
    course = CourseFactory(semester=SemesterFactory.create_current(),
                           teachers=[teacher],
                           group_mode=CourseGroupModes.PROGRAM)
    CourseProgramBindingFactory(course=course, program=program_cub001)
    CourseProgramBindingFactory(course=course, program=program_nup001)
    add_url = course.get_create_assignment_url()
    form_data = {
        "submission_type": AssignmentFormat.ONLINE,
        "title": "title",
        "text": "text",
        "time_zone": "UTC",
        "opens_at_0": "29.06.2010",
        "opens_at_1": "00:00",
        "deadline_at_0": "29.06.2017",
        "deadline_at_1": "00:00",
        "maximum_score": "5",
        "weight": "1.00",
        "assignee_mode": AssigneeMode.DISABLED,
    }
    client.login(teacher)
    response = client.post(add_url, prefixed_form(form_data, "assignment"), follow=True)
    assert response.status_code == 200
    assert Assignment.objects.filter(course=course).count() == 1
    assignment = Assignment.objects.get(course=course)
    assert list(assignment.restricted_to.all()) == []
    assert StudentGroup.objects.filter(course=course).count() == 2
    student_group1, student_group2 = list(StudentGroup.objects.filter(course=course))
    form_data['restricted_to'] = student_group1.pk
    Assignment.objects.filter(course=course).delete()
    response = client.post(add_url, prefixed_form(form_data, "assignment"))
    assert response.status_code == 302
    assert Assignment.objects.filter(course=course).count() == 1
    assignment = Assignment.objects.get(course=course)
    assert assignment.restricted_to.count() == 1
    assert student_group1 in assignment.restricted_to.all()


@pytest.mark.skip("TODO: remove teaching:assignment_comment_create from path")
@pytest.mark.django_db
def test_student_assignment_detail_view_add_comment(client):
    teacher, spectator = TeacherFactory.create_batch(2)
    enrollment = EnrollmentFactory(course__teachers=[teacher])
    CourseTeacherFactory(course=enrollment.course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    student = enrollment.student
    a = AssignmentFactory.create(course=enrollment.course)
    a_s = (StudentAssignment.objects
           .filter(assignment=a, student=student)
           .get())
    teacher_url = a_s.get_teacher_url()
    create_comment_url = reverse("teaching:assignment_comment_create",
                                 kwargs={"pk": a_s.pk})
    form_data = {
        'comment-text': "Test comment without file"
    }
    client.login(spectator)
    response = client.post(create_comment_url, form_data)
    assert response.status_code == 403

    client.login(teacher)
    response = client.post(create_comment_url, form_data)
    assert response.status_code == 302
    assert response.url == teacher_url
    response = client.get(teacher_url)
    assert smart_bytes(form_data['comment-text']) in response.content
    form_data = {
        'comment-text': "Test comment with file",
        'comment-attached_file': SimpleUploadedFile("attachment1.txt",
                                                    b"attachment1_content")
    }
    response = client.post(create_comment_url, form_data)
    assert response.status_code == 302
    assert response.url == teacher_url
    response = client.get(teacher_url)
    assert smart_bytes(form_data['comment-text']) in response.content
    assert smart_bytes('attachment1') in response.content


@pytest.mark.django_db
def test_view_student_assignment_detail_draft_comment_notifications(client, assert_redirect):
    """
    Draft comment shouldn't send any notification until publishing.
    New published comment should replace draft comment record.
    """
    semester = SemesterFactory.create_current()
    student_profile = StudentProfileFactory()
    teacher = TeacherFactory()
    teacher2 = TeacherFactory()
    course = CourseFactory(semester=semester,
                           teachers=[teacher, teacher2])
    EnrollmentFactory(student_profile=student_profile,
                      student=student_profile.user,
                      course=course)
    a = AssignmentFactory.create(course=course)
    sa = (StudentAssignment.objects
          .filter(assignment=a, student=student_profile.user)
          .get())
    client.login(teacher)
    teacher_detail_url = sa.get_teacher_url()
    recipients_count = 1
    assert AssignmentNotification.objects.count() == 1
    n = AssignmentNotification.objects.first()
    assert n.is_about_creation
    # Publish new comment
    AssignmentNotification.objects.all().delete()
    form_data = {
        "review-score": "",
        "review-score_old": "",
        "review-status": sa.status,
        "review-status_old": sa.status,
        'review-text': "Test comment with file",
        'review-attached_file': SimpleUploadedFile("attachment1.txt",
                                                   b"attachment1_content")
    }
    response = client.post(teacher_detail_url, form_data)
    assert_redirect(response, teacher_detail_url)
    response = client.get(teacher_detail_url)
    assert smart_bytes(form_data['review-text']) in response.content
    assert smart_bytes('attachment1') in response.content
    assert AssignmentNotification.objects.count() == recipients_count
    # Create draft message
    assert AssignmentComment.objects.count() == 1
    AssignmentNotification.objects.all().delete()
    form_data = {
        "review-score": "",
        "review-score_old": "",
        "review-status": sa.status,
        "review-status_old": sa.status,
        'review-text': "Test comment 2 with file",
        'review-attached_file': SimpleUploadedFile("a.txt", b"a_content"),
        'save-draft': 'Submit button text'
    }
    response = client.post(teacher_detail_url, form_data)
    assert_redirect(response, teacher_detail_url)
    assert AssignmentComment.objects.count() == 2
    assert AssignmentNotification.objects.count() == 0
    response = client.get(teacher_detail_url)
    assert 'review_form' in response.context_data
    form = response.context_data['review_form']
    assert form_data['review-text'] == form['text'].value()
    # TODO: write a test to save the file in draft
    #  after the bug with its disappearance will be fixed
    draft = AssignmentComment.objects.get(text=form_data['review-text'])
    assert not draft.is_published
    # Publish another draft comment - this one should override the previous one
    # Make sure it won't touch draft comments from other users
    teacher2_draft = AssignmentCommentFactory(author=teacher2,
                                              student_assignment=sa,
                                              is_published=False)
    assert AssignmentComment.published.count() == 1
    form_data = {
        "review-score": "",
        "review-score_old": "",
        "review-status": sa.status,
        "review-status_old": sa.status,
        'review-text': "Updated test comment 2 with file",
        'review-attached_file': SimpleUploadedFile("test_file_b.txt", b"b_content"),
    }
    response = client.post(teacher_detail_url, form_data)
    assert_redirect(response, teacher_detail_url)
    assert AssignmentComment.published.count() == 2
    assert AssignmentNotification.objects.count() == recipients_count
    draft.refresh_from_db()
    assert draft.is_published
    assert draft.attached_file_name.startswith('test_file_b')
    teacher2_draft.refresh_from_db()
    assert not teacher2_draft.is_published


@pytest.mark.django_db
def test_view_student_assignment_detail_draft_review_remembers_score_and_status(client, assert_redirect):
    """
    Draft comment shouldn't update StudentAssignment score and status.
    It should remember this and paste it into the form next time
    """
    teacher = TeacherFactory()
    course = CourseFactory(teachers=[teacher])
    sa = StudentAssignmentFactory(assignment__course=course,
                                  assignment__maximum_score=5)
    client.login(teacher)
    url = sa.get_teacher_url()

    # providing only score is ok
    form_data = {
        "review-score": 1,
        "review-score_old": "",
        "review-status": sa.status,
        "review-status_old": sa.status,
        'review-text': "",
        'review-attached_file': "",
        'save-draft': 'Submit button text'
    }
    response = client.post(url, data=form_data, follow=True)
    assert 'review_form' in response.context_data
    form = response.context_data['review_form']
    assert form['score'].value() == 1
    sa.refresh_from_db()
    assert sa.score is None

    # providing only status is ok
    form_data = {
        "review-score": "",
        "review-score_old": "",
        "review-status": AssignmentStatus.ON_CHECKING,
        "review-status_old": sa.status,
        'review-text': "",
        'review-attached_file': "",
        'save-draft': 'Submit button text'
    }
    response = client.post(url, data=form_data, follow=True)
    assert 'review_form' in response.context_data
    form = response.context_data['review_form']
    assert form['status'].value() == AssignmentStatus.ON_CHECKING
    sa.refresh_from_db()
    assert sa.status == AssignmentStatus.NOT_SUBMITTED

    form_data = {
        "review-score": 2,
        "review-score_old": "",
        "review-status": AssignmentStatus.NEED_FIXES,
        "review-status_old": sa.status,
        'review-text': "some text",
        'review-attached_file': "",
        'save-draft': 'Submit button text'
    }
    response = client.post(url, data=form_data, follow=True)
    assert 'review_form' in response.context_data
    form = response.context_data['review_form']
    assert form['score'].value() == form_data['review-score']
    assert form['status'].value() == form_data['review-status']
    assert form['text'].value() == form_data['review-text']
    sa.refresh_from_db()
    assert sa.score is None
    assert sa.status == AssignmentStatus.NOT_SUBMITTED

    assert AssignmentComment.objects.filter(is_published=True).count() == 0
    assert AssignmentComment.objects.count() == 1


@pytest.mark.django_db
def test_view_student_assignment_detail_add_review(client, assert_redirect, django_capture_on_commit_callbacks):
    teacher = TeacherFactory()
    course = CourseFactory(teachers=[teacher])
    sa = StudentAssignmentFactory(assignment__course=course,
                                  assignment__maximum_score=5)
    client.login(teacher)
    url = sa.get_teacher_url()

    # empty form
    form_data = {
        "review-score": "",
        "review-score_old": "",
        "review-status": sa.status,
        "review-status_old": sa.status,
        'review-text': "",
        'review-attached_file': "",
        'save-draft': 'Submit button text'
    }
    response = client.post(url, data=form_data)
    assert response.status_code == 200
    assert 'review_form' in response.context_data
    form = response.context_data['review_form']
    assert "Form is empty." in form.non_field_errors()

    # test that review was published and score, status has been changed
    form_data = {
        "review-score": 1,
        "review-score_old": "",
        "review-status": AssignmentStatus.ON_CHECKING,
        "review-status_old": sa.status,
        'review-text': "review-text",
        'review-attached_file': SimpleUploadedFile("some_attachment.txt", b"content"),
    }
    response = client.post(url, data=form_data, follow=True)
    sa.refresh_from_db()
    assert sa.score == 1
    assert sa.status == AssignmentStatus.ON_CHECKING
    comments = AssignmentComment.objects.filter(is_published=True)
    assert comments.count() == 1
    comment = comments.get()
    assert form_data['review-text'] in comment.text
    assert smart_bytes(form_data['review-text']) in response.content
    assert smart_bytes("some_attachment") in response.content

    # test wrong score_old
    # it also covers concurrent update
    sa.refresh_from_db()
    form_data = {
        "review-score": 1,
        "review-score_old": "",
        "review-status": AssignmentStatus.COMPLETED,
        "review-status_old": sa.status,
        'review-text': "review-text",
        'review-attached_file': "",
    }
    response = client.post(url, data=form_data)
    assert response.status_code == 200
    assert 'review_form' in response.context_data
    sa.refresh_from_db()
    assert sa.score == 1
    assert sa.status == AssignmentStatus.ON_CHECKING
    assert AssignmentComment.objects.count() == 1

    # test wrong old status
    # it also covers concurrent update
    form_data = {
        "review-score": 2,
        "review-score_old": 1,
        "review-status": AssignmentStatus.NEED_FIXES,
        "review-status_old": AssignmentStatus.COMPLETED,
        'review-text': "review-text",
        'review-attached_file': "",
    }
    response = client.post(url, data=form_data)
    assert response.status_code == 200
    assert 'review_form' in response.context_data
    assert AssignmentComment.objects.count() == 1
    sa.refresh_from_db()
    assert sa.score == 1
    assert sa.status == AssignmentStatus.ON_CHECKING

    with django_capture_on_commit_callbacks(execute=True):
        create_assignment_solution(personal_assignment=sa,
                                   created_by=sa.student,
                                   message="solution")
    sa.refresh_from_db()
    # Provided forbidden status
    form_data = {
        "review-score": 3,
        "review-score_old": 1,
        # AssignmentStatus.NOT_SUBMITTED is not allowed
        "review-status": AssignmentStatus.NOT_SUBMITTED,
        "review-status_old": AssignmentStatus.ON_CHECKING,
        'review-text': "review-text",
        'review-attached_file': "",
    }
    response = client.post(url, data=form_data)
    assert response.status_code == 200
    assert 'review_form' in response.context_data
    form = response.context_data['review_form']
    assert 'status' in form.errors and len(form.errors['status']) == 1
    expected_error = "Please select a valid status"
    assert expected_error == form.errors['status'][0]
    # one was published by teacher above and one from student
    assert AssignmentComment.objects.count() == 2
    sa.refresh_from_db()
    assert sa.score == 1
    assert sa.status == AssignmentStatus.ON_CHECKING


__has_need_fixes = [AssignmentFormat.ONLINE]


@pytest.mark.parametrize('assignment_format', __has_need_fixes)
@pytest.mark.django_db
def test_view_form_assignment_review_status_choices(client, assignment_format):
    teacher = TeacherFactory()
    course = CourseFactory(teachers=[teacher])
    sa = StudentAssignmentFactory(assignment__course=course,
                                  assignment__submission_type=assignment_format)
    client.login(teacher)
    url = sa.get_teacher_url()
    form = client.get(url).context_data['review_form']
    values = [choice[0] for choice in form['status'].field.choices]
    expected_statuses = [
        AssignmentStatus.NOT_SUBMITTED,
        AssignmentStatus.ON_CHECKING,
        AssignmentStatus.COMPLETED,
        AssignmentStatus.NEED_FIXES
    ]
    assert len(values) == len(expected_statuses)
    assert set(values) == set(expected_statuses)
    assert form['status'].field.choices == form['status_old'].field.choices


@pytest.mark.parametrize('assignment_format', [v for v in AssignmentFormat.values if v not in __has_need_fixes])
@pytest.mark.django_db
def test_view_form_assignment_review_status_choices(client, assignment_format):
    teacher = TeacherFactory()
    course = CourseFactory(teachers=[teacher])
    sa = StudentAssignmentFactory(assignment__course=course,
                                  assignment__submission_type=assignment_format)
    client.login(teacher)
    url = sa.get_teacher_url()
    form = client.get(url).context_data['review_form']
    values = [choice[0] for choice in form['status'].field.choices]
    expected_statuses = [
        AssignmentStatus.NOT_SUBMITTED,
        AssignmentStatus.ON_CHECKING,
        AssignmentStatus.COMPLETED
    ]
    assert len(values) == len(expected_statuses)
    assert set(values) == set(expected_statuses)
    assert form['status'].field.choices == form['status_old'].field.choices
