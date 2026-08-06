# SPDX-License-Identifier: Apache-2.0
"""``paragraph.add_run(text, expand_special_characters=True)`` — 특수 인라인
텍스트 원자 저작 (사이클 6.5 트레인 19).

``hp:lineBreak``/``hp:nbSpace``/``hp:fwSpace``는 읽기(추출)는 되지만 저작
API가 없었다 — 저작된 텍스트에 사용자가 줄바꿈·비분리공백·전각공백을
요청해도 평문 문자로만 방출돼(``hp:t`` 텍스트 노드 안 리터럴) 실한컴이
실제로 쓰는 요소 형태와 달랐다. 실코퍼스 3파일
(``error__20230818__test.hwpx``/``error__20251107__test.hwpx``/
``error__20250808__...hwpx``) 리버스: 세 원자 전부 **단일 hp:t 안의
mixed content**로 산다(``hp:tab``이 ``_append_text_with_tabs``로 이미
저작하는 "hp:run 형제" 형태와는 다르다 — 스키마는 둘 다 허용하지만 실
산출물은 이 세 원자에 대해 전자만 쓴다).
"""

from __future__ import annotations

from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.oxml.objects import _missing_shape_children  # noqa: F401  (sanity import)
from hwpx.tools.text_extractor import TextExtractor

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _local(tag: str) -> str:
    return tag.split("}")[-1]


# ============================================================================
# 게이트 ① 생성물 구조 — 단일 hp:t mixed content
# ============================================================================


def test_line_break_is_nested_inside_a_single_t_element() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    run = paragraph.add_run("before\nafter", expand_special_characters=True)

    t_elements = [c for c in run.element if _local(c.tag) == "t"]
    assert len(t_elements) == 1
    t = t_elements[0]
    assert t.text == "before"
    marker = next(c for c in t if _local(c.tag) == "lineBreak")
    assert marker.tail == "after"


def test_nb_space_is_nested_inside_a_single_t_element() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    run = paragraph.add_run("a b", expand_special_characters=True)

    t_elements = [c for c in run.element if _local(c.tag) == "t"]
    assert len(t_elements) == 1
    t = t_elements[0]
    assert t.text == "a"
    marker = next(c for c in t if _local(c.tag) == "nbSpace")
    assert marker.tail == "b"


def test_fw_space_is_nested_inside_a_single_t_element() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    run = paragraph.add_run("a　b", expand_special_characters=True)

    t_elements = [c for c in run.element if _local(c.tag) == "t"]
    assert len(t_elements) == 1
    t = t_elements[0]
    assert t.text == "a"
    marker = next(c for c in t if _local(c.tag) == "fwSpace")
    assert marker.tail == "b"


def test_all_three_atoms_together_preserve_order_in_one_t() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    run = paragraph.add_run(
        "a\nb c　d", expand_special_characters=True,
    )
    t_elements = [c for c in run.element if _local(c.tag) == "t"]
    assert len(t_elements) == 1
    t = t_elements[0]
    child_names = [_local(c.tag) for c in t]
    assert child_names == ["lineBreak", "nbSpace", "fwSpace"]
    assert t.text == "a"
    assert [c.tail for c in t] == ["b", "c", "d"]


def test_default_behaviour_is_unchanged_without_the_flag() -> None:
    """expand_special_characters 기본값 False — 기존 호출자는 영향 없다
    (문자가 hp:t 텍스트 노드 안에 리터럴로 그대로 남는다)."""

    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    run = paragraph.add_run("before\nafter")

    t_elements = [c for c in run.element if _local(c.tag) == "t"]
    assert len(t_elements) == 1
    assert t_elements[0].text == "before\nafter"
    assert len(list(t_elements[0])) == 0


def test_plain_text_without_markers_is_unaffected() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    run = paragraph.add_run("plain text", expand_special_characters=True)
    t_elements = [c for c in run.element if _local(c.tag) == "t"]
    assert len(t_elements) == 1
    assert t_elements[0].text == "plain text"
    assert len(list(t_elements[0])) == 0


# ============================================================================
# 게이트 ② 왕복 무손상 — save/reopen 후 TextExtractor로 원문 복원
# ============================================================================


def test_authored_atoms_round_trip_through_save_and_reopen(tmp_path: Path) -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    paragraph.add_run(
        "line1\nline2 nbsp　fwsp", expand_special_characters=True,
    )
    path = tmp_path / "atoms.hwpx"
    doc.save_to_path(path)
    doc.close()

    with TextExtractor(path) as extractor:
        texts = [info.text() for info in extractor.iter_document_paragraphs()]
    matches = [t for t in texts if t and "line1" in t]
    assert len(matches) == 1
    assert matches[0] == "line1\nline2 nbsp　fwsp"


def test_authored_atoms_pass_open_safety(tmp_path: Path) -> None:
    from hwpx.tools.package_validator import validate_editor_open_safety

    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    paragraph.add_run(
        "line1\nline2 nbsp　fwsp", expand_special_characters=True,
    )
    path = tmp_path / "safe.hwpx"
    doc.save_to_path(path)
    doc.close()

    report = validate_editor_open_safety(path).to_dict()
    assert report["ok"] is True


# ============================================================================
# 게이트 ③ hp:tab과의 구조 차이 — 원자는 hp:t 중첩, tab은 hp:run 형제
# ============================================================================


def test_run_choice_atoms_differ_structurally_from_tab() -> None:
    """paragraph.text 세터는 hp:tab을 _append_text_with_tabs로 저작한다
    (기존 동작, 이번 트레인은 안 건드림) — hp:run 형제인 별도 hp:t로
    갈라진다. add_run(expand_special_characters=True)의 세 원자는 그와
    달리 **하나의** hp:t 안에 중첩된다 — 실코퍼스가 보여주는 실제 차이를
    구조적으로 고정."""

    doc = HwpxDocument.new()
    tab_paragraph = doc.add_paragraph("left\tright")
    tab_run = tab_paragraph._run_elements()[0]
    tab_children = [_local(c.tag) for c in tab_run]
    assert tab_children.count("t") == 2
    assert "tab" in tab_children

    atom_paragraph = doc.add_paragraph("")
    atom_run = atom_paragraph.add_run("left\nright", expand_special_characters=True)
    atom_children = [_local(c.tag) for c in atom_run.element]
    assert atom_children.count("t") == 1
    assert "lineBreak" not in atom_children  # nested inside the single t, not a sibling
