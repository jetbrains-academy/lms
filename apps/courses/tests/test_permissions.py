from datetime import date, timedelta

import pytest
from django.utils import timezone

from auth.mixins import PermissionRequiredMixin
from core.utils import instance_memoize
from courses.constants import MaterialVisibilityTypes
from courses.models import CourseTeacher
from courses.permissions import (
    CreateAssignment, CreateCourseClass, DeleteAssignment, DeleteAssignmentAttachment,
    DeleteCourseClass, EditAssignment, EditCourse, EditCourseClass,
    ViewCourseClassMaterials, ViewCourseContacts, ViewCourseInternalDescription
)
from courses.tests.factories import (
    AssignmentAttachmentFactory, AssignmentFactory, CourseClassFactory, CourseFactory,
    CourseNewsFactory, CourseTeacherFactory, CourseProgramBindingFactory
)
from learning.models import Enrollment, StudentAssignment
from learning.permissions import CreateCourseNews, DeleteCourseNews, EditCourseNews, ViewOwnStudentAssignment
from learning.settings import StudentStatuses
from learning.tests.factories import EnrollmentFactory
from users.models import User
from users.tests.factories import (
    CuratorFactory, InvitedStudentFactory, StudentFactory, TeacherFactory, UserFactory
)

@pytest.mark.django_db
def test_permission_view_own_student_assignment(client, program_cub001, program_run_cub):
    user = UserFactory()
    enrollment: Enrollment = EnrollmentFactory(student=user, grade=4)
    student_profile = enrollment.student_profile
    course = enrollment.course

    now = timezone.now()
    tomorrow = now + timedelta(days=1)
    in_two_days = now + timedelta(days=2)

    # Should have access by default
    assignment = AssignmentFactory(course=course, opens_at=now, deadline_at=in_two_days)
    student_assignment = StudentAssignment.objects.get(assignment=assignment, student=user)
    assert user.has_perm(ViewOwnStudentAssignment.name, student_assignment)

    # Shouldn't have access if the assignment is not open yet
    assignment.opens_at = tomorrow
    assignment.save()
    student_assignment.refresh_from_db()
    instance_memoize.delete_cache(user)
    assert not user.has_perm(ViewOwnStudentAssignment.name, student_assignment)

    # Shouldn't have access if the student has disenrolled
    assignment.opens_at = now
    assignment.save()
    enrollment.is_deleted = True
    enrollment.save()
    student_assignment.refresh_from_db()
    instance_memoize.delete_cache(user)
    assert not user.has_perm(ViewOwnStudentAssignment.name, student_assignment)

    # Shouldn't have access if the student failed the course
    enrollment.is_deleted = False
    enrollment.grade = 1
    enrollment.save()
    course.completed_at = now
    course.save()
    student_assignment.refresh_from_db()
    instance_memoize.delete_cache(user)
    assert not user.has_perm(ViewOwnStudentAssignment.name, student_assignment)

    # Shouldn't have access if the student is expelled
    course.completed_at = tomorrow
    course.save()
    enrollment.grade = 0
    enrollment.save()
    student_assignment.refresh_from_db()
    student_profile.status = StudentStatuses.EXPELLED
    student_profile.save()
    instance_memoize.delete_cache(user)
    assert not user.has_perm(ViewOwnStudentAssignment.name, student_assignment)

    # Should have access if the student is expelled, but has a positive grade for an assignment
    student_assignment.score = 5
    student_assignment.save()
    instance_memoize.delete_cache(user)
    assert user.has_perm(ViewOwnStudentAssignment.name, student_assignment)

    # Check that reverting all modifications works
    student_assignment.score = None
    student_assignment.save()
    student_profile.status = StudentStatuses.NORMAL
    student_profile.save()
    instance_memoize.delete_cache(user)
    assert user.has_perm(ViewOwnStudentAssignment.name, student_assignment)


