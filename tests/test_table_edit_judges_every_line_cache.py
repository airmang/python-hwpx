# SPDX-License-Identifier: Apache-2.0
"""A table's structure edit judges every line cache of the section, as 7.0.0 does, and leaves what it left.

Other calls rely on it. After ``insert_rows`` and the like, 7.0.0 has dropped the cache of every
paragraph of the section whose content changed under it, and watches every cache left with the content
it has now -- so a paragraph's ``line_segments``, ``estimate_pages``, ``write_line_caches``,
``apply_model``, a table moved to another section and the save all see the section judged at that
moment, twice: before the table is rebuilt and after. The judgement was made cheaper since
(:mod:`hwpx.oxml._line_caches`); these tests hold it to the same answers:

* the public sequences in which a later call shows whether the edit judged a paragraph outside its table;
* 7.0.0's judgement, kept here as it was, run beside the present one over the same steps -- edits in the
  XML tree and through the API, in and out of tables, section settings, headers, notes, saves and
  reopenings, refused edits -- comparing after every step the XML, the edited marks and what each
  section watches.
"""

from __future__ import annotations

import copy
import gc
import hashlib
import io
import random
import re
import warnings
import zipfile
from copy import deepcopy
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


def test_a_paragraph_with_two_caches_loses_the_one_left_after_the_first_went() -> None:
    # The judgement before the rebuild keeps the cache nobody watched and drops the one the part was read
    # with -- and the line break after that one goes along, so the paragraph is no longer what the kept
    # cache was just watched with. The judgement after the rebuild looks at the paragraph again, though
    # the edit never touched it, and drops the other.
    made = HwpxDocument.new(**FIXED)
    made.add_paragraph("short")
    made.add_table(1, 1)
    write_line_caches(made)
    doc = HwpxDocument.open(made.to_bytes(), **FIXED)
    paragraph = doc.paragraphs[0]
    read = paragraph.element.find("{*}linesegarray")
    paragraph.element.insert(paragraph.element.index(read), deepcopy(read))
    read.tail = "\n"
    _text_node(paragraph).text = "long text " * 100

    doc.tables[0].insert_rows(0)

    assert len(paragraph.line_segments) == 0
    paragraph.apply_model(paragraph.to_model())
    assert _saved_lines(doc) == 0


def test_section_settings_the_edit_puts_into_the_tree_cost_their_paragraph_its_cache() -> None:
    # Settings written while the section has no hp:secPr wait outside the tree until the section is
    # marked edited -- which the structure edit does between its two judgements. The first paragraph,
    # judged a moment before without them, has other content at the second.
    doc, paragraph = _fresh()
    section = doc.sections[0]
    was = section.element.find(".//{*}secPr")
    was.getparent().remove(was)
    paragraph.element.find("{*}linesegarray")[0].set("horzsize", "901")  # rewritten: it stays the first time
    pending = section.properties.element
    pending.attrib.update(was.attrib)
    pending.extend(list(was))
    pending.set("textDirection", "VERTICAL")
    assert pending.getparent() is None

    doc.tables[0].insert_rows(0)

    assert pending.getparent() is not None
    assert len(paragraph.line_segments) == 0
    paragraph.apply_model(paragraph.to_model())
    assert _saved_lines(doc) == 0


def _section_xml_and_caches(doc: HwpxDocument) -> tuple[bytes, int]:
    root = doc.sections[0].element
    return etree.tostring(root), sum(1 for _ in root.iter(HP + "linesegarray"))


def test_a_copied_document_edits_a_table_as_the_document_it_was_copied_from() -> None:
    # A copy (copy.deepcopy) of a document read from a file takes along what its sections watch, keyed by
    # the ids of the original's elements. Once the original is gone, elements of the copy can be given
    # those ids: what was watched for one paragraph was taken for another, and the edit dropped the caches
    # of paragraphs it never touched (tens of the 245 here). 7.0.0 matched nothing in a copy.
    path = FIXTURES / "hancom_saved" / "pages_joined_rows_over_pages_mixed.hwpx"
    plain = HwpxDocument.open(path, **FIXED)
    plain.tables[0].insert_rows(0)
    expected = _section_xml_and_caches(plain)
    assert expected[1] == 244  # the paragraph holding the table loses its line; nothing else goes

    for _ in range(8):  # how the ids are given again depends on memory; each run so far dropped some
        copied = deepcopy(HwpxDocument.open(path, **FIXED))
        gc.collect()
        held = list(copied.sections[0].element.iter(HP + "linesegarray"))  # a caller looking at the caches
        copied.tables[0].insert_rows(0)
        assert _section_xml_and_caches(copied) == expected
        assert sum(cache.getparent() is None for cache in held) == 1


def test_what_is_watched_for_an_element_counts_for_no_other_with_its_id() -> None:
    # The same, made certain: an entry for another element under a cache's id (as a copied document's are,
    # once the ids are given again) must not judge that cache. It is a cache nobody watched, and stays.
    doc = HwpxDocument.open(FIXTURES / "hancom_saved" / "pages_joined_rows_over_pages_mixed.hwpx", **FIXED)
    doc.tables[0].insert_rows(0)  # judged twice: every cache of the section is watched
    section = doc.sections[0]
    tracker = section._tracked_caches
    assert tracker is not None
    cache = line_caches.cache_elements(section.element)[-1]
    block = line_caches._block_of(section.element, cache)
    stranger = etree.Element("elsewhere")
    # watched for *stranger*: another paragraph's content, and bytes that are this cache's
    tracker._watched[id(cache)] = (stranger, b"another paragraph", etree.tostring(cache, with_tail=False))
    tracker._blocks.pop(id(block), None)  # the block is judged cache by cache

    section._remove_outlived_layout_caches(force=True)

    assert cache.getparent() is not None
    assert tracker._watched[id(cache)][0] is cache  # watched from now on as itself


def test_a_cache_any_depth_down_in_a_body_paragraph_is_judged_without_recursion() -> None:
    # Only a tree made in code can hold one (a file is read at most 256 elements deep). 7.0.0 judged it;
    # the state of its block walked up from it a call per element and ran out of stack.
    doc = HwpxDocument.open(FIXTURES / "hancom_saved" / "line_cache_table_cells.hwpx", **FIXED)
    node = etree.SubElement(doc.sections[0].element, HP + "p")
    for _ in range(3 * 1000):
        node = etree.SubElement(node, HP + "subList")
    inner = etree.SubElement(node, HP + "p")
    deep = etree.SubElement(inner, HP + "linesegarray")

    doc.tables[0].insert_rows(0)
    doc.tables[0].insert_rows(0)  # and again, with the block's state taken before

    assert deep.getparent() is inner  # a cache nobody watched, kept
    assert doc.tables[0].row_count == 9


