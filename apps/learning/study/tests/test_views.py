import datetime
from datetime import timedelta

import pytest
from bs4 import BeautifulSoup
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.utils.encoding import smart_bytes

from auth.mixins import PermissionRequiredMixin
from core.tests.factories import AcademicProgramRunFactory
from core.urls import reverse
from courses.constants import AssigneeMode, AssignmentFormat, AssignmentStatus
from courses.models import CourseTeacher
from courses.tests.factories import (
    AssignmentFactory, CourseFactory, CourseTeacherFactory, SemesterFactory, CourseProgramBindingFactory
)
from learning.invitation.views import create_invited_profile
from learning.models import (
    AssignmentComment, AssignmentNotification, StudentAssignment
)
from learning.permissions import ViewCourses, ViewOwnStudentAssignment
from learning.services.jba_service import JbaService
from learning.settings import StudentStatuses
from learning.tests.factories import (
    AssignmentCommentFactory, CourseInvitationBindingFactory, EnrollmentFactory, StudentAssignmentFactory
)
from learning.tests.jba.test_jba_submission_service import (
    KOTLIN_KOANS_ID,
    mock_jba_service,
    HELLO_WORLD_TASK_ID,
    TEST_JBA_ACCOUNT,
)
from users.models import StudentTypes, StudentProfile
from users.services import update_student_status
from users.tests.factories import (
    StudentFactory, StudentProfileFactory, TeacherFactory, UserFactory, CuratorFactory
)


@pytest.mark.django_db
def test_view_student_assignment_detail_permissions(client, lms_resolver,
                                                    assert_login_redirect):
    from auth.permissions import perm_registry
    teacher = TeacherFactory()
    student = StudentFactory()
    course = CourseFactory(teachers=[teacher],
                           semester=SemesterFactory.create_current())
    AssignmentFactory(course=course)
    EnrollmentFactory(student=student, course=course)
    student_assignment = StudentAssignment.objects.get(student=student)
    url = student_assignment.get_student_url()
    resolver = lms_resolver(url)
    assert issubclass(resolver.func.view_class, PermissionRequiredMixin)
    assert resolver.func.view_class.permission_required == ViewOwnStudentAssignment.name
    assert resolver.func.view_class.permission_required in perm_registry
    assert_login_redirect(url, method='get')
    client.login(student)
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_view_student_assignment_detail_handle_no_permission(client):
    teacher = TeacherFactory()
    client.login(teacher)
    course = CourseFactory(teachers=[teacher])
    student_assignment = StudentAssignmentFactory(assignment__course=course)
    url = student_assignment.get_student_url()
    response = client.get(url)
    assert response.status_code == 302
    assert response.url == student_assignment.get_teacher_url()


@pytest.mark.django_db
def test_view_personal_assignment_contents(client):
    student_profile = StudentProfileFactory()
    student = student_profile.user
    semester = SemesterFactory.create_current()
    course = CourseFactory(semester=semester)
    EnrollmentFactory(student_profile=student_profile,
                      student=student,
                      course=course)
    assignment = AssignmentFactory(course=course)
    student_assignment = (StudentAssignment.objects
                          .filter(assignment=assignment, student=student)
                          .get())
    url = student_assignment.get_student_url()
    client.login(student)
    response = client.get(url)
    assert smart_bytes(assignment.text) in response.content


@pytest.mark.django_db
def test_view_student_assignment_detail_comment(client):
    student_profile = StudentProfileFactory()
    student = student_profile.user
    semester = SemesterFactory.create_current()
    course = CourseFactory(semester=semester)
    EnrollmentFactory(student_profile=student_profile,
                      student=student,
                      course=course)
    assignment = AssignmentFactory(course=course)
    student_assignment = (StudentAssignment.objects
                          .get(assignment=assignment, student=student))
    student_url = student_assignment.get_student_url()
    create_comment_url = reverse("study:assignment_comment_create",
                                 kwargs={"pk": student_assignment.pk})
    form_data = {
        'comment-text': "Test comment without file"
    }
    client.login(student)
    response = client.post(create_comment_url, form_data)
    assert response.status_code == 302
    assert response.url == student_url
    response = client.get(student_url)
    assert smart_bytes(form_data['comment-text']) in response.content
    f = SimpleUploadedFile("attachment1.txt", b"attachment1_content")
    form_data = {
        'comment-text': "Test comment with file",
        'comment-attached_file': f
    }
    response = client.post(create_comment_url, form_data)
    assert response.status_code == 302
    assert response.url == student_url
    response = client.get(student_url)
    assert smart_bytes(form_data['comment-text']) in response.content
    assert smart_bytes('attachment1') in response.content


