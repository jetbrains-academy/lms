import datetime

import factory
import pytest
import time_machine
from django.conf import settings
from django.utils.encoding import smart_bytes
from django_recaptcha.client import RecaptchaResponse

from core.urls import reverse
from core.utils import instance_memoize
from courses.constants import SemesterTypes
from courses.models import CourseTeacher
from courses.tests.factories import CourseFactory, CourseTeacherFactory, SemesterFactory, CourseProgramBindingFactory
from learning.invitation.views import create_invited_profile
from learning.settings import StudentStatuses
from learning.tests.factories import EnrollmentFactory, CourseInvitationBindingFactory, InvitationFactory
from users.constants import Roles
from users.models import StudentTypes, User, StudentProfile
from users.services import create_student_profile, update_student_status
from users.tests.factories import TeacherFactory, UserFactory, StudentFactory, CuratorFactory, StudentProfileFactory


@pytest.mark.django_db
def test_login_restrictions(client, settings, program_run_cub, mocker):
    mocked_submit = mocker.patch('django_recaptcha.fields.client.submit')
    mocked_submit.return_value = RecaptchaResponse(is_valid=True)
    user_data = factory.build(dict, FACTORY_CLASS=UserFactory)
    student = User.objects.create_user(**user_data)
    # Try to login without groups at all
    user_data['g-recaptcha-response'] = 'definitely not a valid response'
    response = client.post(reverse('auth:login'), user_data)
    assert response.status_code == 200
    assert len(response.context["form"].errors) > 0
    # Login as student
    create_student_profile(user=student, profile_type=StudentTypes.REGULAR,
                           year_of_admission=2024,
                           academic_program_enrollment=program_run_cub)
    instance_memoize.delete_cache(student)
    student.refresh_from_db()
    response = client.post(reverse('auth:login'), user_data, follow=True)
    assert response.wsgi_request.user.is_authenticated
    client.logout()
    # And teacher
    student.groups.all().delete()
    student.add_group(Roles.TEACHER)
    response = client.post(reverse('auth:login'), user_data, follow=True)
    assert response.wsgi_request.user.is_authenticated
    # Login as invited
    student.groups.all().delete()
    create_student_profile(user=student, profile_type=StudentTypes.INVITED,
                           year_of_admission=2024)
    response = client.post(reverse('auth:login'), user_data, follow=True)
    assert response.wsgi_request.user.is_authenticated
    client.logout()