def test_a_shallow_copy_of_a_section_judges_with_what_it_watched_when_it_was_made() -> None:
    # 7.0.0 kept what a section watches in attributes each judgement bound anew: a copy.copy of the section
    # made before an edit went on judging against the part as read. The copy shared one record with the
    # section instead, which the edit's judgements moved on.
    doc = HwpxDocument.open(FIXTURES / "hancom_saved" / "cell_blank_lines_saved.hwpx", **FIXED)
    section = doc.sections[0]
    twin = copy.copy(section)
    caches = list(section.element.iter(HP + "linesegarray"))
    assert len(caches) == 1
    cache = caches[0]
    text = next(cache.getparent().iter(HP + "t"))
    text.text = (text.text or "") + "B"  # the paragraph's content changes ...
    line = cache[0]
    width = line.get("horzsize")
    line.set("horzsize", "7")  # ... and its cache is written again: the edit's judgements keep it

    doc.tables.with_nested[0].insert_rows(0)
    line.set("horzsize", width)  # the cache as read again, on content that is not
    twin.mark_dirty()
    twin.remove_stale_layout_caches()

    assert cache.getparent() is None  # judged as read, as 7.0.0's copy judged it
    assert sum(1 for _ in section.element.iter(HP + "linesegarray")) == 0


def _block_and_what_is_judged_in_it(root: Any) -> tuple[Any, list[Any]]:
    block = root.find(".//*[@id='block']")
    caches = line_caches.cache_elements(block)
    state = line_caches._block_state(block, caches, line_caches._whole_bytes(block))
    judged = [(line_caches._content_digest(cache.getparent()), etree.tostring(cache, with_tail=False)) for cache in caches]
    return state, judged


def test_a_blocks_state_decides_every_digest_and_every_cache_comparison_in_it() -> None:
    # What lets a block in the state it had go unjudged. A paragraph's digest and a cache's bytes are
    # serialisations of elements inside the block, written under the namespace declarations they inherit
    # -- so the block's own bytes do not decide them: the order of the declarations in scope and whether
    # an unprefixed element has a namespace at all do not show in the bytes. The state holds both (and
    # the names of the elements over the block, which the next test is about).
    inside = (
        '<p:run><p:tbl><p:tc xmlns:r="urn:r"><p:p q:a="1"><p:run><p:t>text</p:t></p:run>'
        '<p:linesegarray><p:lineseg r:x="1"/></p:linesegarray>tail</p:p></p:tc></p:tbl></p:run><linesegarray/>'
    )
    block = f'<p:p id="block" q:a="1">{inside}</p:p>'
    trees = {
        "plain": f'<s:sec xmlns:s="urn:s" xmlns:p="urn:p" xmlns:q="urn:q" xmlns="urn:p">{block}</s:sec>',
        "the same again": f'<s:sec xmlns:s="urn:s" xmlns:p="urn:p" xmlns:q="urn:q" xmlns="urn:p">{block}</s:sec>',
        "another declaration above": f'<s:sec xmlns:s="urn:s" xmlns:p="urn:p" xmlns:q="urn:q" xmlns="urn:p" xmlns:z="urn:z">{block}</s:sec>',
        "another order above": f'<s:sec xmlns:q="urn:q" xmlns:s="urn:s" xmlns:p="urn:p" xmlns="urn:p">{block}</s:sec>',
        "a prefix declared again on the way down": (
            '<s:sec xmlns:s="urn:s" xmlns:p="urn:p" xmlns:q="urn:q" xmlns="urn:p">'
            f'<s:wrap xmlns:q="urn:q">{block}</s:wrap></s:sec>'
        ),
        "in a wrapper that declares nothing": (
            f'<s:sec xmlns:s="urn:s" xmlns:p="urn:p" xmlns:q="urn:q" xmlns="urn:p"><s:wrap>{block}</s:wrap></s:sec>'
        ),
        "in a wrapper that declares the first of them": (
            '<s:sec xmlns:s="urn:s" xmlns:q="urn:q" xmlns="urn:p">'
            f'<s:wrap xmlns:s="urn:s" xmlns:p="urn:p">{block}</s:wrap></s:sec>'
        ),
    }
    found = {name: _block_and_what_is_judged_in_it(etree.fromstring(xml)) for name, xml in trees.items()}
    without_a_namespace = etree.fromstring(trees["plain"])
    without_a_namespace.find(".//*[@id='block']")[-1].tag = "linesegarray"  # was {urn:p}linesegarray
    found["an unprefixed cache taken out of its namespace"] = _block_and_what_is_judged_in_it(without_a_namespace)

    by_state: dict[Any, Any] = {}
    for state, judged in found.values():
        assert by_state.setdefault(state, judged) == judged  # one state, one answer
    assert found["plain"] == found["the same again"]
    # The same declarations in scope, in the same order, carried by other elements: the same answers. The
    # state keeps each element's own declarations, so it may tell these apart -- that only costs a judgement.
    assert found["in a wrapper that declares nothing"][1] == found["in a wrapper that declares the first of them"][1]

    # And the bytes alone would not do: these serialise to the bytes "plain" does, with other answers.
    plain_bytes = found["plain"][0][0]
    for name in ("a prefix declared again on the way down", "an unprefixed cache taken out of its namespace"):
        state, judged = found[name]
        assert state[0] == plain_bytes and state != found["plain"][0], name
        assert judged != found["plain"][1], name


def _taken_in(block: Any, held: str) -> Any:
    """A subtree for *block* to take in: ``e > m > held``, where ``m`` gives the block's prefix to
    another namespace and ``z`` is the block's namespace declared again. lxml strips that repeated
    declaration and binds whatever used it to the declaration in scope at the block -- below ``m``
    too, where the prefix it is then written with means the other namespace."""

    real, prefix = etree.QName(block).namespace, block.prefix
    held = held.replace("P:", f"{prefix}:")
    return etree.fromstring(f'<z:e xmlns:z="{real}"><{prefix}:m xmlns:{prefix}="urn:other">{held}</{prefix}:m></z:e>')


#: a paragraph of the block's namespace with a cache, in a holder of the namespace ``m`` declares
_HELD_PLAINLY = "<P:a><z:p><z:linesegarray/></z:p></P:a>"


def test_a_name_bound_to_a_declaration_hidden_from_it_shows_in_the_state_of_its_block() -> None:
    # An element or an attribute bound to a declaration that a nearer one hides serialises like one
    # of the nearer namespace, so the block's bytes do not tell. What a paragraph below such an
    # element serialises to by itself does: it is written with the namespace its nearest ancestor of
    # that prefix is bound to. An attribute bound that way is written with a prefix made up for it.
    def block_taking_in(held: str) -> tuple[Any, list[Any]]:
        root = etree.fromstring('<s:sec xmlns:s="urn:s" xmlns:p="urn:p"><p:p id="block"/></s:sec>')
        root[0].append(_taken_in(root[0], held))
        return _block_and_what_is_judged_in_it(root)

    def as_its_bytes_parse(held: str) -> tuple[Any, list[Any]]:
        root = etree.fromstring('<s:sec xmlns:s="urn:s" xmlns:p="urn:p"><p:p id="block"/></s:sec>')
        root[0].append(_taken_in(root[0], held))
        return _block_and_what_is_judged_in_it(etree.fromstring(etree.tostring(root)))

    plain = block_taking_in(_HELD_PLAINLY)
    for held in (
        "<z:a><z:p><z:linesegarray/></z:p></z:a>",  # the holder bound to the hidden declaration
        "<z:b><P:a><z:p><z:linesegarray/></z:p></P:a></z:b>",  # an element further up: the holder is nearer
        '<P:p z:k="1"><P:linesegarray/></P:p>',  # an attribute of the paragraph
        '<P:p><P:linesegarray z:k="1"/></P:p>',  # an attribute of the cache
    ):
        bound, parsed = block_taking_in(held), as_its_bytes_parse(held)
        assert bound[0][0] == parsed[0][0], held  # the same bytes
        if bound[1] != parsed[1]:
            assert bound[0] != parsed[0], held  # another answer: another state
        else:
            assert "z:b" in held  # the one that changes no answer
    held = "<z:a><z:p><z:linesegarray/></z:p></z:a>"
    assert block_taking_in(held)[0][0] == plain[0][0] and block_taking_in(held)[1] != plain[1]
    for held in ('<P:p z:k="1"><P:linesegarray/></P:p>', '<P:p><P:linesegarray z:k="1"/></P:p>'):
        assert block_taking_in(held)[1] != as_its_bytes_parse(held)[1], held

    # The same over the block: a block of another prefix, the element holding it bound to the hidden
    # declaration. Nothing in the block differs, by bytes or by name.
    held = '<z:a><w:w xmlns:w="urn:w" id="block"><P:p><P:linesegarray/></P:p></w:w></z:a>'
    trees = [etree.fromstring('<s:sec xmlns:s="urn:s" xmlns:p="urn:p"><p:p/></s:sec>') for _ in range(2)]
    for tree in trees:
        tree[0].append(_taken_in(tree[0], held))
    bound = _block_and_what_is_judged_in_it(trees[0])
    parsed = _block_and_what_is_judged_in_it(etree.fromstring(etree.tostring(trees[1])))
    assert bound[0][0] == parsed[0][0] and bound[0][2] == parsed[0][2]  # the bytes, and every name in the block
    assert bound[1] != parsed[1] and bound[0] != parsed[0]


