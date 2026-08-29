"""Deterministic time handling: injectable clock and UTC-normalized instants.

The database stores naive UTC instants; the API serializes them as ISO-8601
with an explicit "+00:00" offset.
"""
from __future__ import annotations

from datetime import UTC, datetime


class Clock:
    def utcnow(self) -> datetime:
        raise NotImplementedError


class SystemClock(Clock):
    def utcnow(self) -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)


class FixedClock(Clock):
    def __init__(self, moment: datetime) -> None:
        self.moment = to_utc_naive(moment)

    @classmethod
    def from_iso(cls, iso: str) -> FixedClock:
        return cls(datetime.fromisoformat(iso.replace("Z", "+00:00")))

    def utcnow(self) -> datetime:
        return self.moment


def to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def iso8601_utc(value: datetime) -> str:
    return to_utc_naive(value).isoformat(timespec="seconds") + "+00:00"