@pytest.mark.django_db
def test_view_course_offering_teachers_visibility(client, settings):
    """Spectator should not be displayed as course teacher"""
    teacher, spectator = TeacherFactory.create_batch(2)
    co_1 = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=co_1, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    co_2 = CourseFactory()
    CourseTeacherFactory(course=co_2, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    url = reverse('course_list', subdomain=settings.LMS_SUBDOMAIN)
    client.login(teacher)
    response = client.get(url)
    assert smart_bytes(teacher.get_full_name()) in response.content
    assert smart_bytes(spectator.get_full_name()) not in response.content


@pytest.mark.django_db
def test_view_course_offerings_permission(client, settings, assert_login_redirect):
    url = reverse('course_list', subdomain=settings.LMS_SUBDOMAIN)
    assert_login_redirect(url)
    student = StudentFactory()
    client.login(student)
    assert client.get(url).status_code == 200
    client.login(TeacherFactory())
    assert client.get(url).status_code == 200
    client.login(CuratorFactory())
    assert client.get(url).status_code == 200


@pytest.mark.django_db
def test_view_course_offerings(client, program_cub001, program_run_cub):
    """Course offerings should show all courses except summer term courses"""
    url = reverse('course_list', subdomain=settings.LMS_SUBDOMAIN)
    autumn_term = SemesterFactory(year=2022,
                                  type=SemesterTypes.AUTUMN)
    summer_term = SemesterFactory(year=autumn_term.year - 1,
                                  type=SemesterTypes.SUMMER)
    spring_term = SemesterFactory(year=autumn_term.year - 1,
                                  type=SemesterTypes.SPRING)

    student = UserFactory()
    regular_profile = StudentProfileFactory(user=student, academic_program_enrollment=program_run_cub)
    client.login(student)

    autumn_cpb = CourseProgramBindingFactory.create_batch(
        3,
        program=program_cub001,
        course__semester=autumn_term
    )
    autumn_courses = [x.course for x in autumn_cpb]
    spring_cpb = CourseProgramBindingFactory.create_batch(
        2,
        program=program_cub001,
        course__semester=spring_term
    )
    spring_courses = [x.course for x in spring_cpb]
    CourseProgramBindingFactory.create_batch(7, program=program_cub001, course__semester=summer_term)

    enrolled_curr, unenrolled_curr, can_enroll_curr = autumn_courses
    enrolled_prev = spring_courses[0]
    EnrollmentFactory(student=student,
                      student_profile=regular_profile,
                      course=enrolled_curr)
    EnrollmentFactory(student=student,
                      student_profile=regular_profile,
                      course=unenrolled_curr,
                      is_deleted=True)
    EnrollmentFactory(student=student,
                      student_profile=regular_profile,
                      course=enrolled_prev)
    response = client.get(url)
    terms_courses = list(response.context_data['courses'].values())
    assert len(terms_courses) == 2  # two terms
    found_courses = sum(map(len, terms_courses))
    assert found_courses == len(autumn_courses) + len(spring_courses)

    curator = CuratorFactory()
    client.login(curator)
    response = client.get(url)
    terms_courses = list(response.context_data['courses'].values())
    assert len(terms_courses) == 2  # two terms
    found_courses = sum(map(len, terms_courses))
    assert found_courses == len(autumn_courses) + len(spring_courses)

    teacher = TeacherFactory()
    client.login(teacher)
    response = client.get(url)
    terms_courses = list(response.context_data['courses'].values())
    assert len(terms_courses) == 2  # two terms
    found_courses = sum(map(len, terms_courses))
    assert found_courses == len(autumn_courses) + len(spring_courses)


# Summer semester courses are not shown in the list
# And invited student profiles are considered invalid if
# the profile creation date is not in the current semester,
# so freezing time here
@pytest.mark.django_db
@time_machine.travel(datetime.datetime(2024, 5, 1, 10, 00))
def test_view_course_offerings_invited_restriction(client):
    """Invited students should only see courses
    for which they were enrolled or invited"""
    url = reverse('course_list', subdomain=settings.LMS_SUBDOMAIN)
    autumn_term = SemesterFactory.create_current()
    course_invitation = CourseInvitationBindingFactory(course__semester=autumn_term)
    student_profile = StudentProfileFactory(type=StudentTypes.INVITED)
    student = student_profile.user

    other_invitation = InvitationFactory()
    autumn_courses = CourseFactory.create_batch(3, semester=autumn_term)
    enrolled_curr, unenrolled_curr, can_enroll_curr = autumn_courses
    EnrollmentFactory(
        student=student,
        student_profile=student_profile,
        course=enrolled_curr,
        course_program_binding__invitation=other_invitation
    )
    EnrollmentFactory(
        student=student,
        student_profile=student_profile,
        course=unenrolled_curr,
        course_program_binding__invitation=other_invitation,
        is_deleted=True
    )

    client.login(student)
    response = client.get(url)
    terms_courses = list(response.context_data['courses'].values())
    found_courses = sum(map(len, terms_courses))
    assert found_courses == 1
    assert terms_courses[0][0]['name'] == enrolled_curr.meta_course.name

    response = client.post(course_invitation.invitation.get_absolute_url())
    assert response.status_code == 302
    response = client.get(url)
    terms_courses = list(response.context_data['courses'].values())
    found_courses = sum(map(len, terms_courses))
    assert found_courses == 2


@pytest.mark.django_db
def test_view_course_offerings_old_invited(client):
    """Invited student sees only old courses on which has been enrolled."""
    url = reverse('course_list', subdomain=settings.LMS_SUBDOMAIN)
    current_term = SemesterFactory.create_current()
    previous_term = SemesterFactory(year=current_term.year - 1, type=SemesterTypes.SPRING)

    old_course = CourseFactory(semester=previous_term)
    course_invitation = CourseInvitationBindingFactory(invitation__semester=previous_term, course=old_course)
    student = UserFactory()
    create_invited_profile(student, course_invitation.invitation)
    student_profile = StudentProfile.objects.get(user=student)
    random_course = CourseFactory(semester=current_term)
    enrollment = EnrollmentFactory(course=old_course,
                                   student=student,
                                   student_profile=student_profile,
                                   course_program_binding=course_invitation,
                                   grade=1)

    client.login(student)
    response = client.get(url)
    terms_courses = list(response.context_data['courses'].values())
    founded_courses = sum(map(len, terms_courses))
    assert founded_courses == 1

    enrollment.is_deleted = True
    enrollment.save()
    response = client.get(url)
    terms_courses = list(response.context_data['courses'].values())
    founded_courses = sum(map(len, terms_courses))
    assert founded_courses == 0

    course_invitation.invitation.enrolled_students.add(student_profile)
    response = client.get(url)
    terms_courses = list(response.context_data['courses'].values())
    founded_courses = sum(map(len, terms_courses))
    assert founded_courses == 1

    new_invited_profile = StudentProfileFactory(type=StudentTypes.INVITED,
                                                user=student,
                                                year_of_admission=current_term.year)
    assert student.get_student_profile() == new_invited_profile

    course_invitation.invitation.enrolled_students.add(student_profile)
    response = client.get(url)
    terms_courses = list(response.context_data['courses'].values())
    founded_courses = sum(map(len, terms_courses))
    # Unenrolled access to previous semester courses has been revoked
    assert founded_courses == 0

    enrollment.is_deleted = False
    enrollment.save()
    response = client.get(url)
    terms_courses = list(response.context_data['courses'].values())
    founded_courses = sum(map(len, terms_courses))
    # But the courses the student was enrolled in are still available
    assert founded_courses == 1


@pytest.mark.django_db
@time_machine.travel(datetime.datetime(2024, 5, 1, 10, 00))
def test_view_course_offerings_regular_in_academic(client, program_cub001, program_run_cub):
    url = reverse('course_list', subdomain=settings.LMS_SUBDOMAIN)
    current_term = SemesterFactory.create_current()

    regular_profile = StudentProfileFactory(academic_program_enrollment=program_run_cub)
    student = regular_profile.user

    cpb = CourseProgramBindingFactory.create_batch(
        2,
        program=program_cub001
    )
    course_enrolled, random_course = (x.course for x in cpb)
    enrollment = EnrollmentFactory(course=course_enrolled,
                                   student=student,
                                   student_profile=regular_profile,
                                   grade=1)

    curator = CuratorFactory()
    update_student_status(student_profile=regular_profile,
                          new_status=StudentStatuses.EXPELLED,
                          editor=curator)

    client.login(student)
    response = client.get(url)
    terms_courses = list(response.context_data['courses'].values())
    founded_courses = sum(map(len, terms_courses))
    # Expelled student still have access to courses
    assert founded_courses == 2

    course_invitation = CourseInvitationBindingFactory(course__semester=current_term)
    new_invited_profile = StudentProfileFactory(type=StudentTypes.INVITED,
                                                user=student,
                                                year_of_admission=current_term.year)

    response = client.get(url)
    terms_courses = list(response.context_data['courses'].values())
    founded_courses = sum(map(len, terms_courses))
    # Show only the course the student was enrolled in
    assert founded_courses == 1

    client.post(course_invitation.invitation.get_absolute_url())
    response = client.get(url)
    terms_courses = list(response.context_data['courses'].values())
    founded_courses = sum(map(len, terms_courses))
    assert founded_courses == 2