def _random_element(rng: random.Random, depth: int, prefixes: tuple[str, ...] = ("p:", "p:", "q:", "", "")) -> str:
    name = rng.choice(["p", "p", "run", "tbl", "tc", "linesegarray", "linesegarray", "lineseg"])
    prefix = rng.choice(prefixes)
    declared = "".join(
        f' xmlns{":" + chosen if chosen else ""}="{rng.choice(["urn:p", "urn:q", "urn:r"])}"'
        for chosen in rng.sample(["p", "q", "r", None], k=rng.choice([0, 0, 0, 1, 2]))
    )
    attribute = rng.choice(["", ' a="1"', ' q:b="2"', ' p:c="x&amp;y"'])
    if "z:" in prefixes and rng.random() < 0.3:
        attribute += ' z:d="3"'
    inner = ""
    if depth < 4:
        for _ in range(rng.choice([0, 1, 2, 3])):
            inner += (
                rng.choice(["", "text", "<!-- c -->"])
                + _random_element(rng, depth + 1, prefixes)
                + rng.choice(["", "tail", "\n"])
            )
    return f"<{prefix}{name}{declared}{attribute}>{inner}</{prefix}{name}>"


def _random_context(rng: random.Random, block: str) -> Any:
    """*block* under a root (and perhaps a wrapper) with declarations of its own, then edited in ways a
    serialisation of the block may not show; the block's element, or ``None`` when it is not XML."""

    above = ' xmlns:p="urn:p" xmlns:q="urn:q"' + rng.choice(["", ' xmlns:r="urn:r"', ' xmlns="urn:p"', ' xmlns="urn:r"'])
    wrap = rng.choice([None, None, "p:wrap", "q:wrap"])
    declared = rng.choice(["", "", ' xmlns:q="urn:q"', ' xmlns:r="urn:q"', ' xmlns="urn:q"'])
    inner = f"<{wrap}{declared}>{block}</{wrap}>" if wrap else block
    try:
        root = etree.fromstring(f"<p:root{above}>{inner}</p:root>")
    except etree.XMLSyntaxError:
        return None
    found = root.find(".//*[@id='block']")
    for _ in range(rng.choice([0, 0, 1, 2, 3])):
        nodes = [node for node in found.iter() if isinstance(node.tag, str)]
        node, kind = rng.choice(nodes), rng.randrange(10)
        if kind == 0:
            etree.cleanup_namespaces(root)
        elif kind == 1:
            etree.cleanup_namespaces(root, top_nsmap={"alias": "urn:alias"}, keep_ns_prefixes=["alias", "p"])
        elif kind == 2:  # in or out of a namespace, the local name kept
            local = etree.QName(node).localname
            node.tag = rng.choice([local, "{urn:p}" + local, "{urn:q}" + local])
        elif kind == 3:
            etree.SubElement(node, rng.choice(["linesegarray", "{urn:p}linesegarray", "{urn:q}p", "p"]))
        elif kind == 4 and node is not found:
            node.getparent().replace(node, deepcopy(node))
        elif kind == 5 and node is not found:  # out of the tree and back, which drops repeated declarations
            parent = node.getparent()
            parent.insert(parent.index(node), node)
        elif kind == 6:  # the block itself into another tree
            other = etree.fromstring('<p:root xmlns:p="urn:p" xmlns:q="urn:q" xmlns="urn:q"><p:slot/></p:root>')
            other.append(found)
        elif kind >= 7:  # a subtree taken in whose top declares namespaces again, under another prefix too
            uris = [rng.choice(["urn:p", "urn:q", "urn:r"]) for _ in range(3)]
            inner = "".join(
                _random_element(rng, rng.choice([1, 2, 3]), ("p:", "q:", "z:", "z:", "")) for _ in range(rng.choice([1, 2]))
            )
            taken = f'<z:e xmlns:z="{uris[0]}" xmlns:p="{uris[1]}" xmlns:q="{uris[2]}">{inner}</z:e>'
            node.insert(rng.randrange(len(node) + 1), etree.fromstring(taken))
    return found


def test_over_random_trees_a_blocks_state_decides_what_is_judged_in_it() -> None:
    # The same claim over trees nobody picked: blocks under other declarations, in other orders, with
    # names moved in and out of namespaces, copied, moved between trees, with subtrees taken in whose
    # repeated declarations lxml strips. Each is also set beside its own serialisation parsed again
    # (the same bytes, every name bound as written). Whenever two blocks are in one state, each
    # paragraph digest and each cache in them must agree. (This is also what holds the claim to the
    # lxml the tests run on.)
    rng = random.Random(20261121)
    compared = bound_otherwise = 0
    for _ in range(2000):
        block = f'<p:p id="block">{_random_element(rng, 0)}{_random_element(rng, 0)}<p:linesegarray/></p:p>'
        seen: dict[Any, Any] = {}
        for _ in range(6):
            found = _random_context(rng, block)
            if found is None or found.getparent() is None:
                continue
            again = etree.fromstring(etree.tostring(found.getroottree().getroot())).find(".//*[@id='block']")
            bound_otherwise += [node.tag for node in found.iter()] != [node.tag for node in again.iter()]
            for one in (found, again):
                caches = line_caches.cache_elements(one)
                state = line_caches._block_state(one, caches, line_caches._whole_bytes(one))
                judged = [
                    (line_caches._content_digest(cache.getparent()), etree.tostring(cache, with_tail=False))
                    for cache in caches
                ]
                compared += state in seen
                assert seen.setdefault(state, judged) == judged
    assert compared > 5000 and bound_otherwise > 300
    assert line_caches._states_decide()


