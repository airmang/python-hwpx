# SPDX-License-Identifier: Apache-2.0
"""A table's structure edit judges every line cache of the section, as 7.0.0 does, and leaves what it left.

Other calls rely on it. After ``insert_rows`` and the like, 7.0.0 has dropped the cache of every
paragraph of the section whose content changed under it, and watches every cache left with the content
it has now -- so a paragraph's ``line_segments``, ``estimate_pages``, ``write_line_caches``,
``apply_model``, a table moved to another section and the save all see the section judged at that
moment. The judgement was made cheaper since (:mod:`hwpx.oxml._line_caches`); these tests hold it to
the same answers:

* the public sequences in which a later call shows whether the edit judged a paragraph outside its table;
* 7.0.0's judgement, kept here as it was, run beside the present one over the same edits -- in the XML
  tree directly and through the API, in and out of tables, refused and not -- comparing after every step
  the XML, the edited marks and what each section watches.
"""

from __future__ import annotations

import hashlib
import io
import random
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.layout.line_cache import write_line_caches
from hwpx.layout.pages import estimate_pages
from hwpx.opc.xml_utils import parse_xml
from hwpx.oxml import _line_caches as line_caches

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures"
FIXED = {"seed": 705, "now": datetime(2000, 1, 1, tzinfo=timezone.utc)}


# -- the public sequences ----------------------------------------------------------------------------


def _fresh(two_tables: bool = False) -> tuple[HwpxDocument, Any]:
    """A text paragraph and a table (or two), saved with line caches and opened again."""

    made = HwpxDocument.new(**FIXED)
    made.add_paragraph("가나다")
    made.add_table(1, 1)
    if two_tables:
        made.add_table(1, 1).cell(0, 0).text = "cell"
    write_line_caches(made)
    doc = HwpxDocument.open(made.to_bytes(), **FIXED)
    return doc, doc.paragraphs[0]


def _text_node(paragraph: Any) -> Any:
    return paragraph.element.find(".//{*}t")


def _saved_lines(doc: HwpxDocument) -> int:
    return len(HwpxDocument.open(doc.to_bytes()).paragraphs[0].line_segments)


def test_a_cache_written_again_before_the_edit_goes_when_its_text_grows_after() -> None:
    doc, paragraph = _fresh()
    paragraph.text = "새글"
    write_line_caches(doc)  # a new cache, for two characters
    doc.tables[0].insert_rows(0)  # which the edit starts to watch, though it is outside the table

    _text_node(paragraph).text = "한글 " * 160

    assert _saved_lines(doc) == 0  # not one line computed for two characters under 480


def test_a_restyled_paragraph_has_no_cache_after_the_edit_to_carry_through_its_model() -> None:
    doc, paragraph = _fresh()
    paragraph.style_id_ref = 1
    doc.tables[0].insert_rows(0)
    assert len(paragraph.line_segments) == 0

    paragraph.apply_model(paragraph.to_model())

    assert _saved_lines(doc) == 0


def test_another_tables_changed_cell_takes_no_old_cache_to_the_section_it_moves_to() -> None:
    doc, _paragraph = _fresh(two_tables=True)
    other = doc.tables[1]
    _text_node(other.cell(0, 0).paragraphs[0]).text = "changed"
    doc.tables[0].insert_rows(0)

    other.move_to(doc.add_section().paragraphs[0])

    out = io.BytesIO()
    doc.save(out)
    again = HwpxDocument.open(out.getvalue())
    cell = next(
        found.paragraph for found in again.text.iter_paragraphs(where="cell") if found.paragraph.text == "changed"
    )
    assert len(cell.line_segments) == 0


def test_the_page_estimate_after_the_edit_lays_a_changed_paragraph_out_again() -> None:
    doc, paragraph = _fresh()
    _text_node(paragraph).text = "한글 " * 1600
    doc.tables[0].insert_rows(0)

    estimate = estimate_pages(doc)

    assert (estimate.pages, len(estimate.lines[0])) == (3, 95)  # not one page of one line, the old cache's