@pytest.mark.django_db
def test_view_new_comment_on_assignment_page(client, assert_redirect):
    semester = SemesterFactory.create_current()
    student_profile = StudentProfileFactory()
    course = CourseFactory(semester=semester)
    course_teacher1, course_teacher2 = CourseTeacherFactory.create_batch(2, course=course,
                                                                         roles=CourseTeacher.roles.reviewer)
    EnrollmentFactory(student_profile=student_profile,
                      student=student_profile.user,
                      course=course)
    assignment = AssignmentFactory(course=course, assignee_mode=AssigneeMode.MANUAL,
                                   assignees=[course_teacher1, course_teacher2])
    personal_assignment = (StudentAssignment.objects
                           .filter(assignment=assignment, student=student_profile.user)
                           .get())
    client.login(student_profile.user)
    detail_url = personal_assignment.get_student_url()
    create_comment_url = reverse("study:assignment_comment_create",
                                 kwargs={"pk": personal_assignment.pk})
    recipients_count = 2
    assert AssignmentNotification.objects.count() == 1
    n = AssignmentNotification.objects.first()
    assert n.is_about_creation
    # Publish new comment
    AssignmentNotification.objects.all().delete()
    form_data = {
        'comment-text': "Test comment with file",
        'comment-attached_file': SimpleUploadedFile("attachment1.txt", b"attachment1_content")
    }
    response = client.post(create_comment_url, form_data)
    assert_redirect(response, detail_url)
    response = client.get(detail_url)
    assert smart_bytes(form_data['comment-text']) in response.content
    assert smart_bytes('attachment1') in response.content
    assert AssignmentNotification.objects.count() == recipients_count
    # Create new draft comment
    assert AssignmentComment.objects.count() == 1
    AssignmentNotification.objects.all().delete()
    form_data = {
        'comment-text': "Test comment 2 with file",
        'comment-attached_file': SimpleUploadedFile("a.txt", b"a_content"),
        'save-draft': 'Submit button text'
    }
    response = client.post(create_comment_url, form_data)
    assert_redirect(response, detail_url)
    assert AssignmentComment.objects.count() == 2
    assert AssignmentNotification.objects.count() == 0
    response = client.get(detail_url)
    assert 'comment_form' in response.context_data
    form = response.context_data['comment_form']
    assert form_data['comment-text'] == form.instance.text
    rendered_form = BeautifulSoup(str(form), "html.parser")
    file_name = rendered_form.find('span', class_='fileinput-filename')
    assert file_name and file_name.string == form.instance.attached_file_name
    # Publish another comment. This one should override draft comment.
    # But first create draft comment from another teacher and make sure
    # it won't be published on publishing new comment from the first teacher
    teacher2_draft = AssignmentCommentFactory(author=course_teacher2.teacher,
                                              student_assignment=personal_assignment,
                                              is_published=False)
    assert AssignmentComment.published.count() == 1
    draft = AssignmentComment.objects.get(text=form_data['comment-text'])
    form_data = {
        'comment-text': "Updated test comment 2 with file",
        'comment-attached_file': SimpleUploadedFile("test_file_b.txt", b"b_content"),
    }
    response = client.post(create_comment_url, form_data)
    assert_redirect(response, detail_url)
    assert AssignmentComment.published.count() == 2
    assert AssignmentNotification.objects.count() == recipients_count
    draft.refresh_from_db()
    assert draft.is_published
    assert draft.attached_file_name.startswith('test_file_b')
    teacher2_draft.refresh_from_db()
    assert not teacher2_draft.is_published


@pytest.mark.django_db
def test_view_solution_form_is_visible_by_default(client):
    student_profile = StudentProfileFactory()
    student = student_profile.user
    course = CourseFactory(semester=SemesterFactory.create_current(),
                           ask_ttc=False)
    EnrollmentFactory(student_profile=student_profile,
                      student=student,
                      course=course)
    assignment = AssignmentFactory(course=course)
    student_assignment = (StudentAssignment.objects
                          .get(assignment=assignment, student=student))
    student_url = student_assignment.get_student_url()
    client.login(student)
    response = client.get(student_url)
    rendered = BeautifulSoup(response.content, "html.parser")
    button_solution_find = rendered.find(id="add-solution")
    button_comment_find = rendered.find(id="add-comment")
    form_solution_find = rendered.find(id="solution-form-wrapper")
    form_comment_find = rendered.find(id="comment-form-wrapper")
    assert 'active' in button_solution_find.attrs['class']
    assert 'active' not in button_comment_find.attrs['class']
    assert 'hidden' not in form_solution_find.attrs['class']
    assert 'hidden' in form_comment_find.attrs['class']


