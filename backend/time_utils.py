from datetime import datetime
from zoneinfo import ZoneInfo


_POLAND_TZ = ZoneInfo("Europe/Warsaw")


def now_poland_naive() -> datetime:
    return datetime.now(_POLAND_TZ).replace(tzinfo=None)


def now_poland_iso() -> str:
    return now_poland_naive().replace(microsecond=0).isoformat()