@pytest.mark.django_db
def test_permission_create_course_assignment(client):
    """
    Curators and actual teachers have permissions to create course assignment
    """
    permission_name = CreateAssignment.name
    teacher, spectator = TeacherFactory.create_batch(2)
    course = CourseFactory(teachers=[teacher])
    curator = CuratorFactory()
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    user = UserFactory()
    student = StudentFactory()
    invited_student = InvitedStudentFactory()
    teacher_other = TeacherFactory()
    assert curator.has_perm(permission_name)
    assert teacher.has_perm(permission_name, course)
    assert not spectator.has_perm(permission_name, course)
    assert not user.has_perm(permission_name, course)
    assert not student.has_perm(permission_name, course)
    assert not invited_student.has_perm(permission_name, course)
    assert not teacher_other.has_perm(permission_name, course)


@pytest.mark.django_db
def test_permission_edit_course_assignment(client):
    permission_name = EditAssignment.name
    user = UserFactory()
    student = StudentFactory()
    curator = CuratorFactory()
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    invited_student = InvitedStudentFactory()
    assignment = AssignmentFactory(course=course)
    assert curator.has_perm(permission_name)
    assert teacher.has_perm(permission_name, assignment)
    assert not spectator.has_perm(permission_name, assignment)
    assert not user.has_perm(permission_name, assignment)
    assert not student.has_perm(permission_name, assignment)
    assert not invited_student.has_perm(permission_name, assignment)
    assert not teacher_other.has_perm(permission_name, assignment)


@pytest.mark.django_db
def test_permission_delete_course_assignment(client):
    permission_name = DeleteAssignment.name
    user = UserFactory()
    student = StudentFactory()
    curator = CuratorFactory()
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    invited_student = InvitedStudentFactory()
    assignment = AssignmentFactory(course=course)
    assert curator.has_perm(permission_name)
    assert teacher.has_perm(permission_name, assignment)
    assert not spectator.has_perm(permission_name, assignment)
    assert not user.has_perm(permission_name, assignment)
    assert not student.has_perm(permission_name, assignment)
    assert not invited_student.has_perm(permission_name, assignment)
    assert not teacher_other.has_perm(permission_name, assignment)


@pytest.mark.django_db
def test_permission_delete_assignment_attachment(client):
    permission_name = DeleteAssignmentAttachment.name
    user = UserFactory()
    student = StudentFactory()
    curator = CuratorFactory()
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    invited_student = InvitedStudentFactory()
    attachment = AssignmentAttachmentFactory(assignment__course=course)
    assert curator.has_perm(permission_name)
    assert teacher.has_perm(permission_name, attachment)
    assert not spectator.has_perm(permission_name, attachment)
    assert not user.has_perm(permission_name, attachment)
    assert not student.has_perm(permission_name, attachment)
    assert not invited_student.has_perm(permission_name, attachment)
    assert not teacher_other.has_perm(permission_name, attachment)


@pytest.mark.parametrize("permission_name", [
    EditCourseNews.name,
    DeleteCourseNews.name
])
@pytest.mark.django_db
def test_course_news_edit_delete_permissions(client, permission_name):
    user = UserFactory()
    student = StudentFactory()
    invited_student = InvitedStudentFactory()
    curator = CuratorFactory()
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    news = CourseNewsFactory(course=course)

    assert curator.has_perm(permission_name)
    assert teacher.has_perm(permission_name, news)
    assert not spectator.has_perm(permission_name, news)
    assert not user.has_perm(permission_name, news)
    assert not student.has_perm(permission_name, news)
    assert not invited_student.has_perm(permission_name, news)
    assert not teacher_other.has_perm(permission_name, news)

@pytest.mark.django_db
def test_course_news_create_permission(client):
    permission_name = CreateCourseNews.name
    user = UserFactory()
    student = StudentFactory()
    curator = CuratorFactory()
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    invited_student = InvitedStudentFactory()
    assert curator.has_perm(permission_name)
    assert teacher.has_perm(permission_name, course)
    assert not spectator.has_perm(permission_name, course)
    assert not user.has_perm(permission_name, course)
    assert not student.has_perm(permission_name, course)
    assert not invited_student.has_perm(permission_name, course)
    assert not teacher_other.has_perm(permission_name, course)


