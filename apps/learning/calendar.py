from typing import Iterator, List

from django.db.models import Q

from courses.calendar import CalendarEvent, CalendarEventFactory
from learning.selectors import get_classes, get_student_classes, get_teacher_classes
from users.models import StudentProfile


def _to_range_q_filter(start_date, end_date) -> List[Q]:
    period_filter = []
    if start_date:
        period_filter.append(Q(date__gte=start_date))
    if end_date:
        period_filter.append(Q(date__lte=end_date))
    return period_filter


# FIXME: get_student_events  + CalendarEvent.build(instance) ?
def get_student_calendar_events(*, student_profile: StudentProfile,
                                start_date, end_date) -> Iterator[CalendarEvent]:
    period_filter = _to_range_q_filter(start_date, end_date)
    user = student_profile.user
    for c in get_student_classes(user, period_filter):
        yield CalendarEventFactory.create(c, time_zone=user.time_zone)


def get_teacher_calendar_events(*, user, start_date,
                                end_date) -> Iterator[CalendarEvent]:
    period_filter = _to_range_q_filter(start_date, end_date)
    for c in get_teacher_classes(user, period_filter):
        yield CalendarEventFactory.create(c, time_zone=user.time_zone)


def get_all_calendar_events(*, program_list, start_date, end_date, time_zone):
    """
    Returns events in a given date range for a given program list.
    """
    period_filter = _to_range_q_filter(start_date, end_date)
    for c in get_classes(period_filter).in_programs(program_list):
        yield CalendarEventFactory.create(c, time_zone=time_zone)