@pytest.mark.django_db
def test_view_student_assignment_add_solution(client):
    student_profile = StudentProfileFactory()
    student = student_profile.user
    semester = SemesterFactory.create_current()
    course = CourseFactory(semester=semester, ask_ttc=False)
    EnrollmentFactory(student_profile=student_profile,
                      student=student,
                      course=course)
    assignment = AssignmentFactory(course=course)
    student_assignment = (StudentAssignment.objects
                          .get(assignment=assignment, student=student))
    student_url = student_assignment.get_student_url()
    create_solution_url = reverse("study:assignment_solution_create",
                                  kwargs={"pk": student_assignment.pk})
    form_data = {
        'solution-text': "Test comment without file"
    }
    client.login(student)
    response = client.post(create_solution_url, form_data)
    assert response.status_code == 302
    assert response.url == student_url
    response = client.get(student_url)
    assert smart_bytes(form_data['solution-text']) in response.content
    f = SimpleUploadedFile("attachment1.txt", b"attachment1_content")
    form_data = {
        'solution-text': "Test solution with file",
        'solution-attached_file': f
    }
    response = client.post(create_solution_url, form_data)
    assert response.status_code == 302
    assert response.url == student_url
    response = client.get(student_url)
    assert smart_bytes(form_data['solution-text']) in response.content
    assert smart_bytes('attachment1') in response.content
    # Make execution field mandatory
    form_data = {
        'solution-text': 'Test solution',
    }
    course.ask_ttc = True
    course.save()
    response = client.post(create_solution_url, form_data)
    messages = list(get_messages(response.wsgi_request))
    assert len(messages) == 1
    assert 'error' in messages[0].tags
    client.get('/', follow=True)  # Flush messages with middleware
    form_data = {
        'solution-text': 'Test solution',
        'solution-execution_time': '1:12',
    }
    response = client.post(create_solution_url, form_data)
    messages = list(get_messages(response.wsgi_request))
    assert len(messages) == 1
    assert 'success' in messages[0].tags
    student_assignment.refresh_from_db()
    assert student_assignment.execution_time == timedelta(hours=1, minutes=12)
    # Add another solution
    form_data = {
        'solution-text': 'Fixes on test solution',
        'solution-execution_time': '0:34',
    }
    response = client.post(create_solution_url, form_data)
    student_assignment.refresh_from_db()
    assert student_assignment.execution_time == timedelta(hours=1, minutes=46)


@pytest.mark.django_db
def test_view_student_assignment_jba_cant_submit_solutions(client):
    e = EnrollmentFactory()
    assignment = AssignmentFactory(course=e.course, submission_type=AssignmentFormat.JBA)
    student_assignment = (
        StudentAssignment.objects
        .get(assignment=assignment, student=e.student)
    )
    create_solution_url = reverse("study:assignment_solution_create",
                                  kwargs={"pk": student_assignment.pk})
    form_data = {'solution-text': "Test comment without file"}
    client.login(e.student)
    response = client.post(create_solution_url, form_data)
    assert response.status_code == 400


@pytest.mark.django_db
def test_view_student_assignment_jba_no_submissions_help_text(client, mock_jba_service):
    e = EnrollmentFactory(student__jetbrains_account=TEST_JBA_ACCOUNT)
    client.login(e.student)
    assignment = AssignmentFactory(
        course=e.course,
        submission_type=AssignmentFormat.JBA,
        jba_course_id=KOTLIN_KOANS_ID,
    )
    student_assignment = (
        StudentAssignment.objects
        .get(assignment=assignment, student=e.student)
    )
    student_url = student_assignment.get_student_url()

    # No help text initially
    response = client.get(student_url)
    assert response.status_code == 200
    assert b'jba-no-submissions-help-text' not in response.content

    # Assignment progress was updated, no solved tasks found,
    # so help text should be shown
    JbaService.update_current_assignments_progress()
    response = client.get(student_url)
    assert response.status_code == 200
    assert b'jba-no-submissions-help-text' in response.content

    # Assignment progress updated again, task solved, hide it again
    mock_jba_service.solved_tasks = [HELLO_WORLD_TASK_ID]
    JbaService.update_current_assignments_progress()
    response = client.get(student_url)
    assert response.status_code == 200
    assert b'jba-no-submissions-help-text' not in response.content


@pytest.mark.django_db
def test_view_student_assignment_post_solution_for_assignment_without_solutions(client):
    student_profile = StudentProfileFactory()
    student = student_profile.user
    course = CourseFactory(semester=SemesterFactory.create_current(),
                           ask_ttc=False)
    EnrollmentFactory(student_profile=student_profile,
                      student=student,
                      course=course)
    assignment = AssignmentFactory(
        course=course,
        submission_type=AssignmentFormat.NO_SUBMIT)
    student_assignment = (StudentAssignment.objects
                          .get(assignment=assignment, student=student))
    student_url = student_assignment.get_student_url()
    client.login(student)
    response = client.get(student_url)
    assert response.context_data['solution_form'] is None
    create_solution_url = reverse("study:assignment_solution_create",
                                  kwargs={"pk": student_assignment.pk})
    form_data = {
        'solution-text': "Test comment without file"
    }
    response = client.post(create_solution_url, form_data)
    assert response.status_code == 403
    response = client.get(student_url)
    assert smart_bytes(form_data['solution-text']) not in response.content
    html = BeautifulSoup(response.content, "html.parser")
    assert html.find(id="add-solution") is None
    assert html.find(id="solution-form-wrapper") is None