def test_line_caches_written_after_the_edit_reach_the_file() -> None:
    doc, paragraph = _fresh()
    _text_node(paragraph).text = "한글 " * 160
    doc.tables[0].insert_rows(0)

    report = write_line_caches(doc)

    assert (report.written, report.kept) == (3, 1)  # the changed paragraph is written, not counted as kept
    assert _saved_lines(doc) == 10


def test_a_refused_edit_marks_the_section_edited_before_anything_can_stop_it() -> None:
    doc, paragraph = _fresh()
    was = paragraph.id
    _text_node(paragraph).text = "changed"
    paragraph.element.set("id", "²")  # a digit int() cannot read: collecting the paragraph ids fails

    with pytest.raises(ValueError):
        doc.tables[0].insert_rows(0)

    assert doc.sections[0].dirty  # the judgement came first: the changed paragraph's cache went
    paragraph.element.set("id", was)
    assert HwpxDocument.open(doc.to_bytes()).paragraphs[0].text == "changed"


@pytest.mark.parametrize("name", ["formfit_glyph_cells.hwpx", "pages_footnotes_in_table_cells.hwpx"])
def test_a_hancom_documents_changed_cell_loses_its_cache_before_its_table_moves(name: str) -> None:
    doc = HwpxDocument.open(FIXTURES / "hancom_saved" / name, **FIXED)
    other = doc.tables[1]
    paragraph = next(p for row in other.rows for cell in row.cells for p in cell.paragraphs if p.text.strip())
    node = _text_node(paragraph)
    node.text = "i" * 6 if node.text != "i" * 6 else "l" * 6
    doc.tables[0].insert_rows(0)
    assert paragraph.element.find(f"{HP}linesegarray") is None  # judged with the edit, not at some save

    other.move_to(doc.add_section().paragraphs[0])

    again = HwpxDocument.open(doc.to_bytes())
    moved = [
        found.paragraph
        for found in again.text.iter_paragraphs(where="cell")
        if found.paragraph.text == node.text and found.paragraph.section is again.sections[-1]
    ]
    assert moved and all(len(p.line_segments) == 0 for p in moved)


def test_measuring_a_tables_rows_writes_nothing_into_the_document() -> None:
    # What lets the judgement after a rebuild look at the rebuilt table's block alone: between the two
    # judgements of a structure edit only the table and its holding paragraphs' caches change. The one
    # step there that is not the rebuild itself is this measure.
    for name in ("formfit_glyph_cells.hwpx", "pages_nested_table_rows_holding_tables_split.hwpx"):
        doc = HwpxDocument.open(FIXTURES / "hancom_saved" / name)
        before = [etree.tostring(part.element) for part in (*doc.sections, *doc.oxml.headers)]
        for table in doc.tables.with_nested:
            table._rows_height()
        assert [etree.tostring(part.element) for part in (*doc.sections, *doc.oxml.headers)] == before
        assert not any(section.dirty for section in doc.sections)


# -- 7.0.0's judgement, as it was --------------------------------------------------------------------
#
# Copied from src/hwpx/oxml/section.py at v7.0.0 (2e451dea) and frozen: the answers the present
# judgement must give. ``_Reference`` stands where a section keeps its TrackedCaches.

_REFERENCE_CACHE_BYTES_RE = re.compile(
    rb"<(?P<ns>(?:[A-Za-z_][\w.-]*:)?)linesegarray\b(?:[^>]*?/>|[^>]*>.*?</(?P=ns)linesegarray>)",
    re.DOTALL | re.IGNORECASE,
)


def _reference_local(node: Any) -> str:
    tag = node.tag
    return tag.rpartition("}")[2] if isinstance(tag, str) else ""


def _reference_cache_elements(root: Any) -> list[Any]:
    found = []
    for node in root.iter():
        if _reference_local(node).lower() == "linesegarray":
            parent = node.getparent()
            if parent is not None and _reference_local(parent) == "p":
                found.append(node)
    return found


