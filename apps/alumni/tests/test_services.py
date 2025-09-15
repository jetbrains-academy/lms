import pytest
from django.utils import timezone

from alumni.services import promote_to_alumni
from learning.settings import StudentStatuses
from users.models import StudentProfile, StudentTypes
from users.tests.factories import StudentProfileFactory


@pytest.mark.django_db
def test_promote_to_alumni(program_run_cub):
    sp: StudentProfile = StudentProfileFactory(year_of_admission=2024)
    user = sp.user
    promote_to_alumni(sp)
    sp.refresh_from_db()
    assert sp.status == StudentStatuses.GRADUATED
    assert sp.year_of_graduation == timezone.now().year
    ap = StudentProfile.objects.filter(user=user, type=StudentTypes.ALUMNI).first()
    assert ap is not None
    assert ap != sp

    assert user.get_student_profile() == ap

    # Alumni profile is unused if there is an active student profile
    sp2: StudentProfile = StudentProfileFactory(user=user, year_of_admission=2025)
    assert user.get_student_profile() == sp2

    # There can only be one alumni profile
    promote_to_alumni(sp2)
    sp2.refresh_from_db()
    assert sp2.status == StudentStatuses.GRADUATED
    alumni_profiles = StudentProfile.objects.filter(user=user, type=StudentTypes.ALUMNI).all()
    assert len(alumni_profiles) == 1
    assert alumni_profiles[0] == ap