@pytest.mark.django_db
def test_view_student_assignment_comment_author_should_be_resolved(client):
    student = StudentFactory()
    sa = StudentAssignmentFactory(student=student)
    create_comment_url = reverse("study:assignment_comment_create",
                                 kwargs={"pk": sa.pk})
    form_data = {
        'comment-text': "Test comment with file"
    }
    client.login(student)
    client.post(create_comment_url, form_data)
    assert AssignmentComment.objects.count() == 1
    comment = AssignmentComment.objects.first()
    assert comment.author == student
    assert comment.student_assignment == sa


@pytest.mark.django_db
def test_view_assignment_comment_author_cannot_be_modified_by_user(client):
    student1, student2 = StudentFactory.create_batch(2)
    sa1 = StudentAssignmentFactory(student=student1)
    sa2 = StudentAssignmentFactory(student=student2)
    create_comment_url = reverse("study:assignment_comment_create",
                                 kwargs={"pk": sa1.pk})
    form_data = {
        'comment-text': "Test comment with file",
        # Attempt to explicitly override system fields via POST data
        'author': student2.pk,
        'student_assignment': sa2.pk
    }
    client.login(student1)
    client.post(create_comment_url, form_data)
    assert AssignmentComment.objects.count() == 1
    comment = AssignmentComment.objects.first()
    assert comment.author == student1
    assert comment.student_assignment == sa1


@pytest.mark.django_db
def test_view_student_courses_list(
    client, lms_resolver, assert_login_redirect,
    program_cub001, program_run_cub, program_nup001, program_run_nup
):
    url = reverse('study:course_list')
    resolver = lms_resolver(url)
    assert issubclass(resolver.func.view_class, PermissionRequiredMixin)
    assert resolver.func.view_class.permission_required == ViewCourses.name
    student_profile_cub = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    student_cub = student_profile_cub.user
    assert_login_redirect(url)

    client.login(student_cub)
    response = client.get(url)
    assert response.status_code == 200
    assert len(response.context_data['ongoing_rest']) == 0
    assert len(response.context_data['ongoing_enrolled']) == 0
    assert len(response.context_data['archive']) == 0
    semester = SemesterFactory.create_current()
    cos = CourseFactory.create_batch(4, semester=semester)
    cos_available = cos[:2]
    cos_enrolled = cos[2:]
    today = datetime.date.today()
    cos_archived = CourseFactory.create_batch(3, semester=semester, completed_at=today)
    for co in cos_available:
        CourseProgramBindingFactory(course=co, program=program_cub001)
    for co in cos_enrolled:
        EnrollmentFactory.create(student=student_cub,
                                 student_profile=student_profile_cub,
                                 course=co)
    for co in cos_archived:
        EnrollmentFactory.create(student=student_cub,
                                 student_profile=student_profile_cub,
                                 course=co)
    response = client.get(url)
    assert len(cos_enrolled) == len(response.context_data['ongoing_enrolled'])
    assert set(cos_enrolled) == set(response.context_data['ongoing_enrolled'])
    assert len(cos_archived) == len(response.context_data['archive'])
    assert set(cos_archived) == set(response.context_data['archive'])
    assert len(cos_available) == len(response.context_data['ongoing_rest'])
    assert set(cos_available) == set(response.context_data['ongoing_rest'])

    # Add courses from other binding
    co_nup = CourseProgramBindingFactory.create(
        course__semester=semester, program=program_nup001
    ).course
    response = client.get(url)
    assert len(cos_enrolled) == len(response.context_data['ongoing_enrolled'])
    assert len(cos_available) == len(response.context_data['ongoing_rest'])
    assert len(cos_archived) == len(response.context_data['archive'])
    # Test for student from nup
    student_profile_nup = StudentProfileFactory(academic_program_enrollment=program_run_nup)
    student_nup = student_profile_nup.user
    client.login(student_nup)
    CourseProgramBindingFactory.create(course__completed_at=today, program=program_nup001)
    response = client.get(url)
    assert len(response.context_data['ongoing_enrolled']) == 0
    assert len(response.context_data['ongoing_rest']) == 1
    assert set(response.context_data['ongoing_rest']) == {co_nup}
    assert len(response.context_data['archive']) == 0
    # Add open reading, it should be available on compscicenter.ru
    co_open = CourseProgramBindingFactory.create(
        course__semester=semester, program=program_nup001
    ).course
    response = client.get(url)
    assert len(response.context_data['ongoing_enrolled']) == 0
    assert len(response.context_data['ongoing_rest']) == 2
    assert set(response.context_data['ongoing_rest']) == {co_nup, co_open}
    assert len(response.context_data['archive']) == 0


