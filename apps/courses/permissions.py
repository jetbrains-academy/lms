from rules import predicate

from auth.permissions import Permission, add_perm
from courses.constants import MaterialVisibilityTypes
from courses.models import Assignment, AssignmentAttachment, Course, CourseClass, CourseProgramBinding
from learning.permissions import course_access_role, CourseRole
from users.models import User


def can_view_private_materials(user: User, course: Course) -> bool:
    role = course_access_role(user=user, course=course)
    return role in {
        CourseRole.TEACHER,
        CourseRole.CURATOR,
        CourseRole.STUDENT_REGULAR
    }


@predicate
def can_view_course(user: User, course: Course) -> bool:
    role = course_access_role(user=user, course=course)
    return role in {
        CourseRole.TEACHER,
        CourseRole.CURATOR,
        CourseRole.STUDENT_REGULAR,
        CourseRole.STUDENT_RESTRICT,
        CourseRole.STUDENT_CAN_ENROLL
    }


@add_perm
class EditMetaCourse(Permission):
    name = "courses.change_metacourse"


@add_perm
class ViewCourse(Permission):
    name = "courses.view_course"
    rule = can_view_course


@add_perm
class ViewCourseInternalDescription(Permission):
    name = "courses.view_course_internal_description"


@add_perm
class ViewCourseInternalDescriptionAsTeacher(Permission):
    name = "teaching.view_course_internal_description"

    @staticmethod
    @predicate
    def rule(user, course: Course):
        return user in course.teachers.all()


@add_perm
class ViewCourseInternalDescriptionAsLearner(Permission):
    name = "study.view_course_internal_description"

    @staticmethod
    @predicate
    def rule(user, course: Course):
        from learning.services.enrollment_service import is_course_failed_by_student
        enrollment = user.get_enrollment(course.pk)
        if not enrollment:
            return False
        student_profile = enrollment.student_profile
        is_course_failed = is_course_failed_by_student(course, user, enrollment=enrollment)
        return student_profile.is_active and not is_course_failed


@add_perm
class EditCourse(Permission):
    name = "courses.edit_description"


@add_perm
class EditOwnCourse(Permission):
    name = 'teaching.edit_description'

    @staticmethod
    @predicate
    def rule(user, course: Course):
        return course.is_actual_teacher(user.pk)


@add_perm
class ViewCourseContacts(Permission):
    name = "courses.can_view_contacts"


@add_perm
class ViewCourseContactsAsTeacher(Permission):
    name = "teaching.can_view_contacts"

    @staticmethod
    @predicate
    def rule(user, course: Course):
        return user in course.teachers.all()


@add_perm
class ViewCourseContactsAsLearner(Permission):
    name = "learning.can_view_contacts"

    @staticmethod
    @predicate
    def rule(user, course: Course):
        return bool(user.get_enrollment(course.pk))


@add_perm
class ViewCourseAssignments(Permission):
    name = "courses.can_view_assignments"


@add_perm
class ViewAssignment(Permission):
    name = "courses.view_assignment"


@add_perm
class ViewOwnAssignment(Permission):
    name = "teaching.view_assignment"

    @staticmethod
    @predicate
    def rule(user, course: Course):
        return user in course.teachers.all()


@add_perm
class CreateAssignment(Permission):
    name = "courses.add_assignment"


@add_perm
class CreateOwnAssignment(Permission):
    name = "teaching.add_assignment"

    @staticmethod
    @predicate
    def rule(user, course: Course):
        return course.is_actual_teacher(user.pk)


@add_perm
class EditAssignment(Permission):
    name = "courses.change_assignment"


@add_perm
class EditOwnAssignment(Permission):
    name = "teaching.change_own_assignment"

    @staticmethod
    @predicate
    def rule(user, assignment: Assignment):
        return assignment.course.is_actual_teacher(user.pk)


@add_perm
class DeleteAssignment(Permission):
    name = "courses.delete_assignment"


@add_perm
class DeleteOwnAssignment(Permission):
    name = "teaching.delete_assignment"

    @staticmethod
    @predicate
    def rule(user, assignment: Assignment):
        return assignment.course.is_actual_teacher(user.pk)


@add_perm
class DeleteAssignmentAttachment(Permission):
    name = "courses.delete_assignment_attachment"


@add_perm
class DeleteAssignmentAttachmentAsTeacher(Permission):
    name = "teaching.delete_assignment_attachment"

    @staticmethod
    @predicate
    def rule(user, attachment: AssignmentAttachment):
        course: Course = attachment.assignment.course
        return course.is_actual_teacher(user.pk)


@add_perm
class ViewCourseClassMaterials(Permission):
    name = "courses.view_course_class_materials"

    @staticmethod
    @predicate
    def rule(user, course_class: CourseClass):
        visibility = course_class.materials_visibility
        if visibility == MaterialVisibilityTypes.PARTICIPANTS:
            return user.has_perm(ViewCourse.name, course_class.course)
        elif visibility == MaterialVisibilityTypes.COURSE_PARTICIPANTS:
            return can_view_private_materials(user, course_class.course)
        return False


@add_perm
class CreateCourseClass(Permission):
    name = "learning.create_courseclass"


@add_perm
class CreateOwnCourseClass(Permission):
    name = "teaching.create_courseclass"

    @staticmethod
    @predicate
    def rule(user, course: Course):
        return course.is_actual_teacher(user.pk)


@add_perm
class EditCourseClass(Permission):
    name = "learning.change_courseclass"


@add_perm
class EditOwnCourseClass(Permission):
    name = "teaching.change_courseclass"

    @staticmethod
    @predicate
    def rule(user, course_class: CourseClass):
        return course_class.course.is_actual_teacher(user.pk)


@add_perm
class DeleteCourseClass(Permission):
    name = "learning.delete_courseclass"


@add_perm
class DeleteOwnCourseClass(Permission):
    name = "learning.delete_own_courseclass"

    @staticmethod
    @predicate
    def rule(user, course_class: CourseClass):
        return course_class.course.is_actual_teacher(user.pk)
