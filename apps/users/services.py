import datetime
from enum import Enum, auto
from itertools import islice
from typing import Any, List, Optional

from django.core.exceptions import ValidationError
from django.db.models import Prefetch, Q, prefetch_related_objects
from registration.models import RegistrationProfile

from auth.registry import role_registry
from core.timezone import get_now_utc, UTC
from core.utils import bucketize
from learning.settings import StudentStatuses
from study_programs.models import StudyProgram
from users.constants import GenderTypes, Roles
from users.models import StudentProfile, StudentStatusLog, StudentTypes, User, UserGroup

AccountId = int


def get_student_profile_priority(student_profile: StudentProfile) -> int:
    """
    Calculates student profile priority based on profile type and status.
    The less value the higher priority.

    The priority values are divided into 2 groups by status:
        * active student profiles (the group with the highest priorities,
            value depends on the profile type)
        * inactive student profiles (the lowest priority)
    """
    min_priority = 1000
    if student_profile.type == StudentTypes.REGULAR:
        priority = 200
    else:
        priority = min_priority
    if (
        student_profile.status in StudentStatuses.inactive_statuses
        or student_profile.status == StudentStatuses.GRADUATED
    ):
        priority = min_priority + 200
    return priority


def create_student_profile(*, user: User, profile_type,
                           year_of_admission, **fields) -> StudentProfile:
    profile_fields = {
        **fields,
        "user": user,
        "type": profile_type,
        "year_of_admission": year_of_admission,
    }
    if profile_type == StudentTypes.REGULAR:
        # TODO: move to the .clean method
        if "academic_program_enrollment" not in profile_fields:
            msg = "Academic program enrollment is not set for the regular student"
            raise ValidationError(msg)
    # FIXME: Prevent creating 2 profiles for invited student in the same
    #  term through the admin interface
    student_profile = StudentProfile(**profile_fields)
    student_profile.full_clean()
    student_profile.save()
    # Append role permissions to the account if needed
    permission_role = StudentTypes.to_permission_role(student_profile.type)
    assign_role(account=student_profile.user, role=permission_role)
    return student_profile


# FIXME: get profile for Invited students from the current term ONLY
# FIXME: store term of registration or get date range for the term of registration
def get_student_profile(user: User, profile_type=None,
                        filters: List[Q] = None) -> Optional[StudentProfile]:
    """
    Returns the most actual student profile on site for user.

    User could have multiple student profiles in different cases, e.g.:
    * They passed distance branch in 2011 and then applied to the
        offline branch in 2013
    * Student didn't meet the requirements and was expelled in the first
        semester but reapplied on general terms for the second time
    * Regular student "came back" as invited
    """
    filters = filters or []
    if profile_type is not None:
        filters.append(Q(type=profile_type))
    student_profile = (StudentProfile.objects
                       .filter(*filters, user=user)
                       .order_by('priority', '-year_of_admission', '-pk')
                       .first())
    if student_profile is not None:
        # Invalidate cache on user model if the profile has been changed
        student_profile.user = user
    return student_profile


def get_student_profiles(*, user: User,
                         fetch_status_history: bool = False) -> List[StudentProfile]:
    student_profiles = list(StudentProfile.objects
                            .filter(user=user)
                            .select_related('academic_program_enrollment')
                            .order_by('priority', '-year_of_admission', '-pk'))
    syllabus_data = [
        sp.academic_program_enrollment.start_year if sp.academic_program_enrollment else None
        for sp in student_profiles
    ]
    if syllabus_data:
        academic_program_start_year = syllabus_data[0]
        in_array = Q(year=academic_program_start_year)
        for academic_program_start_year in islice(syllabus_data, 1, None):
            in_array |= Q(year=academic_program_start_year)
        queryset = (StudyProgram.objects
                    .select_related("academic_discipline")
                    .prefetch_core_courses_groups()
                    .filter(in_array)
                    .order_by('academic_discipline__name'))
        syllabus = bucketize(queryset, key=lambda sp: sp.year)
        for sp in student_profiles:
            # XXX: Keep in sync with StudentProfile.syllabus implementation
            key = sp.academic_program_enrollment.start_year if sp.academic_program_enrollment else None
            if sp.type != StudentTypes.INVITED:
                sp.__dict__['syllabus'] = syllabus.get(key, None)
    if fetch_status_history:
        queryset = (StudentStatusLog.objects
                    .order_by('-status_changed_at', '-pk'))
        prefetch_related_objects(student_profiles,
                                 Prefetch('status_history', queryset=queryset))
    return student_profiles


