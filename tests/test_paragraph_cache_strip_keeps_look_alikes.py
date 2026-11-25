# SPDX-License-Identifier: Apache-2.0
"""The byte paths that drop an edited paragraph's line cache drop only ``hp:linesegarray`` (#658).

A comment, CDATA or processing instruction that holds ``<hp:linesegarray>`` text, a ``linesegarray``
of another namespace (declared on the element or on the part's root) and an element whose name only
differs in case are not the layout cache and keep their bytes.
"""

from __future__ import annotations

import io
import re
import zipfile

import pytest

from hwpx import HwpxDocument
from hwpx.body_patch import apply_body_ops, direct_paragraph_spans, strip_runs_by_color
from hwpx.patch import _layout_cache_spans, _strip_paragraph_layout_cache, paragraph_chunks, paragraph_patch
from hwpx.table_patch import fill_cells

SECTION = "Contents/section0.xml"

REAL = (
    b'<hp:linesegarray><hp:lineseg textpos="0" vertpos="0" vertsize="1000" textheight="1000" '
    b'baseline="850" spacing="600" horzpos="0" horzsize="42520" flags="393216"/></hp:linesegarray>'
)
LOOK_ALIKES = (
    b'<!-- <hp:linesegarray><hp:lineseg textpos="0"/></hp:linesegarray> -->'
    b"<![CDATA[<hp:linesegarray/>]]>"
    b"<?keep <hp:linesegarray/>?>"
    b'<x:linesegarray xmlns:x="urn:example:other">keep-other</x:linesegarray>'
    b"<y:linesegarray>keep-root-declared</y:linesegarray>"
    b"<hp:LineSegArray>keep-case</hp:LineSegArray>"
)


def _source() -> bytes:
    """Paragraphs ``FIRST``, ``ABC`` + a red run, ``LAST`` and a 1x1 table holding ``J``.

    Every paragraph carries the look-alikes and then its real cache.
    """

    document = HwpxDocument.new()
    document.add_paragraph("FIRST")
    paragraph = document.add_paragraph("ABC ")
    paragraph.add_run("RED", color="#FF0000")
    document.add_paragraph("LAST")
    document.add_table(1, 1).cell(0, 0).text = "J"
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            payload = source.read(info)
            if info.filename == SECTION:
                payload = payload.replace(b"<hs:sec ", b'<hs:sec xmlns:y="urn:example:root-other" ', 1)
                payload = re.sub(rb"<hp:linesegarray>.*?</hp:linesegarray>", b"", payload, flags=re.S)
                payload = payload.replace(b"</hp:p>", LOOK_ALIKES + REAL + b"</hp:p>")
            target.writestr(info, payload)
    return out.getvalue()


def _section(data: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(SECTION)


def _assert_only_the_edited_cache_went(source: bytes, result: bytes, edited: int = 1) -> None:
    before, after = _section(source), _section(result)
    assert after.count(LOOK_ALIKES) == before.count(LOOK_ALIKES)
    assert after.count(REAL) == before.count(REAL) - edited


def _index_of(data: bytes, marker: str) -> int:
    xml = _section(data).decode("utf-8")
    return next(i for i, (a, b) in enumerate(direct_paragraph_spans(xml)) if marker in xml[a:b])


def test_the_scanner_finds_only_the_paragraph_namespace_element() -> None:
    fragment = (b"<hp:p>" + LOOK_ALIKES + REAL + b"</hp:p>").decode("latin-1")
    start = fragment.index(REAL.decode("latin-1"))
    assert _layout_cache_spans(fragment, scope={"y": "urn:example:root-other"}) == [(start, start + len(REAL))]
    assert _strip_paragraph_layout_cache(b"<hp:p>" + LOOK_ALIKES + REAL + b"</hp:p>") == (
        b"<hp:p>" + LOOK_ALIKES + b"</hp:p>"
    )


def test_a_prefix_bound_to_the_paragraph_namespace_on_the_root_counts() -> None:
    cache = b'<p:linesegarray><p:lineseg textpos="0"/></p:linesegarray><p:linesegarray/>'
    scope = {"p": "http://www.hancom.co.kr/hwpml/2011/paragraph"}
    assert _strip_paragraph_layout_cache(b"<p:p>" + cache + b"</p:p>", scope) == b"<p:p></p:p>"
    # without the declaration in scope a foreign prefix is left alone
    assert _strip_paragraph_layout_cache(b"<p:p>" + cache + b"</p:p>") == b"<p:p>" + cache + b"</p:p>"


def test_paragraph_patch_keeps_the_look_alikes() -> None:
    source = _source()
    index = next(i for i, chunk in enumerate(paragraph_chunks(_section(source))) if b"ABC" in chunk)
    result = paragraph_patch(source, [{"paragraphIndex": index, "text": "NEW"}])
    assert [item.original_text for item in result.applied] == ["ABC RED"]
    _assert_only_the_edited_cache_went(source, result.data)


@pytest.mark.parametrize(
    "ops",
    [
        pytest.param(lambda data: [{"op": "set_paragraph_text", "index": _index_of(data, "ABC"), "text": "NEW"}],
                     id="set_paragraph_text"),
        pytest.param(lambda data: [{"op": "replace_text", "find": "ABC", "replace": "XYZ"}], id="replace_text"),
    ],
)
def test_body_ops_keep_the_look_alikes(ops) -> None:
    source = _source()
    result = apply_body_ops(source, ops(source), dry_run=True)
    assert [entry["status"] for entry in result.transcript] == ["would_apply"]
    _assert_only_the_edited_cache_went(source, result.data)


def test_a_cloned_paragraph_drops_the_cache_and_keeps_the_look_alikes() -> None:
    source = _source()
    index = _index_of(source, "LAST")
    result = apply_body_ops(
        source, [{"op": "insert_paragraph_by_clone", "ref_index": index, "index": index + 1, "count": 1}],
        dry_run=True,
    )
    assert [entry["status"] for entry in result.transcript] == ["would_apply"]
    before, after = _section(source), _section(result.data)
    assert after.count(LOOK_ALIKES) == before.count(LOOK_ALIKES) + 1  # the clone keeps them too
    assert after.count(REAL) == before.count(REAL)  # the clone has no cache, the original keeps its own


def test_strip_runs_by_color_keeps_the_look_alikes() -> None:
    source = _source()
    result = strip_runs_by_color(source, ["#FF0000"], dry_run=True)
    assert b"RED" not in _section(result.data)
    _assert_only_the_edited_cache_went(source, result.data)


def test_fill_cells_keeps_the_look_alikes() -> None:
    source = _source()
    result = fill_cells(source, [{"table_index": 0, "row": 0, "col": 0, "text": "K"}])
    assert [item.original_text for item in result.applied] == ["J"]
    _assert_only_the_edited_cache_went(source, result.data)
