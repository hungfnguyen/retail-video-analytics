from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo


APP_TIME_ZONE_NAME = os.getenv("APP_TIME_ZONE", "Asia/Ho_Chi_Minh")
APP_TIME_ZONE = ZoneInfo(APP_TIME_ZONE_NAME)
TRINO_TIME_ZONE = os.getenv("TRINO_TIME_ZONE", APP_TIME_ZONE_NAME)


def now_local() -> datetime:
    return datetime.now(APP_TIME_ZONE)