@pytest.mark.django_db
def test_view_student_courses_list_enrollment_closed(
    client, program_cub001, program_run_cub
):
    url = reverse('study:course_list')
    student_profile = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    student = student_profile.user
    client.login(student)
    yesterday = timezone.now() - datetime.timedelta(days=1)

    semester = SemesterFactory.create_current()
    cos = CourseFactory.create_batch(4, semester=semester)
    cos_available = cos[:2]
    cos_enrollment_ended = cos[2:]
    for co in cos_available:
        CourseProgramBindingFactory(course=co, program=program_cub001)
    for co in cos_enrollment_ended:
        CourseProgramBindingFactory(course=co, program=program_cub001, enrollment_end_date=yesterday)
    response = client.get(url)
    assert 0 == len(response.context_data['ongoing_enrolled'])
    assert 0 == len(response.context_data['archive'])
    assert len(cos_available) == len(response.context_data['ongoing_rest'])
    assert set(cos_available) == set(response.context_data['ongoing_rest'])


@pytest.mark.django_db
def test_view_student_courses_list_start_year_filter(client):
    url = reverse('study:course_list')
    program_run = AcademicProgramRunFactory(start_year=2024)
    student_profile = StudentProfileFactory(academic_program_enrollment=program_run)
    student = student_profile.user
    client.login(student)

    cos_available = CourseFactory.create_batch(2)
    cos_unavailable = CourseFactory.create_batch(2)
    for co in cos_available:
        CourseProgramBindingFactory(course=co, program=program_run.program, start_year_filter=[2024])
    for co in cos_unavailable:
        CourseProgramBindingFactory(course=co, program=program_run.program, start_year_filter=[2025])
    response = client.get(url)
    assert 0 == len(response.context_data['ongoing_enrolled'])
    assert 0 == len(response.context_data['archive'])
    assert len(cos_available) == len(response.context_data['ongoing_rest'])
    assert set(cos_available) == set(response.context_data['ongoing_rest'])


@pytest.mark.django_db
def test_view_student_courses_list_as_invited(client, program_cub001, program_run_cub):
    courses_url = reverse('study:course_list')
    current_term = SemesterFactory.create_current()
    student = UserFactory()
    regular_profile = StudentProfileFactory(
        user=student, type=StudentTypes.REGULAR, academic_program_enrollment=program_run_cub
    )
    client.login(student)

    all_courses = CourseFactory.create_batch(3, semester=current_term)
    enrolled, unenrolled, rest = all_courses
    EnrollmentFactory(student=student,
                      student_profile=regular_profile,
                      course=enrolled,
                      course_program_binding__program=program_cub001,
                      grade=1)
    EnrollmentFactory(student=student,
                      student_profile=regular_profile,
                      course=unenrolled,
                      course_program_binding__program=program_cub001,
                      is_deleted=True)
    CourseProgramBindingFactory(course=rest, program=program_cub001)

    archived = CourseFactory(completed_at=datetime.date.today())
    EnrollmentFactory(student=student,
                      student_profile=regular_profile,
                      course=archived,
                      course_program_binding__program=program_cub001)

    response = client.get(courses_url)
    assert len(response.context_data['ongoing_enrolled']) == 1
    assert len(response.context_data['ongoing_rest']) == 2
    assert len(response.context_data['archive']) == 1

    curator = CuratorFactory()
    update_student_status(student_profile=regular_profile,
                          new_status=StudentStatuses.EXPELLED,
                          editor=curator)

    course_invitation = CourseInvitationBindingFactory(course__semester=current_term)
    course = course_invitation.course
    create_invited_profile(student, course_invitation.invitation)
    CourseProgramBindingFactory(course=course, program=program_cub001)
    response = client.get(courses_url)
    assert len(response.context_data['ongoing_enrolled']) == 1
    assert len(response.context_data['ongoing_rest']) == 0
    assert len(response.context_data['archive']) == 1

    client.post(course_invitation.invitation.get_absolute_url())
    response = client.get(courses_url)
    assert len(response.context_data['ongoing_rest']) == 1

    client.post(course.get_enroll_url(), follow=True)
    response = client.get(courses_url)
    assert len(response.context_data['ongoing_enrolled']) == 2
    assert len(response.context_data['ongoing_rest']) == 0
    assert len(response.context_data['archive']) == 1


@pytest.mark.django_db
def test_view_student_courses_list_old_invited_profile(client):
    url = reverse('study:course_list')
    today = datetime.date.today()
    course_invitation = CourseInvitationBindingFactory(course__completed_at=today)
    student = UserFactory()
    create_invited_profile(student, course_invitation.invitation)
    student_profile = StudentProfile.objects.get(user=student)

    prev_term_course = CourseFactory(completed_at=today)
    EnrollmentFactory(course=prev_term_course,
                      student=student,
                      student_profile=student_profile,
                      grade=1)

    client.login(student)
    response = client.get(url)
    assert len(response.context_data['ongoing_enrolled']) == 0
    assert len(response.context_data['ongoing_rest']) == 0
    assert len(response.context_data['archive']) == 1

    course_invitation.invitation.enrolled_students.add(student_profile)
    # Even if student has invitation(not used) in previous term
    # the course should not to appear as archive / ongoing_rest
    response = client.get(url)
    assert len(response.context_data['ongoing_enrolled']) == 0
    assert len(response.context_data['ongoing_rest']) == 0
    assert len(response.context_data['archive']) == 1


