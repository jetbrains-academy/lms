import datetime

import pytest
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from django.utils.encoding import smart_bytes
from pytz import UTC

from auth.mixins import PermissionRequiredMixin
from core.tests.factories import LocationFactory
from core.urls import reverse
from courses.tests.factories import CourseClassFactory, CourseFactory, CourseProgramBindingFactory, SemesterFactory
from learning.tests.factories import EnrollmentFactory
from learning.tests.utils import (
    compare_calendar_events_with_models, flatten_calendar_month_events
)
from users.tests.factories import StudentFactory, StudentProfileFactory, TeacherFactory


# TODO: add test: kzn courses not shown on center site and spb on kzn
# TODO: add test: summer courses not shown on club site on main page
# TODO: For SPB, NSC events are not displayed (the opposite would be correct)


@pytest.mark.django_db
def test_teacher_calendar_group_security(client, assert_login_redirect):
    url = reverse('teaching:calendar')
    assert_login_redirect(url)
    client.login(StudentFactory())
    assert client.get(url).status_code == 403
    client.login(TeacherFactory())
    assert client.get(url).status_code == 200


@pytest.mark.django_db
def test_teacher_calendar(client, program_cub001):
    url = reverse('teaching:calendar')
    semester = SemesterFactory.create_current()
    teacher = TeacherFactory(time_zone=UTC)
    other_teacher = TeacherFactory(time_zone=UTC)
    client.login(teacher)
    response = client.get(url)
    classes = flatten_calendar_month_events(response.context_data['calendar'])
    assert len(classes) == 0
    this_month_date = (datetime.datetime.now(tz=timezone.utc)
                       .replace(day=15, tzinfo=timezone.utc))
    own_classes = list(
        CourseClassFactory
        .create_batch(
            3, course__teachers=[teacher],
            course__semester=semester, date=this_month_date.date()
        )
    )
    others_classes = list(
        CourseClassFactory
        .create_batch(
            5, course__teachers=[other_teacher],
            course__semester=semester, date=this_month_date.date()
        )
    )
    for course_class in own_classes + others_classes:
        CourseProgramBindingFactory(course=course_class.course, program=program_cub001)
    location = LocationFactory(city_id=program_cub001.university.city_id)
    # teacher should see only his own classes and non-course events
    resp = client.get(url)
    calendar_events = set(flatten_calendar_month_events(resp.context_data['calendar']))
    compare_calendar_events_with_models(calendar_events, own_classes)
    # No events on the next month
    next_month_qstr = (
        "?year={0}&month={1}"
        .format(resp.context_data['calendar'].next_month.year,
                str(resp.context_data['calendar'].next_month.month)))
    next_month_url = url + next_month_qstr
    assert smart_bytes(next_month_qstr) in resp.content
    classes = flatten_calendar_month_events(
        client.get(next_month_url).context_data['calendar'])
    assert classes == []
    # Add some and test
    next_month_date = this_month_date + relativedelta(months=1)
    next_month_classes = (
        CourseClassFactory
        .create_batch(2, course__teachers=[teacher],
                      date=next_month_date.date()))
    calendar_events = set(flatten_calendar_month_events(
        client.get(next_month_url).context_data['calendar']))
    compare_calendar_events_with_models(calendar_events, next_month_classes)
    # On a full calendar all classes should be shown
    response = client.get(reverse('teaching:calendar_full'))
    calendar_events = set(flatten_calendar_month_events(response.context_data['calendar']))
    compare_calendar_events_with_models(calendar_events, own_classes + others_classes)


@pytest.mark.django_db
def test_student_personal_calendar_view_permissions(lms_resolver):
    resolver = lms_resolver(reverse('study:calendar'))
    assert issubclass(resolver.func.view_class, PermissionRequiredMixin)
    assert resolver.func.view_class.permission_required == "study.view_schedule"


@pytest.mark.django_db
def test_student_personal_calendar_view(client, program_cub001, program_run_cub):
    calendar_url = reverse('study:calendar')
    student_profile = StudentProfileFactory(academic_program_enrollment=program_run_cub, user__time_zone=timezone.utc)
    client.login(student_profile.user)
    course = CourseProgramBindingFactory(program=program_cub001).course
    course_other = CourseProgramBindingFactory(program=program_cub001).course
    e = EnrollmentFactory.create(course=course,
                                 student_profile=student_profile,
                                 student=student_profile.user)
    classes = flatten_calendar_month_events(
        client.get(calendar_url).context_data['calendar'])
    assert len(classes) == 0
    this_month_date = (datetime.datetime.now(tz=timezone.utc)
                       .replace(day=15,
                                tzinfo=timezone.utc)).date()
    own_classes = CourseClassFactory.create_batch(3, course=course, date=this_month_date, time_zone=UTC)
    others_classes = CourseClassFactory.create_batch(5, course=course_other, date=this_month_date, time_zone=UTC)
    # student should see only his own classes
    response = client.get(calendar_url)
    calendar_events = set(flatten_calendar_month_events(response.context_data['calendar']))
    compare_calendar_events_with_models(calendar_events, own_classes)
    # but in full calendar all classes should be shown
    calendar_events = set(
        flatten_calendar_month_events(client.get(reverse('study:calendar_full')).context_data['calendar']))
    compare_calendar_events_with_models(calendar_events, own_classes + others_classes)
    next_month_qstr = (
        "?year={0}&month={1}"
        .format(response.context_data['calendar'].next_month.year,
                str(response.context_data['calendar'].next_month.month)))
    next_month_url = calendar_url + next_month_qstr
    assert smart_bytes(next_month_qstr) in response.content
    classes = flatten_calendar_month_events(
        client.get(next_month_url).context_data['calendar'])
    assert len(classes) == 0
    next_month_date = this_month_date + relativedelta(months=1)
    next_month_classes = (
        CourseClassFactory
        .create_batch(2, course=course, date=next_month_date))
    calendar_events = set(flatten_calendar_month_events(
        client.get(next_month_url).context_data['calendar']))
    compare_calendar_events_with_models(calendar_events, next_month_classes)


@pytest.mark.django_db
def test_full_calendar_security(client, assert_login_redirect, program_run_cub):
    u = StudentProfileFactory(academic_program_enrollment=program_run_cub).user
    url = reverse('study:calendar_full')
    assert_login_redirect(url)
    client.login(u)
    assert client.get(url).status_code == 200
    u = TeacherFactory()
    client.login(u)
    response = client.get(reverse('teaching:calendar_full'))
    assert response.status_code == 200


@pytest.mark.django_db
def test_correspondence_courses_in_a_full_calendar(client, program_cub001, program_run_cub, program_nup001):
    """Make sure correspondence courses are visible in a full calendar"""
    semester = SemesterFactory.create_current()
    student = StudentProfileFactory(academic_program_enrollment=program_run_cub).user
    client.login(student)
    this_month_date = datetime.datetime.utcnow()
    course = CourseFactory(semester=semester)
    for program in [program_cub001, program_nup001]:
        CourseProgramBindingFactory(program=program, course=course)
    CourseClassFactory.create_batch(
        3, course=course, date=this_month_date)
    classes = flatten_calendar_month_events(
        client.get(reverse("study:calendar_full")).context_data['calendar'])
    assert len(classes) == 3
    # Test that teacher sees all classes from any program they have courses from
    teacher = TeacherFactory()
    CourseProgramBindingFactory(
        program=program_cub001, course__teachers=[teacher], course__semester=semester
    )
    client.login(teacher)
    classes = flatten_calendar_month_events(
        client.get(reverse("teaching:calendar_full")).context_data['calendar'])
    assert len(classes) == 3
