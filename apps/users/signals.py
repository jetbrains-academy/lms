from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from lms.utils import PublicRoute
from users.constants import student_permission_roles

from .models import StudentProfile, StudentTypes, User, UserGroup
from .services import get_student_profile, maybe_unassign_student_role


@receiver(post_save, sender=UserGroup)
def post_save_user_group(sender, instance: UserGroup, *args, **kwargs):
    if instance.role in student_permission_roles:
        profile_type = StudentTypes.from_permission_role(instance.role)
        get_student_profile(instance.user, profile_type=profile_type)


# FIXME: move to the service method
@receiver(post_delete, sender=StudentProfile)
def post_delete_student_profile(sender, instance: StudentProfile, **kwargs):
    deleted_profile = instance
    role = StudentTypes.to_permission_role(deleted_profile.type)
    maybe_unassign_student_role(role=role, account=deleted_profile.user)
