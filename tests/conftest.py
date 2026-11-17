# SPDX-License-Identifier: Apache-2.0
"""Test-wide guards.

A document made with ``HwpxDocument.new(seed=..., now=...)`` (or ``open(..., seed=, now=)``) puts its id
and clock source in force for the whole thread until it is closed. A test that leaves one open makes the
ids and dates of every later test in the same pytest worker depend on it, so a test passes or fails by
the order the tests ran in. This guard fails the test that leaves a source in force and takes it away,
so the next test starts clean.
"""

from __future__ import annotations

from typing import Iterator

import pytest

from hwpx.oxml._document_primitives import active_id_source, install_id_source


@pytest.fixture(autouse=True)
def _no_id_source_left_in_force() -> Iterator[None]:
    yield
    left = active_id_source()
    if left is not None:
        install_id_source(None)
        pytest.fail(
            f"this test left a seed/now id source in force (seed={left.seed!r}, now={left.now!r}): "
            "close every HwpxDocument made with seed= or now= (use `with`)",
            pytrace=False,
        )
