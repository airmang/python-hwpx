"""Tests for hwpx.tools.markdown_export — rich Markdown converter."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Mapping
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.templates import blank_document_bytes
from hwpx.tools.markdown_export import export_markdown

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "examples"
FIXTURES = REPO_ROOT / "shared" / "hwpx" / "fixtures"

HWPML_2011 = {
    "app": "http://www.hancom.co.kr/hwpml/2011/app",
    "paragraph": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "section": "http://www.hancom.co.kr/hwpml/2011/section",
    "core": "http://www.hancom.co.kr/hwpml/2011/core",
    "head": "http://www.hancom.co.kr/hwpml/2011/head",
    "history": "http://www.hancom.co.kr/hwpml/2011/history",
    "master-page": "http://www.hancom.co.kr/hwpml/2011/master-page",
}


def _namespace_family(version: str) -> dict[str, str]:
    if version == "2024":
        return {
            family: f"http://www.owpml.org/owpml/2024/{family}"
            for family in HWPML_2011
        }
    raise ValueError(version)


def _replace_package_namespaces(source: bytes, target: Mapping[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source), "r") as src:
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():
                payload = src.read(info.filename)
                if info.filename.endswith(".xml") or info.filename.endswith(".hpf"):
                    for family, old_uri in HWPML_2011.items():
                        payload = payload.replace(old_uri.encode(), target[family].encode())
                dst.writestr(info, payload)
    return buffer.getvalue()


# ──────────────────────────────────────────────────────────────────
# Static fixtures
# ──────────────────────────────────────────────────────────────────
@pytest.fixture
def showcase_doc():
    return HwpxDocument.open(str(EXAMPLES / "FormattingShowcase.hwpx"))


@pytest.fixture
def table_merge_doc():
    return HwpxDocument.open(str(FIXTURES / "tables" / "30_table_merge_min.hwpx"))


@pytest.fixture
def stress_doc():
    return HwpxDocument.open(str(FIXTURES / "stress" / "99_all_in_one_stress.hwpx"))


# ──────────────────────────────────────────────────────────────────
# Dynamic fixtures (notes/hyperlinks/styled notes)
# ──────────────────────────────────────────────────────────────────
@pytest.fixture
def notes_doc():
    """각주·미주·하이퍼링크 + 인접 위치 각주."""
    doc = HwpxDocument.new()
    sec = doc.sections[0]

    p1 = sec.add_paragraph()
    p1.add_run("우리나라는 누리호")
    p1.add_footnote("누리호: 한국형 발사체")
    p1.add_run("와 다누리호")
    p1.add_footnote("다누리호: 달 궤도선")
    p1.add_run("를 보유한 우주강국이다.")

    p2 = sec.add_paragraph("국가 R&D 투자는 ")
    p2.add_run("19년간", bold=True)
    p2.add_footnote("'06~'24 누적")
    p2.add_run(" 8조 7,931억원에 달한다.")

    p3 = sec.add_paragraph("자세한 정책은 ")
    p3.add_hyperlink("https://www.kasa.go.kr", "우주항공청 홈페이지")
    p3.add_run("에 공개되어 있다")
    p3.add_endnote("KASA, 2024.5.30 발표")
    p3.add_run(".")
    return doc


@pytest.fixture
def styled_note_doc():
    """각주 본문에 서식이 섞인 fixture — HwpxOxmlNote.add_run helper 사용."""
    doc = HwpxDocument.new()
    sec = doc.sections[0]
    p = sec.add_paragraph("혼합 서식 각주")
    n = p.add_footnote("기본 ")
    n.add_run("청색", char_pr_id_ref=5)
    n.add_run(" + 일반")
    return doc


# ──────────────────────────────────────────────────────────────────
# 인라인 서식
# ──────────────────────────────────────────────────────────────────
class TestInlineStyles:
    def test_bold_and_color_preserved(self, showcase_doc):
        md = export_markdown(showcase_doc)
        # "굵은 텍스트"는 bold + 청색 #1F4E79
        assert "**<span style=\"color:#1F4E79\">굵은 텍스트</span>**" in md or \
               "<span style=\"color:#1F4E79\">굵은 텍스트</span>" in md
        # "기울임"은 italic + 보라
        assert "*<span style=\"color:#7030A0\">기울임</span>*" in md
        # "강조 표시"는 노란 하이라이트
        assert '<mark style="background-color:#FFF2CC">강조 표시</mark>' in md
        # 빨간 글자
        assert "<span style=\"color:#C00000\">색상이 다른 코드 샘플</span>" in md

    def test_adjacent_same_style_merged(self, notes_doc):
        # "19년간"이 단일 bold로 머지되어야 (마커가 끊기지 않음)
        md = export_markdown(notes_doc)
        assert "**19년간**" in md
        assert "**1****9****년간**" not in md

    def test_white_color_ignored(self):
        # PoC와 동일하게 #FFFFFF는 색상 마커 없이 plain
        doc = HwpxDocument.new()
        p = doc.sections[0].add_paragraph()
        # cpr이 #FFFFFF인 가상 시나리오는 만들기 어려우니, 단순히 출력에 흰색 span이 없음을 회귀로
        p.add_run("테스트")
        md = export_markdown(doc)
        assert "#FFFFFF" not in md

    def test_strikeout_preserved(self):
        doc = HwpxDocument.new()
        strike_id = doc.ensure_run_style(strike=True)
        p = doc.sections[0].add_paragraph()
        p.add_run("취소선", char_pr_id_ref=strike_id)

        md = export_markdown(doc)

        assert "~~취소선~~" in md


# ──────────────────────────────────────────────────────────────────
# 표
# ──────────────────────────────────────────────────────────────────
class TestTables:
    def test_merge_uses_html_with_colspan(self, table_merge_doc):
        md = export_markdown(table_merge_doc)
        assert "<table>" in md
        assert 'colspan="2"' in md
        assert 'rowspan="2"' in md

    def test_nested_table_recursion(self, stress_doc):
        md = export_markdown(stress_doc)
        # 외부 표 안에 또 다른 <table> 들어있어야 (재귀 처리)
        count = md.count("<table>")
        assert count >= 2, f"expected >=2 <table>, got {count}"

    def test_gfm_table_escapes_cell_content(self):
        doc = HwpxDocument.new()
        p = doc.sections[0].add_paragraph()
        table = p.add_table(1, 2)
        table.set_cell_text(0, 0, "a | b")
        table.set_cell_text(0, 1, "<b>x</b> & y")

        md = export_markdown(doc)

        assert "| a \\| b | &lt;b&gt;x&lt;/b&gt; &amp; y |" in md
        assert "<b>x</b>" not in md

    def test_html_table_escapes_cell_content(self):
        doc = HwpxDocument.new()
        p = doc.sections[0].add_paragraph()
        table = p.add_table(1, 2)
        table.set_cell_text(0, 0, "<script>x</script>")
        table.set_cell_text(0, 1, "safe")
        table.merge_cells(0, 0, 0, 1)

        md = export_markdown(doc)

        assert "&lt;script&gt;x&lt;/script&gt;" in md
        assert "<script>" not in md


# ──────────────────────────────────────────────────────────────────
# 각주 / 미주
# ──────────────────────────────────────────────────────────────────
class TestFootnotes:
    def test_marker_precise_position(self, notes_doc):
        md = export_markdown(notes_doc)
        # "누리호" 직후 + "다누리호" 직후 각각 마커
        assert "누리호[^fn1]" in md
        assert "다누리호[^fn2]" in md

    def test_sequence_ids(self, notes_doc):
        md = export_markdown(notes_doc)
        # fn1, fn2, fn3 + en1
        assert "[^fn1]" in md
        assert "[^fn2]" in md
        assert "[^fn3]" in md
        assert "[^en1]" in md
        # 정의 부록
        assert "[^fn1]:" in md
        assert "[^en1]:" in md

    def test_endnote_separate_counter(self, notes_doc):
        md = export_markdown(notes_doc)
        # 각주 3개 + 미주 1개 — en1이 fn4가 되지 않고 별도 카운터
        assert "[^fn1]" in md
        assert "[^en1]" in md
        # fn4 정의는 없어야 함
        assert "[^fn4]:" not in md

    def test_footnote_body_inline_style(self, styled_note_doc):
        md = export_markdown(styled_note_doc)
        # 각주 본문에 cpr=5(청색) 마커가 살아있어야 함
        # cpr=5의 textColor = #2E74B5 (HwpxDocument.new() default)
        assert "#2E74B5" in md, f"각주 본문 색상 마커 누락:\n{md}"


# ──────────────────────────────────────────────────────────────────
# HwpxOxmlNote helper API (body_paragraph / add_run / cpr propagation)
# ──────────────────────────────────────────────────────────────────
class TestNoteHelpers:
    def test_body_paragraph_distinct_from_host(self):
        doc = HwpxDocument.new()
        p = doc.sections[0].add_paragraph("본문")
        n = p.add_footnote("각주 본문")
        # host: sec의 직속 paragraph (p와 동일)
        assert n.paragraph is p
        # body: footNote 안 paragraph (다른 element)
        body = n.body_paragraph
        assert body.element is not p.element
        assert body.element.getparent().tag.endswith("subList")
        assert body.text == "각주 본문"

    def test_add_run_appends_to_body(self):
        doc = HwpxDocument.new()
        p = doc.sections[0].add_paragraph("본문")
        n = p.add_footnote("기본 ")
        n.add_run("추가", char_pr_id_ref=5)
        # 본문에 run 2개 — "기본 "와 "추가"
        body_runs = n.body_paragraph.runs
        assert len(body_runs) == 2
        assert body_runs[1].text == "추가"
        assert body_runs[1].char_pr_id_ref == "5"

    def test_add_footnote_cpr_applies_to_body(self):
        doc = HwpxDocument.new()
        p = doc.sections[0].add_paragraph("본문")
        n = p.add_footnote("청색 각주", char_pr_id_ref=5)
        # 본문 run의 cpr이 5
        body_runs = n.body_paragraph.runs
        assert body_runs[0].char_pr_id_ref == "5"

    def test_styled_note_markdown_preserves_color(self, styled_note_doc):
        md = export_markdown(styled_note_doc)
        # 본문 청색 cpr=5 → #2E74B5 마커
        assert "#2E74B5" in md
        assert "기본 <span style=\"color:#2E74B5\">청색</span> + 일반" in md

    def test_add_hyperlink_helper(self):
        doc = HwpxDocument.new()
        p = doc.sections[0].add_paragraph("본문")
        n = p.add_footnote("기본 ")
        n.add_hyperlink("https://example.com", "여기")
        # body에 hyperlink XML이 정확히 들어갔는지
        body_el = n.body_paragraph.element
        assert body_el.find(f".//{HP}fieldBegin") is not None

    def test_hyperlink_inside_footnote_body(self):
        """각주 본문에 하이퍼링크 → 마커는 정확 위치, 본문은 [text](url)."""
        doc = HwpxDocument.new()
        sec = doc.sections[0]
        p = sec.add_paragraph("본문 시작 ")
        n = p.add_footnote("자세한 정보는 ")
        n.add_hyperlink("https://example.com", "여기")
        n.add_run("를 참고")
        p.add_run("본문 끝")

        md = export_markdown(doc)
        # 마커는 paragraph 안 정확 위치 (본문 시작 뒤, 본문 끝 앞)
        assert "본문 시작 [^fn1]본문 끝" in md
        # 정의에 markdown link 포함
        assert "[^fn1]: 자세한 정보는 [여기](https://example.com)를 참고" in md

    def test_add_run_accepts_rich_style_kwargs(self):
        doc = HwpxDocument.new()
        p = doc.sections[0].add_paragraph("본문")
        note = p.add_footnote("기본 ")
        note.add_run("삭제", strike=True)

        md = export_markdown(doc)

        assert "[^fn1]: 기본 ~~삭제~~" in md


# ──────────────────────────────────────────────────────────────────
# 하이퍼링크
# ──────────────────────────────────────────────────────────────────
class TestHyperlinks:
    def test_markdown_link(self, notes_doc):
        md = export_markdown(notes_doc)
        # [text](url) 변환 확인
        assert "[우주항공청 홈페이지](https://www.kasa.go.kr)" in md


# ──────────────────────────────────────────────────────────────────
# 헤딩 감지
# ──────────────────────────────────────────────────────────────────
class TestHeadings:
    def test_roman_promoted_to_h1(self):
        doc = HwpxDocument.new()
        doc.sections[0].add_paragraph("Ⅰ. 개요")
        md = export_markdown(doc)
        assert md.lstrip().startswith("# Ⅰ. 개요")

    def test_arabic_promoted_to_h2(self):
        doc = HwpxDocument.new()
        doc.sections[0].add_paragraph("1. 수립 배경 및 대상사업")
        md = export_markdown(doc)
        assert "## 1. 수립 배경 및 대상사업" in md

    def test_detect_headings_disabled(self):
        doc = HwpxDocument.new()
        doc.sections[0].add_paragraph("Ⅰ. 개요")
        md = export_markdown(doc, detect_headings=False)
        assert "# Ⅰ" not in md
        assert "Ⅰ. 개요" in md


# ──────────────────────────────────────────────────────────────────
# 이미지
# ──────────────────────────────────────────────────────────────────
class TestImages:
    def test_no_image_dir_means_no_markers(self, showcase_doc, tmp_path):
        md = export_markdown(showcase_doc, image_dir=None)
        assert "![image]" not in md

    def test_image_dir_extracts_bindata(self, table_merge_doc, tmp_path):
        img_dir = tmp_path / "imgs"
        export_markdown(table_merge_doc, image_dir=img_dir, image_ref_prefix="imgs")
        # BinData가 없는 fixture라도 호출 자체는 성공
        assert img_dir.exists()


# ──────────────────────────────────────────────────────────────────
# 라운드트립 (charPrIDRef 보존)
# ──────────────────────────────────────────────────────────────────
class TestRoundtrip:
    def test_charpridref_preserved_after_replace(self, tmp_path, notes_doc):
        src = tmp_path / "src.hwpx"
        notes_doc.save_to_path(str(src))

        def snap(d):
            return [
                (r.char_pr_id_ref, r.text or "")
                for s in d.sections
                for p in s.paragraphs
                for r in p.runs
            ]

        before = snap(HwpxDocument.open(str(src)))
        doc = HwpxDocument.open(str(src))
        doc.replace_text_in_runs("우주", "★우주★")
        dst = tmp_path / "dst.hwpx"
        doc.save_to_path(str(dst))
        after = snap(HwpxDocument.open(str(dst)))

        assert len(before) == len(after)
        # cpr 완전 보존
        loss = sum(1 for b, a in zip(before, after) if b[0] != a[0])
        assert loss == 0, f"charPrIDRef lost in {loss} runs"

    def test_modified_document_still_exports(self, tmp_path, notes_doc):
        src = tmp_path / "src.hwpx"
        notes_doc.save_to_path(str(src))
        doc = HwpxDocument.open(str(src))
        doc.replace_text_in_runs("우주", "★우주★")
        dst = tmp_path / "dst.hwpx"
        doc.save_to_path(str(dst))
        # 라운드트립 후에도 markdown 변환 성공 + 각주/링크 보존
        md = export_markdown(HwpxDocument.open(str(dst)))
        assert "[^fn1]" in md
        # 치환이 link display text 안에서도 일어남 (의도된 동작)
        assert "](https://www.kasa.go.kr)" in md
        assert "★우주★항공청 홈페이지" in md


# ──────────────────────────────────────────────────────────────────
# 통합 — 다양한 입력 형태
# ──────────────────────────────────────────────────────────────────
class TestSourceInputs:
    def test_accepts_document_instance(self, showcase_doc):
        md = export_markdown(showcase_doc)
        assert len(md) > 0

    def test_accepts_path_string(self):
        md = export_markdown(str(EXAMPLES / "FormattingShowcase.hwpx"))
        assert len(md) > 0

    def test_accepts_pathlib(self):
        md = export_markdown(EXAMPLES / "FormattingShowcase.hwpx")
        assert len(md) > 0

    def test_via_document_method(self, showcase_doc):
        md = showcase_doc.export_rich_markdown()
        direct = export_markdown(showcase_doc)
        assert md == direct


class TestNamespaces:
    def test_accepts_2024_owpml_namespace(self):
        package_bytes = _replace_package_namespaces(
            blank_document_bytes(),
            _namespace_family("2024"),
        )
        doc = HwpxDocument.open(package_bytes)
        doc.paragraphs[0].text = "Ⅰ. 개요"

        md = export_markdown(doc)

        assert md.lstrip().startswith("# Ⅰ. 개요")