@pytest.mark.django_db
def test_view_student_assignment_list_filter_course_choices(client):
    course_one, course_two = CourseFactory.create_batch(2, semester=SemesterFactory.create_current())
    student = StudentFactory()
    EnrollmentFactory(course=course_one, student=student)
    EnrollmentFactory(course=course_two, student=student)
    url = reverse('study:assignment_list')
    client.login(student)
    response = client.get(url)
    assert response.status_code == 200
    filter_form = response.context['filter_form']
    course_choices_pk = set(cc[0] for cc in filter_form.fields['course'].choices)
    assert len(course_choices_pk) == 3
    assert course_choices_pk == {None, course_one.pk, course_two.pk}


@pytest.mark.django_db
def test_view_student_assignment_list_course_filtering(client):
    course_one, course_two = CourseFactory.create_batch(2, semester=SemesterFactory.create_current())
    student = StudentFactory()
    EnrollmentFactory(course=course_one, student=student)
    EnrollmentFactory(course=course_two, student=student)
    a_one = AssignmentFactory(course=course_one)
    a_two = AssignmentFactory(course=course_two)
    sa_one = StudentAssignment.objects.get(student=student, assignment=a_one)
    sa_two = StudentAssignment.objects.get(student=student, assignment=a_two)
    url = reverse('study:assignment_list')
    client.login(student)

    response = client.get(url)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert len(open_assignments) == 2

    form_data = {
        "course": course_one.pk
    }
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert open_assignments == [sa_one]
    assert f'course={course_one.pk}' in response.redirect_chain[-1][0]

    form_data = {
        "course": course_two.pk
    }
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert open_assignments == [sa_two]
    assert f'course={course_two.pk}' in response.redirect_chain[-1][0]

    form_data = {
        "course": ''
    }
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert set(open_assignments) == {sa_one, sa_two}
    assert 'course=' not in response.redirect_chain[-1][0]


@pytest.mark.django_db
def test_view_student_assignment_list_filter_status_choices(client):
    student = StudentFactory()
    url = reverse('study:assignment_list')
    client.login(student)
    response = client.get(url)
    assert response.status_code == 200
    filter_form = response.context['filter_form']
    statuses = set(status[0] for status in filter_form.fields['status'].choices)
    assert len(statuses) == len(AssignmentStatus.choices) - 1
    all_statuses = set(map(lambda status: status[0], AssignmentStatus.choices))
    assert all_statuses.difference(statuses) == {AssignmentStatus.NEW}


@pytest.mark.django_db
def test_view_student_assignment_list_filter_assignment_format_choices(client):
    student = StudentFactory()
    url = reverse('study:assignment_list')
    client.login(student)
    response = client.get(url)
    assert response.status_code == 200
    filter_form = response.context['filter_form']
    formats = set(status[0] for status in filter_form.fields['format'].choices)
    assert len(formats) == len(AssignmentFormat.choices)
    all_formats = set(map(lambda status: status[0], AssignmentFormat.choices))
    assert formats == all_formats


@pytest.mark.django_db
def test_view_student_assignment_list_assignment_status_filtering(client):
    course_one, course_two = CourseFactory.create_batch(2, semester=SemesterFactory.create_current())
    student = StudentFactory()
    EnrollmentFactory(course=course_one, student=student)
    EnrollmentFactory(course=course_two, student=student)
    AssignmentFactory.create_batch(size=4, course=course_one)
    a_two = AssignmentFactory(course=course_two)
    sa1_c1, sa2_c1, sa3_c1, sa4_c1 = StudentAssignment.objects.filter(student=student,
                                                                      assignment__course=course_one)
    sa_c2 = StudentAssignment.objects.get(student=student, assignment=a_two)
    sa2_c1.status = AssignmentStatus.ON_CHECKING
    sa3_c1.status = AssignmentStatus.NEED_FIXES
    sa4_c1.status = AssignmentStatus.COMPLETED
    sa2_c1.save()
    sa3_c1.save()
    sa4_c1.save()
    url = reverse('study:assignment_list')
    client.login(student)

    response = client.get(url)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert len(open_assignments) == 5

    form_data = {
        "status": []
    }
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert set(open_assignments) == {sa1_c1, sa2_c1, sa3_c1, sa4_c1, sa_c2}
    assert response.redirect_chain[-1][0][-1] == '?'  # /learning/assignments/?

    form_data = {
        "status": [AssignmentStatus.NOT_SUBMITTED]
    }
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert set(open_assignments) == {sa1_c1, sa_c2}
    assert f"status={AssignmentStatus.NOT_SUBMITTED}" in response.redirect_chain[-1][0]

    # Status NEW not allowed, so filter is not working
    form_data = {
        "status": [AssignmentStatus.NEW]
    }
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert set(open_assignments) == {sa1_c1, sa2_c1, sa3_c1, sa4_c1, sa_c2}

    form_data = {
        "status": [AssignmentStatus.ON_CHECKING,
                   AssignmentStatus.NEED_FIXES,
                   AssignmentStatus.COMPLETED]
    }
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert set(open_assignments) == {sa2_c1, sa3_c1, sa4_c1}
    assert f"status={AssignmentStatus.ON_CHECKING}" in response.redirect_chain[-1][0]
    assert f"status={AssignmentStatus.NEED_FIXES}" in response.redirect_chain[-1][0]
    assert f"status={AssignmentStatus.COMPLETED}" in response.redirect_chain[-1][0]


