# SPDX-License-Identifier: Apache-2.0
"""덧말(hp:dutmal)·글자 겹치기(hp:compose) 저작 (cycle 6.9 train 34).

``hp:compose``'s read model shipped earlier (commit 6f88e2e); this covers
the authoring side plus the newly-reverse-engineered ``hp:dutmal`` (both
read and write -- see docs/owpml-deviations.md DEV-041 for the schema
mismatch its only real-corpus sample exposed).
"""

from __future__ import annotations

from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.oxml.body import ComposedCharacter, ComposedCharacterSlot, Dutmal
from hwpx.tools.id_integrity import check_id_integrity

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "hwpxlib_corpus"
    / "reader_writer__SimpleDutmal.hwpx"
)


def _run_content(paragraph):
    return [content for run in paragraph.to_model().runs for content in run.content]


# ============================================================================
# real-corpus read model (locks the reverse-engineering in as a regression)
# ============================================================================


def test_real_corpus_dutmal_parses_with_the_observed_schema_deviations() -> None:
    doc = HwpxDocument.open(FIXTURE)
    p0 = doc.sections[0].paragraphs[0]
    dutmal = next(c for c in _run_content(p0) if isinstance(c, Dutmal))

    assert dutmal.pos_type == "TOP"
    assert dutmal.align == "CENTER"
    assert dutmal.main_text == "테스트_본말"
    assert dutmal.sub_text == "테스트_닷말"
    # DEV-041: schema says option is fixed="4" and szRatio is
    # xs:positiveInteger (>= 1) -- real Hancom output contradicts both.
    assert dutmal.option == 0
    assert dutmal.sz_ratio == 0


def test_real_corpus_dutmal_is_a_direct_run_child_sibling_of_text() -> None:
    """Locks in the position discovery: hp:dutmal is not nested inside
    hp:t -- it is a sibling, hp:run's direct child, matching hp:compose's
    own already-documented position convention."""

    doc = HwpxDocument.open(FIXTURE)
    p0 = doc.sections[0].paragraphs[0]
    run = p0.element.find(f"{_HP}run")
    child_names = [c.tag.rsplit("}", 1)[-1] for c in run]
    assert "dutmal" in child_names
    assert "t" in child_names


def test_real_corpus_dutmal_round_trips_byte_identical_through_save_reopen() -> None:
    doc = HwpxDocument.open(FIXTURE)
    data = doc.to_bytes()
    reopened = HwpxDocument.open(data)

    def _dutmal_attrs(document):
        p0 = document.sections[0].paragraphs[0]
        for run in p0.element.findall(f"{_HP}run"):
            el = run.find(f"{_HP}dutmal")
            if el is not None:
                return dict(el.attrib), [(c.tag.rsplit("}", 1)[-1], c.text) for c in el]
        raise AssertionError("no hp:dutmal found after reopen")

    assert _dutmal_attrs(doc) == _dutmal_attrs(reopened)


# ============================================================================
# authoring -- add_dutmal
# ============================================================================


def test_add_dutmal_defaults_match_the_only_real_sample() -> None:
    doc = HwpxDocument.new()
    p = doc.add_paragraph("본문")
    obj = doc.shapes.add_dutmal("본말", "덧말", paragraph=p)

    assert obj.element.tag == f"{_HP}dutmal"
    # DEV-041: defaults are the real sample's own observed values (0/0),
    # not the schema's stated fixed=4 / positiveInteger.
    assert obj.get_attribute("option") == "0"
    assert obj.get_attribute("szRatio") == "0"
    assert obj.get_attribute("posType") == "TOP"
    assert obj.get_attribute("align") == "CENTER"


def test_add_dutmal_round_trips_through_the_read_model() -> None:
    doc = HwpxDocument.new()
    p = doc.add_paragraph("본문")
    doc.shapes.add_dutmal("메인", "서브", paragraph=p, pos_type="BOTTOM", align="LEFT")

    data = doc.to_bytes()
    reopened = HwpxDocument.open(data)
    target_p = reopened.sections[0].paragraphs[
        [pp.text for pp in reopened.sections[0].paragraphs].index("본문")
    ]
    dutmal = next(c for c in _run_content(target_p) if isinstance(c, Dutmal))
    assert dutmal.main_text == "메인"
    assert dutmal.sub_text == "서브"
    assert dutmal.pos_type == "BOTTOM"
    assert dutmal.align == "LEFT"


