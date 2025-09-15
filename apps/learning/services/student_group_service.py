import logging
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Q
from typing import Dict, List, Tuple

from core.models import AcademicProgram, AcademicProgramRun
from core.typings import assert_never
from core.utils import bucketize
from courses.constants import AssigneeMode
from courses.models import (
    Assignment, Course, CourseGroupModes, CourseTeacher, StudentGroupTypes, CourseProgramBinding
)
from courses.services import CourseService
from learning.models import (
    AssignmentGroup, CourseClassGroup, Enrollment, StudentGroup, StudentGroupAssignee,
    StudentGroupTeacherBucket
)
from learning.services.assignment_service import AssignmentService
from users.models import StudentProfile

CourseTeacherId = int
StudentGroupId = int
Bucket = dict
# Bucket structure:
#   student_groups: [pk`s of student_groups]
#   teachers: [pk`s of course_teachers]

logger = logging.getLogger(__name__)


class StudentGroupError(Exception):
    pass


class GroupEnrollmentKeyError(StudentGroupError):
    pass


class StudentGroupService:
    @staticmethod
    def _resolve_automatic_group(
        course: Course,
        group_type: str,
        program: AcademicProgram | None = None,
        program_run: AcademicProgramRun | None = None,
    ) -> StudentGroup:
        if group_type == StudentGroupTypes.PROGRAM:
            if not CourseProgramBinding.objects.filter(course=course, program=program).exists():
                raise ValidationError(f'Program {program} is not bound to the course', code='malformed')
            group, _ = StudentGroup.objects.get_or_create(
                type=group_type,
                course_id=course.pk,
                program_id=program.pk,
                defaults={'name': str(program)}
            )
        elif group_type == StudentGroupTypes.PROGRAM_RUN:
            if not CourseProgramBinding.objects.filter(course=course, program=program_run.program).exists():
                raise ValidationError(f"Program {program_run.program} is not bound to course", code="malformed")
            group, _ = StudentGroup.objects.get_or_create(
                type=group_type,
                course_id=course.pk,
                program_run_id=program_run.pk,
                defaults={'name': str(program_run)}
            )
        else:
            assert_never(group_type)
        return group

    @staticmethod
    def create(
        course: Course, *, group_type: str,
        program: AcademicProgram | None = None,
        program_run: AcademicProgramRun | None = None,
        name: str | None = None
    ) -> StudentGroup:
        if course.group_mode == CourseGroupModes.NO_GROUPS:
            raise StudentGroupError(f"Course group mode {course.group_mode} "
                                    f"does not support student groups")
        if group_type in (StudentGroupTypes.PROGRAM, StudentGroupTypes.PROGRAM_RUN):
            if group_type != course.group_mode:
                raise StudentGroupError(
                    f'Tried to add {group_type} group to course with {course.group_mode} group mode')
            return StudentGroupService._resolve_automatic_group(course, group_type, program, program_run)
        elif group_type == StudentGroupTypes.MANUAL:
            if not name:
                raise ValidationError('Provide a unique non-empty name', code='required')
            group = StudentGroup(
                course_id=course.pk,
                type=group_type,
                name=name
            )
            group.save()
            return group
        else:
            assert_never(group_type)

    @staticmethod
    def update(student_group: StudentGroup, *, name: str):
        student_group.name = name
        student_group.save()

    @classmethod
    def remove(cls, student_group: StudentGroup):
        # If this is the only one group presented in assignment restriction
        # settings after deleting it the assignment would be considered as
        # "available to all" - that's not really what we want to achieve.
        # The same is applied to CourseClass restriction settings.
        in_assignment_settings = (AssignmentGroup.objects
                                  .filter(group=student_group))
        in_class_settings = (CourseClassGroup.objects
                             .filter(group=student_group))
        active_students = (Enrollment.active
                           .filter(student_group=student_group))
        # XXX: This action will be triggered after removing course program binding (for PROGRAM type)
        # or all enrollments with that run (for PROGRAM_RUN type)
        if student_group.type in [StudentGroupTypes.PROGRAM, StudentGroupTypes.PROGRAM_RUN]:
            cast_to_manual = (active_students.exists() or
                              in_assignment_settings.exists() or
                              in_class_settings.exists())
            if cast_to_manual:
                student_group.type = StudentGroupTypes.MANUAL
                student_group.program = None
                student_group.program_run = None
                student_group.save()
            else:
                cls._move_unenrolled_students_to_default_group(student_group)
                student_group.delete()
        elif student_group.type == StudentGroupTypes.MANUAL:
            if active_students.exists():
                raise ValidationError("Students are attached to the student group")
            if in_assignment_settings.exists():
                raise ValidationError("Student group is a part of assignment restriction settings")
            if in_class_settings.exists():
                raise ValidationError("Student group is a part of class restriction settings")

            cls._move_unenrolled_students_to_default_group(student_group)
            student_group.delete()

    @classmethod
    def _move_unenrolled_students_to_default_group(cls, student_group: StudentGroup):
        """Transfers students who left the course to the default system group"""
        enrollments = (
            Enrollment.objects
            .filter(
                course_id=student_group.course_id,
                is_deleted=True,
                student_group=student_group,
            )
        )
        if len(enrollments) > 0:
            default_group = cls.get_or_create_default_group(student_group.course)
            enrollments.update(student_group=default_group)

    @classmethod
    def resolve(cls, course: Course, *, student_profile: StudentProfile):
        """Returns the target student group for unenrolled student."""
        if course.group_mode == CourseGroupModes.PROGRAM:
            return StudentGroupService._resolve_automatic_group(
                course,
                StudentGroupTypes.PROGRAM,
                program=student_profile.academic_program_enrollment.program,
            )
        elif course.group_mode == CourseGroupModes.PROGRAM_RUN:
            return StudentGroupService._resolve_automatic_group(
                course,
                StudentGroupTypes.PROGRAM_RUN,
                program_run=student_profile.academic_program_enrollment
            )
        elif course.group_mode == CourseGroupModes.MANUAL:
            student_group = cls.get_or_create_default_group(course)
            return student_group
        raise StudentGroupError(f"Course group mode {course.group_mode} is not supported")

    @staticmethod
    def get_or_create_default_group(course: Course) -> StudentGroup:
        """
        Logically this student group means "No Group" or NULL in terms of DB.

        Each student must be associated with a student group, but it's
        impossible to always know the target group.
        E.g. on enrollment it's impossible to always know in advance the
        target group or on deleting group student must be transferred
        to some group to meet the requirements.
        """
        if course.group_mode == CourseGroupModes.NO_GROUPS:
            raise StudentGroupError(f"Course group mode {course.group_mode} "
                                    f"does not support student groups")

        student_group, _ = StudentGroup.objects.get_or_create(
            course=course,
            type=StudentGroupTypes.SYSTEM,
            program_id__isnull=True,
            program_run_id__isnull=True,
            defaults={
                "name": "Others",
            })
        return student_group

    @classmethod
    def get_choices(cls, course: Course) -> List[Tuple[int, str]]:
        choices = []
        student_groups = CourseService.get_student_groups(course)
        for g in student_groups:
            label = g.get_name()
            choices.append((g.pk, label))
        return choices

    @staticmethod
    def add_assignees(student_group: StudentGroup, *,
                      assignment: Assignment = None,
                      teachers: List[CourseTeacher]) -> None:
        """Assigns new responsible teachers to the student group."""
        new_objects = []
        for teacher in teachers:
            fields = {
                "student_group": student_group,
                "assignee": teacher,
                "assignment": assignment if assignment else None
            }
            new_objects.append(StudentGroupAssignee(**fields))
        # Validate records before call .bulk_create()
        for sga in new_objects:
            sga.full_clean()
        StudentGroupAssignee.objects.bulk_create(new_objects)

    @classmethod
    def update_assignees(cls, student_group: StudentGroup, *,
                         teachers: List[CourseTeacher],
                         assignment: Assignment = None) -> None:
        """
        Set default list of responsible teachers for the student group or
        customize list of teachers for the *assignment* if value is provided.
        """
        current_assignees = set(StudentGroupAssignee.objects
                                .filter(student_group=student_group,
                                        assignment=assignment)
                                .values_list('assignee_id', flat=True))
        to_delete = []
        new_assignee_ids = {course_teacher.pk for course_teacher in teachers}
        for group_assignee_id in current_assignees:
            if group_assignee_id not in new_assignee_ids:
                to_delete.append(group_assignee_id)
        # TODO: try to overwrite records before deleting
        (StudentGroupAssignee.objects
         .filter(student_group=student_group,
                 assignment=assignment,
                 assignee__in=to_delete)
         .delete())
        to_add = [course_teacher for course_teacher in teachers
                  if course_teacher.pk not in current_assignees]
        cls.add_assignees(student_group, assignment=assignment, teachers=to_add)

    @staticmethod
    def get_assignees(student_group: StudentGroup,
                      assignment: Assignment = None) -> List[CourseTeacher]:
        """
        Returns list of responsible teachers. If *assignment* value is provided
        could return list of teachers specific for this assignment or
        default one for the student group.
        """
        default_and_overridden = Q(assignment__isnull=True)
        if assignment:
            default_and_overridden |= Q(assignment=assignment)
        assignees = list(StudentGroupAssignee.objects
                         .filter(default_and_overridden,
                                 student_group=student_group)
                         # FIXME: order by
                         .select_related('assignee__teacher'))
        # Teachers assigned for the particular assignment fully override
        # default list of the teachers assigned on the course level
        if any(ga.assignment_id is not None for ga in assignees):
            # Remove defaults
            assignees = [ga for ga in assignees if ga.assignment_id]
        filtered = [ga.assignee for ga in assignees]
        return filtered

    # FIXME: move to assignment service? it depends on assignee mode :<
    # FIXME: add tests
    @staticmethod
    def set_custom_assignees_for_assignment(*, assignment: Assignment,
                                            data: Dict[StudentGroupId, List[CourseTeacherId]]) -> None:
        if assignment.assignee_mode != AssigneeMode.STUDENT_GROUP_CUSTOM:
            raise ValidationError(f"Change assignee mode first to customize student group "
                                  f"responsible teachers for assignment {assignment}")
        to_add = []
        for student_group_id, assignee_list in data.items():
            for assignee_id in assignee_list:
                obj = StudentGroupAssignee(assignment=assignment,
                                           student_group_id=student_group_id,
                                           assignee_id=assignee_id)
                to_add.append(obj)
        StudentGroupAssignee.objects.filter(assignment=assignment).delete()
        StudentGroupAssignee.objects.bulk_create(to_add)

    @staticmethod
    def set_bucket_assignation_for_assignment(*, assignment: Assignment,
                                              data: List[Bucket]):
        to_create = []
        StudentGroupTeacherBucket.objects.filter(assignment=assignment).delete()
        for bucket in data:
            obj = StudentGroupTeacherBucket.objects.create(assignment=assignment)
            obj.groups.set(bucket['student_groups'])
            obj.teachers.set(bucket['teachers'])
        StudentGroupTeacherBucket.objects.bulk_create(to_create)

    @staticmethod
    def get_enrollments(student_group: StudentGroup) -> List[Enrollment]:
        return list(Enrollment.active
                    .filter(student_group=student_group)
                    .select_related('student_profile__user')
                    .order_by('student_profile__user__last_name'))

    @staticmethod
    def get_groups_for_safe_transfer(source_group: StudentGroup) -> List[StudentGroup]:
        """
        Returns list of target student groups where students of the source
        student group could be transferred to without loosing any progress.

        Unsafe transfer means that some personal assignments may be deleted.
        """
        student_groups = list(StudentGroup.objects
                              .filter(course_id=source_group.course_id)
                              .exclude(pk=source_group.pk)
                              .order_by('name'))
        # Deleting existing personal assignments is forbidden. This means it's
        # not possible to transfer a student to a target group if any
        # assignment available in the source group but not available in
        # the target group.
        all_target_groups = {sg.pk for sg in student_groups}
        available_groups = all_target_groups.copy()
        qs = (AssignmentGroup.objects
              .filter(group__course_id=source_group.course_id))
        assignment_settings = bucketize(qs, key=lambda ag: ag.assignment_id)
        for bucket in assignment_settings.values():
            groups = {ag.group_id for ag in bucket}
            if source_group.pk not in groups:
                groups = all_target_groups
            available_groups &= groups
        return [sg for sg in student_groups if sg.pk in available_groups]

    @staticmethod
    def available_assignments(student_group: StudentGroup) -> List[Assignment]:
        """
        Returns list of course assignments available for the *student_group*.
        """
        available = []
        assignments = (Assignment.objects
                       .filter(course_id=student_group.course_id)
                       .prefetch_related('restricted_to'))
        for assignment in assignments:
            restricted_to_groups = assignment.restricted_to.all()
            if not restricted_to_groups or student_group in restricted_to_groups:
                available.append(assignment)
        return available

    @classmethod
    def transfer_students(cls, *, source: StudentGroup, destination: StudentGroup,
                          enrollments: List[int], safe: bool = True) -> None:
        """
        Note:
            Unsafe transfer means some personal assignments may be
            deleted due to the difference in assignment visibility settings.
        """
        if source.course_id != destination.course_id:
            raise ValidationError("Invalid destination", code="invalid")
        # TODO: validate enrollments? Need to change API
        if safe:
            safe_transfer_to = cls.get_groups_for_safe_transfer(source)
            if destination not in safe_transfer_to:
                raise ValidationError("Invalid destination", code="unsafe")
        updated = (Enrollment.objects
                   .filter(course=source.course,
                           student_group=source,
                           pk__in=enrollments)
                   .update(student_group=destination))
        if updated != len(enrollments):
            # Enrollments are not in a source group
            raise IntegrityError("Some students have not been moved. Abort")

        source_group_assignments = cls.available_assignments(source)
        target_group_assignments = cls.available_assignments(destination)
        # Assignments that are not available in the source group, but
        # available in the target group
        in_target_group_only = set(target_group_assignments).difference(source_group_assignments)
        # Create missing personal assignments after students transfer
        for assignment in in_target_group_only:
            AssignmentService.bulk_create_student_assignments(assignment=assignment,
                                                              for_groups=[destination.pk])
        if not safe:
            in_source_group_only = set(source_group_assignments).difference(target_group_assignments)
            for assignment in in_source_group_only:
                enrollments = list(Enrollment.objects
                                   .filter(pk__in=enrollments,
                                           # Remove records for modified enrollments only
                                           student_group=destination))
                logger.info(f"Delete assignment {assignment} for enrollments {enrollments}")
                AssignmentService.remove_assignment_for_students(assignment,
                                                                 enrollments=enrollments)
