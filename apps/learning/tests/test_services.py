from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.timezone import now

from core.tests.factories import AcademicProgramRunFactory
from courses.constants import AssigneeMode
from courses.models import CourseTeacher, StudentGroupTypes, CourseGroupModes
from courses.tests.factories import (
    AssignmentFactory, CourseFactory, CourseTeacherFactory
)
from learning.models import (
    AssignmentNotification, Enrollment, StudentAssignment, StudentGroup, EnrollmentGradeLog
)
from learning.services import AssignmentService
from learning.services.enrollment_service import update_enrollment_grade
from learning.services.notification_service import generate_notifications_about_new_submission
from learning.settings import StudentStatuses, GradeTypes, EnrollmentGradeUpdateSource
from learning.tests.factories import (
    AssignmentCommentFactory, AssignmentNotificationFactory, EnrollmentFactory,
    StudentAssignmentFactory, StudentGroupAssigneeFactory
)
from users.tests.factories import StudentProfileFactory, StudentFactory, CuratorFactory, TeacherFactory


@pytest.mark.django_db
def test_assignment_service_bulk_create_personal_assignments():
    course = CourseFactory(group_mode=CourseGroupModes.PROGRAM)
    enr_cub = EnrollmentFactory(course=course)
    enr_nup = EnrollmentFactory(course=course)
    enr_other = EnrollmentFactory(course=course)
    group_cub = StudentGroup.objects.get(course=course, program=enr_cub.course_program_binding.program)
    group_nup = StudentGroup.objects.get(course=course, program=enr_nup.course_program_binding.program)

    assert Enrollment.active.count() == 3
    assignment = AssignmentFactory(course=course)
    StudentAssignment.objects.all().delete()
    AssignmentService.bulk_create_student_assignments(assignment)
    assert StudentAssignment.objects.count() == 3
    StudentAssignment.objects.all().delete()
    AssignmentService.bulk_create_student_assignments(
        assignment, for_groups=[group_cub.pk, group_nup.pk]
    )
    # Students without student group will be skipped in this case
    assert StudentAssignment.objects.count() == 2
    StudentAssignment.objects.all().delete()
    AssignmentService.bulk_create_student_assignments(assignment, for_groups=[group_nup.pk])
    ss = StudentAssignment.objects.filter(assignment=assignment)
    assert len(ss) == 1
    assert ss[0].student_id == enr_nup.student_id
    StudentAssignment.objects.all().delete()
    AssignmentService.bulk_create_student_assignments(assignment, for_groups=[])
    assert StudentAssignment.objects.count() == 0
    # Check soft deleted enrollments don't taken into account
    enr_nup.is_deleted = True
    enr_nup.save()
    assert Enrollment.active.count() == 2
    AssignmentService.bulk_create_student_assignments(assignment)
    assert StudentAssignment.objects.count() == 2
    # Inactive status prevents generating student assignment too
    enr_cub.student_profile.status = StudentStatuses.EXPELLED
    enr_cub.student_profile.save()
    StudentAssignment.objects.all().delete()
    AssignmentService.bulk_create_student_assignments(assignment)
    assert StudentAssignment.objects.count() == 1
    # Now test assignment settings
    enr_cub.student_profile.status = StudentStatuses.NORMAL
    enr_cub.student_profile.save()
    enr_nup.is_deleted = False
    enr_nup.save()
    assignment.restricted_to.add(group_cub)
    StudentAssignment.objects.all().delete()
    AssignmentService.bulk_create_student_assignments(assignment)
    assert StudentAssignment.objects.filter(assignment=assignment).count() == 1
    assert StudentAssignment.objects.get(assignment=assignment).student_id == enr_cub.student_id
    # Test that only groups from assignment settings get involved
    # if `for_groups` provided
    StudentAssignment.objects.all().delete()
    AssignmentService.bulk_create_student_assignments(assignment, for_groups=[group_cub.pk, group_nup.pk])
    assert StudentAssignment.objects.filter(assignment=assignment).count() == 1
    assert StudentAssignment.objects.get(assignment=assignment).student_id == enr_cub.student_id


@pytest.mark.django_db
def test_assignment_service_bulk_create_personal_assignments_batches():
    course = CourseFactory(group_mode=CourseGroupModes.PROGRAM)
    enrollments = [
        EnrollmentFactory(course=course)
        for _ in range(200)
    ]
    mail.outbox = []
    assignment = AssignmentFactory(course=course)
    assert StudentAssignment.objects.count() == 200
    assert len(mail.outbox) == 200


