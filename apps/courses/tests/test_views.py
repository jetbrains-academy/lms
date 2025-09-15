import datetime
import io
from typing import Optional
from zoneinfo import ZoneInfo

import pandas
import pytest
from bs4 import BeautifulSoup
from django.conf import settings
from django.utils import formats
from django.utils.encoding import smart_bytes

from auth.permissions import perm_registry
from core.tests.factories import LocationFactory
from core.timezone import UTC
from core.urls import reverse
from courses.constants import MaterialVisibilityTypes
from courses.models import CourseTeacher
from courses.permissions import ViewCourseClassMaterials
from courses.tests.factories import (
    AssignmentFactory, CourseClassAttachmentFactory, CourseClassFactory, CourseFactory,
    CourseNewsFactory, CourseTeacherFactory, CourseProgramBindingFactory
)
from files.response import XAccelRedirectFileResponse
from files.views import ProtectedFileDownloadView
from learning.invitation.views import create_invited_profile
from learning.models import Enrollment
from learning.settings import StudentStatuses
from learning.tests.factories import CourseInvitationBindingFactory, EnrollmentFactory
from users.constants import Roles
from users.services import update_student_status
from users.tests.factories import (
    CuratorFactory, StudentFactory, StudentProfileFactory, TeacherFactory, UserFactory
)


def get_timezone_gmt_offset(tz: datetime.tzinfo) -> Optional[datetime.timedelta]:
    return datetime.datetime(2017, 1, 1, tzinfo=tz).utcoffset()


@pytest.mark.django_db
def test_teacher_detail_view(client, assert_login_redirect):
    user = UserFactory()
    assert_login_redirect(user.teacher_profile_url())
    client.login(user)
    response = client.get(user.teacher_profile_url())
    assert response.status_code == 404
    user.add_group(Roles.TEACHER)
    user.save()
    response = client.get(user.teacher_profile_url())
    assert response.status_code == 200
    assert response.context_data['teacher'] == user


@pytest.mark.django_db
def test_course_news(settings, client):
    settings.LANGUAGE_CODE = 'ru'
    curator = CuratorFactory()
    client.login(curator)
    msk_tz = ZoneInfo('Europe/Moscow')
    nsk_tz = ZoneInfo('Asia/Novosibirsk')
    msk_offset = get_timezone_gmt_offset(msk_tz)
    nsk_offset = get_timezone_gmt_offset(nsk_tz)
    course = CourseFactory()
    created_utc = datetime.datetime(2017, 1, 13, 20, 0, 0, 0, tzinfo=UTC)
    news = CourseNewsFactory(course=course, created=created_utc)

    # News dates are shown in the user time zone
    curator.time_zone = msk_tz
    curator.save()
    created_local = created_utc.astimezone(msk_tz)
    assert created_local.utcoffset() == datetime.timedelta(seconds=msk_offset.total_seconds())
    assert created_local.hour == 23
    date_str = "{:02d}".format(created_local.day)
    assert date_str == "13"
    response = client.get(course.get_absolute_url())
    html = BeautifulSoup(response.content, "html.parser")
    assert any(date_str in s.string for s in html.find_all('div', {"class": "date"}))

    # News dates are shown in the user time zone
    curator.time_zone = nsk_tz
    curator.save()
    created_local = created_utc.astimezone(nsk_tz)
    assert created_local.utcoffset() == datetime.timedelta(seconds=nsk_offset.total_seconds())
    assert created_local.hour == 3
    assert created_local.day == 14
    date_str = "{:02d}".format(created_local.day)
    assert date_str == "14"
    response = client.get(course.get_absolute_url())
    html = BeautifulSoup(response.content, "html.parser")
    assert any(date_str in s.string for s in html.find_all('div', {"class": "date"}))


