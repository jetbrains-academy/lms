import csv
import datetime
import io

import pytest
import pytz
from bs4 import BeautifulSoup
from django.utils.encoding import smart_bytes

from auth.mixins import PermissionRequiredMixin
from core.timezone import now_local
from core.urls import reverse
from courses.constants import AssignmentFormat, AssignmentStatus
from courses.models import CourseGroupModes, CourseTeacher
from courses.permissions import ViewAssignment
from courses.tests.factories import (
    AssignmentFactory, CourseFactory, CourseTeacherFactory, SemesterFactory
)
from learning.models import StudentAssignment, AssignmentSubmissionTypes
from learning.permissions import ViewStudentAssignment, ViewStudentAssignmentList
from learning.services.personal_assignment_service import create_assignment_solution, create_personal_assignment_review
from learning.settings import AssignmentScoreUpdateSource
from learning.tests.factories import (
    AssignmentCommentFactory, EnrollmentFactory, StudentAssignmentFactory
)
from users.tests.factories import CuratorFactory, StudentFactory, TeacherFactory


@pytest.mark.django_db
def test_teaching_index_page_smoke(client):
    """Just to make sure this view doesn't return 50x error"""
    response = client.get(reverse("teaching:base"))
    assert response.status_code == 302


@pytest.mark.django_db
def test_assignments_check_queue_view_permissions(client, lms_resolver,
                                                  assert_login_redirect):
    from auth.permissions import perm_registry
    teacher = TeacherFactory()
    student = StudentFactory()
    url = reverse('teaching:assignments_check_queue')
    resolver = lms_resolver(url)
    assert issubclass(resolver.func.view_class, PermissionRequiredMixin)
    assert resolver.func.view_class.permission_required == ViewStudentAssignmentList.name
    assert resolver.func.view_class.permission_required in perm_registry
    assert_login_redirect(url, method='get')
    client.login(student)
    response = client.get(url)
    assert response.status_code == 403
    client.login(teacher)
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_view_assignments_check_queue(settings, client):
    teacher = TeacherFactory(time_zone=pytz.timezone('Asia/Novosibirsk'))
    client.login(teacher)
    url = reverse('teaching:assignments_check_queue')
    response = client.get(url)
    assert response.status_code == 200
    assert not len(response.context_data)
    term = SemesterFactory(year=2018)
    course = CourseFactory(semester=term, teachers=[teacher],
                           group_mode=CourseGroupModes.MANUAL)
    response = client.get(url)
    assert 'app_data' in response.context_data
    app_data = response.context_data['app_data']
    assert 'courseOptions' in app_data['props']
    assert len(app_data['props']['courseOptions']) == 1
    assert course.pk == app_data['state']['course']
    assert app_data['state']['selectedAssignments'] == []
    assert len(app_data['props']['courseTeachers']) == 2
    assert app_data['props']['courseTeachers'][0]['value'] == 'unset'
    course_teacher = CourseTeacher.objects.get(course=course, teacher=teacher)
    assert app_data['props']['courseTeachers'][1]['value'] == course_teacher.pk
    assert app_data['props']['timeZone'] == str(teacher.time_zone)
    assert 'csrfToken' in app_data['props']
    # Test course input
    course_other = CourseFactory(semester=term,
                                 group_mode=CourseGroupModes.MANUAL)
    response = client.get(f"{url}?course={course_other.pk}")
    assert response.status_code == 302
    term_prev = SemesterFactory(year=2017)
    course_prev = CourseFactory(semester=term_prev, teachers=[teacher],
                                group_mode=CourseGroupModes.MANUAL)
    response = client.get(url)
    app_data = response.context_data['app_data']
    assert len(app_data['props']['courseOptions']) == 2
    assert app_data['props']['courseOptions'][0]['value'] == course.pk
    assert len(app_data['props']['courseGroups']) == 1  # default group


