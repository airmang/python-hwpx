# SPDX-License-Identifier: Apache-2.0
"""Values that come from a document must not become markup, CSS or file names."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.tools import layout_preview, markdown_export
from hwpx.tools.document_viewer import render_document_viewer
from hwpx.tools.layout_preview import render_layout_preview


def _rewrite_member(source: Path, member: str, change) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename == member:
                data = change(data.decode("utf-8")).encode("utf-8")
            dst.writestr(info, data)
    return out.getvalue()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#1A2b3C", "#1A2b3C"),
        ("1A2B3C", "#1A2B3C"),
        ("#80112233", "#11223380"),
        ("none", "#000000"),
        (None, "#000000"),
        ("#000;background:url(http://127.0.0.1:1/x)", "#000000"),
        ("#000000;position:fixed", "#000000"),
        ("red", "#000000"),
        ("#12345", "#000000"),
    ],
)
def test_preview_colour_is_a_hex_colour_or_the_default(value: str | None, expected: str) -> None:
    assert layout_preview._css_color(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0.12 mm", "0.12mm"),
        ("5mm", "5mm"),
        (None, "0.1mm"),
        ("0.1 mm solid red;background:url(x)", "0.1mm"),
        ("1px", "0.1mm"),
    ],
)
def test_preview_border_width_is_a_millimetre_length_or_the_default(value: str | None, expected: str) -> None:
    assert layout_preview._css_border_width(value) == expected


def test_preview_style_attributes_carry_no_document_supplied_css(tmp_path: Path) -> None:
    path = tmp_path / "doc.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    doc.save_to_path(path)

    def inject(xml: str) -> str:
        xml, colours = re.subn(r'textColor="[^"]*"', 'textColor="#000;background:url(http://127.0.0.1:1/MARK)"', xml)
        xml, aligns = re.subn(r'horizontal="[^"]*"', 'horizontal="LEFT;position:fixed"', xml)
        assert colours and aligns
        return xml

    html = render_layout_preview(_rewrite_member(path, "Contents/header.xml", inject)).html

    assert "MARK" not in html
    assert "url(" not in html
    assert "position:fixed" not in html.replace(" ", "")


def test_preview_shows_the_text_after_line_breaks_tabs_and_marks(tmp_path: Path) -> None:
    path = tmp_path / "doc.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("ZQ첫줄\nZQ둘째줄\nZQ셋째줄")
    doc.add_paragraph("ZQ탭앞\tZQ탭뒤")
    doc.add_paragraph("ZQ형광앞ZQ형광뒤")
    doc.save_to_path(path)

    def mark(xml: str) -> str:
        changed = xml.replace("ZQ형광앞ZQ형광뒤", 'ZQ형광앞<hp:markpenBegin color="#FFFF00"/>ZQ형광<hp:markpenEnd/>뒤')
        assert changed != xml
        return changed

    data = _rewrite_member(path, "Contents/section0.xml", mark)

    for html in (render_layout_preview(data).html, render_document_viewer(data).html):
        for piece in ("ZQ첫줄", "ZQ둘째줄", "ZQ셋째줄", "ZQ탭앞", "ZQ탭뒤", "ZQ형광앞", "ZQ형광", "뒤"):
            assert piece in html


def test_markdown_wraps_only_hex_colours() -> None:
    wrapped = markdown_export._wrap("셀값", {"color": '#111"><b>MARK</b><span x="', "shade": "#FFFF00"})

    assert "MARK" not in wrapped
    assert wrapped == '<mark style="background-color:#FFFF00">셀값</mark>'
    assert markdown_export._wrap("값", {"color": "#FF0000"}) == '<span style="color:#FF0000">값</span>'


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com/a?b=1", "https://example.com/a?b=1"),
        ("mailto:someone@example.com", "mailto:someone@example.com"),
        ("https://example.com/a) [x](javascript:mark()", "https://example.com/a%29%20[x]%28javascript:mark%28%29"),
        ("javascript:mark()", None),
        ("file:///C:/Windows/win.ini", None),
        ("\\\\server\\share\\x", None),
        ("", None),
        (None, None),
    ],
)
def test_markdown_links_only_web_and_mail_targets(url: str | None, expected: str | None) -> None:
    assert markdown_export._safe_link_url(url) == expected


def test_markdown_keeps_the_text_of_a_link_it_does_not_link() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("앞 ").add_hyperlink("javascript:mark()", "눌러보기")

    md = markdown_export.export_markdown(doc)

    assert "눌러보기" in md
    assert "javascript:" not in md


@pytest.mark.parametrize(
    ("member", "expected"),
    [
        ("BinData/image1.png", "image1.png"),
        ("BinData/사진.JPG", "사진.JPG"),
        ("BinData/json.py", None),
        ("BinData/.env", None),
        ("BinData/index.html", None),
        ("BinData/C:evil.png", None),
        ("BinData/x.png:stream", None),
        ("BinData/sub\\..\\up.png", "up.png"),
        ("BinData/con.png", None),
        ("BinData/trailing.png.", None),
        ("BinData/", None),
    ],
)
def test_markdown_image_file_name_is_one_image_component(member: str, expected: str | None) -> None:
    assert markdown_export._image_file_name(member) == expected


def test_markdown_image_dir_receives_only_image_members(tmp_path: Path) -> None:
    class Package:
        def files(self) -> list[str]:
            return ["BinData/image1.png", "BinData/json.py", "BinData/C:evil.png", "Contents/section0.xml"]

        def read(self, name: str) -> bytes:
            return b"data"

    class Doc:
        _package = Package()

    target = tmp_path / "imgs"
    mapping = markdown_export._build_image_map(Doc(), target, None)

    assert sorted(p.name for p in target.iterdir()) == ["image1.png"]
    assert mapping == {"image1": "imgs/image1.png"}