def update_student_status(student_profile: StudentProfile, *,
                          new_status: str, editor: User,
                          status_changed_at: Optional[datetime.date] = None) -> StudentProfile:
    """
    Updates student profile status value, then adds new log record to
    the student status history and tries to synchronize related account
    permissions based on the status transition value.

    To correctly resolve status transition must be called before calling
    .save() method on the student profile object.
    """
    # TODO: try to make this method as an implementation detail of the `student_profile_update` service method
    if new_status not in StudentStatuses.values:
        raise ValidationError("Unknown Student Status", code="invalid")

    old_status = student_profile.tracker.previous('status')
    # `status` field tracker will return `None` for unsaved model
    assert old_status is not None
    student_profile.status = new_status
    student_profile.save(update_fields=['status'])

    assign_or_revoke_student_role(student_profile=student_profile,
                                  old_status=old_status, new_status=new_status)

    log_entry = StudentStatusLog(status=new_status,
                                 student_profile=student_profile,
                                 entry_author=editor)

    if status_changed_at:
        log_entry.status_changed_at = status_changed_at

    log_entry.save()

    return student_profile


def get_student_status_history(student_profile: StudentProfile) -> List[StudentStatusLog]:
    return (StudentStatusLog.objects
            .filter(student_profile=student_profile)
            .order_by('-status_changed_at', '-pk'))


def assign_or_revoke_student_role(*, student_profile: StudentProfile,
                                  old_status: str, new_status: str) -> None:
    """
    Auto assign or remove permissions based on student status transition.

    Assumes that *new_status* already saved in DB.
    """
    transition = StudentStatusTransition.resolve(old_status, new_status)
    if transition == StudentStatusTransition.NEUTRAL:
        return None
    role = StudentTypes.to_permission_role(student_profile.type)
    user = student_profile.user
    if transition == StudentStatusTransition.DEACTIVATION:
        maybe_unassign_student_role(role, account=user)
    elif transition == StudentStatusTransition.ACTIVATION:
        assign_role(account=user, role=role)


def maybe_unassign_student_role(role: str, *, account: User):
    """
    Removes permissions associated with a student *role* from the user account
    if all student profiles related to the same role are inactive or
    in a complete state (like GRADUATED)
    """
    if role not in role_registry:
        raise ValidationError(f"Role {role} is not registered")
    valid_roles = {Roles.STUDENT, Roles.INVITED, Roles.ALUMNI}
    if role not in valid_roles:
        raise ValidationError(f"Role {role} is not a student role")
    profile_type = StudentTypes.from_permission_role(role)
    student_profiles = (StudentProfile.objects
                        .filter(user=account, type=profile_type)
                        .only('status'))
    # TODO: has_active_student_profile?
    if all(not sp.is_active for sp in student_profiles):
        unassign_role(account=account, role=role)


class StudentStatusTransition(Enum):
    NEUTRAL = auto()  # active -> active, inactive -> inactive
    ACTIVATION = auto()
    DEACTIVATION = auto()

    @classmethod
    def resolve(cls, old_status: str, new_status: str) -> "StudentStatusTransition":
        """Returns transition type based on student old/new status values."""
        was_active = old_status not in StudentStatuses.inactive_statuses
        is_active_now = new_status not in StudentStatuses.inactive_statuses
        if old_status == new_status:
            return StudentStatusTransition.NEUTRAL
        elif was_active and not is_active_now:
            return StudentStatusTransition.DEACTIVATION
        elif not was_active and is_active_now:
            return StudentStatusTransition.ACTIVATION
        else:
            return StudentStatusTransition.NEUTRAL


def create_account(*, username: str, password: str, email: str,
                   gender: str, time_zone: datetime.tzinfo,
                   is_active: bool, **fields: Any) -> User:
    if time_zone is None:
        time_zone = UTC
    if gender not in GenderTypes.values:
        raise ValidationError("Unknown gender value", code="invalid")
    new_user = User(username=username,
                    email=email, gender=gender, time_zone=time_zone,
                    is_active=is_active, date_joined=get_now_utc(),
                    is_staff=False, is_superuser=False)
    new_user.set_password(password)
    valid_fields = {'first_name', 'last_name'}
    for field_name, field_value in fields.items():
        if field_name in valid_fields:
            setattr(new_user, field_name, field_value)

    new_user.full_clean()
    new_user.save()

    return new_user


def create_registration_profile(*, user: User,
                                activation_key: Optional[str] = None) -> RegistrationProfile:
    if user.is_active:
        raise ValidationError("Account is already activated", code="invalid")
    registration_profile = RegistrationProfile(user=user, activated=False)
    if activation_key is None:
        registration_profile.create_new_activation_key(save=False)
    registration_profile.full_clean()
    registration_profile.save()
    return registration_profile


class UniqueUsernameError(Exception):
    pass


def generate_username_from_email(email: str, attempts: int = 10):
    """Returns username generated from email or random if it's already exists."""
    username = email.split("@", maxsplit=1)[0]
    if User.objects.filter(username=username).exists():
        username = User.generate_random_username(attempts=attempts)
    if not username:
        raise UniqueUsernameError(f"Username '{username}' is already taken. Failed to generate a random name.")
    return username


def assign_role(*, account: User, role: str):
    if role not in Roles.values:
        raise ValidationError(f"Role {role} is not registered", code="invalid")
    UserGroup.objects.get_or_create(user=account, role=role)


def unassign_role(*, account: User, role: str):
    if role not in Roles.values:
        raise ValidationError(f"Role {role} is not registered", code="invalid")
    UserGroup.objects.filter(user=account, role=role).delete()
