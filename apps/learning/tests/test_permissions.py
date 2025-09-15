import datetime

import pytest
from django.utils import timezone

from auth.permissions import perm_registry
from core.utils import instance_memoize
from courses.models import (
    Course, CourseGroupModes, CourseTeacher, StudentGroupTypes
)
from courses.tests.factories import (
    AssignmentFactory, CourseFactory, CourseTeacherFactory, SemesterFactory, CourseProgramBindingFactory
)
from learning.models import StudentAssignment
from learning.permissions import (
    CreateAssignmentComment, CreateAssignmentCommentAsLearner,
    CreateAssignmentCommentAsTeacher, CreateStudentGroup, CreateStudentGroupAsTeacher,
    DeleteStudentGroup, DeleteStudentGroupAsTeacher, EditGradebook,
    EditOwnAssignmentExecutionTime, EditOwnStudentAssignment, EnrollInCourse,
    EnrollOrLeavePermissionObject, UpdateStudentGroup, UpdateStudentGroupAsTeacher,
    ViewAssignmentCommentAttachment, ViewCourseEnrollment, ViewEnrollment,
    ViewGradebook, ViewOwnEnrollment, ViewOwnGradebook, ViewRelatedStudentAssignment,
    ViewStudentAssignment, ViewStudentGroup, ViewStudentGroupAsTeacher
)
from learning.services import CourseRole, EnrollmentService, course_access_role
from learning.settings import GradeTypes, StudentStatuses
from learning.tests.factories import (
    AssignmentCommentFactory, EnrollmentFactory,
    StudentAssignmentFactory, StudentGroupFactory
)
from users.models import ExtendedAnonymousUser, StudentTypes, User
from users.tests.factories import (
    CuratorFactory, StudentFactory, StudentProfileFactory, TeacherFactory, UserFactory
)


def delete_enrollment_cache(user: User, course: Course):
    instance_memoize.delete_cache(user)


@pytest.mark.django_db
def test_view_student_group():
    user = UserFactory()
    teacher, spectator = TeacherFactory.create_batch(2)
    curator = CuratorFactory()
    student = StudentFactory()
    s = SemesterFactory.create_current()
    course = CourseFactory.create(semester=s, teachers=[teacher], group_mode=CourseGroupModes.MANUAL)
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    course_other = CourseFactory.create(semester=s, group_mode=CourseGroupModes.MANUAL)
    sg1 = StudentGroupFactory.create(course=course)
    sg2 = StudentGroupFactory.create()
    EnrollmentFactory.create(student=student, course=course, student_group=sg1)

    assert ViewStudentGroup.name in perm_registry
    assert ViewStudentGroupAsTeacher.name in perm_registry
    assert not user.has_perm(ViewStudentGroup.name, course)
    assert not student.has_perm(ViewStudentGroup.name, course)
    assert teacher.has_perm(ViewStudentGroup.name, course)
    assert spectator.has_perm(ViewStudentGroup.name, course)
    assert not teacher.has_perm(ViewStudentGroup.name, course_other)
    assert curator.has_perm(ViewStudentGroup.name, course)


@pytest.mark.django_db
def test_update_student_group():
    user = UserFactory()
    teacher, spectator = TeacherFactory.create_batch(2)
    curator = CuratorFactory()
    student = StudentFactory()
    s = SemesterFactory.create_current()
    course = CourseFactory.create(semester=s, teachers=[teacher], group_mode=CourseGroupModes.MANUAL)
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    sg1 = StudentGroupFactory.create(course=course)
    sg2 = StudentGroupFactory.create()
    EnrollmentFactory.create(student=student, course=course, student_group=sg1)

    assert UpdateStudentGroup.name in perm_registry
    assert UpdateStudentGroupAsTeacher.name in perm_registry
    assert not user.has_perm(UpdateStudentGroup.name, sg1)
    assert not student.has_perm(UpdateStudentGroup.name, sg1)
    assert not spectator.has_perm(UpdateStudentGroup.name, sg1)
    assert teacher.has_perm(UpdateStudentGroup.name, sg1)
    assert not teacher.has_perm(UpdateStudentGroup.name, sg2)
    assert curator.has_perm(UpdateStudentGroup.name, sg1)
    assert curator.has_perm(UpdateStudentGroup.name, sg2)


