# SPDX-License-Identifier: Apache-2.0
"""Authoring surface for document options/compatibility settings (cycle 6.6
train 23): hh:compatibleDocument (+layoutCompatibility)/hh:docOption
(linkinfo)/hh:paraPr's autoSpacing.

Cycle 6.5's c38bf07 built the read side and stopped deliberately ("no write
API means the OPC layer's untouched-bytes preservation applies"). This
train adds the write side, exposed as doc.parts.set_*, and this file both
exercises each setter and proves the untouched-document byte-preservation
claim c38bf07 made still holds for documents these setters never touch.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.oxml.header import LicenseMark

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"
GUI_PROBES = Path(__file__).parent / "fixtures" / "gui_probes"


def _header_xml(document: HwpxDocument) -> str:
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as archive:
        return archive.read("Contents/header.xml").decode("utf-8")


def test_set_compatible_document_target_program_round_trips() -> None:
    document = HwpxDocument.new()

    document.parts.set_compatible_document_target_program("HWP201X")
    data = document.to_bytes()

    reopened = HwpxDocument.open(data)
    header = reopened.oxml.headers[0].to_model()
    assert header.compatible_document is not None
    assert header.compatible_document.target_program == "HWP201X"


def test_set_compatible_document_target_program_rejects_empty_string() -> None:
    document = HwpxDocument.new()

    with pytest.raises(HwpxValueError, match="non-empty"):
        document.parts.set_compatible_document_target_program("")


def test_set_layout_compatibility_flags_round_trips() -> None:
    document = HwpxDocument.new()

    document.parts.set_layout_compatibility_flags(["applyFontWeightToBold"])
    data = document.to_bytes()

    reopened = HwpxDocument.open(data)
    header = reopened.oxml.headers[0].to_model()
    layout_compatibility = header.compatible_document.layout_compatibility
    assert layout_compatibility is not None
    assert layout_compatibility.flags == frozenset({"applyFontWeightToBold"})


def test_set_layout_compatibility_flags_empty_clears_existing() -> None:
    document = HwpxDocument.new()
    document.parts.set_layout_compatibility_flags(["applyFontWeightToBold"])

    document.parts.set_layout_compatibility_flags([])
    data = document.to_bytes()

    reopened = HwpxDocument.open(data)
    header = reopened.oxml.headers[0].to_model()
    assert header.compatible_document.layout_compatibility.flags == frozenset()


def test_set_layout_compatibility_flags_rejects_empty_flag_name() -> None:
    document = HwpxDocument.new()

    with pytest.raises(HwpxValueError, match="non-empty"):
        document.parts.set_layout_compatibility_flags([""])


def test_set_doc_option_link_info_round_trips() -> None:
    document = HwpxDocument.new()

    document.parts.set_doc_option_link_info(
        path="C:\\master.hwpx", page_inherit=True, footnote_inherit=True
    )
    data = document.to_bytes()

    reopened = HwpxDocument.open(data)
    header = reopened.oxml.headers[0].to_model()
    link_info = header.doc_option.link_info
    assert link_info.path == "C:\\master.hwpx"
    assert link_info.page_inherit is True
    assert link_info.footnote_inherit is True


def test_set_doc_option_link_info_partial_update_leaves_others_unchanged() -> None:
    document = HwpxDocument.new()
    document.parts.set_doc_option_link_info(path="", page_inherit=True, footnote_inherit=False)

    document.parts.set_doc_option_link_info(page_inherit=False)
    data = document.to_bytes()

    reopened = HwpxDocument.open(data)
    link_info = reopened.oxml.headers[0].to_model().doc_option.link_info
    assert link_info.page_inherit is False
    assert link_info.path == ""
    assert link_info.footnote_inherit is False


def test_set_license_mark_matches_the_real_gold_contract() -> None:
    """실측 gold(``tests/fixtures/gui_probes/license_mark_ccl.hwpx``, "입력 >
    CCL 넣기…"): ``hh:linkinfo`` 바로 뒤 형제로
    ``<hh:licensemark type="CCL" flag="0" lang="6"/>``."""

    document = HwpxDocument.new()

    document.parts.set_license_mark(mark_type="CCL", flag=0, lang=6)

    header_xml = _header_xml(document)
    assert (
        '<hh:linkinfo path="" pageInherit="0" footnoteInherit="0"/>'
        '<hh:licensemark type="CCL" flag="0" lang="6"/>'
    ) in header_xml
    assert header_xml.count("<hh:licensemark") == 1


def test_set_license_mark_type_is_a_string_because_real_hancom_writes_one() -> None:
    """스키마(``Header XML schema.xml``의 ``DocOptionType``)는 ``type``을
    ``xs:unsignedInt use="required"``로 선언하지만 실물은 ``"CCL"``이다.
    ``int``로 선언돼 있던 읽기 모델은 실한컴 CCL 문서를 ``to_model()``로
    읽는 순간 ``ValueError``로 터졌다 -- 그 회귀를 이 테스트가 막는다."""

    gold = HwpxDocument.open(GUI_PROBES / "license_mark_ccl.hwpx")
    try:
        license_mark = gold.oxml.headers[0].to_model().doc_option.license_mark
    finally:
        gold.close()

    assert license_mark == LicenseMark(type="CCL", flag=0, lang=6)


def test_set_license_mark_round_trips_through_save_and_reopen() -> None:
    document = HwpxDocument.new()

    document.parts.set_license_mark(mark_type="CCL", flag=0, lang=6)
    reopened = HwpxDocument.open(document.to_bytes())

    license_mark = reopened.oxml.headers[0].to_model().doc_option.license_mark
    assert license_mark == LicenseMark(type="CCL", flag=0, lang=6)


def test_set_license_mark_omits_lang_when_not_given() -> None:
    """``lang``만 스키마상 optional -- 안 주면 속성을 안 단다(``type``/
    ``flag``는 required라 항상 쓴다)."""

    document = HwpxDocument.new()

    document.parts.set_license_mark(mark_type="CCL", flag=0)

    assert '<hh:licensemark type="CCL" flag="0"/>' in _header_xml(document)


def test_set_license_mark_twice_updates_in_place() -> None:
    document = HwpxDocument.new()
    document.parts.set_license_mark(mark_type="CCL", flag=0, lang=6)

    document.parts.set_license_mark(mark_type="CCL", flag=1, lang=1)

    header_xml = _header_xml(document)
    assert header_xml.count("<hh:licensemark") == 1
    assert '<hh:licensemark type="CCL" flag="1" lang="1"/>' in header_xml


def test_set_license_mark_rejects_an_empty_type() -> None:
    document = HwpxDocument.new()

    with pytest.raises(HwpxValueError) as excinfo:
        document.parts.set_license_mark(mark_type="", flag=0)
    assert excinfo.value.code == "header-compat-empty-license-mark-type"


def test_remove_license_mark_reports_whether_it_removed_one() -> None:
    document = HwpxDocument.new()
    assert document.parts.remove_license_mark() is False

    document.parts.set_license_mark(mark_type="CCL", flag=0, lang=6)
    assert document.parts.remove_license_mark() is True

    header_xml = _header_xml(document)
    assert "licensemark" not in header_xml
    # linkinfo는 스키마 필수라 docOption과 함께 남는다.
    assert "<hh:linkinfo" in header_xml


def test_set_paragraph_auto_spacing_round_trips() -> None:
    document = HwpxDocument.new()
    para_pr_id = document.oxml.headers[0].ensure_paragraph_format(alignment="LEFT")

    document.parts.set_paragraph_auto_spacing(para_pr_id, e_asian_eng=True, e_asian_num=False)
    data = document.to_bytes()

    reopened = HwpxDocument.open(data)
    header = reopened.oxml.headers[0].to_model()
    props = header.ref_list.para_properties.properties
    target = next(p for p in props if p.raw_id == para_pr_id)
    assert target.auto_spacing is not None
    assert target.auto_spacing.e_asian_eng is True
    assert target.auto_spacing.e_asian_num is False


def test_set_paragraph_auto_spacing_partial_update_defaults_the_other_to_zero_on_creation() -> None:
    """Both attributes are schema-required -- creating a fresh autoSpacing
    with only one explicit value must not leave the other unset."""

    document = HwpxDocument.new()
    para_pr_id = document.oxml.headers[0].ensure_paragraph_format(alignment="LEFT")

    document.parts.set_paragraph_auto_spacing(para_pr_id, e_asian_eng=True)
    data = document.to_bytes()

    reopened = HwpxDocument.open(data)
    props = reopened.oxml.headers[0].to_model().ref_list.para_properties.properties
    target = next(p for p in props if p.raw_id == para_pr_id)
    assert target.auto_spacing.e_asian_eng is True
    assert target.auto_spacing.e_asian_num is False


def test_set_paragraph_auto_spacing_unknown_id_raises() -> None:
    document = HwpxDocument.new()

    with pytest.raises(HwpxValueError, match="no hh:paraPr"):
        document.parts.set_paragraph_auto_spacing("does-not-exist")


def test_set_paragraph_auto_spacing_on_a_real_switch_wrapped_document_does_not_disturb_margin() -> None:
    """Real corpus evidence (cycle 6.6 train 23): unlike margin/lineSpacing,
    autoSpacing is never hp:switch-wrapped (1832/1832 direct children, 0
    nested) -- editing it on a real switch-wrapped paraPr must leave the
    switch's margin/lineSpacing branches completely untouched."""

    document = HwpxDocument.open(CORPUS / "tool__blank.hwpx")
    header = document.oxml.headers[0]
    before = header.to_model()
    props_before = before.ref_list.para_properties.properties
    target_id = props_before[0].raw_id
    margin_before = props_before[0].margin
    line_spacing_before = props_before[0].line_spacing

    document.parts.set_paragraph_auto_spacing(target_id, e_asian_eng=True, e_asian_num=True)
    data = document.to_bytes()

    reopened = HwpxDocument.open(data)
    props_after = reopened.oxml.headers[0].to_model().ref_list.para_properties.properties
    target_after = next(p for p in props_after if p.raw_id == target_id)

    assert target_after.auto_spacing.e_asian_eng is True
    assert target_after.auto_spacing.e_asian_num is True
    assert target_after.margin == margin_before
    assert target_after.line_spacing == line_spacing_before


@pytest.mark.parametrize("sample_path", sorted(CORPUS.glob("*.hwpx")), ids=lambda path: path.name)
def test_real_corpus_document_options_round_trip_untouched(sample_path: Path) -> None:
    """The byte-preservation claim cycle 6.5's read-only train made
    ("no write API means the OPC layer's untouched-bytes preservation
    applies") must still hold now that a write API exists -- documents this
    train's setters never call must be unaffected."""

    document = HwpxDocument.open(sample_path)
    before = document.oxml.headers[0].to_model()

    data = document.to_bytes()
    reopened = HwpxDocument.open(data)
    after = reopened.oxml.headers[0].to_model()

    assert before.compatible_document == after.compatible_document
    assert before.doc_option == after.doc_option

    props_before = (
        before.ref_list.para_properties.properties
        if before.ref_list and before.ref_list.para_properties
        else []
    )
    props_after = (
        after.ref_list.para_properties.properties
        if after.ref_list and after.ref_list.para_properties
        else []
    )
    assert [p.auto_spacing for p in props_before] == [p.auto_spacing for p in props_after]