@pytest.mark.parametrize("inactive_status", [StudentStatuses.EXPELLED])
@pytest.mark.django_db
def test_assignment_service_create_personal_assignments_inactive_status(inactive_status, settings):
    """
    Inactive student profile status prevents from generating assignment
    record for student.
    """
    course = CourseFactory(group_mode=CourseGroupModes.PROGRAM)
    assignment = AssignmentFactory(course=course)
    e = EnrollmentFactory(course=course)
    student_profile = e.student_profile
    StudentAssignment.objects.all().delete()
    AssignmentService.bulk_create_student_assignments(assignment)
    assert StudentAssignment.objects.count() == 1
    # Set inactive status
    StudentAssignment.objects.all().delete()
    student_profile.status = inactive_status
    student_profile.save()
    AssignmentService.bulk_create_student_assignments(assignment)
    assert StudentAssignment.objects.count() == 0


@pytest.mark.django_db
def test_assignment_service_bulk_create_personal_assignments_with_existing_records(settings):
    """
    Create personal assignments for assignment where some personal records
    already exist.
    """
    course = CourseFactory(group_mode=CourseGroupModes.MANUAL)
    enrollment1, enrollment2, enrollment3 = EnrollmentFactory.create_batch(3, course=course)
    student_profile1 = enrollment1.student_profile
    assignment = AssignmentFactory(course=course)
    StudentAssignment.objects.all().delete()
    AssignmentService.bulk_create_student_assignments(assignment)
    assert StudentAssignment.objects.filter(assignment=assignment).count() == 3
    StudentAssignment.objects.filter(assignment=assignment, student=student_profile1.user).delete()
    AssignmentService.bulk_create_student_assignments(assignment)
    assert StudentAssignment.objects.filter(assignment=assignment).count() == 3


@pytest.mark.django_db
def test_assignment_service_bulk_create_personal_assignments_notifications(settings):
    course = CourseFactory(group_mode=CourseGroupModes.MANUAL)
    enrollment1, enrollment2, enrollment3 = EnrollmentFactory.create_batch(3, course=course)
    assignment = AssignmentFactory(course=course)
    StudentAssignment.objects.all().delete()
    AssignmentService.bulk_create_student_assignments(assignment)
    assert AssignmentNotification.objects.count() == 3
    # 1 already exist
    StudentAssignment.objects.all().delete()
    AssignmentService.create_or_restore_student_assignment(assignment, enrollment1)
    AssignmentNotification.objects.all().delete()
    AssignmentService.bulk_create_student_assignments(assignment)
    assert AssignmentNotification.objects.count() == 2
    # 1 exist, 1 soft deleted
    StudentAssignment.objects.all().delete()
    AssignmentService.create_or_restore_student_assignment(assignment, enrollment1)
    student_assignment2 = AssignmentService.create_or_restore_student_assignment(assignment, enrollment2)
    student_assignment2.delete()
    assert student_assignment2.is_deleted
    AssignmentNotification.objects.all().delete()
    AssignmentService.bulk_create_student_assignments(assignment)
    assert AssignmentNotification.objects.count() == 2


@pytest.mark.django_db
def test_assignment_service_remove_personal_assignments():
    course = CourseFactory(group_mode=CourseGroupModes.PROGRAM)
    enr_cub = EnrollmentFactory(course=course)
    enr_nup = EnrollmentFactory(course=course)
    enr_other = EnrollmentFactory(course=course)
    group_cub = StudentGroup.objects.get(course=course, program=enr_cub.course_program_binding.program)
    group_nup = StudentGroup.objects.get(course=course, program=enr_nup.course_program_binding.program)

    assignment = AssignmentFactory(course=course)
    assert StudentAssignment.objects.filter(assignment=assignment).count() == 3
    AssignmentService.bulk_remove_student_assignments(assignment)
    assert StudentAssignment.objects.filter(assignment=assignment).count() == 0
    assert StudentAssignment.trash.filter(assignment=assignment).count() == 3
    AssignmentService.bulk_create_student_assignments(assignment)
    AssignmentService.bulk_remove_student_assignments(assignment, for_groups=[group_cub.pk])
    assert StudentAssignment.objects.filter(assignment=assignment).count() == 2
    assert StudentAssignment.trash.filter(assignment=assignment).count() == 1
    AssignmentService.bulk_remove_student_assignments(assignment, for_groups=[])
    assert StudentAssignment.objects.filter(assignment=assignment).count() == 2
    # Make sure notifications will be hard deleted
    sa_nup = StudentAssignment.objects.get(assignment=assignment, student=enr_nup.student)
    sa_other = StudentAssignment.objects.get(assignment=assignment, student=enr_other.student)
    AssignmentNotification.objects.all().delete()
    AssignmentNotificationFactory(student_assignment=sa_nup)
    AssignmentNotificationFactory(student_assignment=sa_other)
    assert AssignmentNotification.objects.count() == 2
    AssignmentService.bulk_remove_student_assignments(assignment, for_groups=[group_nup.pk])
    assert AssignmentNotification.objects.count() == 1
    assert AssignmentNotification.objects.filter(student_assignment=sa_other).exists()


