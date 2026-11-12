from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.ingest import DocumentIngestor, UnsupportedDocumentFormat, normalize_markdown


def _sample_hwpx(path: Path) -> Path:
    doc = HwpxDocument.new()
    doc.add_paragraph("2026학년도 운영 계획")
    doc.add_paragraph("1. 추진 목적")
    table = doc.add_table(2, 2)
    table.set_cell_text(0, 0, "항목")
    table.set_cell_text(0, 1, "내용")
    table.set_cell_text(1, 0, "기간")
    table.set_cell_text(1, 1, "2026. 3.")
    doc.save_to_path(path)
    return path


def test_document_ingestor_converts_hwpx_to_rich_markdown(tmp_path: Path) -> None:
    source = _sample_hwpx(tmp_path / "sample.hwpx")

    result = DocumentIngestor.default().convert(source)

    assert result.engine == "python-hwpx"
    assert result.source_format == "hwpx"
    assert result.lossiness == "low"
    assert "2026학년도 운영 계획" in result.markdown
    assert "## 1. 추진 목적" in result.markdown
    assert "| 항목 | 내용 |" in result.markdown
    assert result.metadata["table_count"] == 1
    assert result.tables[0]["data"][1] == ["기간", "2026. 3."]
    assert result.attempts[0].accepted is True


def test_document_ingestor_detects_hwpx_from_stream_without_extension(tmp_path: Path) -> None:
    source = _sample_hwpx(tmp_path / "sample.hwpx")
    stream = BytesIO(source.read_bytes())

    result = DocumentIngestor.default().convert(stream)

    assert result.source_format == "hwpx"
    assert "2026학년도 운영 계획" in result.markdown


def test_document_ingestor_reports_unsupported_format(tmp_path: Path) -> None:
    source = tmp_path / "sample.txt"
    source.write_text("plain text is a later adapter", encoding="utf-8")

    with pytest.raises(UnsupportedDocumentFormat) as exc:
        DocumentIngestor.default().convert(source)

    payload = exc.value.as_dict()
    assert payload["error"] == "UnsupportedDocumentFormat"
    assert payload["attempts"][0]["converter"] == "HwpxMarkdownConverter"
    assert payload["attempts"][0]["accepted"] is False


def test_normalize_markdown_trims_trailing_space_and_extra_blank_lines() -> None:
    assert normalize_markdown("a  \n\n\n\nb\n") == "a\n\nb"


def _rich_hwpx() -> bytes:
    with HwpxDocument.new() as doc:
        doc.add_paragraph("본문 문장입니다")
        doc.page.set_header(text="머리말 ZQ글")
        doc.page.set_footer(text="꼬리말 ZQ글")
        anchor = doc.add_paragraph("메모 달린 문단")
        doc.notes.add_memo("메모 ZQ내용", anchor=anchor)
        doc.shapes.add_equation("x = {-b +- sqrt {b^2 - 4ac}} over {2a}")
        doc.shapes.add_composed_character("가나")
        doc.fields.add_check_box(caption="체크ZQ캡션")
        return doc.to_bytes()


def test_ingest_reports_what_the_markdown_leaves_out() -> None:
    """빠뜨린 요소가 있으면 ``low``가 아니고, 종류와 개수를 알린다(ENG-21).

    보고는 결과와 대조해 만든다. 여기서 보는 것은 "Markdown에 글이 없는 종류는
    반드시 보고된다"는 한 방향이다. 내보내기가 어떤 종류를 싣게 되면 그 종류는
    보고에서 빠지고 이 시험은 그대로 통과한다.
    """

    result = DocumentIngestor.default().convert(_rich_hwpx())
    markers = {
        "header": "머리말 ZQ글",
        "footer": "꼬리말 ZQ글",
        "memo": "메모 ZQ내용",
        "equation": "sqrt",
        "form_caption": "체크ZQ캡션",
    }
    left_out = result.metadata["left_out"]
    absent = {kind for kind, marker in markers.items() if marker not in result.markdown}
    assert absent, "이 문서에서 Markdown이 모두 싣는다면 시험 문서를 바꿔야 한다"
    assert absent <= set(left_out)
    for kind in set(markers) - absent:
        assert kind not in left_out
    assert result.lossiness in {"medium", "high"}
    assert len(result.warnings) == len(left_out)
    assert all("Markdown에 없는 내용" in warning for warning in result.warnings)
    assert result.as_dict()["warnings"] == result.warnings


