# SPDX-License-Identifier: Apache-2.0
"""``ensure_border_fill(fill_image=/fill_gradient=)`` — 이미지·그라데이션 채우기.

실코퍼스(hwpxlib_corpus, imgBrush 5파일·gradation 2파일)와 OWPML 스키마(Core
XML schema.xml:650-889) 리버스: ``hc:fillBrush``는 winBrush/gradation/imgBrush
중 하나만 허용하는 선택형이다. 관측된 실형태는 ``mode="TOTAL"``(imgBrush)·
``type="LINEAR"``(gradation) 전량이라 그 값을 인체공학적 기본값으로 쓴다.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.objects.binary_item import BinaryItem

REPO = Path(__file__).resolve().parent.parent
REAL_CORPUS_FILE = (
    REPO
    / "tests"
    / "fixtures"
    / "hwpxlib_corpus"
    / "error__20250808__2015년_12월_재난안전종합상황_분석_및_전망.hwpx"
)


def _document_with_image() -> tuple[HwpxDocument, BinaryItem]:
    doc = HwpxDocument.new()
    image = doc.media.add_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, "png")
    return doc, image


def _section_xml(path) -> str:
    with zipfile.ZipFile(path) as archive:
        return "".join(
            archive.read(name).decode("utf-8")
            for name in sorted(archive.namelist())
            if name.endswith("header.xml")
        )


# --------------------------------------------------------------------------
# ensure_border_fill(fill_image=...) — 이미지 채우기


def test_ensure_border_fill_with_fill_image_emits_the_measured_hancom_shape() -> None:
    doc, image = _document_with_image()
    border_id = doc.styles.ensure_border_fill(fill_image=image)

    border_fill = doc.styles.border_fill(border_id)
    fill_brush = next(c for c in border_fill.children if c.name == "fillBrush")
    assert [c.name for c in fill_brush.children] == ["imgBrush"]
    img_brush = fill_brush.children[0]
    assert img_brush.attributes["mode"] == "TOTAL"
    img = img_brush.children[0]
    assert img.name == "img"
    assert img.attributes == {
        "binaryItemIDRef": image.item_id,
        "bright": "0",
        "contrast": "0",
        "effect": "REAL_PIC",
        "alpha": "0",
    }


def test_ensure_border_fill_fill_image_accepts_a_bare_id_string() -> None:
    doc, image = _document_with_image()
    by_item = doc.styles.ensure_border_fill(fill_image=image)
    by_id_string = doc.styles.ensure_border_fill(fill_image=str(image))
    assert by_item == by_id_string


def test_ensure_border_fill_fill_image_dedupes_on_repeat() -> None:
    doc, image = _document_with_image()
    first = doc.styles.ensure_border_fill(fill_image=image)
    second = doc.styles.ensure_border_fill(fill_image=image)
    assert first == second


def test_ensure_border_fill_fill_image_mode_override() -> None:
    doc, image = _document_with_image()
    border_id = doc.styles.ensure_border_fill(fill_image={"item": image, "mode": "TILE"})
    border_fill = doc.styles.border_fill(border_id)
    fill_brush = next(c for c in border_fill.children if c.name == "fillBrush")
    assert fill_brush.children[0].attributes["mode"] == "TILE"
    # a different mode is a different fill — no dedupe collision with TOTAL.
    total_id = doc.styles.ensure_border_fill(fill_image=image)
    assert total_id != border_id


# --------------------------------------------------------------------------
# ensure_border_fill(fill_gradient=...) — 그라데이션 채우기


def test_ensure_border_fill_with_fill_gradient_emits_the_measured_hancom_shape() -> None:
    doc = HwpxDocument.new()
    border_id = doc.styles.ensure_border_fill(
        fill_gradient={"colors": ["#FFFFFF", "#4B87CB"], "angle": 90},
    )

    border_fill = doc.styles.border_fill(border_id)
    fill_brush = next(c for c in border_fill.children if c.name == "fillBrush")
    assert [c.name for c in fill_brush.children] == ["gradation"]
    gradation = fill_brush.children[0]
    assert gradation.attributes == {
        "type": "LINEAR",
        "angle": "90",
        "centerX": "0",
        "centerY": "0",
        "step": "255",
        "colorNum": "2",
        "stepCenter": "50",
        "alpha": "0",
    }
    assert [c.attributes["value"] for c in gradation.children] == ["#FFFFFF", "#4B87CB"]


def test_ensure_border_fill_fill_gradient_dedupes_on_repeat() -> None:
    doc = HwpxDocument.new()
    spec = {"colors": ["#FFFFFF", "#4B87CB"], "angle": 90}
    first = doc.styles.ensure_border_fill(fill_gradient=spec)
    second = doc.styles.ensure_border_fill(fill_gradient=dict(spec))
    assert first == second


def test_ensure_border_fill_fill_gradient_three_colors() -> None:
    doc = HwpxDocument.new()
    border_id = doc.styles.ensure_border_fill(
        fill_gradient={"colors": ["#FFFFFF", "#CCCCCC", "#000000"], "type": "radial"},
    )
    border_fill = doc.styles.border_fill(border_id)
    fill_brush = next(c for c in border_fill.children if c.name == "fillBrush")
    gradation = fill_brush.children[0]
    assert gradation.attributes["type"] == "RADIAL"
    assert gradation.attributes["colorNum"] == "3"
    assert len(gradation.children) == 3


# --------------------------------------------------------------------------
# 왕복 — save/reopen


def test_border_fill_image_round_trips_through_save_and_reopen(tmp_path) -> None:
    doc, image = _document_with_image()
    border_id = doc.styles.ensure_border_fill(fill_image=image)
    path = tmp_path / "image_fill.hwpx"
    doc.save_to_path(path)
    doc.close()

    xml = _section_xml(path)
    assert '<hc:imgBrush mode="TOTAL">' in xml
    assert f'binaryItemIDRef="{image.item_id}"' in xml

    reopened = HwpxDocument.open(path)
    border_fill = reopened.styles.border_fill(border_id)
    fill_brush = next(c for c in border_fill.children if c.name == "fillBrush")
    assert fill_brush.children[0].name == "imgBrush"
    reopened.close()


def test_border_fill_gradient_round_trips_through_save_and_reopen(tmp_path) -> None:
    doc = HwpxDocument.new()
    border_id = doc.styles.ensure_border_fill(
        fill_gradient={"colors": ["#FFFFFF", "#4B87CB"], "angle": 90},
    )
    path = tmp_path / "gradient_fill.hwpx"
    doc.save_to_path(path)
    doc.close()

    xml = _section_xml(path)
    assert '<hc:gradation type="LINEAR" angle="90"' in xml

    reopened = HwpxDocument.open(path)
    border_fill = reopened.styles.border_fill(border_id)
    fill_brush = next(c for c in border_fill.children if c.name == "fillBrush")
    assert fill_brush.children[0].name == "gradation"
    reopened.close()


# --------------------------------------------------------------------------
# 실 소비 경로 — 표 셀 배경


def test_set_cell_fill_image_applies_to_a_table_cell(tmp_path) -> None:
    doc, image = _document_with_image()
    table = doc.add_table(2, 2)
    table.set_cell_fill_image(0, 0, image)

    border_fill_id = table.cell(0, 0).element.get("borderFillIDRef")
    border_fill = doc.styles.border_fill(border_fill_id)
    fill_brush = next(c for c in border_fill.children if c.name == "fillBrush")
    assert fill_brush.children[0].name == "imgBrush"
    # the untouched cell keeps its own (unfilled) border-fill.
    assert table.cell(1, 1).element.get("borderFillIDRef") != border_fill_id

    path = tmp_path / "cell_image.hwpx"
    doc.save_to_path(path)
    doc.close()
    report = _open_safety(path)
    assert report["ok"] is True


def test_set_cell_fill_gradient_applies_to_a_table_cell(tmp_path) -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(2, 2)
    table.set_cell_fill_gradient(1, 0, ["#FFFFFF", "#4B87CB"])

    border_fill_id = table.cell(1, 0).element.get("borderFillIDRef")
    border_fill = doc.styles.border_fill(border_fill_id)
    fill_brush = next(c for c in border_fill.children if c.name == "fillBrush")
    assert fill_brush.children[0].name == "gradation"

    path = tmp_path / "cell_gradient.hwpx"
    doc.save_to_path(path)
    doc.close()
    report = _open_safety(path)
    assert report["ok"] is True


def _open_safety(path) -> dict:
    from hwpx.tools.package_validator import validate_editor_open_safety

    return validate_editor_open_safety(path).to_dict()


def test_set_cell_fill_image_rejects_an_unsupported_mode() -> None:
    doc, image = _document_with_image()
    table = doc.add_table(1, 1)
    with pytest.raises(ValueError, match="unsupported mode"):
        table.set_cell_fill_image(0, 0, image, mode="DIAGONAL")


def test_set_cell_fill_gradient_rejects_too_few_colors() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1)
    with pytest.raises(ValueError, match="at least two"):
        table.set_cell_fill_gradient(0, 0, ["#FFFFFF"])


# --------------------------------------------------------------------------
# typed error — 색·모드·타입·개수·상호배타


def test_fill_color_image_gradient_are_mutually_exclusive() -> None:
    doc, image = _document_with_image()
    with pytest.raises(HwpxValueError) as excinfo:
        doc.styles.ensure_border_fill(fill_color="#FFFFFF", fill_image=image)
    assert excinfo.value.code == "style-border-fill-conflict"


def test_fill_image_missing_reference_is_a_typed_error() -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        doc.styles.ensure_border_fill(fill_image={"mode": "TOTAL"})
    assert excinfo.value.code == "style-border-fill-image-missing"


def test_fill_image_invalid_mode_is_a_typed_error() -> None:
    doc, image = _document_with_image()
    with pytest.raises(HwpxValueError) as excinfo:
        doc.styles.ensure_border_fill(fill_image={"item": image, "mode": "DIAGONAL"})
    assert excinfo.value.code == "style-border-fill-image-mode-invalid"
    assert "TOTAL" in excinfo.value.context["allowed"]


def test_fill_image_invalid_effect_is_a_typed_error() -> None:
    doc, image = _document_with_image()
    with pytest.raises(HwpxValueError) as excinfo:
        doc.styles.ensure_border_fill(fill_image={"item": image, "effect": "SEPIA"})
    assert excinfo.value.code == "style-border-fill-image-effect-invalid"


def test_fill_gradient_invalid_type_is_a_typed_error() -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        doc.styles.ensure_border_fill(
            fill_gradient={"colors": ["#FFFFFF", "#000000"], "type": "SPIRAL"},
        )
    assert excinfo.value.code == "style-border-fill-gradient-type-invalid"


def test_fill_gradient_too_few_colors_is_a_typed_error() -> None:
    doc = HwpxDocument.new()
    with pytest.raises(HwpxValueError) as excinfo:
        doc.styles.ensure_border_fill(fill_gradient={"colors": ["#FFFFFF"]})
    assert excinfo.value.code == "style-border-fill-gradient-colors-invalid"


def test_border_fill_errors_are_still_catchable_as_plain_value_error() -> None:
    doc, image = _document_with_image()
    with pytest.raises(ValueError):
        doc.styles.ensure_border_fill(fill_color="#FFFFFF", fill_image=image)


def test_border_fill_error_codes_are_registered() -> None:
    from hwpx.errors import ERROR_CODES

    for code in (
        "style-border-fill-conflict",
        "style-border-fill-image-missing",
        "style-border-fill-image-mode-invalid",
        "style-border-fill-image-effect-invalid",
        "style-border-fill-gradient-type-invalid",
        "style-border-fill-gradient-colors-invalid",
    ):
        assert code in ERROR_CODES


# --------------------------------------------------------------------------
# 기존 동작 회귀 없음 — 단색 fill_color 는 그대로


def test_plain_fill_color_still_works_unaffected() -> None:
    doc = HwpxDocument.new()
    border_id = doc.styles.ensure_border_fill(fill_color="#FF0000")
    border_fill = doc.styles.border_fill(border_id)
    fill_brush = next(c for c in border_fill.children if c.name == "fillBrush")
    assert fill_brush.children[0].name == "winBrush"
    assert fill_brush.children[0].attributes["faceColor"] == "#FF0000"


def test_ensure_border_fill_with_no_fill_still_works_unaffected() -> None:
    doc = HwpxDocument.new()
    border_id = doc.styles.ensure_border_fill()
    border_fill = doc.styles.border_fill(border_id)
    assert not any(c.name == "fillBrush" for c in border_fill.children)


# --------------------------------------------------------------------------
# 실코퍼스 — 읽기는 기존 doc.styles.border_fills()(GenericElement 보존형)로
# 이미 됐다(신규 read 모델 불필요) 를 실파일로 증명한다.


@pytest.mark.skipif(not REAL_CORPUS_FILE.exists(), reason="real corpus fixture missing")
def test_real_corpus_image_and_gradient_border_fills_read_through_the_existing_accessor() -> None:
    document = HwpxDocument.open(REAL_CORPUS_FILE)
    try:
        image_kinds = 0
        gradient_kinds = 0
        for border_fill in document.styles.border_fills.values():
            fill_brush = next(
                (c for c in border_fill.children if c.name == "fillBrush"), None
            )
            if fill_brush is None or not fill_brush.children:
                continue
            kind = fill_brush.children[0]
            if kind.name == "imgBrush":
                image_kinds += 1
                img = kind.children[0]
                assert img.attributes["binaryItemIDRef"]
            elif kind.name == "gradation":
                gradient_kinds += 1
                assert len(kind.children) == int(kind.attributes["colorNum"])
        assert image_kinds == 3
        assert gradient_kinds == 6
    finally:
        document.close()