def test_where_the_states_would_not_decide_every_cache_is_digested_every_time(monkeypatch: pytest.MonkeyPatch) -> None:
    # An lxml that serialised otherwise than the states take it to: no block is taken as unchanged.
    monkeypatch.setattr(line_caches, "_STATES_DECIDE", False)
    digests: list[int] = []
    digest = line_caches._content_digest
    monkeypatch.setattr(line_caches, "_content_digest", lambda paragraph: digests.append(1) or digest(paragraph))
    doc = HwpxDocument.open(FIXTURES / "hancom_saved" / "formfit_glyph_cells.hwpx")
    caches = len(line_caches.cache_elements(doc.sections[0].element))

    doc.tables[0].insert_rows(0)
    first = len(digests)
    doc.tables[0].insert_rows(0)

    assert first >= 3 * (caches - 2)  # the part as read once, the tree twice: 7.0.0's work
    assert len(digests) - first >= 2 * (caches - 2)
    data = (FIXTURES / "hancom_saved" / "formfit_glyph_cells.hwpx").read_bytes()
    assert run_steps(data, random.Random("states do not decide"), 24) == 24


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


def _pair(data: bytes, source: bytes | None = None) -> tuple[HwpxDocument, HwpxDocument]:
    """The same document twice: one judging as now, one as 7.0.0 did."""

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


def _open_pair(path: Path, source: bytes | None = None) -> tuple[HwpxDocument, HwpxDocument]:
    return _pair(path.read_bytes(), source)


def _with_sections_rewritten(data: bytes, rewrite: Any) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            part = source.read(info)
            target.writestr(info, rewrite(part) if re.fullmatch(r"Contents/section\d+\.xml", info.filename) else part)
    return out.getvalue()


def _paragraphs_in_the_default_namespace(data: bytes) -> bytes:
    """The same package with ``hp:p`` and ``hp:linesegarray`` written without a prefix, the section's
    root declaring the paragraph namespace as the default one too: the same document, in a form where
    an element taken out of its namespace serialises as it did."""

    def rewrite(part: bytes) -> bytes:
        part = re.sub(rb"<(/?)hp:(p|linesegarray)(?=[\s>/])", rb"<\1\2", part)
        # declared last: an element in the namespace writes it first when serialised by itself
        return re.sub(
            rb"(<hs:sec\b[^>]*?)(/?>)", rb'\1 xmlns="http://www.hancom.co.kr/hwpml/2011/paragraph"\2', part, count=1)

    return _with_sections_rewritten(data, rewrite)


def _body_paragraphs_declaring_their_prefix_again(data: bytes) -> bytes:
    """The same package with every body paragraph (the children of a section's root) declaring two
    prefixes itself that the root declares too, and carrying an attribute in the second: the same
    document, in a form where a block can lose its own declarations without its bytes changing (as
    the element serialised it writes its name's and its attributes' namespaces first either way)."""

    def rewrite(part: bytes) -> bytes:
        out, depth, copied = [], 0, 0
        for tag in re.finditer(rb"<(/?)([\w:.-]+)[^<>]*?(/?)>", part):
            closing, name, empty = tag.groups()
            if closing:
                depth -= 1
                continue
            if depth == 1 and name == b"hp:p":
                at = tag.start() + 1 + len(name)
                out += [
                    part[copied:at],
                    b' xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
                    b' xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" hc:mark="1"',
                ]
                copied = at
            depth += not empty
        return b"".join([*out, part[copied:]])

    return _with_sections_rewritten(data, rewrite)


def _state(doc: HwpxDocument, reference: bool) -> list[Any]:
    state: list[Any] = []
    for section in doc.sections:
        tracker: Any = section._tracked_caches
        if tracker is None:  # a section made since the document was read: nothing to compare it with
            watched: Any = "no part"
        else:
            watched = tracker.watched(section.element) if reference else _watched(tracker, section.element)
        state.append((etree.tostring(section.element), section.dirty, watched))
    state.append([header.dirty for header in doc.oxml.headers])
    return state


# -- the same steps, judged both ways -----------------------------------------------------------------
#
# Each step takes the document and a number that picks what it works on (the same in both documents).


def _of(items: list[Any], pick: int) -> Any:
    return items[pick % len(items)] if items else None


def _all(doc: HwpxDocument, tag: str) -> list[Any]:
    return [node for section in doc.sections for node in section.element.iter(f"{HP}{tag}")]


def _caches(doc: HwpxDocument) -> list[Any]:
    return [cache for section in doc.sections for cache in _reference_cache_elements(section.element)]


def _tables(doc: HwpxDocument) -> list[Any]:
    """Every table, wherever it stands: in the body, in a cell, in a header or a footer."""

    return [place.object for place in doc.text.iter_objects(kinds="table")]


def _result(call: Any) -> Any:
    try:
        value = call()
    except Exception as error:  # the same refusal is the same result
        return type(error).__name__, str(error)
    return "returned", None if value is None else type(value).__name__


def _direct_text(doc: HwpxDocument, pick: int) -> Any:
    node = _of([node for node in _all(doc, "t") if node.text], pick)
    if node is not None:
        node.text = ("X" if node.text[0] != "X" else "Y") + node.text[1:] + "+" * (pick % 3)


def _direct_long_text(doc: HwpxDocument, pick: int) -> Any:
    node = _of([node for node in _all(doc, "t") if node.text], pick)
    if node is not None:
        node.text = "한글 " * (20 + pick % 200)


def _text_as_cdata(doc: HwpxDocument, pick: int) -> Any:
    node = _of(_all(doc, "t"), pick)
    if node is not None and len(node) == 0:
        node.text = etree.CDATA("é & 글")


def _direct_attribute(doc: HwpxDocument, pick: int) -> Any:
    paragraph = _of(_all(doc, "p"), pick)
    paragraph.set("paraPrIDRef", "0" if paragraph.get("paraPrIDRef") != "0" else "1")


def _attributes_reordered(doc: HwpxDocument, pick: int) -> Any:
    paragraph = _of(_all(doc, "p"), pick)
    attributes = list(paragraph.attrib.items())
    paragraph.attrib.clear()
    paragraph.attrib.update(dict(reversed(attributes)))


def _qualified_name_changed(doc: HwpxDocument, pick: int) -> Any:
    # In or out of the paragraph namespace, the local name kept: where the section declares that
    # namespace as the default one, an unprefixed element serialises alike either way.
    nodes = [node for node in _caches(doc)] + [cache.getparent() for cache in _caches(doc)]
    node = _of(nodes, pick)
    if node is not None:
        local = etree.QName(node).localname
        node.tag = local if node.tag != local else f"{HP}{local}"


def _cache_rewritten(doc: HwpxDocument, pick: int) -> Any:
    cache = _of([cache for cache in _caches(doc) if len(cache)], pick)
    if cache is not None:
        cache[0].set("horzsize", str(int(cache[0].get("horzsize", "0") or 0) + 1))


def _cache_removed(doc: HwpxDocument, pick: int) -> Any:
    cache = _of(_caches(doc), pick)
    if cache is not None:
        cache.getparent().remove(cache)


def _taken_out(doc: HwpxDocument) -> list[tuple[Any, int, Any]]:
    """The caches the steps took out of *doc*, kept on the document itself (an id() of a document that
    is gone can be another document's)."""

    return doc.__dict__.setdefault("_caches_the_steps_took_out", [])  # type: ignore[no-any-return]


