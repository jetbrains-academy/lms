import datetime

import pytest
from django.utils.encoding import smart_bytes

from courses.models import CourseNews, CourseReview, CourseTeacher
from courses.services import CourseService
from courses.tests.factories import (
    AssignmentFactory, CourseFactory, CourseNewsFactory, CourseReviewFactory,
    CourseTeacherFactory, MetaCourseFactory, SemesterFactory, CourseProgramBindingFactory
)
from learning.permissions import EnrollInCourse, EnrollOrLeavePermissionObject
from learning.tabs import CourseReviewsTab
from learning.tests.factories import EnrollmentFactory
from users.constants import Roles
from users.tests.factories import CuratorFactory, StudentFactory, TeacherFactory, InvitedStudentFactory


# TODO: test for tab visibility from different roles (hide tab in view if there is no content)


@pytest.mark.django_db
def test_course_news_tab_permissions_student(client, assert_login_redirect):
    news: CourseNews = CourseNewsFactory()
    course = news.course
    news_prev: CourseNews = CourseNewsFactory(course__meta_course=course.meta_course,
                                              course__completed_at=datetime.date.today())
    co_prev = news_prev.course
    assert_login_redirect(course.get_absolute_url())
    # By default student can't see the news until enroll in the course
    student_spb = StudentFactory()
    student_profile = student_spb.get_student_profile()
    CourseProgramBindingFactory(
        course=course,
        program=student_profile.academic_program_enrollment.program
    )
    CourseProgramBindingFactory(
        course=co_prev,
        program=student_profile.academic_program_enrollment.program
    )
    client.login(student_spb)
    response = client.get(course.get_absolute_url())
    assert "news" not in response.context_data['course_tabs']
    response = client.get(co_prev.get_absolute_url())
    assert response.status_code == 403
    e_current = EnrollmentFactory(course=course, student=student_spb)
    response = client.get(course.get_absolute_url())
    assert "news" in response.context_data['course_tabs']
    # To see the news for completed course student should successfully pass it.
    e_prev = EnrollmentFactory(course=co_prev, student=student_spb)
    response = client.get(co_prev.get_absolute_url())
    assert "news" not in response.context_data['course_tabs']
    e_prev.grade = 4
    e_prev.save()
    response = client.get(co_prev.get_absolute_url())
    assert "news" in response.context_data['course_tabs']


@pytest.mark.django_db
def test_course_news_tab_permissions_teacher_and_curator(client):
    course_teacher = TeacherFactory()
    other_teacher = StudentFactory()
    other_teacher.add_group(Roles.TEACHER)
    course = CourseFactory(semester=SemesterFactory.create_current(),
                           teachers=[course_teacher])
    CourseProgramBindingFactory(
        course=course,
        program=other_teacher.get_student_profile().academic_program_enrollment.program
    )
    news = CourseNewsFactory(course=course)
    client.login(other_teacher)
    response = client.get(course.get_absolute_url())
    assert "news" not in response.context_data['course_tabs']
    client.login(course_teacher)
    response = client.get(course.get_absolute_url())
    assert "news" in response.context_data['course_tabs']
    curator = CuratorFactory()
    client.login(curator)
    response = client.get(course.get_absolute_url())
    assert "news" in response.context_data['course_tabs']


@pytest.mark.django_db
def test_course_assignments_tab_permissions(client, assert_login_redirect, program_cub001, program_run_cub):
    current_term = SemesterFactory.create_current()
    prev_term = SemesterFactory.create_prev(current_term)
    teacher = StudentFactory(student_profile__academic_program_enrollment=program_run_cub)
    teacher.add_group(Roles.TEACHER)
    course = CourseFactory(semester=current_term,
                           teachers=[teacher])
    course_prev = CourseFactory(meta_course=course.meta_course,
                                semester=prev_term)
    CourseProgramBindingFactory(
        course=course_prev,
        program=program_cub001
    )
    assert_login_redirect(course_prev.get_absolute_url())
    client.login(teacher)
    response = client.get(course.get_absolute_url())
    assert "assignments" not in response.context_data['course_tabs']
    a = AssignmentFactory(course=course)
    response = client.get(course.get_absolute_url())
    assert "assignments" in response.context_data['course_tabs']
    assert smart_bytes(a.get_teacher_url()) in response.content
    # Show links only if a teacher is an actual teacher of the course
    a_prev = AssignmentFactory(course=course_prev)
    response = client.get(course_prev.get_absolute_url())
    assert "assignments" in response.context_data['course_tabs']
    assert smart_bytes(a_prev.get_teacher_url()) not in response.content
    student = StudentFactory(student_profile__academic_program_enrollment=program_run_cub)
    client.login(student)
    response = client.get(course_prev.get_absolute_url())
    assert "assignments" in response.context_data['course_tabs']
    tab = response.context_data['course_tabs']['assignments']
    assert len(tab.tab_panel.context["items"]) == 1
    assert smart_bytes(a_prev.get_teacher_url()) not in response.content