def _reference_content_digest(paragraph: Any) -> bytes:
    content = _REFERENCE_CACHE_BYTES_RE.sub(b"", etree.tostring(paragraph, with_tail=False))
    return hashlib.blake2b(content, digest_size=16).digest()


def _reference_track(caches: list[Any], source_root: Any) -> list[tuple[Any, bytes, bytes]] | None:
    originals = _reference_cache_elements(source_root)
    if len(originals) != len(caches):
        return None
    return [
        (cache, _reference_content_digest(original.getparent()), etree.tostring(original, with_tail=False))
        for cache, original in zip(caches, originals)
    ]


def _reference_remove(root: Any, tracked: list[tuple[Any, bytes, bytes]]) -> tuple[int, list[tuple[Any, bytes, bytes]]]:
    known = {id(cache): (digest, was) for cache, digest, was in tracked}
    removed = 0
    following: list[tuple[Any, bytes, bytes]] = []
    for cache in _reference_cache_elements(root):
        paragraph = cache.getparent()
        digest = _reference_content_digest(paragraph)
        now = etree.tostring(cache, with_tail=False)
        expected = known.get(id(cache))
        if expected is not None and expected[0] != digest and expected[1] == now:
            paragraph.remove(cache)
            removed += 1
        else:
            following.append((cache, digest, now))
    return removed, following


class _Reference:
    def __init__(self, caches: list[Any], source_xml: bytes | None) -> None:
        self.source_xml: bytes | None = source_xml
        self.source_caches: list[Any] | None = caches
        self.tracked: list[tuple[Any, bytes, bytes]] | None = None

    def judge_all(self, root: Any, *, about_to_rebuild: Any = None) -> int:
        tracked = self.tracked
        if tracked is None:
            if self.source_xml is None or self.source_caches is None:
                return 0
            try:
                tracked = _reference_track(self.source_caches, parse_xml(self.source_xml))
            except Exception:
                tracked = None
            self.source_xml = self.source_caches = None
            if tracked is None:
                return 0
        removed, self.tracked = _reference_remove(root, tracked)
        return removed

    def judge_rebuilt(self, root: Any, element: Any, holder: Any) -> int:
        return self.judge_all(root)

    def watched(self, root: Any) -> Any:
        if self.tracked is None:
            return "not judged yet" if self.source_xml is not None else "judges nothing"
        known = {id(cache): (digest, was) for cache, digest, was in self.tracked}
        return len(known), [known.get(id(cache)) for cache in _reference_cache_elements(root)]


def _watched(tracker: line_caches.TrackedCaches, root: Any) -> Any:
    """What *tracker* watches, in the reference's terms (a cache watched "as read" with what the part
    holds for it)."""

    if not tracker._judges:
        return "judges nothing"
    if not tracker._judged_once:
        return "not judged yet"
    known = {key: (digest, was) for key, (_cache, digest, was) in tracker._watched.items()}
    if tracker._as_read:
        assert tracker._source_xml is not None
        originals = _reference_cache_elements(parse_xml(tracker._source_xml))
        for key, (_cache, place) in tracker._as_read.items():
            assert key not in known
            original = originals[place]
            known[key] = (
                _reference_content_digest(original.getparent()), etree.tostring(original, with_tail=False))
    return len(known), [known.get(id(cache)) for cache in _reference_cache_elements(root)]


def _open_pair(path: Path, source: bytes | None = None) -> tuple[HwpxDocument, HwpxDocument]:
    """The same document twice: one judging as now, one as 7.0.0 did."""

    data = path.read_bytes()
    now, then = HwpxDocument.open(data, **FIXED), HwpxDocument.open(data, **FIXED)
    for section in then.sections:
        tracker = section._tracked_caches
        assert tracker is not None and not tracker._judged_once
        caches = [cache for cache, _place in sorted(tracker._as_read.values(), key=lambda found: found[1])]
        section._tracked_caches = _Reference(caches, tracker._source_xml if source is None else source)  # type: ignore[assignment]
    if source is not None:
        for section in now.sections:
            assert section._tracked_caches is not None
            section._tracked_caches._source_xml = source
    return now, then


