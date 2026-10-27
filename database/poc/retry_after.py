"""Validated, non-sensitive Retry-After data; no clock, waiting or retry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import re


@dataclass(frozen=True)
class RetryAfter:
    seconds: int | None = None
    not_before: float | None = None
    legacy_date: tuple[int, ...] | None = None  # yy, month, day, hour, minute, second, weekday
    excessive: bool = False

    def __post_init__(self):
        if type(self.excessive) is not bool or sum((self.seconds is not None, self.not_before is not None,
                                                  self.legacy_date is not None, self.excessive)) != 1:
            raise ValueError("One normalized Retry-After value required")
        if self.seconds is not None and (type(self.seconds) is not int or not 0 <= self.seconds < 10**18):
            raise ValueError("Invalid normalized Retry-After seconds")
        if self.not_before is not None:
            try:
                valid = (not isinstance(self.not_before, bool) and isinstance(self.not_before, (int, float))
                         and math.isfinite(self.not_before))
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError("Invalid normalized Retry-After date")
        if self.legacy_date is not None:
            parts = tuple(self.legacy_date)
            if len(parts) != 7 or any(type(part) is not int for part in parts) or not 0 <= parts[0] < 100 or not 0 <= parts[-1] < 7:
                raise ValueError("Invalid normalized Retry-After calendar")
            try:
                datetime(2000 + parts[0], *parts[1:6], tzinfo=timezone.utc)
            except ValueError:
                raise ValueError("Invalid normalized Retry-After calendar") from None
            object.__setattr__(self, "legacy_date", parts)


def parse_retry_after(value: object) -> RetryAfter | None:
    """Accept ASCII seconds or the three HTTP-date forms, discard original text.

    An extreme but numeric value is marked excessive, never silently ignored
    or shortened. No wall clock is read here: execution supplies it later.
    The century of an RFC850 date is resolved by execution's injected wall
    clock, not email.utils' fixed two-digit-year heuristic.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.isascii() and text.isdecimal():
        digits = text.lstrip("0") or "0"
        if len(digits) > 18:
            return RetryAfter(excessive=True)
        return RetryAfter(seconds=int(digits))
    imf = re.fullmatch(
        r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), [0-9]{2} "
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
        r"[0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2} GMT", text,
    )
    legacy = re.fullmatch(
        r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), [0-9]{2}-"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-[0-9]{2} "
        r"[0-9]{2}:[0-9]{2}:[0-9]{2} GMT", text,
    )
    asctime = re.fullmatch(
        r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
        r"(?:[0-9]{2}| [0-9]) [0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4}", text,
    )
    if not (imf or legacy or asctime):
        return None
    try:
        date = parsedate_to_datetime(text)
        if legacy:
            weekday = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday").index(legacy[1])
            return RetryAfter(legacy_date=(date.year % 100, date.month, date.day, date.hour, date.minute, date.second, weekday))
        if asctime:
            date = date.replace(tzinfo=timezone.utc)
        # email.utils is locale independent; reject inconsistent weekdays too.
        if date.weekday() != ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun").index(text[:3]):
            return None
        return RetryAfter(not_before=date.timestamp())
    except (ValueError, TypeError, OverflowError, OSError):
        return None