@pytest.mark.django_db
def test_course_assignment_deadline_l10n(settings, client):
    settings.LANGUAGE_CODE = 'ru'  # formatting depends on locale
    dt = datetime.datetime(2017, 1, 1, 15, 0, 0, 0, tzinfo=UTC)
    teacher = TeacherFactory()
    assignment = AssignmentFactory(deadline_at=dt,
                                   time_zone=ZoneInfo('Europe/Moscow'),
                                   course__teachers=[teacher])
    course = assignment.course
    client.login(teacher)
    response = client.get(course.get_url_for_tab('assignments'))
    html = BeautifulSoup(response.content, "html.parser")
    deadline_date_str = formats.date_format(assignment.deadline_at_local(), 'd E')
    assert deadline_date_str == "01 января"
    assert any(deadline_date_str in s.text for s in
               html.find_all('div', {"class": "assignment-deadline"}))
    deadline_time_str = formats.date_format(assignment.deadline_at_local(), 'H:i')
    assert deadline_time_str == "18:00"
    assert any(deadline_time_str in s.string for s in
               html.find_all('span', {"class": "text-muted"}))


@pytest.mark.django_db
def test_venue_list(client):
    v = LocationFactory(city__code=settings.DEFAULT_CITY_CODE)
    response = client.get(reverse('courses:venue_list'))
    assert response.status_code == 200
    assert v in list(response.context_data['object_list'])


@pytest.mark.django_db
def test_download_course_class_attachment(client, lms_resolver, settings):
    settings.USE_CLOUD_STORAGE = False
    course_class = CourseClassFactory(
        materials_visibility=MaterialVisibilityTypes.PARTICIPANTS)
    cca = CourseClassAttachmentFactory(course_class=course_class)
    download_url = cca.get_download_url()
    resolver = lms_resolver(download_url)
    assert issubclass(resolver.func.view_class, ProtectedFileDownloadView)
    assert resolver.func.view_class.permission_required == ViewCourseClassMaterials.name
    assert resolver.func.view_class.permission_required in perm_registry
    student = StudentFactory()
    student_profile = student.get_student_profile()
    course = course_class.course
    CourseProgramBindingFactory(
        course=course,
        program=student_profile.academic_program_enrollment.program
    )
    client.login(student)
    response = client.get(download_url)
    assert isinstance(response, XAccelRedirectFileResponse)


@pytest.mark.django_db
def test_course_update(client, assert_redirect):
    course = CourseFactory()
    curator = CuratorFactory()
    client.login(curator)
    form = {
        "description": "foobar",
        "internal_description": "super secret"
    }
    response = client.post(course.get_update_url(), form)
    assert response.status_code == 302
    course.refresh_from_db()
    assert course.description == "foobar"
    assert course.internal_description == "super secret"


@pytest.mark.django_db
def test_view_course_detail_teacher_contacts_visibility(client):
    """Contacts of all teachers whose role is not Spectator
    should be displayed on course page"""
    lecturer_contacts = "Lecturer contacts"
    organizer_contacts = "Organizer contacts"
    spectator_contacts = "Spectator contacts"
    lecturer = TeacherFactory(private_contacts=lecturer_contacts)
    organizer = TeacherFactory(private_contacts=organizer_contacts)
    spectator = TeacherFactory(private_contacts=spectator_contacts)
    course = CourseFactory()
    ct_lec = CourseTeacherFactory(course=course, teacher=lecturer,
                                  roles=CourseTeacher.roles.lecturer)
    ct_org = CourseTeacherFactory(course=course, teacher=organizer,
                                  roles=CourseTeacher.roles.organizer)
    ct_spe = CourseTeacherFactory(course=course, teacher=spectator,
                                  roles=CourseTeacher.roles.spectator)

    url = course.get_absolute_url()
    client.login(lecturer)
    response = client.get(url)

    context_teachers = response.context_data['teachers']
    assert set(context_teachers['main']) == {ct_lec, ct_org}
    assert not context_teachers['others']
    assert smart_bytes(lecturer.get_full_name()) in response.content
    assert smart_bytes(organizer.get_full_name()) in response.content
    assert smart_bytes(spectator.get_full_name()) not in response.content


@pytest.mark.django_db
def test_view_course_edit_description_btn_visibility(client):
    """
    The button for editing a course description should
    only be displayed if the user has permissions to do so.
    """
    teacher, spectator = TeacherFactory.create_batch(2)
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)

    def has_course_description_edit_btn(user):
        client.login(user)
        url = course.get_absolute_url()
        html = client.get(url).content.decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        client.logout()
        return soup.find('a', {
            "href": course.get_update_url()
        }) is not None

    assert has_course_description_edit_btn(teacher)
    assert not has_course_description_edit_btn(spectator)