@pytest.mark.django_db
def test_view_student_assignment_list_assignment_format_filtering(client):
    course_one, course_two = CourseFactory.create_batch(2, semester=SemesterFactory.create_current())
    student = StudentFactory()
    EnrollmentFactory(course=course_one, student=student)
    EnrollmentFactory(course=course_two, student=student)
    a1_c1 = AssignmentFactory(course=course_one, submission_type=AssignmentFormat.NO_SUBMIT)
    a2_c1 = AssignmentFactory(course=course_one, submission_type=AssignmentFormat.ONLINE)
    a3_c1 = AssignmentFactory(course=course_one, submission_type=AssignmentFormat.EXTERNAL)
    a1_c2 = AssignmentFactory(course=course_two, submission_type=AssignmentFormat.NO_SUBMIT)
    sa1_c1 = StudentAssignment.objects.get(student=student, assignment=a1_c1)
    sa2_c1 = StudentAssignment.objects.get(student=student, assignment=a2_c1)
    sa3_c1 = StudentAssignment.objects.get(student=student, assignment=a3_c1)
    sa1_c2 = StudentAssignment.objects.get(student=student, assignment=a1_c2)
    url = reverse('study:assignment_list')
    client.login(student)

    response = client.get(url)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert len(open_assignments) == 4

    form_data = {
        "format": []
    }
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert set(open_assignments) == {sa1_c1, sa2_c1, sa3_c1, sa1_c2}
    assert response.redirect_chain[-1][0][-1] == '?'  # /learning/assignments/?

    form_data = {
        "format": [AssignmentFormat.NO_SUBMIT]
    }
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert set(open_assignments) == {sa1_c1, sa1_c2}
    assert f"format={AssignmentFormat.NO_SUBMIT}" in response.redirect_chain[-1][0]

    form_data = {
        "format": [AssignmentFormat.ONLINE,
                   AssignmentFormat.EXTERNAL]
    }
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert set(open_assignments) == {sa2_c1, sa3_c1}
    assert f"format={AssignmentFormat.ONLINE}" in response.redirect_chain[-1][0]
    assert f"format={AssignmentFormat.EXTERNAL}" in response.redirect_chain[-1][0]