@pytest.mark.django_db
def test_view_assignment_detail_permissions(client, lms_resolver,
                                            assert_login_redirect):
    from auth.permissions import perm_registry
    teacher = TeacherFactory()
    student = StudentFactory()
    assignment = AssignmentFactory(course__teachers=[teacher])
    url = assignment.get_teacher_url()
    resolver = lms_resolver(url)
    assert issubclass(resolver.func.view_class, PermissionRequiredMixin)
    assert resolver.func.view_class.permission_required == ViewAssignment.name
    assert resolver.func.view_class.permission_required in perm_registry
    assert_login_redirect(url, method='get')
    client.login(student)
    response = client.get(url)
    assert response.status_code == 403
    client.login(teacher)
    response = client.get(url)
    assert response.status_code == 200
    client.login(CuratorFactory())
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_view_student_assignment_detail_permissions(client, lms_resolver,
                                                    assert_login_redirect,
                                                    assert_redirect):
    from auth.permissions import perm_registry
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    student = StudentFactory()
    today = now_local(student.time_zone).date()
    next_day = today + datetime.timedelta(days=1)
    course = CourseFactory(teachers=[teacher], completed_at=next_day)
    CourseTeacherFactory(course=course, teacher=spectator, roles=CourseTeacher.roles.spectator)
    student_assignment = StudentAssignmentFactory(student=student,
                                                  assignment__course=course)
    url = student_assignment.get_teacher_url()
    resolver = lms_resolver(url)
    assert issubclass(resolver.func.view_class, PermissionRequiredMixin)
    assert resolver.func.view_class.permission_required == ViewStudentAssignment.name
    assert resolver.func.view_class.permission_required in perm_registry

    assert_login_redirect(url, method='get')
    assert_login_redirect(url, method='post')

    client.login(student)
    response = client.get(url)
    assert_redirect(response, student_assignment.get_student_url())
    assert_login_redirect(url, method='post')

    client.login(teacher_other)
    assert_login_redirect(url, method='get')
    assert_login_redirect(url, method='post')

    client.login(spectator)
    assert_login_redirect(url, method='get')
    assert_login_redirect(url, method='post')

    client.login(teacher)
    response = client.get(url)
    assert response.status_code == 200
    response = client.post(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_assignment_detail_view_details(client):
    teacher = TeacherFactory()
    student = StudentFactory()
    s = SemesterFactory.create_current()
    co = CourseFactory.create(semester=s, teachers=[teacher])
    a = AssignmentFactory.create(course=co)
    client.login(teacher)
    url = a.get_teacher_url()
    response = client.get(url)
    assert response.context_data['assignment'] == a
    assert len(response.context_data['a_s_list']) == 0
    EnrollmentFactory.create(student=student, course=co)
    a_s = StudentAssignment.objects.get(student=student, assignment=a)
    response = client.get(url)
    assert response.context_data['assignment'] == a
    assert {a_s} == set(response.context_data['a_s_list'])
    assert len(response.context_data['a_s_list']) == 1


@pytest.mark.django_db
def test_assignment_contents(client):
    teacher = TeacherFactory()
    student = StudentFactory()
    co = CourseFactory.create(teachers=[teacher])
    EnrollmentFactory.create(student=student, course=co)
    a = AssignmentFactory.create(course=co)
    a_s = (StudentAssignment.objects
           .get(assignment=a, student=student))
    client.login(teacher)
    assert smart_bytes(a.text) in client.get(a_s.get_teacher_url()).content


@pytest.mark.django_db
def test_student_assignment_detail_view_context_next_unchecked(client, django_capture_on_commit_callbacks):
    teacher = TeacherFactory()
    student = StudentFactory()
    co = CourseFactory.create(teachers=[teacher])
    co_other = CourseFactory.create()
    EnrollmentFactory.create(student=student, course=co)
    EnrollmentFactory.create(student=student, course=co_other)
    a1, a2 = AssignmentFactory.create_batch(2, course=co)
    a_other = AssignmentFactory.create(course=co_other)
    a_s1 = (StudentAssignment.objects
            .get(assignment=a1, student=student))
    a_s2 = (StudentAssignment.objects
            .get(assignment=a2, student=student))
    a_s_other = (StudentAssignment.objects
                 .get(assignment=a_other, student=student))
    url1 = a_s1.get_teacher_url()
    url2 = a_s2.get_teacher_url()
    client.login(teacher)
    assert client.get(url1).context_data['next_student_assignment'] is None
    assert client.get(url2).context_data['next_student_assignment'] is None
    with django_capture_on_commit_callbacks(execute=True):
        for student_assignment in [a_s1, a_s2]:
            create_assignment_solution(personal_assignment=student_assignment,
                                       created_by=student_assignment.student,
                                       message="solution")
    assert client.get(url1).context_data['next_student_assignment'] == a_s2
    assert client.get(url2).context_data['next_student_assignment'] == a_s1


@pytest.mark.django_db
def test_gradebook_list(client, mocker, assert_redirect):
    # This test will fail if current term is of a summer type since we
    # omit summer semesters in the gradebook list view
    mocked = mocker.patch('courses.utils.now_local')
    msk_tz = pytz.timezone("Europe/Moscow")
    mocked.return_value = datetime.datetime(2021, 5, 1, 12, 0, tzinfo=msk_tz)
    teacher = TeacherFactory()
    client.login(teacher)
    gradebooks_url = reverse("teaching:gradebook_list")
    response = client.get(gradebooks_url)
    assert response.status_code == 200
    # Redirect if there is only one course in the current term
    semester = SemesterFactory.create_current()
    course = CourseFactory(semester=semester, teachers=[teacher])
    response = client.get(gradebooks_url)
    assert_redirect(response, course.get_gradebook_url())
    course2 = CourseFactory(semester=semester, teachers=[teacher])
    response = client.get(gradebooks_url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_student_assignment_detail_view_context_assignee_list(client):
    teacher, spectator, organizer = TeacherFactory.create_batch(3)
    co = CourseFactory.create()
    ct_lec = CourseTeacherFactory(course=co, teacher=teacher,
                                  roles=CourseTeacher.roles.lecturer)
    ct_org = CourseTeacherFactory(course=co, teacher=organizer,
                                  roles=CourseTeacher.roles.organizer)
    CourseTeacherFactory(course=co, teacher=spectator, roles=CourseTeacher.roles.spectator)
    student = StudentFactory()
    EnrollmentFactory.create(student=student, course=co)
    a = AssignmentFactory.create(course=co, maximum_score=13)
    a_s = (StudentAssignment.objects
           .get(assignment=a, student=student))
    url = a_s.get_teacher_url()
    client.login(teacher)
    actual_teachers = client.get(url).context_data['assignee_teachers']
    assert len(actual_teachers) == 2
    assert {ct_lec, ct_org} == set(actual_teachers)


@pytest.mark.django_db
def test_view_student_assignment_detail_forbidden_statuses_disabled(client):
    teacher = TeacherFactory()
    course = CourseFactory(teachers=[teacher])
    sa = StudentAssignmentFactory(assignment__course=course,
                                  assignment__maximum_score=5)
    create_assignment_solution(personal_assignment=sa,
                               created_by=sa.student,
                               message="solution")
    sa.refresh_from_db()
    client.login(teacher)
    url = sa.get_teacher_url()
    response = client.get(url)
    soup = BeautifulSoup(response.content, "html.parser")
    widget = soup.find("select", attrs={"id": "id_review-status"})
    for option in widget.findChildren("option"):
        db_value = option['value']
        should_be_disabled = not sa.is_status_transition_allowed(db_value)
        is_disabled = option.has_attr('disabled')
        assert should_be_disabled == is_disabled


@pytest.mark.django_db
def test_assignments_check_queue_view_default_selected_assignment(client):
    teacher = TeacherFactory()
    course = CourseFactory(teachers=[teacher])
    online_assignments = AssignmentFactory.create_batch(size=3,
                                                        course=course,
                                                        submission_type=AssignmentFormat.ONLINE)
    AssignmentFactory(course=course, submission_type=AssignmentFormat.NO_SUBMIT)
    AssignmentFactory(course=course, submission_type=AssignmentFormat.PENALTY)
    AssignmentFactory(course=course, submission_type=AssignmentFormat.EXTERNAL)
    client.login(teacher)
    url = reverse('teaching:assignments_check_queue')
    response = client.get(f"{url}?course={course.pk}")
    data = response.context_data['app_data']['state']
    selected_assignments = set(data['selectedAssignments'])
    expected_selected = set(a.pk for a in online_assignments)
    assert expected_selected == selected_assignments


@pytest.mark.django_db
def test_view_assignment_status_log_csv_permission(client, lms_resolver, assert_login_redirect):
    from auth.permissions import perm_registry
    teacher = TeacherFactory()
    student = StudentFactory()
    course = CourseFactory(teachers=[teacher])
    EnrollmentFactory(course=course, student=student)
    assignment = AssignmentFactory(course=course,
                                   submission_type=AssignmentFormat.ONLINE)
    url = reverse('teaching:assignment_status_log_csv', args=[assignment.pk])
    resolver = lms_resolver(url)
    assert issubclass(resolver.func.view_class, PermissionRequiredMixin)
    assert resolver.func.view_class.permission_required == ViewAssignment.name
    assert resolver.func.view_class.permission_required in perm_registry
    assert_login_redirect(url, method='get')
    client.login(student)
    response = client.get(url)
    assert response.status_code == 403
    client.login(teacher)
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_view_assignment_status_log_csv_wrong_format(client, lms_resolver, assert_login_redirect):
    teacher = TeacherFactory()
    student = StudentFactory()
    course = CourseFactory(teachers=[teacher])
    EnrollmentFactory(course=course, student=student)
    assignment = AssignmentFactory(course=course,
                                   submission_type=AssignmentFormat.NO_SUBMIT)
    url = reverse('teaching:assignment_status_log_csv', args=[assignment.pk])
    client.login(teacher)
    response = client.get(url)
    assert response.status_code == 400


@pytest.mark.django_db
def test_view_assignment_status_log_csv_online_assignments(client):
    teacher = TeacherFactory()
    student_one, student_two = StudentFactory.create_batch(2)
    course = CourseFactory(teachers=[teacher])
    EnrollmentFactory(course=course, student=student_one)
    EnrollmentFactory(course=course, student=student_two)
    assignment = AssignmentFactory(course=course, submission_type=AssignmentFormat.ONLINE)
    csv_download_url = reverse('teaching:assignment_status_log_csv', args=[assignment.pk])
    client.login(teacher)
    table_headers = [
        "student",
        "student_id",
        "task",
        "comment_author",
        "comment_author_id",
        "action",
        "comment_posted_ISO"
    ]
    response = client.get(csv_download_url)
    assert response.status_code == 200
    assert response['Content-Type'] == 'text/csv; charset=utf-8'
    status_log_csv = response.content.decode('utf-8')
    data = [s for s in csv.reader(io.StringIO(status_log_csv)) if s]
    assert data == [table_headers]

    sa_one = StudentAssignment.objects.get(student=student_one)
    sa_two = StudentAssignment.objects.get(student=student_two)

    # just student comment
    AssignmentCommentFactory(student_assignment=sa_one, author=student_one)
    status_log_csv = client.get(csv_download_url).content.decode('utf-8')
    data = [s for s in csv.reader(io.StringIO(status_log_csv)) if s]
    assert data == [table_headers]

    AssignmentCommentFactory(student_assignment=sa_one, author=student_one,
                             type=AssignmentSubmissionTypes.SOLUTION)
    status_log_csv = client.get(csv_download_url).content.decode('utf-8')
    data = [s for s in csv.reader(io.StringIO(status_log_csv)) if s]
    expected_created_student1_row = [
        student_one.get_short_name(),
        str(student_one.id),
        assignment.title,
        student_one.get_short_name(),
        str(student_one.id),
        'Solution submitted for review',
    ]
    assert len(data) == 2
    assert data[1][:-1] == expected_created_student1_row

    # submission
    AssignmentCommentFactory(student_assignment=sa_two, author=student_two,
                             type=AssignmentSubmissionTypes.SOLUTION)
    status_log_csv = client.get(csv_download_url).content.decode('utf-8')
    data = [s for s in csv.reader(io.StringIO(status_log_csv)) if s]
    expected_created_student2_row = [
        student_two.get_short_name(),
        str(student_two.id),
        assignment.title,
        student_two.get_short_name(),
        str(student_two.id),
        'Solution submitted for review',
    ]
    assert len(data) == 3
    assert data[1][:-1] == expected_created_student1_row
    assert data[2][:-1] == expected_created_student2_row

    # just teacher comment
    create_personal_assignment_review(student_assignment=sa_one,
                                      reviewer=teacher,
                                      is_draft=False,
                                      message="Just a comment",
                                      score_old=sa_one.score,
                                      score_new=sa_one.score,
                                      status_old=sa_one.status,
                                      status_new=sa_one.status,
                                      source=AssignmentScoreUpdateSource.FORM_ASSIGNMENT
                                      )
    status_log_csv = client.get(csv_download_url).content.decode('utf-8')
    data = [s for s in csv.reader(io.StringIO(status_log_csv)) if s]
    assert len(data) == 3
    assert data[1][:-1] == expected_created_student1_row
    assert data[2][:-1] == expected_created_student2_row

    # review with need fixes
    create_personal_assignment_review(student_assignment=sa_one,
                                      reviewer=teacher,
                                      is_draft=False,
                                      message="",
                                      score_old=sa_one.score,
                                      score_new=sa_one.score,
                                      status_old=sa_one.status,
                                      status_new=AssignmentStatus.NEED_FIXES,
                                      source=AssignmentScoreUpdateSource.FORM_ASSIGNMENT
                                      )
    status_log_csv = client.get(csv_download_url).content.decode('utf-8')
    data = [s for s in csv.reader(io.StringIO(status_log_csv)) if s]
    expected_need_fixes_row = [
        student_one.get_short_name(),
        str(student_one.id),
        assignment.title,
        teacher.get_short_name(),
        str(teacher.id),
        'New comment received from reviewer'
    ]
    assert len(data) == 4
    # order [student, created_timestamp]
    assert data[1][:-1] == expected_created_student1_row
    assert data[2][:-1] == expected_need_fixes_row
    assert data[3][:-1] == expected_created_student2_row

    # review with completed
    create_personal_assignment_review(student_assignment=sa_two,
                                      reviewer=teacher,
                                      is_draft=False,
                                      message="",
                                      score_old=sa_two.score,
                                      score_new=sa_two.score,
                                      status_old=sa_two.status,
                                      status_new=AssignmentStatus.COMPLETED,
                                      source=AssignmentScoreUpdateSource.FORM_ASSIGNMENT
                                      )
    status_log_csv = client.get(csv_download_url).content.decode('utf-8')
    data = [s for s in csv.reader(io.StringIO(status_log_csv)) if s]
    expected_completed_row = [
        student_two.get_short_name(),
        str(student_two.id),
        assignment.title,
        teacher.get_short_name(),
        str(teacher.id),
        'Grade updated'
    ]
    assert len(data) == 5
    assert data[1][:-1] == expected_created_student1_row
    assert data[2][:-1] == expected_need_fixes_row
    assert data[3][:-1] == expected_created_student2_row
    assert data[4][:-1] == expected_completed_row
