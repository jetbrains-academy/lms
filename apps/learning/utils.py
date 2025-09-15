from datetime import timedelta
from typing import List, Optional, Tuple

from django.utils.translation import gettext_lazy as _

from learning.settings import GradeTypes, GradingSystems


def split_on_condition(iterable, predicate) -> Tuple[List, List]:
    true_lst, false_lst = [], []
    for x in iterable:
        if predicate(x):
            true_lst.append(x)
        else:
            false_lst.append(x)
    return true_lst, false_lst


def humanize_duration(execution_time: timedelta) -> Optional[str]:
    if execution_time is not None:
        total_minutes = int(execution_time.total_seconds()) // 60
        hours, minutes = divmod(total_minutes, 60)
        return str(_("{} hrs {:02d} min")).format(hours, minutes)
    return None
