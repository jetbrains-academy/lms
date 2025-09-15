import rules

from auth.permissions import Permission, add_perm
from courses.models import CourseTeacher, Course
from users.models import User, StudentProfile


@add_perm
class ViewProfile(Permission):
    name = "users.view_profile"


@add_perm
class ViewOwnProfile(Permission):
    name = "users.view_own_profile"

    @staticmethod
    @rules.predicate
    def rule(current_user: User, user: User):
        return current_user.id == user.id


@add_perm
class ViewLearnerProfile(Permission):
    name = "users.view_learner_profile"

    @staticmethod
    @rules.predicate
    def rule(current_user: User, user: User):
        return (
            Course.objects
            .filter(
                course_teachers__teacher_id=current_user.pk,
                course_teachers__roles=~CourseTeacher.roles.spectator
            )
            .filter(
                enrollment__student_id=user.pk,
                enrollment__is_deleted=False
            )
            .exists()
        )


@add_perm
class CreateCertificateOfParticipation(Permission):
    name = "users.create_certificate_of_participation"


@add_perm
class ViewCertificateOfParticipation(Permission):
    name = "users.view_certificate_of_participation"


@add_perm
class ViewAccountConnectedServiceProvider(Permission):
    name = "users.view_account_connected_service_provider"


@add_perm
class ViewOwnAccountConnectedServiceProvider(Permission):
    name = "users.view_own_account_connected_service_provider"

    @staticmethod
    @rules.predicate
    def rule(user, account: User):
        return user.is_authenticated and user == account


@add_perm
class UpdateStudentProfileStudentId(Permission):
    name = "users.update_student_profile_student_id"

    @staticmethod
    @rules.predicate
    def rule(user, profile: StudentProfile):
        return user.is_curator or profile.user_id == user.id


@rules.predicate
def is_curator(user):
    return user.is_superuser and user.is_staff
