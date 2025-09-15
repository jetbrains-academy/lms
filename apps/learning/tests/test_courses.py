import datetime
from zoneinfo import ZoneInfo

import pytest
import pytz

from courses.tests.factories import AssignmentFactory, CourseFactory, CourseProgramBindingFactory
from users.tests.factories import StudentFactory, TeacherFactory


@pytest.mark.django_db
def test_course_detail_view_timezone(client, program_cub001, program_run_cub, program_nup001, program_run_nup):
    """Test `tz_override` based on user time zone"""
    # 12 january 2017 23:59 (UTC)
    deadline_at = datetime.datetime(2017, 1, 12, 23, 59, 0, 0,
                                    tzinfo=pytz.UTC)
    tz_cub = ZoneInfo(program_cub001.university.city.time_zone)
    tz_nup = ZoneInfo(program_nup001.university.city.time_zone)
    teacher_nup = TeacherFactory(time_zone=tz_nup)
    student_cub = StudentFactory(time_zone=tz_cub, student_profile__academic_program_enrollment=program_run_cub)
    student_nup = StudentFactory(time_zone=tz_nup, student_profile__academic_program_enrollment=program_run_nup)
    course = CourseFactory(teachers=[teacher_nup])
    assignment = AssignmentFactory(deadline_at=deadline_at, course=course)
    # Anonymous user doesn't see tab
    assignments_tab_url = course.get_url_for_tab("assignments")
    response = client.get(assignments_tab_url)
    assert response.status_code == 302
    CourseProgramBindingFactory(course=course, program=program_nup001)
    CourseProgramBindingFactory(course=course, program=program_cub001)
    client.logout()

    client.login(teacher_nup)
    response = client.get(assignments_tab_url)
    assert response.status_code == 200
    assert response.context_data["tz_override"] == tz_nup
    client.login(student_nup)
    response = client.get(assignments_tab_url)
    assert response.status_code == 200
    assert response.context_data["tz_override"] == tz_nup
    client.login(student_cub)
    response = client.get(assignments_tab_url)
    assert response.status_code == 200
    assert response.context_data["tz_override"] == tz_cub
