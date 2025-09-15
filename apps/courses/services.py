import datetime
from django.db.models import Prefetch, prefetch_related_objects
from typing import Dict, List

from core.models import AcademicProgram
from core.timezone import UTC
from courses.constants import TeacherRoles
from courses.models import Course, CourseReview
from courses.utils import get_terms_in_range
from learning.models import StudentGroup, StudentGroupAssignee


def group_teachers(teachers, multiple_roles=False) -> Dict[str, List]:
    """
    Returns teachers grouped by the most priority role.
    Groups are in priority order.

    Set `multiple_roles=True` if you need to take into account
    all teacher roles.
    """
    roles_in_priority = (
        TeacherRoles.LECTURER,  # Lecturer is the most priority role
        TeacherRoles.SEMINAR,
        *TeacherRoles.values.keys()
    )
    grouped = {role: [] for role in roles_in_priority}
    for teacher in teachers:
        for role in grouped:
            if role in teacher.roles:
                grouped[role].append(teacher)
                if not multiple_roles:
                    break
    return {k: v for k, v in grouped.items() if v}


class CourseService:

    @staticmethod
    def get_reviews(course):
        reviews = (CourseReview.objects
                   .filter(course__meta_course_id=course.meta_course_id)
                   .select_related('course', 'course__semester')
                   .only('pk', 'modified', 'text',
                         'course__semester__year', 'course__semester__type'))
        return list(reviews)

    @staticmethod
    def get_contacts(course):
        teachers_by_role = group_teachers(course.course_teachers.all())
        if teachers_by_role.get(TeacherRoles.ORGANIZER, []):
            teachers_by_role = {
                TeacherRoles.ORGANIZER: teachers_by_role[TeacherRoles.ORGANIZER]
            }
        teachers_by_role.pop(TeacherRoles.SPECTATOR, None)
        return [ct for g in teachers_by_role.values() for ct in g
                if len(ct.teacher.private_contacts.strip()) > 0]

    @staticmethod
    def get_news(course):
        return course.coursenews_set.all()

    @staticmethod
    def get_classes(course):
        return (course.courseclass_set
                .select_related("venue", "venue__location")
                .order_by("date", "starts_at"))

    @staticmethod
    def get_time_zones(course: Course) -> set[datetime.tzinfo]:
        """Returns a set of of unique course time zones."""
        time_zones = {UTC, course.time_zone}
        for binding in course.programs.all():
            if binding.program:
                program: AcademicProgram = binding.program
                time_zones.add(program.university.city.time_zone)
        return time_zones

    @staticmethod
    def get_student_groups(course: Course, with_assignees=False) -> List[StudentGroup]:
        """
        Set `with_assignees=True` to prefetch default responsible teachers
        for each group.
        """
        # TODO: prefetch student groups instead
        student_groups = list(StudentGroup.objects
                              .filter(course=course)
                              .order_by('name', 'pk'))
        if with_assignees:
            responsible_teachers = Prefetch('student_group_assignees',
                                            queryset=(StudentGroupAssignee.objects
                                                      .filter(assignment__isnull=True)))
            prefetch_related_objects(student_groups, responsible_teachers)
        for s in student_groups:
            s.course = course
        return student_groups

    @staticmethod
    def get_course_uri(course: Course) -> str:
        return f"{course.semester.slug}/{course.pk}-{course.meta_course.slug}"


def get_teacher_programs(user, start_date, end_date):
    """
    Returns branches where user has been participated as a teacher in a
    given period.
    """
    term_indexes = [t.index for t in get_terms_in_range(start_date, end_date)]
    return AcademicProgram.objects.filter(
        courses__course__semester__index__in=term_indexes,
        courses__course__teachers=user
    ).distinct()
