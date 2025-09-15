import datetime
import pytest
from django.db import models
from urllib.parse import urlencode

from core.models import AcademicProgram, AcademicProgramRun
from core.tests.factories import SiteFactory
from core.urls import reverse_lazy
from courses.constants import SemesterTypes
from courses.tests.factories import CourseFactory, MetaCourseFactory, SemesterFactory
from learning.settings import GradeTypes, StudentStatuses
from learning.tests.factories import EnrollmentFactory
from users.models import StudentTypes
from users.tests.factories import CuratorFactory, StudentFactory, InvitedStudentFactory


def search(client, expected_code=200, expected_count=None, **filters):
    allowed_filters = (
        "name", "universities", "academic_programs", "profile_types",
        "year_of_admission", "status", "cnt_enrollments",
        "is_paid_basis"
    )
    base = reverse_lazy('staff:student_search_json')
    query = {}
    for k, v in filters.items():
        if not isinstance(v, list):
            v = [v]
        if k not in allowed_filters:
            raise ValueError(f'Search filter not allowed: {k}')
        # convert models to ids
        v = [x.pk if isinstance(x, models.Model) else x for x in v]
        query[k] = ','.join(str(x) for x in v)
    query = urlencode(query)
    response = client.get(f'{base}?{query}')
    assert response.status_code == expected_code
    response_data = response.json()
    if expected_code == 200:
        assert response_data['count'] == expected_count
    else:
        if expected_count is not None:
            raise NotImplementedError()
    return response_data


@pytest.mark.django_db
def test_student_search_by_name(client, settings, program_run_cub):
    curator = CuratorFactory()
    client.login(curator)
    student = StudentFactory(student_profile__year_of_admission=2024,
                             student_profile__academic_program_enrollment=program_run_cub,
                             student_profile__status=StudentStatuses.NORMAL,
                             last_name="Иванов",
                             first_name="Иван")
    search(client, name='лол', expected_count=0)
    # 1 symbol is too short to apply filter by name
    # but students will be searched anyway since lookup isn't empty
    search(client, name='и', expected_count=1)
    search(client, name='ан', expected_count=0)
    # Make sure `ts_vector` works fine with single quotes
    search(client, name="'d", expected_count=0)


@pytest.mark.django_db
def test_student_search(
    client, curator, settings,
    university_cub, university_nup,
    program_run_cub, program_run_nup
):
    """Simple test cases to make sure, multi values still works"""
    student = StudentFactory(student_profile__year_of_admission=2024,
                             student_profile__academic_program_enrollment=program_run_cub,
                             last_name='Иванов',
                             first_name='Иван')
    StudentFactory(student_profile__year_of_admission=2024,
                   student_profile__academic_program_enrollment=program_run_nup,
                   last_name='Иванов',
                   first_name='Иван')
    StudentFactory(student_profile__year_of_admission=2024,
                   student_profile__academic_program_enrollment=program_run_cub,
                   student_profile__status=StudentStatuses.EXPELLED,
                   last_name='Иванов',
                   first_name='Иван')
    invited = InvitedStudentFactory(student_profile__year_of_admission=2024)

    search(client, expected_code=403)
    client.login(curator)
    # Empty results by default
    search(client, expected_count=0)

    search(client, universities=university_cub, expected_count=2)
    search(client, universities=[university_cub, university_nup], expected_count=3)

    # Now test groups filter
    search(client, universities=university_cub, profile_types=StudentTypes.REGULAR, expected_count=2)
    search(client, universities=university_cub, profile_types=StudentTypes.INVITED, expected_count=0)

    search(
        client,
        universities=university_cub,
        profile_types=[StudentTypes.REGULAR, StudentTypes.INVITED],
        expected_count=2
    )

    search(
        client,
        universities=university_cub,
        profile_types=[StudentTypes.REGULAR, StudentTypes.INVITED],
        cnt_enrollments=2,
        expected_count=0,
    )

    # Check multi values still works for cnt_enrollments
    search(
        client,
        universities=university_cub,
        profile_types=[StudentTypes.REGULAR, StudentTypes.INVITED],
        cnt_enrollments=[0, 2],
        expected_count=2,
    )


@pytest.mark.django_db
def test_student_search_enrollments(client, curator, program_cub001, program_run_cub):
    """
    Count successfully passed courses instead of course_offerings.
    """
    client.login(curator)
    student = StudentFactory(student_profile__academic_program_enrollment=program_run_cub,
                             last_name='Иванов', first_name='Иван')
    filters = {
        'academic_programs': program_cub001,
        'profile_types': [StudentTypes.REGULAR, StudentTypes.INVITED],
    }
    search(client, **filters, cnt_enrollments=2, expected_count=0)
    search(client, **filters, cnt_enrollments=[0, 2], expected_count=1)

    s1 = SemesterFactory.create(year=2027, type=SemesterTypes.SPRING)
    s2 = SemesterFactory.create(year=2027, type=SemesterTypes.AUTUMN)
    mc1, mc2 = MetaCourseFactory.create_batch(2)
    co1 = CourseFactory.create(meta_course=mc1, semester=s1)
    co2 = CourseFactory.create(meta_course=mc1, semester=s2)
    e1 = EnrollmentFactory.create(student=student, course=co1,
                                  grade=4)
    e2 = EnrollmentFactory.create(student=student, course=co2,
                                  grade=GradeTypes.NOT_GRADED)
    search(client, **filters, cnt_enrollments=1, expected_count=1)

    e2.grade = 4
    e2.save()
    search(client, **filters, cnt_enrollments=1, expected_count=1)

    co3 = CourseFactory.create(meta_course=mc2)
    EnrollmentFactory.create(student=student, grade=4, course=co3)
    search(client, **filters, cnt_enrollments=2, expected_count=1)

    other_student = StudentFactory(student_profile__academic_program_enrollment=program_run_cub)
    e3 = EnrollmentFactory.create(student=other_student, grade=4)
    search(client, **filters, cnt_enrollments=2, expected_count=1)
    search(client, **filters, cnt_enrollments=[1, 2], expected_count=2)


