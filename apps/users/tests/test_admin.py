import pytest

from core.tests.factories import AcademicProgramRunFactory
from courses.models import Semester
from learning.settings import StudentStatuses
from users.admin import StudentProfileForm
from users.models import StudentTypes, AlumniConsent
from users.tests.factories import StudentProfileFactory


@pytest.mark.django_db
def test_create_different_profile_types_in_one_year_of_admission(client):
    current_year = Semester.get_current().year
    student = StudentProfileFactory(
        type=StudentTypes.INVITED,
        year_of_admission=current_year,
    )

    new_student_profile = {
        'user': student.user.pk,
        'type': StudentTypes.REGULAR,
        'status': StudentStatuses.NORMAL,
        'year_of_admission': current_year,
        'academic_program_enrollment': AcademicProgramRunFactory(),
        'alumni_consent': AlumniConsent.NOT_SET,
    }
    form = StudentProfileForm(new_student_profile)
    assert form.is_valid()