@pytest.mark.django_db
def test_assignment_service_sync_personal_assignments():
    course = CourseFactory(group_mode=CourseGroupModes.PROGRAM)
    enr_cub = EnrollmentFactory(course=course)
    enr_nup = EnrollmentFactory(course=course)
    enr_other = EnrollmentFactory(course=course)
    group_cub = StudentGroup.objects.get(course=course, program=enr_cub.course_program_binding.program)
    group_nup = StudentGroup.objects.get(course=course, program=enr_nup.course_program_binding.program)

    assignment = AssignmentFactory(course=course, restricted_to=[group_cub])
    assert StudentAssignment.objects.filter(assignment=assignment).count() == 1
    assert StudentAssignment.objects.get(assignment=assignment).student_id == enr_cub.student_id
    # [cub] -> [cub, nup]
    assignment.restricted_to.add(group_nup)
    AssignmentService.sync_student_assignments(assignment)
    assert StudentAssignment.objects.filter(assignment=assignment).count() == 2
    assert not StudentAssignment.objects.filter(assignment=assignment,
                                                student_id=enr_other.student_id).exists()
    # [cub, nup] -> all
    assignment.restricted_to.clear()
    AssignmentService.sync_student_assignments(assignment)
    assert StudentAssignment.objects.filter(assignment=assignment).count() == 3
    # all -> [nup]
    assignment.restricted_to.add(group_nup)
    AssignmentService.sync_student_assignments(assignment)
    assert StudentAssignment.objects.filter(assignment=assignment).count() == 1
    # [cub] -> [nup, cub]
    assignment.restricted_to.add(group_cub)
    AssignmentService.sync_student_assignments(assignment)
    assert StudentAssignment.objects.filter(assignment=assignment).count() == 2


@pytest.mark.django_db
def test_mean_execution_time():
    assignment = AssignmentFactory()
    assert AssignmentService.get_mean_execution_time(assignment) is None
    sa1 = StudentAssignmentFactory(assignment=assignment,
                                   execution_time=timedelta(hours=2, minutes=4))
    assert AssignmentService.get_mean_execution_time(assignment) == timedelta(hours=2, minutes=4)
    sa2 = StudentAssignmentFactory(assignment=assignment,
                                   execution_time=timedelta(hours=4, minutes=12))
    assert AssignmentService.get_mean_execution_time(assignment) == timedelta(hours=3, minutes=8)
    sa3 = StudentAssignmentFactory(assignment=assignment,
                                   execution_time=timedelta(minutes=56))
    assert AssignmentService.get_mean_execution_time(assignment) == timedelta(hours=2, minutes=24)


@pytest.mark.django_db
def test_median_execution_time():
    assignment = AssignmentFactory()
    assert AssignmentService.get_median_execution_time(assignment) is None
    sa1 = StudentAssignmentFactory(assignment=assignment,
                                   execution_time=timedelta(hours=2, minutes=4))
    assert AssignmentService.get_median_execution_time(assignment) == timedelta(hours=2, minutes=4)
    sa2 = StudentAssignmentFactory(assignment=assignment,
                                   execution_time=timedelta(hours=4, minutes=12))
    assert AssignmentService.get_median_execution_time(assignment) == timedelta(hours=3, minutes=8)
    sa3 = StudentAssignmentFactory(assignment=assignment,
                                   execution_time=timedelta(minutes=56))
    assert AssignmentService.get_median_execution_time(assignment) == timedelta(hours=2, minutes=4)
    sa4 = StudentAssignmentFactory(assignment=assignment,
                                   execution_time=timedelta(minutes=4))
    assert AssignmentService.get_median_execution_time(assignment) == timedelta(hours=1, minutes=30)


