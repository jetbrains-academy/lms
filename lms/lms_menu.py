import functools
import re
from django.urls import ResolverMatch
from django.utils.translation import pgettext_lazy
from menu import Menu
from typing import Literal

from alumni.permissions import ViewAlumniMenu
from core.http import HttpRequest
from core.menu import MenuItem
from core.urls import reverse
from courses.models import CourseTeacher
from courses.urls import RE_COURSE_URI
from learning.models import Enrollment


def course_matcher(menu_name: Literal['learning', 'teaching'], request: HttpRequest):
    resolver_match: ResolverMatch = request.resolver_match
    if not re.match('/courses/' + RE_COURSE_URI.removeprefix('^'), request.path):
        return False
    user = request.user
    course_id = int(resolver_match.kwargs.get('course_id'))
    match menu_name:
        case 'learning':
            return Enrollment.active.filter(student=user, course_id=course_id).exists()
        case 'teaching':
            return CourseTeacher.objects.filter(teacher=user, course_id=course_id).exists()
    return False


top_menu = [
    MenuItem(
        pgettext_lazy("menu", "Learning"),
        reverse('study:assignment_list'),
        weight=10,
        children=[
            MenuItem(
                pgettext_lazy("menu", "Assignments"),
                '/learning/assignments/',
                weight=10,
                budge='assignments_student',
            ),
            MenuItem(
                pgettext_lazy("menu", "My schedule"),
                '/learning/timetable/',
                weight=20,
                selected_patterns=[r"^/learning/calendar/"],
            ),
            MenuItem(
                pgettext_lazy("menu", "My courses"),
                '/learning/courses/',
                weight=40,
                match_func=functools.partial(course_matcher, 'learning'),
            ),
        ],
        permissions=("learning.view_study_menu",),
        css_classes='for-students',
    ),
    MenuItem(
        pgettext_lazy("menu", "Teaching"),
        reverse('teaching:assignments_check_queue'),
        weight=20,
        children=[
            MenuItem(
                pgettext_lazy("menu", "Review queue"),
                reverse('teaching:assignments_check_queue'),
                weight=10,
                budge='assignments_teacher',
                excluded_patterns=[
                    r"^/teaching/assignments/\d+/$",
                ]
            ),
            MenuItem(
                pgettext_lazy("menu", "My schedule"),
                reverse('teaching:timetable'),
                weight=20,
                selected_patterns=[r"^/teaching/calendar/"],
            ),
            MenuItem(
                pgettext_lazy("menu", "My courses"),
                reverse("teaching:course_list"),
                weight=40,
                budge='courseoffering_news',
                selected_patterns=[
                    r"^/teaching/assignments/\d+/$",
                ],
                match_func=functools.partial(course_matcher, 'teaching'),
            ),
            MenuItem(
                pgettext_lazy("menu", "Gradebooks"),
                reverse('teaching:gradebook_list'),
                weight=50,
            ),
        ],
        permissions=("learning.view_teaching_menu",),
        css_classes='for-teachers',
    ),
    MenuItem(
        pgettext_lazy("menu", "Supervision"),
        reverse('staff:gradebook_list'),
        weight=40,
        children=[
            MenuItem(
                pgettext_lazy("menu", "Courses"),
                reverse("course_list"),
                weight=10,
            ),
            MenuItem(
                pgettext_lazy("menu", "Gradebooks"),
                reverse('staff:gradebook_list'),
                weight=10,
            ),
            MenuItem(
                pgettext_lazy("menu", "Find Students"),
                reverse('staff:student_search'),
                weight=20,
            ),
            MenuItem(
                pgettext_lazy("menu", "Files"),
                reverse('staff:exports'),
                weight=30,
                selected_patterns=[r"^/staff/reports/enrollment-invitations/"],
            ),
            MenuItem(
                pgettext_lazy("menu", "Resources"),
                reverse('staff:staff_warehouse'),
                weight=40,
            ),
            MenuItem(
                pgettext_lazy("menu", "Facebook"),
                reverse('staff:student_faces'),
                weight=50,
            ),
            MenuItem(
                pgettext_lazy("menu", "Overlaps"),
                reverse('staff:course_participants_intersection'),
                weight=60,
            ),
        ],
        for_staff=True,
        css_classes='for-staff',
    ),
    MenuItem(
        pgettext_lazy('menu', 'Alumni'),
        reverse('alumni:list'),
        weight=50,
        children=[
            MenuItem(
                pgettext_lazy('menu', 'Search'),
                reverse('alumni:list'),
            ),
            MenuItem(
                pgettext_lazy('menu', 'Promote'),
                reverse('alumni:promote'),
                for_staff=True,
            ),
        ],
        permissions=(ViewAlumniMenu.name,),
    )
]

for item in top_menu:
    Menu.add_item("menu_private", item)