def test_ingest_counts_a_header_once_and_stays_low_when_nothing_is_left_out(
    tmp_path: Path,
) -> None:
    plain = DocumentIngestor.default().convert(_sample_hwpx(tmp_path / "plain.hwpx"))
    assert plain.lossiness == "low"
    assert plain.warnings == []
    assert plain.metadata["left_out"] == {}

    with HwpxDocument.new() as doc:
        doc.add_paragraph("본문 " * 200)
        doc.page.set_header(text="한 번만 세는 머리말")
        data = doc.to_bytes()
    result = DocumentIngestor.default().convert(data)
    if "한 번만 세는 머리말" not in result.markdown:
        assert result.metadata["left_out"] == {"header": 1}
        assert result.lossiness == "medium"


_HWP_FIXTURES = Path(__file__).parent / "fixtures" / "hwp5"


def test_ingest_reads_hwp_through_the_same_entry_point() -> None:
    result = DocumentIngestor.default().convert(_HWP_FIXTURES / "border_3d.hwp")

    assert result.source_format == "hwp"
    assert result.engine == "python-hwpx"
    assert result.metadata["table_count"] == 1
    assert result.metadata["hwp_conversion"] == {"unconverted": {}, "dropped": {}}
    assert result.markdown.strip()
    assert result.attempts[0].accepted is True


def test_ingest_detects_hwp_from_bytes_without_a_name() -> None:
    data = (_HWP_FIXTURES / "border_3d.hwp").read_bytes()

    from_bytes = DocumentIngestor.default().convert(data)
    from_stream = DocumentIngestor.default().convert(BytesIO(data))

    assert from_bytes.source_format == from_stream.source_format == "hwp"
    assert from_bytes.markdown == from_stream.markdown


def test_ingest_keeps_hwpx_results_free_of_hwp_conversion_data(tmp_path: Path) -> None:
    result = DocumentIngestor.default().convert(_sample_hwpx(tmp_path / "plain.hwpx"))

    assert result.source_format == "hwpx"
    assert "hwp_conversion" not in result.metadata


def test_ingest_says_why_an_old_hwp_cannot_be_read(tmp_path: Path) -> None:
    source = tmp_path / "old.hwp"
    source.write_bytes(b"HWP Document File V3.00 \x1a\x01\x02\x03\x04\x05" + b"\x00" * 64)

    with pytest.raises(UnsupportedDocumentFormat) as exc:
        DocumentIngestor.default().convert(source)

    attempt = exc.value.attempts[0]
    assert attempt.accepted is True
    assert "HWP 3.x" in (attempt.message or "")


def test_ingest_reports_what_an_hwp_conversion_left_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hwpx.hwp5.errors import Hwp5ConversionReport

    monkeypatch.setattr(
        HwpxDocument,
        "conversion_report",
        property(lambda self: Hwp5ConversionReport.of({"chart": 2, "ole": 1}, {"layout_cache": 3})),
    )

    result = DocumentIngestor.default().convert(_HWP_FIXTURES / "border_3d.hwp")

    assert result.metadata["hwp_conversion"] == {
        "unconverted": {"chart": 2, "ole": 1},
        "dropped": {"layout_cache": 3},
    }
    assert result.lossiness == "medium"
    assert any("chart 2" in warning and "ole 1" in warning for warning in result.warnings)