@pytest.mark.django_db
def test_student_search_by_types(client, curator, settings, program_run_cub, program_run_nup):
    client.login(curator)
    students = StudentFactory.create_batch(
        3,
        student_profile__year_of_admission=2024,
        student_profile__academic_program_enrollment=program_run_cub,
    )
    invitees = InvitedStudentFactory.create_batch(
        4,
        student_profile__year_of_admission=2024,
    )
    # Empty results if no query provided
    search(client, expected_count=0)
    # And without any value it still empty
    search(client, profile_types=[], expected_count=0)

    search(
        client,
        status=StudentStatuses.NORMAL,
        profile_types=[],
        expected_count=len(students) + len(invitees),
    )

    search(
        client,
        status=StudentStatuses.NORMAL,
        profile_types=StudentTypes.REGULAR,
        year_of_admission=[2024, 2025],
        expected_count=len(students)
    )


@pytest.mark.django_db
def test_student_by_statuses(client, curator):
    client.login(curator)
    students_spb = StudentFactory.create_batch(
        4, student_profile__year_of_admission=2024
    )
    students_nsk = StudentFactory.create_batch(
        7, student_profile__year_of_admission=2024,
    )
    invitees = InvitedStudentFactory.create_batch(
        3, student_profile__year_of_admission=2024,
    )

    total_studying = len(students_spb) + len(students_nsk) + len(invitees)
    search(client, status=StudentStatuses.NORMAL, expected_count=total_studying)

    # Add some students with inactive status
    expelled = StudentFactory.create_batch(
        2, student_profile__year_of_admission=2024,
        student_profile__status=StudentStatuses.EXPELLED,
    )
    search(client, status=StudentStatuses.NORMAL, expected_count=total_studying)

    # More precisely by group
    search(
        client,
        profile_types=StudentTypes.INVITED,
        expected_count=len(invitees),
    )


@pytest.mark.django_db
def test_student_search_by_year_of_admission(settings, client):
    client.login(CuratorFactory())
    students_1 = StudentFactory.create_batch(3, student_profile__year_of_admission=2024)
    students_2 = StudentFactory.create_batch(2, student_profile__year_of_admission=2025)
    students_3 = StudentFactory.create_batch(2, student_profile__year_of_admission=2026)
    # Empty query
    search(client, year_of_admission=[], expected_count=0)
    search(client, year_of_admission=[2024], expected_count=len(students_1))
    search(client, year_of_admission=[2024, 2025], expected_count=len(students_1) + len(students_2))
    results3 = search(client, year_of_admission=[2026], expected_count=len(students_3))
    assert {s.pk for s in students_3} == {r["user_id"] for r in results3["results"]}


@pytest.mark.django_db
def test_filter_student_search_by_is_paid_basis(settings, client):
    client.login(CuratorFactory())
    students_1 = StudentFactory.create_batch(3, student_profile__is_paid_basis=True)
    students_2 = StudentFactory.create_batch(2, student_profile__is_paid_basis=True)
    students_3 = StudentFactory.create_batch(2, student_profile__is_paid_basis=False)
    # Empty query
    search(client, is_paid_basis=[], expected_count=0)
    results = search(client, is_paid_basis=0, expected_count=len(students_3))
    assert {s.pk for s in students_3} == {r["user_id"] for r in results["results"]}
    search(client, is_paid_basis=1, expected_count=len(students_1) + len(students_2))
    search(client, is_paid_basis=[0, 1], expected_count=len(students_1) + len(students_2) + len(students_3))


@pytest.mark.django_db
def test_filter_student_search_by_program_and_uni(
    settings,
    client,
    program_run_cub,
    program_run_nup,
    program_cub001,
    program_nup001,
    university_cub,
    university_nup,
):
    client.login(CuratorFactory())
    program_cub002 = AcademicProgram(title='cub002', code='CUB-002', university=university_cub)
    program_cub002.save()
    program_run_cub_2 = AcademicProgramRun(start_year=2024, program=program_cub002)
    program_run_cub_2.save()
    students_1 = StudentFactory.create_batch(1, student_profile__academic_program_enrollment=program_run_cub)
    students_2 = StudentFactory.create_batch(2, student_profile__academic_program_enrollment=program_run_cub_2)
    students_3 = StudentFactory.create_batch(4, student_profile__academic_program_enrollment=program_run_nup)

    search(client, academic_programs=[], expected_count=0)
    search(
        client,
        academic_programs=[program_cub001],
        expected_count=len(students_1)
    )
    results = search(
        client,
        academic_programs=[program_cub001, program_nup001],
        expected_count=len(students_1) + len(students_3)
    )
    assert {s.pk for s in students_1} | {s.pk for s in students_3} == {r["user_id"] for r in results["results"]}
    search(
        client,
        academic_programs=[program_cub001, program_cub002, program_nup001],
        expected_count=len(students_1) + len(students_2) + len(students_3)
    )

    search(client, universities=[], expected_count=0)
    search(
        client,
        universities=[university_cub],
        expected_count=len(students_1) + len(students_2)
    )
    search(
        client,
        universities=[university_cub, university_nup],
        expected_count=len(students_1) + len(students_2) + len(students_3)
    )
    results = search(
        client,
        universities=[university_nup],
        expected_count=len(students_3)
    )
    assert {s.pk for s in students_3} == {r["user_id"] for r in results["results"]}
