from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.exam.parser import parse_exam_markdown

FIX = Path(__file__).parent / "fixtures" / "exam"


def test_form_fixtures_open():
    for name in ("A_form.hwpx", "B_submitted.hwpx"):
        doc = HwpxDocument.open(FIX / name)
        assert len(doc.paragraphs) >= 1


def test_sample_exam_md_parses_with_a_set_and_placeholders():
    doc = parse_exam_markdown((FIX / "sample_exam.md").read_text(encoding="utf-8"))
    qs = list(doc.iter_questions())
    assert len(qs) >= 12
    assert any(b.__class__.__name__ == "QuestionSet" for b in doc.blocks)
    assert any(q.placeholders for q in qs)