@pytest.mark.django_db
def test_delete_student_group():
    user = UserFactory()
    teacher, spectator = TeacherFactory.create_batch(2)
    curator = CuratorFactory()
    student = StudentFactory()
    semester = SemesterFactory.create_current()
    course1, course2 = CourseFactory.create_batch(2, semester=semester, teachers=[teacher])
    sg1 = StudentGroupFactory(course=course1, type=StudentGroupTypes.MANUAL)
    sg2 = StudentGroupFactory(course=course2, type=StudentGroupTypes.SYSTEM)
    sg3 = StudentGroupFactory(type=StudentGroupTypes.MANUAL)
    CourseTeacherFactory(course=course1, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    EnrollmentFactory(student=student, course=course1, student_group=sg1)
    assert DeleteStudentGroup.name in perm_registry
    assert DeleteStudentGroupAsTeacher.name in perm_registry
    assert not user.has_perm(DeleteStudentGroup.name, sg1)
    assert not student.has_perm(DeleteStudentGroup.name, sg1)
    assert not spectator.has_perm(DeleteStudentGroup.name, sg1)
    assert not teacher.has_perm(DeleteStudentGroup.name, sg1), "has active student"
    assert not teacher.has_perm(DeleteStudentGroup.name, sg2), "unsupported group mode"
    assert not curator.has_perm(DeleteStudentGroup.name, sg2)
    sg2.type = StudentGroupTypes.MANUAL
    sg2.save()
    assert teacher.has_perm(DeleteStudentGroup.name, sg2)
    assert not teacher.has_perm(DeleteStudentGroup.name, sg3), "not a course teacher"
    assert curator.has_perm(DeleteStudentGroup.name, sg1)
    assert curator.has_perm(DeleteStudentGroup.name, sg2)


@pytest.mark.django_db
def test_create_student_group():
    user = UserFactory()
    teacher, spectator = TeacherFactory.create_batch(2)
    curator = CuratorFactory()
    student = StudentFactory()
    s = SemesterFactory.create_current()
    course = CourseFactory.create(semester=s, teachers=[teacher], group_mode=CourseGroupModes.MANUAL)
    course1 = CourseFactory.create(semester=s, group_mode=CourseGroupModes.MANUAL)
    CourseTeacherFactory(course=course, teacher=spectator,
                         roles=CourseTeacher.roles.spectator)
    assert CreateStudentGroup.name in perm_registry
    assert CreateStudentGroupAsTeacher.name in perm_registry
    assert not user.has_perm(CreateStudentGroup.name, course)
    assert not user.has_perm(CreateStudentGroup.name, course1)
    assert not student.has_perm(CreateStudentGroup.name, course)
    assert not student.has_perm(CreateStudentGroup.name, course1)
    assert not spectator.has_perm(CreateStudentGroup.name, course)
    assert teacher.has_perm(CreateStudentGroup.name, course)
    assert not teacher.has_perm(CreateStudentGroup.name, course1)
    assert curator.has_perm(CreateStudentGroup.name, course)
    assert curator.has_perm(CreateStudentGroup.name, course1)


@pytest.mark.django_db
def test_course_access_role_for_anon_and_curator():
    course = CourseFactory()
    anonymous_user = ExtendedAnonymousUser()
    role = course_access_role(course=course, user=anonymous_user)
    assert role == CourseRole.NO_ROLE
    curator = CuratorFactory()
    role = course_access_role(course=course, user=curator)
    assert role == CourseRole.CURATOR
    curator.status = StudentStatuses.EXPELLED
    curator.save()
    delete_enrollment_cache(curator, course)
    role = course_access_role(course=course, user=curator)
    assert role == CourseRole.CURATOR


@pytest.mark.django_db
def test_course_access_role_teacher():
    teacher = TeacherFactory()
    teacher_other = TeacherFactory()
    course = CourseFactory(teachers=[teacher])
    role = course_access_role(course=course, user=teacher)
    assert role == CourseRole.TEACHER
    role = course_access_role(course=course, user=teacher_other)
    assert role == CourseRole.NO_ROLE
    # Make sure that teacher role is prevailed on any student role
    student_profile = StudentProfileFactory(user=teacher)
    role = course_access_role(course=course, user=teacher)
    assert role == CourseRole.TEACHER
    delete_enrollment_cache(teacher, course)
    student_profile.status = StudentStatuses.EXPELLED
    student_profile.save()
    role = course_access_role(course=course, user=teacher)
    assert role == CourseRole.TEACHER
    EnrollmentFactory(student=teacher, course=course, grade=1)
    delete_enrollment_cache(teacher, course)
    assert course_access_role(course=course, user=teacher) == CourseRole.TEACHER
    # Spectator has a teacher role
    ct = CourseTeacher.objects.get(course=course, teacher=teacher)
    ct.roles = CourseTeacher.roles.spectator
    ct.save()
    assert course_access_role(course=course, user=teacher) == CourseRole.TEACHER


@pytest.mark.django_db
@pytest.mark.parametrize("inactive_status", StudentStatuses.inactive_statuses)
def test_course_access_role_student(inactive_status, settings):
    course = CourseFactory()
    prev_course = CourseFactory(completed_at=datetime.date.today())
    student = StudentFactory()  # not expelled
    role = course_access_role(course=course, user=student)
    assert role == CourseRole.NO_ROLE
    delete_enrollment_cache(student, course)
    student_profile = student.get_student_profile()
    e = EnrollmentFactory(student=student, course=course,
                          grade=GradeTypes.NOT_GRADED)
    # The course from the current semester and student has no grade.
    # It means to us that course is not failed by enrolled student
    role = course_access_role(course=course, user=student)
    assert role == CourseRole.STUDENT_REGULAR
    # Failed course enrollment
    e2 = EnrollmentFactory(student=student, course=prev_course, grade=1)
    role = course_access_role(course=prev_course, user=student)
    assert role == CourseRole.STUDENT_RESTRICT
    # Inactive student has restricted access to all courses they enrolled in
    delete_enrollment_cache(student, course)
    delete_enrollment_cache(student, prev_course)
    assert student_profile == e.student_profile
    student_profile.status = inactive_status
    student_profile.save()
    role = course_access_role(course=prev_course, user=student)
    assert role == CourseRole.STUDENT_RESTRICT
    role = course_access_role(course=course, user=student)
    assert role == CourseRole.STUDENT_RESTRICT


@pytest.mark.django_db
def test_enroll_in_course(program_cub001, program_run_cub, program_nup001, program_run_nup):
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)
    tomorrow = today + datetime.timedelta(days=1)
    term = SemesterFactory.create_current()
    course = CourseFactory(
        semester=term,
        completed_at=(today + datetime.timedelta(days=10)),
        capacity=0,
    )
    binding_cub = CourseProgramBindingFactory(
        course=course,
        program=program_cub001,
        enrollment_end_date=tomorrow
    )
    student_cub = StudentFactory(student_profile__academic_program_enrollment=program_run_cub)
    student_cub_profile = student_cub.get_student_profile()
    perm_obj_cub = EnrollOrLeavePermissionObject(course, student_cub_profile)
    student_nup = StudentFactory(student_profile__academic_program_enrollment=program_run_nup)
    student_nup_profile = student_nup.get_student_profile()
    perm_obj_nup = EnrollOrLeavePermissionObject(course, student_nup_profile)
    assert student_cub.has_perm(EnrollInCourse.name, perm_obj_cub)
    # Enrollment is closed
    binding_cub.enrollment_end_date = yesterday
    binding_cub.save()
    assert not student_cub.has_perm(EnrollInCourse.name, perm_obj_cub)
    binding_cub.enrollment_end_date = tomorrow
    binding_cub.save()
    assert student_cub.has_perm(EnrollInCourse.name, perm_obj_cub)
    # Student with inactive status
    student_cub_profile.status = StudentStatuses.EXPELLED
    student_cub_profile.save()
    assert not student_cub.has_perm(EnrollInCourse.name, perm_obj_cub)
    student_cub_profile.status = StudentStatuses.NORMAL
    student_cub_profile.save()
    assert student_cub.has_perm(EnrollInCourse.name, perm_obj_cub)
    # Full course capacity
    course.capacity = 1
    course.learners_count = 1
    assert not student_cub.has_perm(EnrollInCourse.name, perm_obj_cub)
    course.learners_count = 0
    assert student_cub.has_perm(EnrollInCourse.name, perm_obj_cub)
    # Student from other program shouldn't be able to enroll
    assert not student_nup.has_perm(EnrollInCourse.name, perm_obj_nup)

    binding_nup = CourseProgramBindingFactory(
        course=course,
        program=program_nup001,
        enrollment_end_date=tomorrow,
    )
    assert student_nup.has_perm(EnrollInCourse.name, perm_obj_nup)
    # Adding another course program binding shouldn't affect existing ones
    assert student_cub.has_perm(EnrollInCourse.name, perm_obj_cub)

    binding_cub.delete()
    assert student_nup.has_perm(EnrollInCourse.name, perm_obj_nup)
    assert not student_cub.has_perm(EnrollInCourse.name, perm_obj_cub)