def test_add_dutmal_without_a_paragraph_creates_its_own() -> None:
    doc = HwpxDocument.new()
    before = len(doc.sections[0].paragraphs)
    doc.shapes.add_dutmal("본말", "덧말")
    assert len(doc.sections[0].paragraphs) == before + 1


def test_add_dutmal_is_a_run_direct_child_sibling_of_text_like_real_output() -> None:
    doc = HwpxDocument.new()
    p = doc.add_paragraph("옆에 텍스트")
    doc.shapes.add_dutmal("본말", "덧말", paragraph=p)

    run_tags = []
    for run in p.element.findall(f"{_HP}run"):
        run_tags.extend(c.tag.rsplit("}", 1)[-1] for c in run)
    assert "dutmal" in run_tags
    assert "t" in run_tags


# ============================================================================
# authoring -- add_composed_character
# ============================================================================


def test_add_composed_character_round_trips_through_the_read_model() -> None:
    doc = HwpxDocument.new()
    p = doc.add_paragraph("본문")
    cid = doc.styles.ensure_run(bold=True)
    doc.shapes.add_composed_character(
        "합", [cid], paragraph=p, circle_type="SHAPE_CIRCLE", compose_type="OVERLAP",
    )

    data = doc.to_bytes()
    reopened = HwpxDocument.open(data)
    target_p = reopened.sections[0].paragraphs[
        [pp.text for pp in reopened.sections[0].paragraphs].index("본문")
    ]
    composed = next(c for c in _run_content(target_p) if isinstance(c, ComposedCharacter))
    assert composed.compose_text == "합"
    assert composed.circle_type == "SHAPE_CIRCLE"
    assert composed.compose_type == "OVERLAP"
    assert composed.slots == [ComposedCharacterSlot(pr_id_ref=int(cid))]


def test_add_composed_character_without_slots_omits_char_pr_cnt() -> None:
    doc = HwpxDocument.new()
    p = doc.add_paragraph("본문")
    obj = doc.shapes.add_composed_character("합", paragraph=p)
    assert obj.get_attribute("charPrCnt") is None


def test_add_composed_character_without_a_paragraph_creates_its_own() -> None:
    doc = HwpxDocument.new()
    before = len(doc.sections[0].paragraphs)
    doc.shapes.add_composed_character("합")
    assert len(doc.sections[0].paragraphs) == before + 1


# ============================================================================
# structural/referential integrity after authoring both together
# ============================================================================


def test_authoring_both_together_keeps_the_document_referentially_sound() -> None:
    doc = HwpxDocument.new()
    p = doc.add_paragraph("본문")
    doc.shapes.add_dutmal("본말", "덧말", paragraph=p, style_id_ref=0)
    doc.shapes.add_composed_character("합", ["0"], paragraph=p)

    report = check_id_integrity(doc)
    assert report.ok, report.dangling

    data = doc.to_bytes()
    reopened = HwpxDocument.open(data)
    report_after = check_id_integrity(reopened)
    assert report_after.ok, report_after.dangling


# ============================================================================
# capability registration -- these authoring methods must not become phantom
# entries in the registry (see capabilities.py's dutmal-compose comment)
# ============================================================================


def test_capability_area_is_doc_shapes_only_with_no_root_shim() -> None:
    """dutmal-compose is a post-6.0 capability, same as add_polygon/add_arc/
    add_container -- doc.shapes-only, deliberately no root _legacy shim."""

    doc = HwpxDocument.new()
    assert hasattr(doc.shapes, "add_dutmal")
    assert hasattr(doc.shapes, "add_composed_character")
    assert not hasattr(doc, "add_dutmal")
    assert not hasattr(doc, "add_composed_character")