def _state(doc: HwpxDocument, reference: bool) -> list[Any]:
    state = []
    for section in doc.sections:
        tracker: Any = section._tracked_caches
        watched = tracker.watched(section.element) if reference else _watched(tracker, section.element)
        state.append((etree.tostring(section.element), section.dirty, watched))
    return state


# -- the same edits, judged both ways ----------------------------------------------------------------


def _all(doc: HwpxDocument, tag: str) -> list[Any]:
    return [node for section in doc.sections for node in section.element.iter(f"{HP}{tag}")]


def _caches(doc: HwpxDocument) -> list[Any]:
    return [cache for section in doc.sections for cache in _reference_cache_elements(section.element)]


def _result(call: Any) -> Any:
    try:
        value = call()
        return "returned", value if value is None else (type(value).__name__, len(value))
    except Exception as error:  # the same refusal is the same result
        return type(error).__name__, str(error)


def _direct_text(doc: HwpxDocument, pick: int) -> Any:
    nodes = [node for node in _all(doc, "t") if node.text]
    node = nodes[pick % len(nodes)]
    node.text = ("X" if node.text[0] != "X" else "Y") + node.text[1:] + "+"
    return None


def _direct_attribute(doc: HwpxDocument, pick: int) -> Any:
    paragraphs = _all(doc, "p")
    paragraph = paragraphs[pick % len(paragraphs)]
    paragraph.set("paraPrIDRef", "0" if paragraph.get("paraPrIDRef") != "0" else "1")
    return None


def _cache_rewritten(doc: HwpxDocument, pick: int) -> Any:
    caches = [cache for cache in _caches(doc) if len(cache)]
    if caches:
        segment = caches[pick % len(caches)][0]
        segment.set("horzsize", str(int(segment.get("horzsize", "0") or 0) + 1))
    return None


def _cache_removed(doc: HwpxDocument, pick: int) -> Any:
    caches = _caches(doc)
    if caches:
        cache = caches[pick % len(caches)]
        cache.getparent().remove(cache)
    return None


def _cache_replaced_by_its_copy(doc: HwpxDocument, pick: int) -> Any:
    from copy import deepcopy

    caches = _caches(doc)
    if caches:
        cache = caches[pick % len(caches)]
        cache.getparent().replace(cache, deepcopy(cache))
    return None


def _cache_given_a_tail(doc: HwpxDocument, pick: int) -> Any:
    caches = _caches(doc)
    if caches:
        cache = caches[pick % len(caches)]
        cache.tail = "\n" if not cache.tail else None
    return None


def _cache_copied_onto_another_paragraph(doc: HwpxDocument, pick: int) -> Any:
    from copy import deepcopy

    caches = _caches(doc)
    bare = [p for p in _all(doc, "p") if p.find(f"{HP}linesegarray") is None]
    if caches and bare:
        bare[pick % len(bare)].append(deepcopy(caches[pick % len(caches)]))
    return None


def _cache_moved_before_its_runs(doc: HwpxDocument, pick: int) -> Any:
    caches = _caches(doc)
    if caches:
        cache = caches[pick % len(caches)]
        cache.getparent().insert(0, cache)  # the same element, now ahead of the tables its paragraph holds
    return None


def _body_paragraph_moved_to_the_end(doc: HwpxDocument, pick: int) -> Any:
    section = doc.sections[pick % len(doc.sections)]
    movable = [p for p in section.element.findall(f"{HP}p")[1:]]
    if movable:
        section.element.append(movable[pick % len(movable)])
    return None


def _marked_edited(doc: HwpxDocument, pick: int) -> Any:
    doc.sections[pick % len(doc.sections)].mark_dirty()
    return None


def _judged_as_a_save_does(doc: HwpxDocument, pick: int) -> Any:
    return [section._remove_outlived_layout_caches() for section in doc.sections]


def _saved(doc: HwpxDocument, pick: int) -> Any:
    return hashlib.sha256(doc.to_bytes()).hexdigest()