@pytest.mark.django_db
def test_leave_course(settings):
    now = timezone.now()
    yesterday = now - datetime.timedelta(days=1)
    future = now + datetime.timedelta(days=3)
    term = SemesterFactory.create_current()
    enrollment = EnrollmentFactory(course__semester=term)
    student = enrollment.student
    perm_obj = EnrollOrLeavePermissionObject(
        enrollment.course,
        enrollment.student_profile,
    )
    assert student.has_perm("learning.leave_course", perm_obj)
    binding = enrollment.course_program_binding
    binding.enrollment_end_date = yesterday
    binding.save()
    assert not student.has_perm("learning.leave_course", perm_obj)
    binding.enrollment_end_date = future
    binding.save()
    assert student.has_perm("learning.leave_course", perm_obj)
    # Student couldn't leave abandoned course
    enrollment.is_deleted = True
    enrollment.save()
    student = User.objects.get(pk=student.pk)  # avoid cache
    assert not student.has_perm("learning.leave_course", perm_obj)


@pytest.mark.django_db
def test_create_assignment_comment():
    user = UserFactory()
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    curator = CuratorFactory()
    student_other = StudentFactory()
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=spectator, roles=CourseTeacher.roles.spectator)
    assert CreateAssignmentComment.name in perm_registry
    assert CreateAssignmentCommentAsTeacher in perm_registry
    assert CreateAssignmentCommentAsLearner in perm_registry
    enrollment = EnrollmentFactory(course=course)
    student_profile = enrollment.student_profile
    student = enrollment.student
    AssignmentFactory(course=course)
    assert StudentAssignment.objects.count() == 1
    sa = StudentAssignment.objects.first()
    assert teacher.has_perm(CreateAssignmentCommentAsTeacher.name, sa)
    assert not spectator.has_perm(CreateAssignmentCommentAsTeacher.name, sa)
    assert not teacher_other.has_perm(CreateAssignmentCommentAsTeacher.name, sa)
    assert not curator.has_perm(CreateAssignmentCommentAsTeacher.name, sa)
    assert not user.has_perm(CreateAssignmentCommentAsTeacher.name, sa)
    assert curator.has_perm(CreateAssignmentComment.name, sa)
    # Now check relation
    assert teacher.has_perm(CreateAssignmentComment.name, sa)
    assert not spectator.has_perm(CreateAssignmentComment.name, sa)
    assert not teacher_other.has_perm(CreateAssignmentComment.name, sa)
    assert not student_other.has_perm(CreateAssignmentComment.name, sa)
    assert student.has_perm(CreateAssignmentComment.name, sa)
    assert not user.has_perm(CreateAssignmentComment.name, sa)
    # User is a teacher and an invited student
    StudentProfileFactory(type=StudentTypes.INVITED, user=teacher)
    teacher.refresh_from_db()
    assert teacher.has_perm(CreateAssignmentComment.name, sa)
    assert teacher.has_perm(CreateAssignmentCommentAsTeacher.name, sa)
    assert not teacher.has_perm(CreateAssignmentCommentAsLearner.name, sa)
    # Inactive status
    student_profile.status = StudentStatuses.EXPELLED
    student_profile.save()
    instance_memoize.delete_cache(student)
    assert not student.has_perm(CreateAssignmentComment.name, sa)


