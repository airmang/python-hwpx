# SPDX-License-Identifier: Apache-2.0
"""A new document's dates come from its own call, not from another document (#683 follow-up).

``HwpxDocument.new(now=...)`` dates the document it makes. A document made with ``new()`` and no
``now`` while another document with ``now=`` is open still takes the clock: what a call writes
does not depend on the state of a document it was not given. A replay that needs fixed dates
passes ``now=`` itself or writes the dates (the fuzz runner does both).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterator

import pytest

from hwpx import HwpxDocument
from hwpx import templates

FIXED = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def moving_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real clock, made to move a second at every new document."""

    ticks: Iterator[int] = iter(range(10_000))
    monkeypatch.setattr(
        templates, "_creation_time", lambda: datetime(2030, 5, 5, tzinfo=timezone.utc) + timedelta(seconds=next(ticks))
    )


def _created(doc: HwpxDocument) -> str | None:
    return doc.parts.metadata.created_date


def test_a_document_made_meanwhile_keeps_the_clock(moving_clock: None) -> None:
    with HwpxDocument.new(now=FIXED) as fixed:
        made = HwpxDocument.new()
        assert _created(fixed) == "2026-01-01T00:00:00Z"
        assert _created(made) == "2030-05-05T00:00:00Z"
        made.close()


def test_its_own_now_dates_it(moving_clock: None) -> None:
    with HwpxDocument.new(now=FIXED):
        own = HwpxDocument.new(now=datetime(2027, 3, 3, tzinfo=timezone.utc))
        assert _created(own) == "2027-03-03T00:00:00Z"
        own.close()