@pytest.mark.django_db
def test_view_student_assignment_list_filtering(client):
    course_one, course_two = CourseFactory.create_batch(2, semester=SemesterFactory.create_current())
    student = StudentFactory()
    EnrollmentFactory(course=course_one, student=student)
    EnrollmentFactory(course=course_two, student=student)
    a1_c1 = AssignmentFactory(course=course_one, submission_type=AssignmentFormat.NO_SUBMIT)
    a2_c1 = AssignmentFactory(course=course_one, submission_type=AssignmentFormat.ONLINE)
    a3_c1 = AssignmentFactory(course=course_one, submission_type=AssignmentFormat.ONLINE)

    sa1_c1 = StudentAssignment.objects.get(student=student, assignment=a1_c1)
    sa2_c1 = StudentAssignment.objects.get(student=student, assignment=a2_c1)
    sa3_c1 = StudentAssignment.objects.get(student=student, assignment=a3_c1)

    sa1_c1.status = AssignmentStatus.NOT_SUBMITTED
    sa2_c1.status = AssignmentStatus.ON_CHECKING
    sa3_c1.status = AssignmentStatus.NEED_FIXES
    sa1_c1.save()
    sa2_c1.save()
    sa3_c1.save()

    a1_c2 = AssignmentFactory(course=course_two, submission_type=AssignmentFormat.NO_SUBMIT)
    a3_c2 = AssignmentFactory(course=course_two, submission_type=AssignmentFormat.EXTERNAL)

    sa1_c2 = StudentAssignment.objects.get(student=student, assignment=a1_c2)
    sa3_c2 = StudentAssignment.objects.get(student=student, assignment=a3_c2)

    sa1_c2.status = AssignmentStatus.NOT_SUBMITTED
    sa1_c2.status = AssignmentStatus.NOT_SUBMITTED
    sa1_c2.save()
    sa3_c2.save()

    url = reverse('study:assignment_list')
    client.login(student)

    response = client.get(url)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert len(open_assignments) == 5

    form_data = {
        "course": '',
        "status": [],
        "format": []
    }
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert set(open_assignments) == {sa1_c1, sa2_c1, sa3_c1, sa1_c2, sa3_c2}
    assert response.redirect_chain[-1][0][-1] == '?'  # /learning/assignments/?

    form_data = {
        "course": course_two.pk,
        "format": [AssignmentFormat.NO_SUBMIT, AssignmentFormat.EXTERNAL],
        "status": [AssignmentStatus.COMPLETED]
    }
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert not set(open_assignments)
    assert f"course={course_two.pk}" in response.redirect_chain[-1][0]
    assert f"format={AssignmentFormat.NO_SUBMIT}" in response.redirect_chain[-1][0]
    assert f"format={AssignmentFormat.EXTERNAL}" in response.redirect_chain[-1][0]
    assert f"status={AssignmentStatus.COMPLETED}" in response.redirect_chain[-1][0]

    form_data["status"] = [AssignmentStatus.NOT_SUBMITTED]
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert set(open_assignments) == {sa1_c2, sa3_c2}
    assert f"status={AssignmentStatus.NOT_SUBMITTED}" in response.redirect_chain[-1][0]

    form_data = {
        "course": '',
        "format": [AssignmentFormat.NO_SUBMIT],
        "status": [AssignmentStatus.NOT_SUBMITTED]
    }
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert set(open_assignments) == {sa1_c1, sa1_c2}
    assert f"format={AssignmentFormat.NO_SUBMIT}" in response.redirect_chain[-1][0]
    assert f"status={AssignmentStatus.NOT_SUBMITTED}" in response.redirect_chain[-1][0]

    form_data = {
        "course": '',
        "format": [AssignmentFormat.ONLINE, AssignmentFormat.EXTERNAL],
        "status": [AssignmentStatus.NOT_SUBMITTED, AssignmentStatus.ON_CHECKING,
                   AssignmentStatus.NEED_FIXES, AssignmentStatus.COMPLETED]
    }
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert set(open_assignments) == {sa2_c1, sa3_c1, sa3_c2}

    assert f"format={AssignmentFormat.ONLINE}" in response.redirect_chain[-1][0]
    assert f"format={AssignmentFormat.EXTERNAL}" in response.redirect_chain[-1][0]

    assert f"status={AssignmentStatus.NOT_SUBMITTED}" in response.redirect_chain[-1][0]
    assert f"status={AssignmentStatus.ON_CHECKING}" in response.redirect_chain[-1][0]
    assert f"status={AssignmentStatus.NEED_FIXES}" in response.redirect_chain[-1][0]
    assert f"status={AssignmentStatus.COMPLETED}" in response.redirect_chain[-1][0]

    # forbidden status AssignmentStatus.NEW for filter
    form_data["status"].append(AssignmentStatus.NEW)
    response = client.post(url, form_data, follow=True)
    assert response.status_code == 200
    open_assignments = response.context['assignment_list_open']
    assert set(open_assignments) == {sa1_c1, sa2_c1, sa3_c1, sa1_c2, sa3_c2}


@pytest.mark.django_db
def test_draft_comment_with_file(client, assert_redirect):
    student_profile = StudentProfileFactory()
    course = CourseFactory()
    course_teacher = CourseTeacherFactory(course=course)
    EnrollmentFactory(
        student_profile=student_profile,
        student=student_profile.user,
        course=course,
    )
    assignment = AssignmentFactory(course=course)
    personal_assignment = (
        StudentAssignment.objects
        .filter(assignment=assignment, student=student_profile.user)
        .get()
    )
    client.login(student_profile.user)
    detail_url = personal_assignment.get_student_url()
    create_comment_url = reverse(
        'study:assignment_comment_create',
        kwargs={'pk': personal_assignment.pk},
    )

    # Create new draft comment
    form_data = {
        'comment-text': 'Test comment',
        'comment-attached_file': SimpleUploadedFile("test_file.txt", b"a_content"),
        'save-draft': 'Submit button text'
    }
    response = client.post(create_comment_url, form_data)
    assert_redirect(response, detail_url)
    draft = AssignmentComment.objects.get(text=form_data['comment-text'])

    # Check that file is unchanged when no file is uploaded
    form_data = {
        'comment-text': draft.text,
        'comment-attached_file': '',
        'save-draft': 'Submit button text',
    }
    response = client.post(create_comment_url, form_data)
    assert_redirect(response, detail_url)
    draft.refresh_from_db()
    assert draft.attached_file_name.startswith('test_file')

    # Check that file is removed when "Clear" is checked
    form_data = {
        'comment-text': draft.text,
        'comment-attached_file': '',
        'comment-attached_file-clear': 'on',
        'save-draft': 'Submit button text',
    }
    response = client.post(create_comment_url, form_data)
    assert_redirect(response, detail_url)
    draft.refresh_from_db()
    assert not draft.attached_file_name