@pytest.mark.django_db
def test_view_assignment_comment_attachment():
    user = UserFactory()
    assert not user.has_perm(ViewAssignmentCommentAttachment.name)
    curator = CuratorFactory()
    assert curator.has_perm(ViewAssignmentCommentAttachment.name)
    teacher, spectator = TeacherFactory.create_batch(2)
    # Relation check permissions on object only
    assert not teacher.has_perm(ViewAssignmentCommentAttachment.name)
    comment = AssignmentCommentFactory(author=teacher)
    comment.student_assignment.assignment.course.teachers.add(teacher)
    course = comment.student_assignment.assignment.course
    CourseTeacherFactory(course=course, teacher=spectator, roles=CourseTeacher.roles.spectator)
    assert teacher.has_perm(ViewAssignmentCommentAttachment.name,
                            comment.student_assignment)
    assert not spectator.has_perm(ViewAssignmentCommentAttachment.name,
                                  comment.student_assignment)
    student = StudentFactory()
    comment = AssignmentCommentFactory(author=student)
    course = comment.student_assignment.assignment.course
    course.semester = SemesterFactory.create_current()
    course.save()
    assert not student.has_perm(ViewAssignmentCommentAttachment.name,
                                comment.student_assignment)
    EnrollmentFactory(student=student, course=course)
    # Wrong student assignment
    assert not student.has_perm(ViewAssignmentCommentAttachment.name,
                                comment.student_assignment)
    comment.student_assignment = StudentAssignment.objects.get(
        student=student, assignment=comment.student_assignment.assignment)
    comment.save()
    assert student.has_perm(ViewAssignmentCommentAttachment.name,
                            comment.student_assignment)


