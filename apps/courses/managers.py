from typing import List, TYPE_CHECKING

from django.db import models
from django.db.models import (
    Case, Count, F, IntegerField, Prefetch, Q, Subquery, Value, When, query
)
from django.utils import timezone

if TYPE_CHECKING:
    from users.models import StudentProfile, User


class CourseTeacherQuerySet(query.QuerySet):
    # FIXME: do I need subquery here?
    def for_meta_course(self, meta_course):
        course_pks = (self
                      .model.course.field.related_model.objects
                      .filter(meta_course=meta_course)
                      # Note: can't reset default ordering in a Subquery
                      .order_by("pk")
                      .values("pk"))
        return self.filter(course__in=Subquery(course_pks))


CourseTeacherManager = models.Manager.from_queryset(CourseTeacherQuerySet)


class AssignmentQuerySet(query.QuerySet):
    def with_future_deadline(self):
        """
        Returns assignments with unexpired deadlines.
        """
        return self.filter(deadline_at__gt=timezone.now())

    def prefetch_student_assignment(self, student: 'User'):
        """
        Prefetch student assignment for a given student to `student_assignment` attr
        as a single-element list.
        """
        from learning.models import AssignmentSubmissionTypes, StudentAssignment

        # FIXME: get solutions count from meta['stats']['solutions'] instead of joining all submissions
        solutions_total = Case(
            When(Q(assignmentcomment__author_id=student.pk) &
                 Q(assignmentcomment__type=AssignmentSubmissionTypes.SOLUTION),
                 then=Value(1)),
            output_field=IntegerField()
        )
        qs = (StudentAssignment.objects
              .filter(student=student)
              .annotate(solutions_total=Count(solutions_total))
              .order_by("pk"))  # optimize by overriding default order
        return self.prefetch_related(
            Prefetch("studentassignment_set", queryset=qs, to_attr="student_assignment")
        )


AssignmentManager = models.Manager.from_queryset(AssignmentQuerySet)


class CourseClassQuerySet(query.QuerySet):
    def select_calendar_data(self):
        return (self
                .select_related('course',
                                'course__meta_course',
                                'course__semester')
                .defer('course__description',
                       'course__meta_course__description',
                       'course__meta_course__short_description'))

    def in_programs(self, programs):
        """
        Returns distinct course classes for a given list of programs
        """
        return self.filter(course__programs__program__in=programs).distinct()

    def for_student(self, user):
        # Get common courses classes and restricted to the student group
        common_classes = Q(courseclassgroup__isnull=True)
        restricted_to_student_group = Q(courseclassgroup__group_id=F('course__enrollment__student_group_id'))
        return (self.filter(common_classes | restricted_to_student_group,
                            course__enrollment__student_id=user.pk,
                            course__enrollment__is_deleted=False))

    def for_teacher(self, user):
        from courses.models import CourseTeacher
        spectator = CourseTeacher.roles.spectator
        return self.filter(course__teachers=user,
                           course__course_teachers__roles=~spectator)


CourseClassManager = models.Manager.from_queryset(CourseClassQuerySet)


class CourseQuerySet(models.QuerySet):
    def for_teacher(self, user):
        return self.filter(teachers=user)

    def in_program(self, academic_program_code: str):
        return self.filter(programs__program__code=academic_program_code)

    def student_can_enroll_from_program(self, student_profile: 'StudentProfile'):
        return (
            self
            .in_program(student_profile.academic_program_enrollment.program.code)
            .filter(
                programs__start_year_filter__contains=[student_profile.academic_program_enrollment.start_year],
                programs__enrollment_end_date__gte=timezone.now()
            )
        )

    def alumni_can_enroll(self):
        return self.filter(
            programs__is_alumni=True,
            programs__enrollment_end_date__gte=timezone.now(),
        )


CourseDefaultManager = models.Manager.from_queryset(CourseQuerySet)


class CourseProgramBindingQuerySet(models.QuerySet):
    def student_can_enroll_by_invitation(self, student_profile: 'StudentProfile'):
        student_invitations = student_profile.invitations.all()
        return self.filter(
            invitation__in=student_invitations,
            enrollment_end_date__gte=timezone.now(),
        )


CourseProgramBindingDefaultManager = models.Manager.from_queryset(CourseProgramBindingQuerySet)
