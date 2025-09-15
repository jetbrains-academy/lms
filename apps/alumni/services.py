from django.db import transaction
from django.utils import timezone

from alumni.tasks import send_alumni_promotion_email
from learning.settings import StudentStatuses
from users.constants import Roles
from users.models import StudentProfile, StudentTypes
from users.services import assign_role


def promote_to_alumni(student_profile: StudentProfile) -> None:
    with transaction.atomic():
        current_year = timezone.now().year
        student_profile.status = StudentStatuses.GRADUATED
        student_profile.year_of_graduation = current_year
        student_profile.save()
        has_alumni_profile = StudentProfile.objects.filter(
            user=student_profile.user, type=StudentTypes.ALUMNI
        ).exists()
        if not has_alumni_profile:
            alumni_profile = StudentProfile(
                user=student_profile.user,
                year_of_admission=current_year,
                type=StudentTypes.ALUMNI,
            )
            alumni_profile.save()
            assign_role(account=student_profile.user, role=Roles.ALUMNI)
    if not has_alumni_profile:
        send_alumni_promotion_email.delay(
            student_profile.user.email, student_profile.user.first_name
        )
