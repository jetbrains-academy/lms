from django.db import models
from django.db.models import query
from django.utils import timezone

from core.db.models import LiveManager


class StudentAssignmentQuerySet(query.QuerySet):
    def for_student(self, user):
        return (self.filter(student=user)
                .select_related('assignment',
                                'assignment__course',
                                'assignment__course',
                                'assignment__course__meta_course',
                                'assignment__course__semester'))

    def in_term(self, term):
        return self.filter(assignment__course__semester_id=term.id)

    def with_future_deadline(self):
        """
        Returns individual assignments with unexpired deadlines.
        """
        return self.filter(assignment__deadline_at__gt=timezone.now())


class _StudentAssignmentDefaultManager(LiveManager):
    """On compsciclub.ru always restrict by open readings"""
    def get_queryset(self):
        qs = super().get_queryset()
        return qs


StudentAssignmentManager = _StudentAssignmentDefaultManager.from_queryset(
    StudentAssignmentQuerySet)


class EventQuerySet(query.QuerySet):
    pass


class _EnrollmentDefaultManager(models.Manager):
    """On compsciclub.ru always restrict selection by open readings"""
    def get_queryset(self):
        return super().get_queryset()


class _EnrollmentActiveManager(models.Manager):
    def get_queryset(self):
        qs = super().get_queryset().filter(is_deleted=False)
        return qs


class EnrollmentQuerySet(models.QuerySet):
    pass


EnrollmentDefaultManager = _EnrollmentDefaultManager.from_queryset(
    EnrollmentQuerySet)
EnrollmentActiveManager = _EnrollmentActiveManager.from_queryset(
    EnrollmentQuerySet)


class AssignmentCommentQuerySet(models.QuerySet):
    pass


class _AssignmentCommentPublishedManager(LiveManager):
    def get_queryset(self):
        return super().get_queryset().filter(is_published=True)


AssignmentCommentPublishedManager = _AssignmentCommentPublishedManager.from_queryset(
    AssignmentCommentQuerySet)
