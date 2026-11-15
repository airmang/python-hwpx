# SPDX-License-Identifier: Apache-2.0
"""Mail merge finds placeholders with Korean keys and in headers/footers, and fails rows that keep one."""

from __future__ import annotations

from pathlib import Path

from hwpx import HwpxDocument
from hwpx.tools.mail_merge import inspect_mail_merge_placeholders, merge_template_rows


def _template(tmp_path: Path) -> Path:
    doc = HwpxDocument.new()
    doc.add_paragraph("이름: {{성명}} / {{name}} / ${학교명} / <<반>>")
    doc.page.set_header(text="머리말 {{school}}")
    doc.page.set_footer(text="꼬리말 {{쪽}}")
    path = tmp_path / "tpl.hwpx"
    doc.save_to_path(path)
    return path


def _everywhere_text(path: Path) -> str:
    from hwpx.tools.mail_merge import _template_text

    doc = HwpxDocument.open(path)
    try:
        return _template_text(doc)
    finally:
        doc.close()


def test_inspect_finds_korean_keys_and_header_footer_placeholders(tmp_path: Path) -> None:
    report = inspect_mail_merge_placeholders(_template(tmp_path))

    assert report["keys"] == sorted(["name", "school", "성명", "쪽", "학교명", "반"])


def test_merge_replaces_korean_keys_and_header_footer(tmp_path: Path) -> None:
    row = {"성명": "홍길동", "name": "Hong", "학교명": "가나고", "반": "3", "school": "다라고", "쪽": "1"}
    report = merge_template_rows(_template(tmp_path), [row], output_dir=tmp_path / "out")

    assert report["ok"] is True
    assert report["rows"][0]["unresolvedPlaceholders"] == []
    text = _everywhere_text(Path(report["rows"][0]["filename"]))
    assert "홍길동" in text and "가나고" in text and "다라고" in text and "꼬리말 1" in text
    assert "{{" not in text and "${" not in text and "<<" not in text


def test_row_with_placeholder_left_is_not_ok(tmp_path: Path) -> None:
    # The value brings in a new placeholder, so the output still has one after replacing.
    row = {"성명": "{{남은칸}}", "name": "Hong", "학교명": "가", "반": "1", "school": "s", "쪽": "1"}
    report = merge_template_rows(_template(tmp_path), [row], output_dir=tmp_path / "out")

    assert report["ok"] is False
    assert report["rows"][0]["unresolvedPlaceholders"] == ["{{남은칸}}"]
    assert "unresolved_placeholder" in report["rows"][0]["reasons"]


def test_header_placeholder_left_in_output_fails_the_row(tmp_path: Path) -> None:
    # A key the data lacks keeps its header placeholder; the row reports it instead of passing.
    report = merge_template_rows(_template(tmp_path), [{"name": "Hong"}], output_dir=tmp_path / "out")

    row = report["rows"][0]
    assert report["ok"] is False
    assert set(row["missingKeys"]) == {"school", "성명", "쪽", "학교명", "반"}


def test_digit_first_text_is_not_a_placeholder(tmp_path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("{{1번}} {{ }} {{a b}}")
    path = tmp_path / "t.hwpx"
    doc.save_to_path(path)

    assert inspect_mail_merge_placeholders(path)["keys"] == []
