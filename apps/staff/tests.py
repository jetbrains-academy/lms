from urllib.parse import urlencode

import pytest

from core.models import University
from core.tests.factories import AcademicProgramRunFactory, LegacyUniversityFactory
from core.urls import reverse
from courses.tests.factories import SemesterFactory
from users.models import StudentProfile
from users.tests.factories import CuratorFactory, StudentProfileFactory


@pytest.mark.django_db
def test_view_student_progress_report_full_download_csv(client):
    url = reverse(
        "staff:students_progress_report",
        kwargs={"output_format": "csv", "on_duplicate": "last"},
    )
    curator = CuratorFactory()
    client.login(curator)
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"


@pytest.mark.django_db
def test_view_student_progress_report_for_term(client):
    curator = CuratorFactory()
    client.login(curator)
    term = SemesterFactory.create_current()
    url = reverse(
        "staff:students_progress_report_for_term",
        kwargs={"output_format": "csv", "term_type": term.type, "term_year": term.year},
    )
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"


@pytest.mark.django_db
def test_view_student_faces(client):
    university_1 = LegacyUniversityFactory()
    university_2 = LegacyUniversityFactory()
    program_2023 = AcademicProgramRunFactory(start_year=2023, program__university=university_1)
    program_2023_2 = AcademicProgramRunFactory(start_year=2023, program__university=university_2)
    program_2024 = AcademicProgramRunFactory(start_year=2024, program__university=university_1)
    program_2025 = AcademicProgramRunFactory(start_year=2025, program__university=university_2)
    student_profile_2023 = StudentProfileFactory(academic_program_enrollment=program_2023, year_of_admission=2023)
    student_profile_2023_2 = StudentProfileFactory(academic_program_enrollment=program_2023_2, year_of_admission=2023)
    student_profile_2024 = StudentProfileFactory(academic_program_enrollment=program_2024, year_of_admission=2024)
    student_profile_2025 = StudentProfileFactory(academic_program_enrollment=program_2025, year_of_admission=2025)

    curator = CuratorFactory()
    client.login(curator)
    url = reverse("staff:student_faces")

    response = client.get(url)
    assert response.status_code == 302
    response = client.get(response.url)
    university_choices = response.context_data['filter_form'].fields['university'].choices
    assert (university_1.id, university_1.name) in university_choices
    assert (university_2.id, university_2.name) in university_choices
    year_choices = response.context_data['filter_form'].fields['year'].choices
    assert year_choices == [(2025, 2025), (2024, 2024), (2023, 2023)]

    def search(university: University, year: int, expected_profiles: set[StudentProfile]):
        query = {
            'university': university.id,
            'year': year,
            'type': 'regular',
        }
        response = client.get(f'{url}?{urlencode(query)}')
        assert set(response.context_data['users']) == {x.user for x in expected_profiles}

    search(university_1, 2023, {student_profile_2023})
    search(university_1, 2024, {student_profile_2024})
    search(university_1, 2025, set())

    search(university_2, 2023, {student_profile_2023_2})
    search(university_2, 2024, set())
    search(university_2, 2025, {student_profile_2025})
