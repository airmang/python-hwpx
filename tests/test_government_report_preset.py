from __future__ import annotations

from hwpx import create_document_from_plan, validate_document_plan
from hwpx.builder import Bullet, Document, Heading, Paragraph, Section
from hwpx.document import HwpxDocument


PLAN_V2_SCHEMA_VERSION = "hwpx.document_plan.v2"


def _heading_style(document: HwpxDocument, text: str) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    run = next(run for run in document.iter_runs() if run.text == text)
    assert run.style is not None
    return dict(run.style.attributes), dict(run.style.child_attributes)


def _bullet_chars_for_texts(document: HwpxDocument, texts: list[str]) -> dict[str, str]:
    chars: dict[str, str] = {}
    for paragraph in document.paragraphs:
        if paragraph.text not in texts:
            continue
        para_pr = document.paragraph_property(paragraph.para_pr_id_ref)
        assert para_pr is not None
        assert para_pr.heading is not None
        bullet = document.bullet(para_pr.heading.id_ref)
        assert bullet is not None
        chars[paragraph.text] = bullet.char
    return chars


def test_government_report_heading_style_differs_from_default() -> None:
    default_doc = Document(sections=(Section(children=(Heading(level=1, text="제목"),)),)).lower()
    government_doc = Document(
        preset="government_report",
        sections=(Section(children=(Heading(level=1, text="제목"),)),),
    ).lower()
    try:
        default_attrs, default_children = _heading_style(default_doc, "제목")
        gov_attrs, gov_children = _heading_style(government_doc, "제목")
        assert gov_attrs != default_attrs or gov_children != default_children
        assert default_children.get("underline", {}).get("type") != "SOLID"
        assert gov_children["underline"]["type"] == "SOLID"
        assert gov_attrs["textColor"] == "#1F4E79"
    finally:
        default_doc.close()
        government_doc.close()


def test_government_report_bullets_render_and_reopen_with_korean_office_chars(tmp_path) -> None:
    path = tmp_path / "government-bullets.hwpx"
    expected = {
        "default": "•",
        "square": "□",
        "circle": "○",
        "dash": "-",
        "note": "※",
        "star": "*",
    }
    Document(
        preset="government_report",
        sections=(
            Section(
                children=tuple(
                    Bullet(items=(label,), style=None if label == "default" else label)
                    for label in expected
                )
            ),
        ),
    ).save_to_path(path)

    reopened = HwpxDocument.open(path)
    try:
        assert _bullet_chars_for_texts(reopened, list(expected)) == expected
    finally:
        reopened.close()


def test_plan_v2_preset_government_report_matches_builder_preset(tmp_path) -> None:
    builder_path = tmp_path / "builder-gov.hwpx"
    plan_path = tmp_path / "plan-gov.hwpx"
    Document(
        preset="government_report",
        sections=(
            Section(
                children=(
                    Heading(level=1, text="제목"),
                    Bullet(items=("square",), style="square"),
                    Paragraph(text="본문"),
                )
            ),
        ),
    ).save_to_path(builder_path)

    plan = {
        "schemaVersion": PLAN_V2_SCHEMA_VERSION,
        "preset": "government_report",
        "sections": [
            {
                "blocks": [
                    {"type": "heading", "level": 1, "text": "제목"},
                    {"type": "bullets", "items": ["square"], "style": "square"},
                    {"type": "paragraph", "text": "본문"},
                ]
            }
        ],
    }
    assert validate_document_plan(plan).ok is True
    document = create_document_from_plan(plan)
    try:
        document.save_to_path(plan_path)
    finally:
        document.close()

    builder_doc = HwpxDocument.open(builder_path)
    plan_doc = HwpxDocument.open(plan_path)
    try:
        assert _heading_style(plan_doc, "제목") == _heading_style(builder_doc, "제목")
        assert _bullet_chars_for_texts(plan_doc, ["square"]) == {"square": "□"}
    finally:
        builder_doc.close()
        plan_doc.close()
