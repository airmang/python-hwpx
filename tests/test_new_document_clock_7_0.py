# SPDX-License-Identifier: Apache-2.0
"""A document made while another's ``now=`` is in force takes that clock (#683).

``HwpxDocument.new(seed=..., now=...)`` keeps its seed and clock for the thread until it is
closed. Ids minted meanwhile for other documents already came from the seed; 7.0 gives a document
made meanwhile with ``new()`` and no ``now`` of its own that clock as its dates too, so a replay
that makes documents through other code (the fuzz runner's builder) writes the same bytes
whenever it runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest

from hwpx import HwpxDocument
from hwpx import templates

FIXED = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def moving_clock(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    """The real clock, made to move a second at every new document."""

    moments: list[datetime] = []
    ticks: Iterator[int] = iter(range(10_000))

    def tick() -> datetime:
        moment = datetime(2030, 5, 5, tzinfo=timezone.utc) + timedelta(seconds=next(ticks))
        moments.append(moment)
        return moment

    monkeypatch.setattr(templates, "_creation_time", tick)
    return moments


def _dates(doc: HwpxDocument) -> tuple[str | None, str | None]:
    metadata = doc.parts.metadata
    return metadata.created_date, metadata.modified_date


def test_a_document_made_meanwhile_takes_the_clock_in_force(moving_clock: list[datetime]) -> None:
    holder = HwpxDocument.new(now=FIXED)
    try:
        made = HwpxDocument.new()
        assert _dates(made) == ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
        made.close()
    finally:
        holder.close()

    after = HwpxDocument.new()
    assert _dates(after)[0] == "2030-05-05T00:00:00Z"  # the real clock once the holder is closed
    assert moving_clock


def test_its_own_now_wins(moving_clock: list[datetime]) -> None:
    with HwpxDocument.new(now=FIXED):
        own = HwpxDocument.new(now=datetime(2027, 3, 3, tzinfo=timezone.utc))
        assert _dates(own)[0] == "2027-03-03T00:00:00Z"
        own.close()


def test_a_seed_alone_inside_keeps_the_outer_clock(moving_clock: list[datetime]) -> None:
    with HwpxDocument.new(now=FIXED):
        seeded = HwpxDocument.new(seed=3)
        assert _dates(seeded)[0] == "2026-01-01T00:00:00Z"
        seeded.close()


def _replay() -> bytes:
    with HwpxDocument.new(seed=11, now=FIXED):
        made = HwpxDocument.new()  # made by "other code", without seed or now
        made.add_paragraph("같은 씨앗")
        made.notes.add_memo("메모")  # its date comes from the clock too
        data = made.to_bytes()
        made.close()
    return data


def test_two_replays_a_clock_apart_write_the_same_bytes(moving_clock: list[datetime]) -> None:
    first = _replay()
    second = _replay()

    assert first == second
