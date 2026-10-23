"""Deterministic 5 daily + 2 weekly + 2 monthly retention selection.

Pure logic over successful generation names; no I/O. The rule:

- daily:    the 5 newest successful generations;
- weekly:   walk ISO weeks (Mon-Sun) newest-first; the newest generation of a
            week satisfies that week's weekly point (a generation already
            retained as a daily satisfies the week without duplication); the
            first two weeks whose weekly point is not already retained each
            contribute one additional generation;
- monthly:  for each of the 2 most recent calendar months that contain a
            successful generation, the FIRST generation of that month that is
            not already retained.

A generation may satisfy more than one class without duplication; the keep set
holds distinct generations only (<= 9). The newest generation is always kept.
Prune candidates are every other known generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

GEN_NAME_RE_TEMPLATE = r"^{prefix}-(?P<stamp>[0-9]{{8}}T[0-9]{{6}}Z)-(?P<suffix>[0-9a-f]{{8}})\.tar\.zst$"
STAMP_FORMAT = "%Y%m%dT%H%M%SZ"


@dataclass(frozen=True, order=True)
class Generation:
    timestamp: datetime
    suffix: str
    name: str

    @property
    def generation_id(self) -> str:
        return f"{self.timestamp.strftime(STAMP_FORMAT)}-{self.suffix}"


class RetentionError(RuntimeError):
    pass


def compile_generation_pattern(prefix: str) -> re.Pattern[str]:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", prefix):
        raise RetentionError(f"invalid archive prefix: {prefix!r}")
    return re.compile(GEN_NAME_RE_TEMPLATE.format(prefix=re.escape(prefix)))


def parse_generation_name(name: str, prefix: str) -> Generation | None:
    """Return a Generation for a well-formed archive name, else None."""
    match = compile_generation_pattern(prefix).fullmatch(name)
    if match is None:
        return None
    try:
        timestamp = datetime.strptime(match.group("stamp"), STAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return Generation(timestamp=timestamp, suffix=match.group("suffix"), name=name)


def _iso_week(dt: datetime) -> tuple[int, int]:
    iso = dt.isocalendar()
    return (iso[0], iso[1])


def select_retention(
    generations: Iterable[Generation],
    *,
    now: datetime,
    daily: int = 5,
    weekly: int = 2,
    monthly: int = 2,
) -> tuple[dict[str, str], list[str]]:
    """Return (keep_map, prune_ids): keep_map maps generation_id -> class label.

    `now` must be timezone-aware UTC. Raises RetentionError on invariant
    violations; callers must treat that as fail-safe (no prune) rather than
    deleting anything.
    """
    if daily < 1 or weekly < 0 or monthly < 0:
        raise RetentionError("retention class sizes must be non-negative with daily >= 1")
    unique: dict[str, Generation] = {}
    for gen in generations:
        if not isinstance(gen, Generation) or gen.timestamp.tzinfo is None:
            raise RetentionError("generations must be timezone-aware Generation objects")
        unique[gen.generation_id] = gen
    ordered = sorted(unique.values(), reverse=True)
    if now.tzinfo is None:
        raise RetentionError("now must be timezone-aware")
    future = [gen for gen in ordered if gen.timestamp > now + timedelta(hours=1)]
    if future:
        raise RetentionError(f"refusing retention with future-dated generations: {future[0].name}")

    keep: dict[str, str] = {}  # generation_id -> class label

    def take(gen: Generation, label: str) -> None:
        keep.setdefault(gen.generation_id, label)

    for gen in ordered[:daily]:
        take(gen, "daily")

    # Weekly: newest already-kept-unaware generation per ISO week, newest weeks first.
    weeks: dict[tuple[int, int], Generation] = {}
    for gen in ordered:
        weeks.setdefault(_iso_week(gen.timestamp), gen)
    picked_weeks = 0
    for week in sorted(weeks, reverse=True):
        if picked_weeks >= weekly:
            break
        candidate = weeks[week]
        if candidate.generation_id in keep:
            continue
        take(candidate, "weekly")
        picked_weeks += 1

    # Monthly: FIRST generation of each of the most recent months, newest first.
    months: dict[tuple[int, int], Generation] = {}
    for gen in sorted(unique.values()):  # ascending so first-of-month wins
        months.setdefault((gen.timestamp.year, gen.timestamp.month), gen)
    picked_months = 0
    for month in sorted(months, reverse=True):
        if picked_months >= monthly:
            break
        candidate = months[month]
        if candidate.generation_id in keep:
            continue
        take(candidate, "monthly")
        picked_months += 1

    if not ordered:
        return {}, []
    newest_id = ordered[0].generation_id
    if newest_id not in keep:
        raise RetentionError("retention invariant violated: newest generation not retained")
    prune_ids = [gen.generation_id for gen in ordered if gen.generation_id not in keep]
    if len(keep) > daily + weekly + monthly:
        raise RetentionError("retention invariant violated: keep set exceeds max distinct generations")
    return keep, prune_ids
