import time_machine
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from core.timezone.utils import timezones_to_choices


@time_machine.travel(datetime(2024, 9, 1, 10, 00))
def test_timezones_to_choices():
    expected = [
        ('UTC', 'GMT+00:00 UTC'),
        ('Europe/Berlin', 'GMT+02:00 Europe/Berlin'),
        ('Asia/Nicosia', 'GMT+03:00 Asia/Nicosia'),
    ]

    normal = timezones_to_choices(
        [ZoneInfo('Europe/Berlin'), ZoneInfo('UTC'), ZoneInfo('Asia/Nicosia')]
    )
    assert normal == expected

    generator = timezones_to_choices(
        ZoneInfo(x) for x in ('Europe/Berlin', 'UTC', 'Asia/Nicosia')
    )
    assert generator == expected

    duplicates = timezones_to_choices([
        ZoneInfo('Europe/Berlin'),
        ZoneInfo('UTC'),
        ZoneInfo('Asia/Nicosia'),
        ZoneInfo('Asia/Nicosia'),
    ])
    assert duplicates == expected