@pytest.mark.django_db
def test_permission_create_course_class(client):
    user = UserFactory()
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    curator = CuratorFactory()
    student = StudentFactory()

    course = CourseFactory()
    co_other = CourseFactory()

    assert not user.has_perm(CreateCourseClass.name, course)
    assert not teacher.has_perm(CreateCourseClass.name, course)
    assert not student.has_perm(CreateCourseClass.name, course)
    assert curator.has_perm(CreateCourseClass.name, course)

    CourseTeacherFactory(course=co_other, teacher=teacher)
    CourseTeacherFactory(course=co_other, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)

    assert teacher.has_perm(CreateCourseClass.name, co_other)
    assert not spectator.has_perm(CreateCourseClass.name, co_other)
    assert not teacher_other.has_perm(CreateCourseClass.name, co_other)
    assert not teacher.has_perm(CreateCourseClass.name, course)


@pytest.mark.django_db
def test_permission_edit_course_class(client, lms_resolver):
    user = UserFactory()
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    curator = CuratorFactory()
    student = StudentFactory()
    course_class = CourseClassFactory()
    cc_other = CourseClassFactory()

    url = course_class.get_update_url()
    resolver = lms_resolver(url)
    assert issubclass(resolver.func.view_class, PermissionRequiredMixin)
    assert resolver.func.view_class.permission_required == EditCourseClass.name

    assert not user.has_perm(EditCourseClass.name, course_class)
    assert not teacher.has_perm(EditCourseClass.name, course_class)
    assert not student.has_perm(EditCourseClass.name, course_class)
    assert curator.has_perm(EditCourseClass.name, course_class)

    CourseTeacherFactory(course=cc_other.course, teacher=teacher)
    CourseTeacherFactory(course=cc_other.course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    assert teacher.has_perm(EditCourseClass.name, cc_other)
    assert not spectator.has_perm(EditCourseClass.name, cc_other)
    assert not teacher_other.has_perm(EditCourseClass.name, cc_other)
    assert not teacher.has_perm(EditCourseClass.name, course_class)


@pytest.mark.django_db
def test_permission_delete_course_class(client, lms_resolver):
    user = UserFactory()
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    curator = CuratorFactory()
    student = StudentFactory()
    course_class = CourseClassFactory()
    cc_other = CourseClassFactory()

    url = course_class.get_delete_url()
    resolver = lms_resolver(url)
    assert issubclass(resolver.func.view_class, PermissionRequiredMixin)
    assert resolver.func.view_class.permission_required == DeleteCourseClass.name

    assert not user.has_perm(DeleteCourseClass.name, course_class)
    assert not teacher.has_perm(DeleteCourseClass.name, course_class)
    assert not student.has_perm(DeleteCourseClass.name, course_class)
    assert curator.has_perm(DeleteCourseClass.name, course_class)

    CourseTeacherFactory(course=cc_other.course, teacher=teacher)
    CourseTeacherFactory(course=cc_other.course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    assert teacher.has_perm(DeleteCourseClass.name, cc_other)
    assert not spectator.has_perm(DeleteCourseClass.name, cc_other)
    assert not teacher_other.has_perm(DeleteCourseClass.name, cc_other)
    assert not teacher.has_perm(DeleteCourseClass.name, course_class)


@pytest.mark.django_db
def test_course_class_materials_visibility_default(client):
    """User without bindings/enrollments can't see course materials"""
    user = UserFactory()
    course = CourseFactory()
    course_class = CourseClassFactory(
        course=course,
        materials_visibility=MaterialVisibilityTypes.PARTICIPANTS)
    assert not user.has_perm(ViewCourseClassMaterials.name, course_class)
    course_class.materials_visibility = MaterialVisibilityTypes.COURSE_PARTICIPANTS
    instance_memoize.delete_cache(user)
    assert not user.has_perm(ViewCourseClassMaterials.name, course_class)


@pytest.mark.django_db
def test_course_class_materials_visibility_students(client):
    course = CourseFactory()
    course_class = CourseClassFactory(
        course=course,
        materials_visibility=MaterialVisibilityTypes.PARTICIPANTS
    )
    participant: User = StudentFactory()
    student_profile = participant.get_student_profile()
    CourseProgramBindingFactory(
        course=course,
        program=student_profile.academic_program_enrollment.program
    )
    assert participant.has_perm(ViewCourseClassMaterials.name, course_class)
    course_class.materials_visibility = MaterialVisibilityTypes.COURSE_PARTICIPANTS
    instance_memoize.delete_cache(participant)
    assert not participant.has_perm(ViewCourseClassMaterials.name, course_class)
    EnrollmentFactory(student=participant, course=course, grade=4)
    instance_memoize.delete_cache(participant)
    assert participant.has_perm(ViewCourseClassMaterials.name, course_class)


@pytest.mark.django_db
def test_course_class_materials_visibility_teachers(client):
    teacher, course_teacher, spectator = TeacherFactory.create_batch(3)
    course = CourseFactory(teachers=[course_teacher])
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    course_class = CourseClassFactory(
        course=course,
        materials_visibility=MaterialVisibilityTypes.PARTICIPANTS
    )
    assert not teacher.has_perm(ViewCourseClassMaterials.name, course_class)
    assert spectator.has_perm(ViewCourseClassMaterials.name, course_class)
    assert course_teacher.has_perm(ViewCourseClassMaterials.name, course_class)
    course_class.materials_visibility = MaterialVisibilityTypes.COURSE_PARTICIPANTS
    instance_memoize.delete_cache(teacher)
    instance_memoize.delete_cache(course_teacher)
    assert not teacher.has_perm(ViewCourseClassMaterials.name, course_class)
    assert spectator.has_perm(ViewCourseClassMaterials.name, course_class)
    assert course_teacher.has_perm(ViewCourseClassMaterials.name, course_class)


@pytest.mark.django_db
def test_view_course_internal_description():
    permission_name = ViewCourseInternalDescription.name
    curator = CuratorFactory()
    teacher1, teacher_other, spectator = TeacherFactory.create_batch(3)
    course = CourseFactory(teachers=[teacher1], completed_at=date.today())
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    assert curator.has_perm(permission_name)
    assert curator.has_perm(permission_name, course)
    assert teacher1.has_perm(permission_name, course)
    assert spectator.has_perm(permission_name, course)
    assert not teacher1.has_perm(permission_name)
    assert not teacher_other.has_perm(permission_name, course)
    assert not teacher_other.has_perm(permission_name)
    enrollment1 = EnrollmentFactory(course=course, grade=4)
    student = enrollment1.student_profile.user
    assert not student.has_perm(permission_name)
    assert student.has_perm(permission_name, course)
    # Failed the course
    enrollment1.grade = 1
    enrollment1.save()
    instance_memoize.delete_cache(student)
    assert not student.has_perm(permission_name, course)
    # Inactive profile
    enrollment1.grade = 4
    enrollment1.save()
    instance_memoize.delete_cache(student)
    assert student.has_perm(permission_name, course)
    enrollment1.student_profile.status = StudentStatuses.EXPELLED
    enrollment1.student_profile.save()
    instance_memoize.delete_cache(student)
    assert not student.has_perm(permission_name, course)
    enrollment2 = EnrollmentFactory(grade=4)
    student2 = enrollment2.student_profile.user
    assert not student2.has_perm(permission_name)
    assert not student2.has_perm(permission_name, course)


@pytest.mark.django_db
def test_permission_edit_course_description(client):
    permission_name = EditCourse.name
    user = UserFactory()
    student = StudentFactory()
    curator = CuratorFactory()
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    invited_student = InvitedStudentFactory()
    assert curator.has_perm(permission_name)
    assert teacher.has_perm(permission_name, course)
    assert not spectator.has_perm(permission_name, course)
    assert not user.has_perm(permission_name, course)
    assert not student.has_perm(permission_name, course)
    assert not invited_student.has_perm(permission_name, course)
    assert not teacher_other.has_perm(permission_name, course)


@pytest.mark.django_db
def test_permission_view_course_contacts(client):
    permission_name = ViewCourseContacts.name
    user = UserFactory()
    curator = CuratorFactory()
    course_student, student = StudentFactory.create_batch(2)
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    EnrollmentFactory(course=course, student=course_student,
                      grade=4)

    assert not user.has_perm(permission_name, course)
    assert not student.has_perm(permission_name, course)
    assert not teacher_other.has_perm(permission_name, course)
    assert curator.has_perm(permission_name)
    assert course_student.has_perm(permission_name, course)
    assert teacher.has_perm(permission_name, course)