@pytest.mark.django_db
def test_create_notifications_about_new_submission():
    course = CourseFactory()
    assignment = AssignmentFactory(course=course, assignee_mode=AssigneeMode.MANUAL)
    student_assignment = StudentAssignmentFactory(assignment=assignment)
    comment = AssignmentCommentFactory(author=student_assignment.student,
                                       student_assignment=student_assignment)
    AssignmentNotification.objects.all().delete()
    generate_notifications_about_new_submission(comment)
    assert AssignmentNotification.objects.count() == 0
    # Add first course teacher
    course_teacher1 = CourseTeacherFactory(course=course, roles=CourseTeacher.roles.lecturer)
    generate_notifications_about_new_submission(comment)
    assert AssignmentNotification.objects.count() == 0
    # Add course teachers with a reviewer role and mark them as responsible
    course_teacher2 = CourseTeacherFactory(course=course,
                                           roles=CourseTeacher.roles.reviewer,
                                           notify_by_default=True)
    course_teacher3 = CourseTeacherFactory(course=course,
                                           roles=CourseTeacher.roles.reviewer,
                                           notify_by_default=True)
    assignment.assignees.add(course_teacher2, course_teacher3)
    generate_notifications_about_new_submission(comment)
    assert AssignmentNotification.objects.count() == 2
    # Assign student assignment to teacher
    student_assignment.assignee = course_teacher2
    student_assignment.save()
    AssignmentNotification.objects.all().delete()
    generate_notifications_about_new_submission(comment)
    notifications = (AssignmentNotification.objects
                     .filter(student_assignment=student_assignment))
    assert notifications.count() == 1
    assert notifications[0].user == course_teacher2.teacher
    student_assignment.assignee = None
    student_assignment.save()
    # Set responsible teachers for the student group
    AssignmentNotification.objects.all().delete()
    enrollment = Enrollment.objects.get(course=course)
    StudentGroupAssigneeFactory(student_group=enrollment.student_group,
                                assignee=course_teacher3)
    assignment.assignee_mode = AssigneeMode.STUDENT_GROUP_DEFAULT
    assignment.save()
    generate_notifications_about_new_submission(comment)
    notifications = (AssignmentNotification.objects
                     .filter(student_assignment=student_assignment))
    assert notifications.count() == 1
    assert notifications[0].user == course_teacher3.teacher
    StudentGroupAssigneeFactory(student_group=enrollment.student_group,
                                assignee=course_teacher2)
    AssignmentNotification.objects.all().delete()
    generate_notifications_about_new_submission(comment)
    notifications = (AssignmentNotification.objects
                     .filter(student_assignment=student_assignment))
    assert notifications.count() == 2


