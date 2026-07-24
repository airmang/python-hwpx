# SPDX-License-Identifier: Apache-2.0
"""Public byte-preserving primitives retained in the core layer."""
from __future__ import annotations

from pathlib import Path

from hwpx.table_patch import (
    _iter_table_spans,
    _sections,
    _text_of,
    iter_table_spans,
    read_source_bytes,
    section_parts,
    table_text,
)


SIMPLE = (
    Path(__file__).parent
    / "fixtures"
    / "hwpxlib_corpus"
    / "reader_writer__SimpleTable.hwpx"
)


def test_public_form_fill_primitives_match_internal_byte_owners() -> None:
    source = SIMPLE.read_bytes()
    parts = section_parts(source)

    assert parts == _sections(source)
    section = next(iter(parts.values()))
    spans = iter_table_spans(section)
    assert spans == _iter_table_spans(section)
    assert spans
    first = section[slice(*spans[0])]
    assert table_text(first) == _text_of(first)
    assert read_source_bytes(source) == source
    assert read_source_bytes(SIMPLE) == source