@pytest.mark.django_db
def test_view_course_detail_contacts_visibility(client):
    user = UserFactory()
    curator = CuratorFactory()
    course_student, student = StudentFactory.create_batch(2)
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    contacts = "Some contacts"
    course = CourseFactory(teachers=[teacher], contacts=contacts)
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    EnrollmentFactory(course=course, student=course_student,
                      grade=4)
    url = course.get_absolute_url()

    def has_contacts_header(user):
        client.login(user)
        response = client.get(url)
        return smart_bytes(contacts) in response.content

    assert not has_contacts_header(user)
    assert not has_contacts_header(student)
    assert not has_contacts_header(teacher_other)
    assert has_contacts_header(curator)
    assert has_contacts_header(teacher)
    assert has_contacts_header(course_student)


@pytest.mark.django_db
def test_view_course_detail_enroll_by_invitation(client, program_cub001, program_run_cub):
    student = UserFactory()
    course_invitation = CourseInvitationBindingFactory()
    create_invited_profile(student, course_invitation.invitation)
    invited_profile = student.get_student_profile()

    course = course_invitation.course
    CourseProgramBindingFactory(course=course, program=program_cub001)
    regular_profile = StudentProfileFactory(user=student, academic_program_enrollment=program_run_cub)
    assert student.get_student_profile() == regular_profile

    client.login(student)
    response = client.get(course.get_absolute_url())
    assert response.status_code == 200
    assert 'Enroll in the course' in response.content.decode('utf-8')

    curator = CuratorFactory()
    update_student_status(student_profile=regular_profile,
                          new_status=StudentStatuses.EXPELLED,
                          editor=curator)

    assert student.get_student_profile() == invited_profile

    response = client.get(course.get_absolute_url())
    assert response.status_code == 403

    response = client.post(course_invitation.invitation.get_absolute_url())
    assert response.status_code == 302
    response = client.get(course.get_absolute_url())
    assert response.status_code == 200
    assert b'Enroll in the course' in response.content

    url = course.get_enroll_url()
    response = client.post(url, follow=True)
    assert response.redirect_chain[-1][0] == course.get_absolute_url()
    assert Enrollment.objects.filter(student=student, course_program_binding=course_invitation).exists()

    response = client.get(course.get_absolute_url())
    assert response.status_code == 200
    assert b'Unenroll from the course' in response.content


@pytest.mark.django_db
def test_view_course_student_faces(client):
    teacher = TeacherFactory()
    client.login(teacher)
    course = CourseFactory(teachers=[teacher])
    enrollment1 = EnrollmentFactory(course=course)
    enrollment2 = EnrollmentFactory(course=course)
    url = course.get_student_faces_url()

    response = client.get(url)
    assert response.status_code == 200
    assert enrollment1.student.get_full_name().encode() in response.content
    assert enrollment2.student.get_full_name().encode() in response.content


@pytest.mark.django_db
def test_view_course_student_faces_csv(client):
    teacher = TeacherFactory()
    client.login(teacher)
    course = CourseFactory(teachers=[teacher])
    enrollment1 = EnrollmentFactory(course=course, student__telegram_username='telegram1')
    student1 = enrollment1.student
    enrollment2 = EnrollmentFactory(course=course, student__telegram_username='telegram2')
    student2 = enrollment2.student
    url = course.get_student_faces_export_url()

    response = client.get(url)
    assert response.status_code == 200
    file = io.BytesIO(response.getvalue())
    df = pandas.read_csv(file)
    assert len(df) == 2
    for i, row in df.iterrows():
        if i == 0:
            assert row['First Name'] == student1.first_name
            assert row['Last Name'] == student1.last_name
            assert row['Telegram'] == student1.telegram_username
        elif i == 1:
            assert row['First Name'] == student2.first_name
            assert row['Last Name'] == student2.last_name
            assert row['Telegram'] == student2.telegram_username
