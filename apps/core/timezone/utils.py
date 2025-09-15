from zoneinfo import ZoneInfo

from typing import Iterable

from datetime import datetime, timezone as dt_timezone, tzinfo, timedelta

from babel.dates import get_timezone_gmt

from django.conf import settings
from django.utils import timezone

__all__ = ['now_local', 'get_now_utc', 'get_gmt', 'UTC', 'timezones_to_choices']


def now_local(tz: tzinfo) -> datetime:
    return timezone.localtime(timezone=tz)


def get_now_utc() -> datetime:
    """Returns current time in UTC"""
    return datetime.now(UTC)


def get_gmt(tz: tzinfo) -> str:
    """
    Returns string indicating current offset from GMT for the timezone
    associated with the given `datetime` object.
    """
    dt = get_now_utc()
    return get_timezone_gmt(dt.astimezone(tz), locale=settings.LANGUAGE_CODE)


UTC = ZoneInfo('UTC')

def timezones_to_choices(timezones: Iterable[tzinfo]) -> list[tuple[str, str]]:
    timezones = set(timezones)
    choices = []
    now_utc = get_now_utc()
    zero = timedelta(0)
    for tz in timezones:
        now_tz = now_utc.astimezone(tz)
        if isinstance(tz, ZoneInfo):
            tz_name = tz.key
        else:
            tz_name = now_tz.tzname()
        offset = now_tz.utcoffset()
        assert offset is not None
        sign = "+" if offset >= zero else "-"
        hh_mm = str(abs(offset)).zfill(8)[:-3]
        label = f"GMT{sign}{hh_mm} {tz_name.replace('_', ' ')}"
        choices.append((tz_name, offset, label))
    choices.sort(key=lambda x: (x[1], x[0]))
    return [(value, label) for value, _, label in choices]