def _tables(doc: HwpxDocument) -> list[Any]:
    """Every table, wherever it stands: in the body, in a cell, in a header or a footer."""

    return [place.object for place in doc.text.iter_objects(kinds="table")]


def _cell_text_through_the_api(doc: HwpxDocument, pick: int) -> Any:
    tables = _tables(doc)
    table = tables[pick % len(tables)]
    return _result(lambda: table.set_cell_text(0, 0, f"cell {pick}"))


def _paragraph_text_through_the_api(doc: HwpxDocument, pick: int) -> Any:
    paragraphs = doc.paragraphs
    paragraph = paragraphs[1 + pick % (len(paragraphs) - 1)] if len(paragraphs) > 1 else paragraphs[0]
    return _result(lambda: setattr(paragraph, "text", f"paragraph {pick}"))


def _structure_edit(doc: HwpxDocument, pick: int) -> Any:
    tables = _tables(doc)
    table = tables[pick % len(tables)]
    edits = [
        lambda: table.insert_rows(0),
        lambda: table.insert_rows(table.row_count - 1, copy_content=True),
        lambda: table.insert_columns(0),
        lambda: table.insert_columns(0, side="left", copy_content=True),
        lambda: table.delete_rows(table.row_count - 1),
        lambda: table.delete_columns(0),
        lambda: table.split_cell(0, 0, cols=2),
        lambda: table.split_cell(0, 0, rows=2),
        lambda: table.insert_rows(10_000),  # refused
        lambda: table.move_rows(0, to=table.row_count),
        lambda: table.copy_rows(0, to=0),
    ]
    return _result(edits[(pick // 7) % len(edits)])


STEPS = [
    _direct_text, _direct_text, _direct_attribute, _cache_rewritten, _cache_removed, _cache_replaced_by_its_copy,
    _cache_given_a_tail, _cache_copied_onto_another_paragraph, _cache_moved_before_its_runs,
    _body_paragraph_moved_to_the_end, _marked_edited, _judged_as_a_save_does, _saved,
    _cell_text_through_the_api, _paragraph_text_through_the_api,
    _structure_edit, _structure_edit, _structure_edit, _structure_edit, _structure_edit,
]
DOCUMENTS = [
    "hancom_saved/formfit_glyph_cells.hwpx",
    "hancom_saved/line_cache_table_cells.hwpx",
    "hancom_saved/merge_3x3_a1c2.hwpx",
    "hancom_saved/pages_cell_top_bottom_table_among_mixed_sizes.hwpx",  # tables in cells
    "hancom_saved/pages_nested_table_rows_holding_tables_split.hwpx",
    "hancom_saved/pages_footnotes_in_table_cells.hwpx",
    "hancom_saved/pages_ellipsis_starts_a_cell_line.hwpx",  # two sections
    "hwpxlib_corpus/error__20240626__no_manifest.hwpx",  # two sections
    "exam/A_form.hwpx",  # tables in the header and the footer
]


@pytest.mark.parametrize("name", DOCUMENTS)
def test_every_step_leaves_what_the_7_0_0_judgement_leaves(name: str) -> None:
    steps = 0
    for seed in range(6):
        rng = random.Random(f"{name}/{seed}")
        now, then = _open_pair(FIXTURES / name)
        assert _state(now, False) == _state(then, True)
        for _ in range(14):
            step, pick = rng.choice(STEPS), rng.randrange(10_000)
            results = (step(now, pick), step(then, pick))
            assert results[0] == results[1], (seed, step.__name__, pick)
            assert _state(now, False) == _state(then, True), (seed, step.__name__, pick)
            steps += 1
        assert hashlib.sha256(now.to_bytes()).digest() == hashlib.sha256(then.to_bytes()).digest(), seed
    assert steps == 84


# -- sequences the random steps seldom reach, each judged both ways ------------------------------------


def _both_ways(name: str, *steps: Any) -> list[Any]:
    """Run *steps* (each takes the document) on the pair, comparing what each returns and leaves after
    every one. Returns the states (per section: XML, edited mark, what is watched) after each step."""

    now, then = _open_pair(FIXTURES / name)
    states = [_state(now, False)]
    for step in steps:
        assert step(now) == step(then), step
        states.append(_state(now, False))
        assert states[-1] == _state(then, True), step
    return states


def _judge(doc: HwpxDocument) -> Any:
    return [section._remove_outlived_layout_caches(force=True) for section in doc.sections]


def _save(doc: HwpxDocument) -> Any:
    return hashlib.sha256(doc.to_bytes()).hexdigest()


def _cached_cell_paragraphs(doc: HwpxDocument) -> list[Any]:
    return [
        paragraph
        for table in _tables(doc)
        for paragraph in table.element.iter(f"{HP}p")
        if paragraph.find(f"{HP}linesegarray") is not None and (paragraph.findtext(f"{HP}run/{HP}t") or "")
    ]


def _caches_in(state: Any) -> int:
    return sum(len(_reference_cache_elements(etree.fromstring(xml))) for xml, _dirty, _watched_now in state)


def _watched_count(state: Any) -> int:
    return sum(watched_now[0] for _xml, _dirty, watched_now in state)


def test_a_table_in_a_header_takes_the_cache_of_the_body_paragraph_holding_the_header() -> None:
    # No editing API clears that one: the body paragraph holds the header, the header a paragraph, and
    # that one the table. Its content changed with the table, so the judgement after the rebuild (which
    # looks at the paragraphs the table sits in) drops its cache, as 7.0.0's look at the section did.
    def header_table(doc: HwpxDocument) -> Any:
        return next(
            table for table in _tables(doc)
            if any(_reference_local(ancestor) == "header" for ancestor in table.element.iterancestors())
        )

    def body_paragraph_cached(doc: HwpxDocument) -> bool:
        holders = [a for a in header_table(doc).element.iterancestors() if _reference_local(a) == "p"]
        return holders[-1].find(f"{HP}linesegarray") is not None

    states = _both_ways(
        "exam/A_form.hwpx",
        body_paragraph_cached,
        lambda doc: _result(lambda: header_table(doc).insert_rows(0)),
        body_paragraph_cached,
        _judge,
        _save,
    )
    with HwpxDocument.open(FIXTURES / "exam" / "A_form.hwpx") as doc:
        assert body_paragraph_cached(doc)
        header_table(doc).insert_rows(0)
        assert not body_paragraph_cached(doc)
    assert _caches_in(states[2]) < _caches_in(states[0])


def test_caches_swapped_between_two_paragraphs_are_caches_on_other_content() -> None:
    # Two cells' caches are often the same bytes. Swapped by hand before anything was judged, the block
    # still serialises to what it was read as, but each cache sits on content it did not come with.
    def swap(doc: HwpxDocument) -> Any:
        cached = _cached_cell_paragraphs(doc)[1:]  # not the block's first cache: the rest of it lines up
        for first in cached:
            for second in cached:
                one, two = first.find(f"{HP}linesegarray"), second.find(f"{HP}linesegarray")
                if (
                    first is not second
                    and etree.tostring(one) == etree.tostring(two)
                    and first.findtext(f"{HP}run/{HP}t") != second.findtext(f"{HP}run/{HP}t")
                ):
                    before = [etree.tostring(section.element) for section in doc.sections]
                    places = list(first).index(one), list(second).index(two)
                    first.insert(places[0], two)
                    second.insert(places[1], one)
                    assert [etree.tostring(section.element) for section in doc.sections] == before
                    return True
        raise AssertionError("no two cells with the same cache and other text")

    states = _both_ways("hancom_saved/line_cache_table_cells.hwpx", swap, _judge, _save)
    assert _caches_in(states[2]) == _caches_in(states[0]) - 2

    # And swapped after a judgement: the block serialises to what it did then, with the same cache
    # elements in it, in another order.
    states = _both_ways("hancom_saved/line_cache_table_cells.hwpx", _judge, swap, _judge, _save)
    assert _caches_in(states[3]) == _caches_in(states[0]) - 2


def test_a_dropped_cache_put_back_by_hand_is_a_cache_nobody_watched() -> None:
    held: dict[int, Any] = {}

    def change(doc: HwpxDocument) -> Any:
        paragraph = _cached_cell_paragraphs(doc)[0]
        held[id(doc)] = (paragraph, paragraph.find(f"{HP}linesegarray"))
        node = paragraph.find(f"{HP}run/{HP}t")
        node.text = "X" + node.text
        return None

    def put_back(doc: HwpxDocument) -> Any:
        paragraph, cache = held[id(doc)]
        assert cache.getparent() is None  # the judgement dropped it
        paragraph.append(cache)
        return None

    def change_again(doc: HwpxDocument) -> Any:
        node = held[id(doc)][0].find(f"{HP}run/{HP}t")
        node.text = "Y" + node.text
        return None

    states = _both_ways(
        "hancom_saved/line_cache_table_cells.hwpx", _judge, change, _judge, put_back, _judge, change_again, _judge, _save)

    watched = [_watched_count(states[index]) for index in (1, 3, 5, 7)]
    # Dropped, and with it the cache of the paragraph holding the table (its content changed too); put
    # back, it is watched from then on with the content it was put back on; dropped again.
    assert watched == [watched[0], watched[0] - 2, watched[0] - 1, watched[0] - 2]


def test_a_cache_rewritten_along_with_its_paragraph_stays() -> None:
    def rewrite(doc: HwpxDocument) -> Any:
        paragraph = _cached_cell_paragraphs(doc)[0]
        node = paragraph.find(f"{HP}run/{HP}t")
        node.text = "X" + node.text
        segment = paragraph.find(f"{HP}linesegarray")[0]
        segment.set("horzsize", "31415")
        return None

    for edit in (lambda table: table.insert_columns(0), lambda table: table.insert_rows(10_000)):
        states = _both_ways(
            "hancom_saved/line_cache_table_cells.hwpx",
            rewrite,
            lambda doc, edit=edit: _result(lambda: edit(_tables(doc)[0])),  # type: ignore[misc]
            _judge,
            _save,
        )
        assert b'horzsize="31415"' in states[-1][0][0]  # written on purpose: not what the part was read with


def test_a_cache_dropped_just_before_the_rebuild_still_costs_the_paragraph_around_it_its_own() -> None:
    # The judgement before a rebuild meets caches in document order. Here a paragraph holding a table in
    # a cell keeps its cache ahead of its runs, so it is judged (and kept: the cache was rewritten) before
    # a cache inside that table goes -- and the text after that cache goes with it, so the holding
    # paragraph no longer has the content it was just watched with. 7.0.0's second look at the whole
    # section drops its cache; the judgement after the rebuild of *another* table of the block must too,
    # though that paragraph neither is in the rebuilt table nor holds it.
    name = "hancom_saved/pages_table_cell_tables_as_characters_among_text_split.hwpx"
    picked: dict[int, tuple[Any, Any, int]] = {}

    def rewrite(cache: Any) -> None:
        cache[0].set("horzsize", str(int(cache[0].get("horzsize", "0")) + 1))

    def prepare(doc: HwpxDocument) -> Any:
        for block in doc.sections[0].element.findall(f"{HP}p"):
            nested = [table for table in block.iter(f"{HP}tbl") if len(list(table.iterancestors(f"{HP}tbl"))) == 1]
            for inner in nested:
                holder = next(inner.iterancestors(f"{HP}p"))
                cached = [
                    paragraph
                    for paragraph in inner.iter(f"{HP}p")
                    if paragraph.find(f"{HP}linesegarray") is not None and (paragraph.findtext(f"{HP}run/{HP}t") or "")
                ]
                others = [table for table in nested if table is not inner and holder not in table.iterancestors()]
                if holder.find(f"{HP}linesegarray") is None or not cached or not others:
                    continue
                holder.insert(0, holder.find(f"{HP}linesegarray"))
                cached[0].find(f"{HP}linesegarray").tail = "text after the cache"
                for cache in block.iter(f"{HP}linesegarray"):  # written on purpose: each stays, with this content
                    rewrite(cache)
                tables = [table.element for table in _tables(doc)]
                picked[id(doc)] = (holder, cached[0], tables.index(others[0]))
                return tables.index(inner), tables.index(others[0])
        raise AssertionError("no block with two tables in cells, one of them with cached paragraphs")

    def change_the_inner_paragraph(doc: HwpxDocument) -> Any:
        holder, inner_paragraph, _other = picked[id(doc)]
        node = inner_paragraph.find(f"{HP}run/{HP}t")
        node.text = "X" + node.text
        rewrite(holder.find(f"{HP}linesegarray"))  # the holding paragraph's stays through the next judgement
        return None

    def holder_cached(doc: HwpxDocument) -> bool:
        return picked[id(doc)][0].find(f"{HP}linesegarray") is not None

    def inner_cached(doc: HwpxDocument) -> bool:
        return picked[id(doc)][1].find(f"{HP}linesegarray") is not None

    def edit_the_other_table(doc: HwpxDocument) -> Any:
        return _result(lambda: _tables(doc)[picked[id(doc)][2]].insert_rows(0))

    _both_ways(
        name, prepare, _judge, holder_cached, inner_cached, change_the_inner_paragraph,
        edit_the_other_table, holder_cached, inner_cached, _judge, _save,
    )

    doc = HwpxDocument.open(FIXTURES / name)
    prepare(doc)
    _judge(doc)
    change_the_inner_paragraph(doc)
    assert holder_cached(doc) and inner_cached(doc)
    edit_the_other_table(doc)
    assert not inner_cached(doc)  # at the judgement before the rebuild
    assert not holder_cached(doc)  # at the one after it


def test_the_judgement_after_a_rebuild_looks_at_the_whole_section_unless_the_one_before_named_its_table() -> None:
    def unannounced(doc: HwpxDocument) -> Any:
        table = _tables(doc)[0]
        section = doc.sections[0]
        section._remove_outlived_layout_caches(force=True)  # names no table
        outside = next(
            paragraph
            for paragraph in section.element.findall(f"{HP}p")
            if paragraph.find(f"{HP}linesegarray") is not None
            and (paragraph.findtext(f"{HP}run/{HP}t") or "")
            and next(paragraph.iter(f"{HP}tbl"), None) is None
        )
        node = outside.find(f"{HP}run/{HP}t")
        node.text = "X" + node.text  # outside the table's block, after that judgement
        section.mark_dirty()
        dropped = section._remove_outlived_layout_caches(rebuilt=(table.element, table.paragraph.element))
        return dropped, outside.find(f"{HP}linesegarray") is None

    states = _both_ways("hancom_saved/formfit_glyph_cells.hwpx", unannounced)

    now = HwpxDocument.open(FIXTURES / "hancom_saved" / "formfit_glyph_cells.hwpx")
    assert unannounced(now) == (1, True)
    assert _caches_in(states[1]) == _caches_in(states[0]) - 1


@pytest.mark.parametrize(
    "source",
    [b"<not xml", b"<?xml version='1.0'?><hs:sec xmlns:hs='http://www.hancom.co.kr/hwpml/2011/section'/>"],
    ids=["unreadable", "other caches"],
)
def test_a_part_that_does_not_line_up_judges_nothing_either_way(source: bytes) -> None:
    now, then = _open_pair(FIXTURES / "hancom_saved" / "formfit_glyph_cells.hwpx", source=source)
    for doc in (now, then):
        _direct_text(doc, 3)
        _direct_text(doc, 40)
    for step, pick in ((_structure_edit, 0), (_judged_as_a_save_does, 0), (_structure_edit, 21), (_saved, 0)):
        assert step(now, pick) == step(then, pick)
        assert _state(now, False) == _state(then, True)
        assert _state(now, False)[0][2] == "judges nothing"
