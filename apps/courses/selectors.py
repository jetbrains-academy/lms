from typing import Any, Dict, List, Optional

from django_filters import Filter, NumberFilter
from django_filters.rest_framework import FilterSet
from rest_framework.exceptions import ValidationError

from django.contrib.sites.models import Site
from django.db.models import Prefetch, Q

from courses.managers import AssignmentQuerySet, CourseQuerySet, CourseTeacherQuerySet
from courses.models import Assignment, Course, CourseTeacher
from learning.managers import StudentAssignmentQuerySet
from learning.models import StudentAssignment


def get_teachers(*, filters: Optional[List[Q]] = None) -> CourseTeacherQuerySet:
    """
    Returns course teachers queryset.
    """
    filters = filters or []
    qs = (CourseTeacher.objects
          .filter(*filters)
          .select_related('teacher'))
    return qs


def get_lecturers() -> CourseTeacherQuerySet:
    filters = [Q(roles=CourseTeacher.roles.lecturer)]
    return get_teachers(filters=filters)


def get_reviewers() -> CourseTeacherQuerySet:
    filters = [Q(roles=CourseTeacher.roles.reviewer)]
    return get_teachers(filters=filters)


# FIXME: move to the service method
def get_course_teachers(*, course: Course) -> CourseTeacherQuerySet:
    filters = [
        Q(course=course),
        ~CourseTeacher.has_any_hidden_role(hidden_roles=(CourseTeacher.roles.spectator,))
    ]
    return get_teachers(filters=filters)


def course_teachers_prefetch_queryset(*, role_priority: bool = True,
                                      hidden_roles=(CourseTeacher.roles.spectator,)) -> CourseTeacherQuerySet:
    """
    Returns public course teachers sorted by the most priority role
    within the course by default.
    """
    filters = []
    if hidden_roles:
        filters = [~CourseTeacher.has_any_hidden_role(hidden_roles=hidden_roles)]
    queryset = get_teachers(filters=filters)
    order_by = [CourseTeacher.get_most_priority_role_expr().desc()] if role_priority else []
    return (queryset
            .only('id', 'course_id', 'teacher_id', 'roles',
                  'teacher__first_name', 'teacher__last_name',
                  'teacher__gender', 'teacher__photo', 'teacher__cropbox_data')
            .order_by(*order_by, 'teacher__last_name', 'teacher__first_name'))


class BaseAssignmentFilter(FilterSet):
    class Meta:
        model = Assignment
        fields = ('course',)


def assignments_list(*, filters: Optional[Dict[str, Any]] = None,
                     filter_class: Optional[FilterSet] = None) -> AssignmentQuerySet:
    filters = filters or {}
    filter_class = filter_class or BaseAssignmentFilter
    base_queryset = Assignment.objects.all()
    return filter_class(filters, base_queryset).qs


class BasePersonalAssignmentFilter(FilterSet):
    # FIXME: right now this filter does not validate anything and expects valid array
    assignments = Filter(field_name='assignment__id', lookup_expr='in')
    course = NumberFilter(field_name='assignment__course', lookup_expr='exact')

    class Meta:
        model = StudentAssignment
        fields = ('assignments', 'course')


def personal_assignments_list(*, filters: Optional[Dict[str, Any]] = None,
                              filter_class: Optional[FilterSet] = None) -> StudentAssignmentQuerySet:
    filters = filters or {}
    filter_class = filter_class or BasePersonalAssignmentFilter
    base_queryset = StudentAssignment.objects.all()
    filter_set = filter_class(filters, base_queryset)
    if not filter_set.is_valid():
        raise ValidationError(filter_set.errors)
    return filter_set.qs.order_by()


def course_personal_assignments(*, course: Course, filters: Optional[Dict[str, Any]] = None,
                                filter_class: Optional[FilterSet] = None) -> StudentAssignmentQuerySet:
    filters = filters or {}
    filters.update({'course': course.pk})
    prefetch_assignments = Prefetch('assignment',
                                    queryset=(Assignment.objects
                                              .filter(course=course)
                                              .order_by()))
    return (personal_assignments_list(filters=filters)
            .select_related('student')
            .prefetch_related(prefetch_assignments,
                              'assignee')
            .order_by())