@pytest.mark.django_db
def test_update_enrollment_grade_permissions():
    student = StudentFactory()

    enrollment = EnrollmentFactory(student=student)

    grade_changed_at = now()
    with pytest.raises(PermissionDenied):
        update_enrollment_grade(enrollment=enrollment,
                                old_grade=enrollment.grade,
                                new_grade=5,
                                editor=student,
                                grade_changed_at=grade_changed_at,
                                source=EnrollmentGradeUpdateSource.GRADEBOOK)

    curator = CuratorFactory()
    update_enrollment_grade(enrollment=enrollment,
                            old_grade=enrollment.grade,
                            new_grade=5,
                            editor=curator,
                            grade_changed_at=grade_changed_at,
                            source=EnrollmentGradeUpdateSource.GRADEBOOK)
    enrollment.refresh_from_db()
    assert enrollment.grade == 5
    logs = EnrollmentGradeLog.objects.all()
    assert logs.count() == 1
    log = logs.first()
    assert log.grade == 5
    assert log.entry_author == curator
    assert log.grade_changed_at == grade_changed_at
    assert log.source == EnrollmentGradeUpdateSource.GRADEBOOK

    teacher, another_teacher, spectator = TeacherFactory.create_batch(3)
    CourseTeacherFactory(teacher=teacher, course=enrollment.course)
    update_enrollment_grade(enrollment=enrollment,
                            old_grade=enrollment.grade,
                            new_grade=3,
                            editor=teacher,
                            grade_changed_at=grade_changed_at,
                            source=EnrollmentGradeUpdateSource.GRADEBOOK)
    enrollment.refresh_from_db()
    assert enrollment.grade == 3  # changed in db

    with pytest.raises(PermissionDenied):
        CourseTeacherFactory(teacher=another_teacher, course=CourseFactory())
        update_enrollment_grade(enrollment=enrollment,
                                old_grade=enrollment.grade,
                                new_grade=4,
                                editor=another_teacher,
                                grade_changed_at=grade_changed_at,
                                source=EnrollmentGradeUpdateSource.GRADEBOOK)

    CourseTeacherFactory(teacher=spectator, course=enrollment.course,
                         roles=CourseTeacher.roles.spectator)
    with pytest.raises(PermissionDenied) as e:
        CourseTeacherFactory(teacher=another_teacher, course=CourseFactory())
        update_enrollment_grade(enrollment=enrollment,
                                old_grade=enrollment.grade,
                                new_grade=4,
                                editor=spectator,
                                grade_changed_at=grade_changed_at,
                                source=EnrollmentGradeUpdateSource.GRADEBOOK)


@pytest.mark.django_db
def test_update_enrollment_grade_validation():
    enrollment = EnrollmentFactory()
    curator = CuratorFactory()

    with pytest.raises(ValidationError):
        update_enrollment_grade(enrollment=enrollment,
                                old_grade=enrollment.grade,
                                new_grade='incorrect grade',
                                editor=curator,
                                source=EnrollmentGradeUpdateSource.GRADEBOOK)

    with pytest.raises(ValidationError):
        update_enrollment_grade(enrollment=enrollment,
                                old_grade=enrollment.grade,
                                new_grade=4,
                                editor=curator,
                                source='incorrect source')


@pytest.mark.django_db
def test_update_enrollment_grade_concurrency():
    enrollment = EnrollmentFactory()
    curator = CuratorFactory()

    updated, _ = update_enrollment_grade(enrollment=enrollment,
                                         old_grade=enrollment.grade,
                                         new_grade=4,
                                         editor=curator,
                                         source=EnrollmentGradeUpdateSource.GRADEBOOK)
    assert updated
    assert enrollment.grade == 4  # changed on instance level
    enrollment.refresh_from_db()
    assert enrollment.grade == 4  # changed in db
    logs = EnrollmentGradeLog.objects.all()
    assert logs.count() == 1
    log = logs.first()
    assert log.grade == 4

    updated, _ = update_enrollment_grade(enrollment=enrollment,
                                         old_grade=3,
                                         new_grade=5,
                                         editor=curator,
                                         source=EnrollmentGradeUpdateSource.GRADEBOOK)
    assert not updated
    assert enrollment.grade == 4  # not changed on instance level
    enrollment.refresh_from_db()
    assert enrollment.grade == 4  # not changed in db
    logs = EnrollmentGradeLog.objects.all()
    assert logs.count() == 1  # there is no new logs

    # External grade change
    (Enrollment.objects.
     filter(pk=enrollment.pk)
     .update(grade=3))
    enrollment.grade = 1
    updated, _ = update_enrollment_grade(enrollment=enrollment,
                                         old_grade=3,
                                         new_grade=5,
                                         editor=curator,
                                         source=EnrollmentGradeUpdateSource.GRADEBOOK)
    assert updated
    assert enrollment.grade == 5  # instance value has been changed
    enrollment.refresh_from_db()
    assert enrollment.grade == 5  # db values has been changed
    logs = EnrollmentGradeLog.objects.all()
    assert logs.count() == 2

    # instance value is correct, but old_grade argument not
    updated, _ = update_enrollment_grade(enrollment=enrollment,
                                         old_grade=GradeTypes.RE_CREDIT,
                                         new_grade=3,
                                         editor=curator,
                                         source=EnrollmentGradeUpdateSource.GRADEBOOK)
    assert not updated
    assert enrollment.grade == 5  # instance value has been changed
    enrollment.refresh_from_db()
    assert enrollment.grade == 5  # db values has been changed
    logs = EnrollmentGradeLog.objects.all()
    assert logs.count() == 2