@pytest.mark.django_db
def test_course_reviews_tab_permissions(client, curator, program_cub001, program_run_cub):
    current_term = SemesterFactory.create_current()
    prev_term = SemesterFactory.create_prev(current_term)
    course = CourseFactory(semester=current_term)
    binding = CourseProgramBindingFactory(course=course, program=program_cub001)
    prev_course = CourseFactory(semester=prev_term, meta_course=course.meta_course)
    prev_binding = CourseProgramBindingFactory(course=prev_course, program=program_cub001)
    CourseReview(course=prev_course, text='Very good').save()
    student = StudentFactory(student_profile__academic_program_enrollment=program_run_cub)
    student_profile = student.get_student_profile()
    perm_obj = EnrollOrLeavePermissionObject(course, student_profile)
    assert student.has_perm(EnrollInCourse.name, perm_obj)
    client.login(student)
    response = client.get(course.get_absolute_url())
    assert CourseReviewsTab.is_enabled(course, student)
    assert "reviews" in response.context_data['course_tabs']
    invitee = InvitedStudentFactory()
    assert CourseReviewsTab.is_enabled(course, invitee)
    assert CourseReviewsTab.is_enabled(course, curator)
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    course.completed_at = yesterday
    course.save()
    assert not student.has_perm(EnrollInCourse.name, perm_obj)
    assert not CourseReviewsTab.is_enabled(course, curator)


@pytest.mark.django_db
def test_get_course_reviews(settings):
    meta_course1, meta_course2 = MetaCourseFactory.create_batch(2)
    c1 = CourseFactory(meta_course=meta_course1,
                       semester__year=2015)
    c2 = CourseFactory(meta_course=meta_course1,
                       semester__year=2016)
    cr1 = CourseReviewFactory(course=c1)
    cr2 = CourseReviewFactory(course=c2)
    c3 = CourseFactory(meta_course=meta_course1,
                       semester__year=2016)
    c4 = CourseFactory(meta_course=meta_course2,
                       semester__year=2015)
    cr3 = CourseReviewFactory(course=c3)
    CourseReview(course=c4, text='zzz').save()
    assert len(CourseService.get_reviews(c1)) == 3
    assert set(CourseService.get_reviews(c1)) == {cr1, cr2, cr3}


@pytest.mark.django_db
def test_contacts_tab_has_no_spectator_contacts(client):
    curator = CuratorFactory()
    teacher_contacts = "Teacher contacts"
    spectator_contacts = "Spectator contacts"
    teacher = TeacherFactory(private_contacts=teacher_contacts)
    spectator = TeacherFactory(private_contacts=spectator_contacts)
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)

    url = course.get_absolute_url()
    client.login(curator)
    response = client.get(url)
    assert smart_bytes(teacher_contacts) in response.content
    assert smart_bytes(spectator_contacts) not in response.content


@pytest.mark.django_db
def test_contacts_tab_has_only_organizer_contacts(client):
    curator = CuratorFactory()
    teacher_contacts = "Teacher contacts"
    organizer_contacts = "Organizer contacts"
    teacher = TeacherFactory(private_contacts=teacher_contacts)
    organizer = TeacherFactory(private_contacts=organizer_contacts)
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=organizer,
                         roles=CourseTeacher.roles.organizer)

    url = course.get_absolute_url()
    client.login(curator)
    response = client.get(url)
    assert smart_bytes("Course Organizers") in response.content
    assert smart_bytes(organizer_contacts) in response.content
    assert smart_bytes(teacher_contacts) not in response.content