def _cache_taken_out(doc: HwpxDocument, pick: int) -> Any:
    cache = _of(_caches(doc), pick)
    if cache is not None:
        parent = cache.getparent()
        _taken_out(doc).append((parent, parent.index(cache), cache))
        parent.remove(cache)


def _cache_put_back(doc: HwpxDocument, pick: int) -> Any:
    taken = _taken_out(doc)
    if taken:
        parent, place, cache = taken.pop(pick % len(taken))
        parent.insert(min(place, len(parent)), cache)  # the very element that was taken out


def _cache_replaced_by_its_copy(doc: HwpxDocument, pick: int) -> Any:
    cache = _of(_caches(doc), pick)
    if cache is not None:
        cache.getparent().replace(cache, deepcopy(cache))


def _cache_given_a_tail(doc: HwpxDocument, pick: int) -> Any:
    cache = _of(_caches(doc), pick)
    if cache is not None:
        cache.tail = ("\n", "text after it", None)[pick % 3] if not cache.tail else None


def _second_cache_beside_the_first(doc: HwpxDocument, pick: int) -> Any:
    cache = _of(_caches(doc), pick)
    if cache is not None:
        parent, copy = cache.getparent(), deepcopy(cache)
        copy.tail = None
        parent.insert(parent.index(cache) + (pick // 7) % 2, copy)  # before it, or after


def _cache_copied_onto_another_paragraph(doc: HwpxDocument, pick: int) -> Any:
    cache = _of(_caches(doc), pick)
    bare = _of([paragraph for paragraph in _all(doc, "p") if paragraph.find(f"{HP}linesegarray") is None], pick // 3)
    if cache is not None and bare is not None:
        bare.append(deepcopy(cache))


def _cache_moved_before_its_runs(doc: HwpxDocument, pick: int) -> Any:
    cache = _of(_caches(doc), pick)
    if cache is not None:
        cache.getparent().insert(0, cache)  # the same element, now ahead of the tables its paragraph holds


def _comment_put_in(doc: HwpxDocument, pick: int) -> Any:
    target = _of(_all(doc, "p"), pick) if pick % 4 else doc.sections[pick % len(doc.sections)].element
    target.insert(1 + (pick // 5) % len(target) if len(target) else 0, etree.Comment(" <hp:linesegarray/> "))


def _body_paragraph_moved_to_the_end(doc: HwpxDocument, pick: int) -> Any:
    section = doc.sections[pick % len(doc.sections)]
    paragraph = _of(section.element.findall(f"{HP}p")[1:], pick)
    if paragraph is not None:
        section.element.append(paragraph)


def _body_paragraph_copied_in(doc: HwpxDocument, pick: int) -> Any:
    section = doc.sections[pick % len(doc.sections)]
    paragraph = _of(section.element.findall(f"{HP}p")[1:], pick)
    if paragraph is not None:
        section.element.insert(1 + (pick // 3) % len(section.element), deepcopy(paragraph))


def _body_paragraph_removed(doc: HwpxDocument, pick: int) -> Any:
    section = doc.sections[pick % len(doc.sections)]
    paragraphs = section.element.findall(f"{HP}p")[1:]
    if len(paragraphs) > 3:
        section.element.remove(_of(paragraphs, pick))


def _block_given_a_tail(doc: HwpxDocument, pick: int) -> Any:
    _of(doc.sections[pick % len(doc.sections)].element.findall(f"{HP}p"), pick).tail = "\n " * (pick % 3)


_HELD = (
    _HELD_PLAINLY,
    "<z:a><z:p><z:linesegarray/></z:p></z:a>",
    '<P:a><P:p z:k="1"><P:linesegarray/></P:p></P:a>',
    "<z:a><P:p><P:linesegarray/><P:run><P:t>held</P:t></P:run></P:p></z:a>",
    '<P:a><z:p><z:linesegarray z:k="1"/>tail</z:p></P:a>',
)


def _subtree_taken_in(doc: HwpxDocument, pick: int) -> Any:
    paragraph = _of(_all(doc, "p"), pick)
    if paragraph is not None:
        paragraph.append(_taken_in(paragraph, _HELD[pick % len(_HELD)]))


def _held_paragraph_given_another_holder(doc: HwpxDocument, pick: int) -> Any:
    """The holder of a paragraph taken in, swapped for one bound the other way (to the declaration hidden
    from it, or to the one that hides it): where the holder held nothing but the paragraph, no byte of
    the body paragraph changes. With nothing taken in yet, a paragraph in a holder is."""

    wrapper = _of([node for section in doc.sections for node in section.element.iter(f"{HP}e")], pick)
    if wrapper is None or not len(wrapper) or not len(wrapper[0]):
        return _subtree_taken_in(doc, pick - pick % len(_HELD))
    holder = wrapper[0][0]
    wrapper.addnext(_taken_in(wrapper.getparent(), "<P:a/>" if etree.QName(holder).namespace != "urn:other" else "<z:a/>"))
    for child in list(holder):
        wrapper.getnext()[0][0].append(child)
    wrapper.getparent().remove(wrapper)


def _namespaces_tidied(doc: HwpxDocument, pick: int) -> Any:
    root = doc.sections[pick % len(doc.sections)].element
    etree.cleanup_namespaces(root, top_nsmap={"alias": "urn:alias"}, keep_ns_prefixes=["alias", "hp", "hs"])


def _root_attribute_set(doc: HwpxDocument, pick: int) -> Any:
    doc.sections[pick % len(doc.sections)].element.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def _section_settings_taken_out(doc: HwpxDocument, pick: int) -> Any:
    section = doc.sections[pick % len(doc.sections)]
    found = section.element.find(f".//{HP}secPr")
    if found is not None:
        found.getparent().remove(found)


def _section_settings_written(doc: HwpxDocument, pick: int) -> Any:
    # In the tree, or (after the step above) waiting outside it for the section to be marked edited.
    element = doc.sections[pick % len(doc.sections)].properties.element
    element.set("textDirection", "VERTICAL" if element.get("textDirection") != "VERTICAL" else "HORIZONTAL")
    return element.getparent() is not None


def _section_settings_moved_to_another_paragraph(doc: HwpxDocument, pick: int) -> Any:
    section = doc.sections[pick % len(doc.sections)]
    found = section.element.find(f".//{HP}secPr")
    run = _of([run for paragraph in section.element.findall(f"{HP}p") for run in paragraph.findall(f"{HP}run")], pick)
    if found is not None and run is not None:
        run.insert(0, found)


def _page_setting_through_the_api(doc: HwpxDocument, pick: int) -> Any:
    index = pick % len(doc.sections)
    paragraph = (pick // 11) % max(1, len(doc.paragraphs))
    calls = [
        lambda: doc.page.set_margins(left=7000 + pick % 500, section=index),
        lambda: doc.page.set_size(orientation=("LANDSCAPE", "PORTRAIT")[pick % 2], section=index),
        lambda: doc.page.set_columns(1 + pick % 3, section=index),
        lambda: doc.page.set_columns(2, paragraph=paragraph),
        lambda: doc.page.set_header(text=f"header {pick}", section=index),
        lambda: doc.page.set_footer(text=f"footer {pick}", section=index),
        lambda: doc.page.set_page_number(section=index),
        lambda: doc.page.remove_header(section=index),
        lambda: doc.page.add_number_restart(paragraph, number=1 + pick % 5),
        lambda: doc.page.add_page_hiding(paragraph, header=True),
        lambda: doc.page.set_text_direction(("VERTICAL", "HORIZONTAL")[pick % 2], section=index),
        lambda: doc.page.set_visibility(hide_first_header=bool(pick % 2), section=index),
        lambda: doc.page.set_line_numbers(count_by=1 + pick % 4, section=index),
        lambda: doc.page.set_grid(line_grid=pick % 30, section=index),
        lambda: doc.page.set_start_numbers(page=1 + pick % 9, section=index),
        lambda: doc.page.set_master_page(doc.oxml.add_master_page(), section=index),
    ]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # a footer written over a page number says so
        return _result(calls[(pick // 7) % len(calls)])


def _marked_edited(doc: HwpxDocument, pick: int) -> Any:
    doc.sections[pick % len(doc.sections)].mark_dirty()


def _edited_mark_cleared(doc: HwpxDocument, pick: int) -> Any:
    doc.sections[pick % len(doc.sections)].reset_dirty()


def _header_marked_edited(doc: HwpxDocument, pick: int) -> Any:
    doc.oxml.headers[pick % len(doc.oxml.headers)].mark_dirty()


def _judged_as_a_save_does(doc: HwpxDocument, pick: int) -> Any:
    return [section._remove_outlived_layout_caches() for section in doc.sections]


def _saved(doc: HwpxDocument, pick: int) -> Any:
    return _result(lambda: hashlib.sha256(doc.to_bytes()).hexdigest()), _try_bytes(doc)


def _try_bytes(doc: HwpxDocument) -> Any:
    try:
        return hashlib.sha256(doc.to_bytes()).hexdigest()
    except Exception as error:
        return type(error).__name__


def _reopened(doc: HwpxDocument, pick: int) -> Any:
    """Handled by the loop: both documents are saved, compared, and opened again as a new pair."""

    raise AssertionError("the loop reopens")


def _lines_read(doc: HwpxDocument, pick: int) -> Any:
    return _result_of(lambda: [len(place.paragraph.line_segments) for place in doc.text.iter_paragraphs()])


def _result_of(call: Any) -> Any:
    try:
        return call()
    except Exception as error:
        return type(error).__name__, str(error)


def _pages_estimated(doc: HwpxDocument, pick: int) -> Any:
    def estimate() -> Any:
        found = estimate_pages(doc)
        return found.pages, [len(lines) for lines in found.lines]

    return _result_of(estimate)


def _line_caches_written(doc: HwpxDocument, pick: int) -> Any:
    return _result_of(lambda: repr(write_line_caches(doc)))


def _validated(doc: HwpxDocument, pick: int) -> Any:
    def validate() -> Any:
        report = doc.validate()
        return report.ok, len(report.errors), len(report.warnings)

    return _result_of(validate)


def _cell_text_through_the_api(doc: HwpxDocument, pick: int) -> Any:
    table = _of(_tables(doc), pick)
    return _result(lambda: table.set_cell_text(0, 0, f"cell {pick}"))


def _paragraph_text_through_the_api(doc: HwpxDocument, pick: int) -> Any:
    paragraph = _of(doc.paragraphs[1:] or doc.paragraphs, pick)
    return _result(lambda: setattr(paragraph, "text", f"paragraph {pick}"))


def _paragraph_restyled(doc: HwpxDocument, pick: int) -> Any:
    paragraph = _of(doc.paragraphs, pick)
    return _result(lambda: setattr(paragraph, "style_id_ref", (pick // 3) % 3))


def _paragraph_model_applied(doc: HwpxDocument, pick: int) -> Any:
    paragraph = _of(doc.paragraphs, pick)
    return _result(lambda: paragraph.apply_model(paragraph.to_model()))


def _paragraph_text_regenerated(doc: HwpxDocument, pick: int) -> Any:
    paragraph = _of(doc.paragraphs[1:] or doc.paragraphs, pick)
    return _result(lambda: setattr(paragraph, "text", "새글")), _line_caches_written(doc, pick)


def _note_added(doc: HwpxDocument, pick: int) -> Any:
    return _result(lambda: doc.notes.add_footnote(f"note {pick}", paragraph=pick % max(1, len(doc.paragraphs))))


def _section_added(doc: HwpxDocument, pick: int) -> Any:
    if len(doc.sections) < 3:
        doc.add_section()


def _table_moved_or_copied(doc: HwpxDocument, pick: int) -> Any:
    table = _of(_tables(doc), pick)
    target = _of(doc.sections[(pick // 3) % len(doc.sections)].paragraphs, pick // 5)
    calls = [lambda: table.move_to(target), lambda: table.copy_to(target), lambda: table.copy_after()]
    return _result(calls[(pick // 7) % len(calls)])


def _paragraph_moved_or_copied(doc: HwpxDocument, pick: int) -> Any:
    paragraph = _of(doc.paragraphs[1:], pick)
    target = _of(doc.sections[(pick // 3) % len(doc.sections)].paragraphs, pick // 5)
    if paragraph is None:
        return None
    calls = [lambda: paragraph.move_after(target), lambda: paragraph.copy_to(target), lambda: paragraph.move_before(target)]
    return _result(calls[(pick // 7) % len(calls)])


def _structure_edit(doc: HwpxDocument, pick: int) -> Any:
    table = _of(_tables(doc), pick)
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


IN_THE_TREE = [
    _direct_text, _direct_long_text, _text_as_cdata, _direct_attribute, _attributes_reordered, _cache_rewritten,
    _qualified_name_changed,
    _cache_removed, _cache_taken_out, _cache_put_back, _cache_replaced_by_its_copy, _cache_given_a_tail,
    _second_cache_beside_the_first, _cache_copied_onto_another_paragraph, _cache_moved_before_its_runs,
    _comment_put_in, _body_paragraph_moved_to_the_end, _body_paragraph_copied_in, _body_paragraph_removed,
    _block_given_a_tail, _namespaces_tidied, _root_attribute_set, _section_settings_taken_out,
    _section_settings_written, _section_settings_moved_to_another_paragraph,
    _subtree_taken_in, _held_paragraph_given_another_holder,
]
THROUGH_THE_API = [
    _page_setting_through_the_api, _marked_edited, _edited_mark_cleared, _header_marked_edited,
    _judged_as_a_save_does, _saved, _reopened, _lines_read, _pages_estimated, _line_caches_written, _validated,
    _cell_text_through_the_api, _paragraph_text_through_the_api, _paragraph_restyled, _paragraph_model_applied,
    _paragraph_text_regenerated, _note_added, _section_added, _table_moved_or_copied, _paragraph_moved_or_copied,
]
#: a step in the tree, a structure edit, a call that shows what the edit left -- in that mix
STEPS = IN_THE_TREE * 2 + THROUGH_THE_API + [_structure_edit] * 22
DOCUMENTS = [
    "hancom_saved/formfit_glyph_cells.hwpx",
    "hancom_saved/line_cache_table_cells.hwpx",
    "hancom_saved/merge_3x3_a1c2.hwpx",
    "hancom_saved/pages_cell_top_bottom_table_among_mixed_sizes.hwpx",  # tables in cells
    "hancom_saved/pages_table_cell_tables_as_characters_among_text_split.hwpx",  # two tables in one block's cells
    "hancom_saved/pages_footnotes_in_table_cells.hwpx",
    "hancom_saved/pages_table_cell_holding_a_header_with_a_table.hwpx",
    "hancom_saved/pages_repeated_header_holding_a_table_without_room.hwpx",
    "hancom_saved/pages_ellipsis_starts_a_cell_line.hwpx",  # two sections
    "hwpxlib_corpus/error__20240626__no_manifest.hwpx",  # two sections
    "exam/A_form.hwpx",  # tables in the header and the footer
]


def _stepped(step: Any, doc: HwpxDocument, pick: int) -> Any:
    try:
        return step(doc, pick)
    except Exception as error:  # a step the document refuses: the same way in both, or the test says
        return "raised", type(error).__name__, str(error)


def run_steps(data: bytes, rng: random.Random, count: int) -> int:
    """*count* random steps on a pair made from *data*, compared after each. Returns how many ran."""

    now, then = _pair(data)
    assert _state(now, False) == _state(then, True)
    for done in range(count):
        step, pick = rng.choice(STEPS), rng.randrange(10_000)
        if step is _reopened:
            saved = _try_bytes(now), _try_bytes(then)
            assert saved[0] == saved[1], (done, "saved before reopening")
            if len(saved[0]) != 64:  # the save was refused, the same way: go on with the documents as they are
                continue
            data = now.to_bytes()
            assert data == then.to_bytes()
            now, then = _pair(data)
        else:
            results = (_stepped(step, now, pick), _stepped(step, then, pick))
            assert results[0] == results[1], (done, step.__name__, pick)
        assert _state(now, False) == _state(then, True), (done, step.__name__, pick)
    assert _try_bytes(now) == _try_bytes(then)
    return count


@pytest.mark.parametrize("name", DOCUMENTS)
def test_every_step_leaves_what_the_7_0_0_judgement_leaves(name: str) -> None:
    data = (FIXTURES / name).read_bytes()
    steps = sum(run_steps(data, random.Random(f"{name}/{seed}"), 16) for seed in range(5))
    assert steps == 80


@pytest.mark.parametrize("name", DOCUMENTS[:4])
@pytest.mark.parametrize("form", [_paragraphs_in_the_default_namespace, _body_paragraphs_declaring_their_prefix_again])
def test_every_step_leaves_it_in_other_namespace_forms_of_the_document_too(name: str, form: Any) -> None:
    data = form((FIXTURES / name).read_bytes())
    assert len(HwpxDocument.open(data).paragraphs) == len(HwpxDocument.open(FIXTURES / name).paragraphs)
    steps = sum(run_steps(data, random.Random(f"{form.__name__}/{name}/{seed}"), 16) for seed in range(3))
    assert steps == 48


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
    return _try_bytes(doc)  # the package's hash, or the refusal's name


def _edit_table(index: int, call: Any = lambda table: table.insert_rows(0)) -> Any:
    return lambda doc: _result(lambda: call(_tables(doc)[index]))


def _cached_cell_paragraphs(doc: HwpxDocument) -> list[Any]:
    return [
        paragraph
        for table in _tables(doc)
        for paragraph in table.element.iter(f"{HP}p")
        if paragraph.find(f"{HP}linesegarray") is not None and (paragraph.findtext(f"{HP}run/{HP}t") or "")
    ]


def _cached_body_paragraphs(doc: HwpxDocument) -> list[Any]:
    return [
        paragraph
        for paragraph in doc.sections[0].element.findall(f"{HP}p")
        if paragraph.find(f"{HP}linesegarray") is not None
        and (paragraph.findtext(f"{HP}run/{HP}t") or "")
        and next(paragraph.iter(f"{HP}tbl"), None) is None
    ]


def _caches_in(state: Any) -> int:
    return sum(len(_reference_cache_elements(etree.fromstring(part[0]))) for part in state[:-1])


def _watched_count(state: Any) -> int:
    return sum(part[2][0] for part in state[:-1])


@pytest.mark.parametrize("beside", ["before", "after"])
@pytest.mark.parametrize("between", ["nothing", "comment", "text"])
@pytest.mark.parametrize("where", ["body", "cell"])
def test_two_caches_in_one_paragraph_go_as_two_looks_at_the_section_take_them(
    beside: str, between: str, where: str
) -> None:
    # A copy of a paragraph's cache beside the cache, with or without something between them, and the
    # paragraph's text changed: what goes at the judgement before the rebuild (of another table), and
    # what at the one after, is the order two looks at every cache give.
    def prepare(doc: HwpxDocument) -> Any:
        paragraph = (_cached_body_paragraphs(doc) if where == "body" else _cached_cell_paragraphs(doc)[2:])[0]
        read = paragraph.find(f"{HP}linesegarray")
        copy = deepcopy(read)
        copy.tail = None
        paragraph.insert(paragraph.index(read) + (beside == "after"), copy)
        first = paragraph.findall(f"{HP}linesegarray")[0]
        if between == "comment":
            first.addnext(etree.Comment(" between "))
        elif between == "text":
            first.tail = "\n"
        read.tail = "\n" if between == "text" else read.tail
        node = paragraph.find(f"{HP}run/{HP}t")
        node.text = "long text " * 40
        return len(paragraph.findall(f"{HP}linesegarray"))

    name = "hancom_saved/pages_table_cell_tables_as_characters_among_text_split.hwpx"
    last = len(_tables(HwpxDocument.open(FIXTURES / name))) - 1
    for edit in (_edit_table(last), _edit_table(0), _edit_table(last, lambda table: table.insert_rows(10_000))):
        states = _both_ways(name, prepare, edit, _judge, _save)
        assert _caches_in(states[2]) < _caches_in(states[1])


@pytest.mark.parametrize("settings", ["taken out", "taken out and written", "moved", "written in the tree"])
@pytest.mark.parametrize("marked", [False, True])
def test_section_settings_out_of_or_into_the_tree_are_judged_as_two_looks_at_the_section_judge_them(
    settings: str, marked: bool
) -> None:
    def prepare(doc: HwpxDocument) -> Any:
        section = doc.sections[0]
        cache = section.element.find(f"{HP}p/{HP}linesegarray")
        if cache is not None and len(cache):
            cache[0].set("horzsize", "901")  # the first paragraph's stays through the first judgement
        if settings.startswith("taken out"):
            _section_settings_taken_out(doc, 0)
        if settings.endswith("written") or settings == "written in the tree":
            _section_settings_written(doc, 0)
        if settings == "moved":
            _section_settings_moved_to_another_paragraph(doc, 5)
        if marked:
            section.mark_dirty()
        return section.properties.element.getparent() is not None

    for name in ("hancom_saved/formfit_glyph_cells.hwpx", "hancom_saved/line_cache_table_cells.hwpx"):
        _both_ways(
            name, prepare, _edit_table(0), lambda doc: _lines_read(doc, 0), _judge,
            _edit_table(0, lambda table: table.insert_rows(10_000)), lambda doc: _pages_estimated(doc, 0), _save,
        )


def test_an_unprefixed_cache_taken_out_of_its_namespace_is_a_cache_written_again() -> None:
    # Under a default namespace the block serialises to the very bytes it had; the cache itself, as the
    # element serialised for the comparison, does not. So it stays when its paragraph changes with it --
    # and goes when the paragraph changes after, once it has been watched in its new form.
    data = _paragraphs_in_the_default_namespace((FIXTURES / "hancom_saved" / "line_cache_table_cells.hwpx").read_bytes())
    picked: dict[int, Any] = {}

    def out_of_its_namespace(doc: HwpxDocument) -> Any:
        paragraph = _cached_body_paragraphs(doc)[0]
        cache = paragraph.find(f"{HP}linesegarray")
        before = etree.tostring(doc.sections[0].element)
        cache.tag = "linesegarray"
        assert etree.tostring(doc.sections[0].element) == before
        picked[id(doc)] = (paragraph, cache)
        return None

    def change(doc: HwpxDocument) -> Any:
        node = picked[id(doc)][0].find(f"{HP}run/{HP}t")
        node.text = "X" + node.text
        return None

    def cached(doc: HwpxDocument) -> bool:
        return picked[id(doc)][1].getparent() is not None

    now, then = _pair(data)
    for step in (_judge, out_of_its_namespace, change, _edit_table(0), cached, change, _judge, cached, _save):
        assert step(now) == step(then), step
        assert _state(now, False) == _state(then, True), step
    doc = HwpxDocument.open(data)
    _judge(doc)
    out_of_its_namespace(doc)
    change(doc)
    _edit_table(0)(doc)
    assert cached(doc)
    change(doc)
    _judge(doc)
    assert not cached(doc)


def test_a_block_put_back_without_the_declaration_it_repeated_holds_caches_written_again() -> None:
    # Each paragraph declares the prefix the root declares too. A body paragraph taken out of the tree
    # and put back where it was loses that repeated declaration (lxml drops it): the block serialises to
    # the very bytes it had, but what a cache or a paragraph inside serialises to by itself now lists the
    # inherited declarations in the root's order. So every cache in it counts as written again (it
    # stays, watched in its new form) -- and one whose paragraph changes after that goes.
    data = _body_paragraphs_declaring_their_prefix_again((FIXTURES / "hancom_saved" / "line_cache_table_cells.hwpx").read_bytes())
    picked: dict[int, Any] = {}

    def tidy(doc: HwpxDocument) -> Any:
        root = doc.sections[0].element
        paragraph = _cached_cell_paragraphs(doc)[1]
        block = next(ancestor for ancestor in paragraph.iterancestors() if ancestor.getparent() is root)
        before, scope = etree.tostring(block), list(block.nsmap)
        root.insert(root.index(block), block)
        assert etree.tostring(block) == before and list(block.nsmap) != scope
        picked[id(doc)] = paragraph
        return None

    def change(doc: HwpxDocument) -> Any:
        node = picked[id(doc)].find(f"{HP}run/{HP}t")
        node.text = "X" + node.text
        return None

    def cached(doc: HwpxDocument) -> bool:
        return picked[id(doc)].find(f"{HP}linesegarray") is not None

    now, then = _pair(data)
    for step in (_judge, tidy, change, _judge, cached, change, _edit_table(0, lambda table: table.insert_rows(10_000)), cached, _save):
        assert step(now) == step(then), step
        assert _state(now, False) == _state(then, True), step
    doc = HwpxDocument.open(data)
    _judge(doc)
    tidy(doc)
    change(doc)
    _judge(doc)
    assert cached(doc)  # its text changed, but so did the cache as the judgement reads it
    change(doc)
    _judge(doc)
    assert not cached(doc)


def test_a_paragraph_whose_holder_is_bound_to_a_hidden_declaration_is_content_changed() -> None:
    # A paragraph with a cache sits in a holder, under an element that gives the document's prefix to
    # another namespace. Then the holder is swapped for one bound to the document's own namespace
    # through the declaration that element hides: the body paragraph serialises to the very bytes it
    # had, but the paragraph inside, serialised by itself for its digest, is now written with the
    # document's namespace. Its content changed under its cache, as a look at every cache finds.
    held: dict[int, Any] = {}

    def take_in(doc: HwpxDocument) -> Any:
        block = _cached_body_paragraphs(doc)[0]
        block.append(_taken_in(block, _HELD_PLAINLY))
        held[id(doc)] = (block, block[-1][0][0][0])
        return etree.QName(block[-1][0][0]).namespace

    def another_holder(doc: HwpxDocument) -> Any:
        block, paragraph = held[id(doc)]
        first, before = block[-1], etree.tostring(block)
        first.addnext(_taken_in(block, "<z:a/>"))
        block[-1][0][0].append(paragraph)
        block.remove(first)
        assert etree.tostring(block) == before
        return etree.QName(block[-1][0][0]).namespace == etree.QName(block).namespace

    def cached(doc: HwpxDocument) -> int:
        return len(held[id(doc)][1])

    data = (FIXTURES / "hancom_saved" / "line_cache_table_cells.hwpx").read_bytes()
    now, then = _pair(data)
    for step in (_judge, take_in, _judge, _judge, cached, another_holder, _edit_table(0), cached, _judge, _save):
        assert step(now) == step(then), step
        assert _state(now, False) == _state(then, True), step
    doc = HwpxDocument.open(data)
    assert take_in(doc) == "urn:other"
    doc.tables[0].insert_rows(0)
    assert cached(doc) == 1
    assert another_holder(doc)
    doc.tables[0].insert_rows(0)
    assert cached(doc) == 0


def test_a_table_in_a_header_takes_the_cache_of_the_body_paragraph_holding_the_header() -> None:
    # No editing API clears that one: the body paragraph holds the header, the header a paragraph, and
    # that one the table. Its content changed with the table, so the judgement after the rebuild drops
    # its cache.
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

    for call in (lambda table: table.insert_columns(0), lambda table: table.insert_rows(10_000)):
        states = _both_ways("hancom_saved/line_cache_table_cells.hwpx", rewrite, _edit_table(0, call), _judge, _save)
        assert b'horzsize="31415"' in states[-1][0][0]  # written on purpose: not what the part was read with


def test_a_cache_dropped_just_before_the_rebuild_still_costs_the_paragraph_around_it_its_own() -> None:
    # A judgement meets caches in document order. Here a paragraph holding a table in a cell keeps its
    # cache ahead of its runs, so it is judged (and kept: the cache was rewritten) before a cache inside
    # that table goes -- and the text after that cache goes with it, so the holding paragraph no longer
    # has the content it was just watched with. The judgement after the rebuild of *another* table of
    # the block drops its cache, though that paragraph neither is in the rebuilt table nor holds it.
    name = "hancom_saved/pages_table_cell_tables_as_characters_among_text_split.hwpx"
    picked: dict[int, tuple[Any, Any, int]] = {}

    def rewrite(cache: Any) -> None:
        cache[0].set("horzsize", str(int(cache[0].get("horzsize", "0")) + 1))

    def candidates(doc: HwpxDocument) -> Any:
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
                if holder.find(f"{HP}linesegarray") is not None and cached and others:
                    yield block, holder, cached[0], others[0]

    def prepare(doc: HwpxDocument) -> Any:
        block, holder, inner_paragraph, other = next(candidates(doc))
        holder.insert(0, holder.find(f"{HP}linesegarray"))
        inner_paragraph.find(f"{HP}linesegarray").tail = "text after the cache"
        for cache in block.iter(f"{HP}linesegarray"):  # written on purpose: each stays, with this content
            rewrite(cache)
        tables = [table.element for table in _tables(doc)]
        picked[id(doc)] = (holder, inner_paragraph, tables.index(other))
        return tables.index(other)

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
