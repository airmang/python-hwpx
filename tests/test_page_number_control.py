# SPDX-License-Identifier: Apache-2.0
"""``doc.page.restart_page_number``/``hide_page_elements`` — 쪽번호 제어 심부.

실코퍼스(hwpxlib_corpus, newNum 13+파일·pageHiding 3파일 — reader_writer__
PageFunctions.hwpx가 이 두 기능을 나란히 담은 목적 fixture)와 OWPML 스키마
(ParaList XML schema.xml:132-163, 2741-2759) 리버스: ``hp:newNum``/
``hp:pageHiding``은 둘 다 ``hp:ctrl``의 독립 자식으로, 문단 run 안에 산다.
``hp:newNum``은 스키마가 ``autoNumFormat`` 자식을 필수로 선언하지만 실코퍼스
전량이 self-close(``num``/``numType``만) — 스키마보다 실측을 따른다.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError

REPO = Path(__file__).resolve().parent.parent
REAL_CORPUS_FILE = (
    REPO / "tests" / "fixtures" / "hwpxlib_corpus" / "reader_writer__PageFunctions.hwpx"
)


def _controls(paragraph) -> list[tuple[str, dict]]:
    found: list[tuple[str, dict]] = []
    for run in paragraph.runs:
        model = run.to_model()
        for ctrl in model.controls:
            for child in ctrl.children:
                found.append((child.name, dict(child.attributes)))
    return found


def _section_xml(path) -> str:
    with zipfile.ZipFile(path) as archive:
        return "".join(
            archive.read(name).decode("utf-8")
            for name in sorted(archive.namelist())
            if "section" in name and name.endswith(".xml")
        )


# --------------------------------------------------------------------------
# 저작 — restart_page_number


def test_restart_page_number_emits_the_measured_hancom_shape() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    doc.page.restart_page_number(paragraph)

    controls = _controls(paragraph)
    assert ("newNum", {"num": "1", "numType": "PAGE"}) in controls


def test_restart_page_number_with_explicit_number_and_kind() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    doc.page.restart_page_number(paragraph, number=23, kind="page")

    controls = _controls(paragraph)
    assert ("newNum", {"num": "23", "numType": "PAGE"}) in controls


def test_restart_page_number_accepts_paragraph_index_or_object() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    doc.page.restart_page_number(1, number=5)
    doc.page.restart_page_number(doc.paragraphs[1], number=6)
    controls = _controls(doc.paragraphs[1])
    assert ("newNum", {"num": "5", "numType": "PAGE"}) in controls
    assert ("newNum", {"num": "6", "numType": "PAGE"}) in controls


# --------------------------------------------------------------------------
# 저작 — hide_page_elements


def test_hide_page_elements_emits_the_measured_hancom_shape() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    doc.page.hide_page_elements(paragraph, header=True, master_page=True)

    controls = _controls(paragraph)
    assert (
        "pageHiding",
        {
            "hideHeader": "1",
            "hideFooter": "0",
            "hideMasterPage": "1",
            "hideBorder": "0",
            "hideFill": "0",
            "hidePageNum": "0",
        },
    ) in controls


def test_hide_page_elements_default_is_unhidden() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    doc.page.hide_page_elements(paragraph)

    controls = _controls(paragraph)
    assert (
        "pageHiding",
        {
            "hideHeader": "0",
            "hideFooter": "0",
            "hideMasterPage": "0",
            "hideBorder": "0",
            "hideFill": "0",
            "hidePageNum": "0",
        },
    ) in controls


def test_hide_page_elements_all_six_flags() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    doc.page.hide_page_elements(
        paragraph, header=True, footer=True, master_page=True,
        border=True, fill=True, page_num=True,
    )
    controls = _controls(paragraph)
    assert (
        "pageHiding",
        {
            "hideHeader": "1", "hideFooter": "1", "hideMasterPage": "1",
            "hideBorder": "1", "hideFill": "1", "hidePageNum": "1",
        },
    ) in controls


# --------------------------------------------------------------------------
# 왕복 — save/reopen


def test_restart_page_number_round_trips_through_save_and_reopen(tmp_path) -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    doc.page.restart_page_number(paragraph, number=7)
    path = tmp_path / "restart.hwpx"
    doc.save_to_path(path)
    doc.close()

    xml = _section_xml(path)
    assert '<hp:newNum num="7" numType="PAGE"' in xml

    reopened = HwpxDocument.open(path)
    controls = _controls(reopened.paragraphs[-1])
    assert ("newNum", {"num": "7", "numType": "PAGE"}) in controls
    reopened.close()


def test_hide_page_elements_round_trips_through_save_and_reopen(tmp_path) -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    doc.page.hide_page_elements(paragraph, footer=True, page_num=True)
    path = tmp_path / "hide.hwpx"
    doc.save_to_path(path)
    doc.close()

    xml = _section_xml(path)
    assert "hideFooter=\"1\"" in xml and "hidePageNum=\"1\"" in xml

    reopened = HwpxDocument.open(path)
    controls = _controls(reopened.paragraphs[-1])
    hiding = dict(next(attrs for name, attrs in controls if name == "pageHiding"))
    assert hiding["hideFooter"] == "1"
    assert hiding["hidePageNum"] == "1"
    reopened.close()


def test_authored_page_controls_pass_open_safety(tmp_path) -> None:
    from hwpx.tools.package_validator import validate_editor_open_safety

    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    doc.page.restart_page_number(paragraph, number=3)
    doc.page.hide_page_elements(paragraph, header=True)
    path = tmp_path / "safe.hwpx"
    doc.save_to_path(path)
    doc.close()

    report = validate_editor_open_safety(path).to_dict()
    assert report["ok"] is True


# --------------------------------------------------------------------------
# typed error


def test_restart_page_number_invalid_kind_is_a_typed_error() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    with pytest.raises(HwpxValueError) as excinfo:
        doc.page.restart_page_number(paragraph, kind="CHAPTER")
    assert excinfo.value.code == "page-new-num-kind-invalid"
    assert "PAGE" in excinfo.value.context["allowed"]


def test_restart_page_number_error_is_still_catchable_as_plain_value_error() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    with pytest.raises(ValueError):
        doc.page.restart_page_number(paragraph, kind="CHAPTER")


def test_page_control_error_code_is_registered() -> None:
    from hwpx.errors import ERROR_CODES

    assert "page-new-num-kind-invalid" in ERROR_CODES


def test_add_new_num_oxml_layer_rejects_invalid_kind_too() -> None:
    """네임스페이스를 우회해 oxml 계층을 직접 불러도 방어적으로 거부한다."""

    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("본문")
    with pytest.raises(ValueError, match="unsupported kind"):
        paragraph.add_new_num(kind="CHAPTER")


# --------------------------------------------------------------------------
# 실코퍼스


@pytest.mark.skipif(not REAL_CORPUS_FILE.exists(), reason="real corpus fixture missing")
def test_real_corpus_page_functions_reads_correctly() -> None:
    document = HwpxDocument.open(REAL_CORPUS_FILE)
    try:
        controls = _controls(document.paragraphs[0])
        names = [name for name, _ in controls]
        assert "newNum" in names
        assert "pageHiding" in names
        newnum = dict(next(attrs for name, attrs in controls if name == "newNum"))
        assert newnum == {"num": "23", "numType": "PAGE"}
        hiding = dict(next(attrs for name, attrs in controls if name == "pageHiding"))
        assert hiding["hideHeader"] == "1"
        assert hiding["hideMasterPage"] == "1"
    finally:
        document.close()


@pytest.mark.skipif(not REAL_CORPUS_FILE.exists(), reason="real corpus fixture missing")
def test_real_corpus_new_controls_coexist_with_existing_ones_after_roundtrip(
    tmp_path,
) -> None:
    document = HwpxDocument.open(REAL_CORPUS_FILE)
    new_paragraph = document.add_paragraph("추가된 재시작 지점")
    document.page.restart_page_number(new_paragraph, number=100)
    document.page.hide_page_elements(new_paragraph, footer=True, border=True)

    out = tmp_path / "roundtrip.hwpx"
    document.save_to_path(out)
    document.close()

    reopened = HwpxDocument.open(out)
    try:
        all_controls: list[tuple[str, dict]] = []
        for paragraph in reopened.paragraphs:
            all_controls.extend(_controls(paragraph))
        # original (num=23) survives
        assert ("newNum", {"num": "23", "numType": "PAGE"}) in all_controls
        # new one (num=100) is present
        assert ("newNum", {"num": "100", "numType": "PAGE"}) in all_controls
        new_hiding = dict(
            next(attrs for name, attrs in all_controls
                 if name == "pageHiding" and attrs.get("hideFooter") == "1")
        )
        assert new_hiding["hideBorder"] == "1"
    finally:
        reopened.close()


def test_titlemark_authoring_lives_on_the_paragraph_not_doc_page() -> None:
    """감사 갭 titleMark(DEV-044) — 6.15 트레인에서 캐럿 문단 타겟팅이
    실측 확정돼 저작 보류가 풀렸다(``tests/test_title_mark.py``가 계약을
    고정). 이 테스트는 남은 결정 하나만 고정한다: 저작 동사가
    ``doc.page``가 아니라 문단 자신(``HwpxOxmlParagraph.add_title_mark``)
    에 있다는 것 — 캐럿이 있던 "그 문단"을 호출자가 직접 지정하는 API
    형태가 실 편집기의 캐럿 타겟팅과 대응하므로, 페이지 레벨 동사로는
    표현이 안 된다.
    """

    doc = HwpxDocument.new()
    assert not hasattr(doc.page, "add_title_mark")
    assert not hasattr(doc.page, "set_title_mark")
    paragraph = doc.add_paragraph("제목")
    assert hasattr(paragraph, "add_title_mark")