@pytest.mark.django_db
def test_view_student_assignment_as_teacher():
    curator = CuratorFactory()
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=spectator, roles=CourseTeacher.roles.spectator)
    sa = StudentAssignmentFactory(assignment__course=course)
    assert not ViewRelatedStudentAssignment.rule(UserFactory(), sa)
    assert teacher.has_perm(ViewRelatedStudentAssignment.name, sa)
    assert not teacher_other.has_perm(ViewRelatedStudentAssignment.name, sa)
    assert not spectator.has_perm(ViewRelatedStudentAssignment.name, sa)
    assert not curator.has_perm(ViewRelatedStudentAssignment.name, sa)
    # `expelled` status on a student profile doesn't affect a teacher role
    StudentProfileFactory(user=teacher, status=StudentStatuses.EXPELLED)
    assert ViewRelatedStudentAssignment.rule(teacher, sa)


@pytest.mark.django_db
def test_view_student_assignment_relation():
    """
    Tests call chain `teacher.has_perm(ViewStudentAssignment.name, sa)` ->
    `teacher.has_perm(ViewRelatedStudentAssignment.name, sa)`
    """
    curator = CuratorFactory()
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=spectator, roles=CourseTeacher.roles.spectator)
    sa = StudentAssignmentFactory(assignment__course=course)
    assert not UserFactory().has_perm(ViewStudentAssignment.name, sa)
    assert teacher.has_perm(ViewStudentAssignment.name, sa)
    assert not spectator.has_perm(ViewStudentAssignment.name)
    assert not spectator.has_perm(ViewStudentAssignment.name, sa)
    assert not teacher.has_perm(ViewStudentAssignment.name)
    assert not teacher_other.has_perm(ViewStudentAssignment.name, sa)
    assert curator.has_perm(ViewStudentAssignment.name, sa)
    assert curator.has_perm(ViewStudentAssignment.name)


@pytest.mark.django_db
def test_edit_own_student_assignment():
    curator = CuratorFactory()
    teacher, teacher_other, spectator = TeacherFactory.create_batch(3)
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=spectator, roles=CourseTeacher.roles.spectator)
    sa = StudentAssignmentFactory(assignment__course=course)
    assert not EditOwnStudentAssignment.rule(UserFactory(), sa)
    assert EditOwnStudentAssignment.rule(teacher, sa)
    assert not EditOwnStudentAssignment.rule(teacher_other, sa)
    assert not EditOwnStudentAssignment.rule(spectator, sa)
    assert not EditOwnStudentAssignment.rule(curator, sa)
    # Teacher of the same meta course can't edit assignments where he's
    # not participated
    meta_course = course.meta_course
    teacher2 = TeacherFactory()
    course2 = CourseFactory(meta_course=meta_course, teachers=[teacher2])
    sa2 = StudentAssignmentFactory(assignment__course=course2)
    assert EditOwnStudentAssignment.rule(teacher2, sa2)
    assert not EditOwnStudentAssignment.rule(teacher2, sa)


