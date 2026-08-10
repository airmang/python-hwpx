# SPDX-License-Identifier: Apache-2.0
"""Drop cap authoring (문단 첫 글자 장식, cycle 6.12 트레인㊸ 갭②).

Reverse-engineered from the ONE real-corpus example with a non-default
``dropcapstyle`` (``error__20230809__test.hwpx``, hwpxlib_corpus). v1
supports only ``style="TripleLine"`` -- the only value with structural
ground truth; ``DoubleLine``/``Margin`` are schema-declared but
structurally unverified and stay typed-rejected rather than guessed at.
See ``hwpx.oxml.drop_cap``'s own docstring for the full reverse
engineering.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
REAL_SAMPLE = CORPUS / "error__20230809__test.hwpx"
_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_HC = "{http://www.hancom.co.kr/hwpml/2011/core}"


def _find_drop_cap_rect(section_element) -> "etree._Element | None":
    for node in section_element.iter(f"{_HP}rect"):
        if node.get("dropcapstyle"):
            return node
    return None


def test_add_drop_cap_creates_a_rect_with_the_requested_style() -> None:
    document = HwpxDocument.new()

    result = document.shapes.add_drop_cap("붐", width=4200, height=4200)

    assert result.element.tag == f"{_HP}rect"
    assert result.element.get("dropcapstyle") == "TripleLine"
    assert result.element.get("lock") == "1"
    assert result.element.get("textFlow") == "RIGHT_ONLY"


def test_add_drop_cap_embeds_the_character_in_a_nested_paragraph() -> None:
    document = HwpxDocument.new()

    result = document.shapes.add_drop_cap("붐", width=4200, height=4200)

    text_nodes = [node for node in result.element.iter(f"{_HP}t") if node.text]
    assert text_nodes
    assert text_nodes[0].text == "붐"
    # the character does NOT live in the paragraph's own top-level run --
    # it's nested inside drawText/subList/p/run/t (see module docstring).
    draw_text = result.element.find(f"{_HP}drawText")
    assert draw_text is not None
    sub_list = draw_text.find(f"{_HP}subList")
    assert sub_list is not None
    assert sub_list.find(f"{_HP}p") is not None


def test_add_drop_cap_round_trips_through_save_and_reopen() -> None:
    document = HwpxDocument.new()
    document.shapes.add_drop_cap("붐", width=4200, height=4200)

    data = document.to_bytes()
    reopened = HwpxDocument.open(data)

    rect = _find_drop_cap_rect(reopened.sections[0].element)
    assert rect is not None
    assert rect.get("dropcapstyle") == "TripleLine"
    text_nodes = [node for node in rect.iter(f"{_HP}t") if node.text]
    assert text_nodes[0].text == "붐"


def test_add_drop_cap_rejects_unmeasured_styles() -> None:
    document = HwpxDocument.new()

    for style in ("DoubleLine", "Margin"):
        with pytest.raises(HwpxValueError) as excinfo:
            document.shapes.add_drop_cap("붐", width=4200, height=4200, style=style)
        assert excinfo.value.code == "shape-drop-cap-style-unsupported"
        assert excinfo.value.context.get("style") == style


def test_add_drop_cap_rejects_empty_character() -> None:
    document = HwpxDocument.new()

    with pytest.raises(HwpxValueError) as excinfo:
        document.shapes.add_drop_cap("", width=4200, height=4200)
    assert excinfo.value.code == "shape-drop-cap-character-empty"


def test_add_drop_cap_matches_the_real_corpus_structure() -> None:
    """Structural fidelity check against the one real sample this feature
    was reverse-engineered from -- same attribute *names* on the rect and
    the same child element shape (not exact values, which are naturally
    instance-specific: ids, the character itself, size)."""

    if not REAL_SAMPLE.exists():
        pytest.skip(f"{REAL_SAMPLE.name} not present in this checkout")

    with zipfile.ZipFile(REAL_SAMPLE) as archive:
        real_section = etree.fromstring(archive.read("Contents/section0.xml"))
    real_rect = _find_drop_cap_rect(real_section)
    assert real_rect is not None

    document = HwpxDocument.new()
    result = document.shapes.add_drop_cap("붐", width=4200, height=4200)

    # same attribute keys on the rect itself (values legitimately differ:
    # id/instid are freshly minted).
    comparable_keys = set(real_rect.attrib) - {"id", "instid"}
    assert comparable_keys <= set(result.element.attrib)
    for key in comparable_keys:
        assert result.element.get(key) == real_rect.get(key), key

    # same immediate child tag sequence.
    real_children = [etree.QName(c).localname for c in real_rect]
    ours_children = [etree.QName(c).localname for c in result.element]
    assert real_children == ours_children


def test_real_corpus_drop_cap_sample_still_parses_and_round_trips() -> None:
    """Sanity check on the source-of-truth fixture itself -- this codebase's
    own parser must still open the one real drop cap sample without error
    (regression guard: if a future change ever broke parsing of this shape,
    this test fails independently of the authoring path above)."""

    if not REAL_SAMPLE.exists():
        pytest.skip(f"{REAL_SAMPLE.name} not present in this checkout")

    document = HwpxDocument.open(str(REAL_SAMPLE))
    try:
        rect = _find_drop_cap_rect(document.sections[0].element)
        assert rect is not None
        assert rect.get("dropcapstyle") == "TripleLine"
    finally:
        document.close()