@pytest.mark.django_db
def test_update_assignment_execution_time():
    """
    Available to the student only after course teacher assessed student work
    """
    permission_name = EditOwnAssignmentExecutionTime.name
    sa = StudentAssignmentFactory(score=None)
    curator = CuratorFactory()
    student = sa.student
    student_other = StudentFactory()
    teacher = TeacherFactory()
    user = UserFactory()
    no_permission = [teacher, user, student_other, curator]
    for u in no_permission:
        assert not u.has_perm(permission_name, sa)
    # Permission denied until student assignment without a score
    assert not student.has_perm(permission_name, sa)
    sa.score = 0
    assert student.has_perm(permission_name, sa)
    for u in no_permission:
        assert not u.has_perm(permission_name, sa)


@pytest.mark.django_db
def test_view_gradebook():
    teacher = TeacherFactory()
    teacher_other = TeacherFactory()
    teacher_spectator = TeacherFactory()
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=teacher_spectator,
                         roles=CourseTeacher.roles.spectator)
    assert not teacher.has_perm(ViewGradebook.name)
    assert teacher.has_perm(ViewGradebook.name, course)
    assert not teacher_other.has_perm(ViewGradebook.name, course)
    assert teacher_spectator.has_perm(ViewGradebook.name, course)
    e = EnrollmentFactory(course=course)
    assert not e.student.has_perm(ViewGradebook.name, course)
    assert not UserFactory().has_perm(ViewGradebook.name, course)
    curator = CuratorFactory()
    assert curator.has_perm(ViewGradebook.name)


@pytest.mark.django_db
def test_edit_gradebook():
    teacher = TeacherFactory()
    teacher_other = TeacherFactory()
    teacher_spectator = TeacherFactory()
    course = CourseFactory(teachers=[teacher])
    CourseTeacherFactory(course=course, teacher=teacher_spectator,
                         roles=CourseTeacher.roles.spectator)
    assert teacher.has_perm(EditGradebook.name, course)
    assert not teacher_other.has_perm(EditGradebook.name, course)
    assert not teacher_spectator.has_perm(EditGradebook.name, course)
    e = EnrollmentFactory(course=course)
    assert not e.student.has_perm(EditGradebook.name, course)
    assert not UserFactory().has_perm(EditGradebook.name, course)
    curator = CuratorFactory()
    assert curator.has_perm(EditGradebook.name)
    assert not curator.has_perm(ViewOwnGradebook.name, course)


@pytest.mark.django_db
def test_view_enrollment(program_cub001, program_run_cub):
    semester = SemesterFactory.create_current()
    course = CourseFactory(semester=semester, group_mode=CourseGroupModes.MANUAL)
    CourseProgramBindingFactory(course=course, program=program_cub001)
    course_other = CourseFactory.create(semester=semester, group_mode=CourseGroupModes.MANUAL)
    CourseProgramBindingFactory(course=course_other, program=program_cub001)
    student_profile1, student_profile2 = StudentProfileFactory.create_batch(
        2, academic_program_enrollment=program_run_cub
    )
    user = UserFactory()
    curator = CuratorFactory()
    student1 = student_profile1.user
    student_other = StudentFactory()
    teacher, spectator, teacher_other = TeacherFactory.create_batch(3)
    CourseTeacherFactory(course=course, teacher=spectator, roles=CourseTeacher.roles.spectator)
    CourseTeacherFactory(course=course, teacher=teacher, roles=CourseTeacher.roles.lecturer)
    enrollment = EnrollmentService.enroll(student_profile1, course,
                                          student_group=StudentGroupFactory(course=course),
                                          reason_entry='test enrollment')
    enrollment_other = EnrollmentService.enroll(student_profile2, course_other,
                                                student_group=StudentGroupFactory(course=course_other),
                                                reason_entry='test enrollment')
    assert ViewEnrollment.name in perm_registry
    assert ViewCourseEnrollment.name in perm_registry
    assert ViewOwnEnrollment.name in perm_registry
    assert not user.has_perm(ViewEnrollment.name)
    assert not user.has_perm(ViewEnrollment.name, enrollment)
    assert not student_other.has_perm(ViewEnrollment.name, enrollment)
    assert not student1.has_perm(ViewEnrollment.name, enrollment_other)
    assert not teacher_other.has_perm(ViewEnrollment.name, enrollment)
    assert curator.has_perm(ViewEnrollment.name)
    assert curator.has_perm(ViewEnrollment.name, enrollment)
    assert teacher.has_perm(ViewEnrollment.name, enrollment)
    assert not spectator.has_perm(ViewEnrollment.name, enrollment)
    assert student1.has_perm(ViewEnrollment.name, enrollment)
