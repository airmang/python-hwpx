import copy

from hwpx.document import HwpxDocument
from hwpx.exam import ir
from hwpx.exam.compose import lower_exam, replace_body_region
from hwpx.exam.profile import profile_form
from pathlib import Path

FIX = Path(__file__).parent / "fixtures" / "exam"


def _exam():
    q1 = ir.Question(number="1", stem="발문 하나", choices=("① 가", "② 나"), points="3")
    ph = ir.Placeholder(id="그림1", kind="img", raw_text="[그림1]")
    # Real parser keeps the [그림N] marker INLINE in the stem (parser.py) and also
    # records it in .placeholders; the fixture mirrors that so the composer is
    # exercised the way live input reaches it.
    q2 = ir.Question(number="2", stem="발문 둘 [그림1]", choices=("① 다", "② 라"), placeholders=(ph,))
    return ir.ExamDoc(title="t", blocks=(q1, q2))


def test_lower_sets_keep_with_next_on_all_but_last_para_of_each_question():
    doc = HwpxDocument.open(FIX / "A_form.hwpx")
    profile = profile_form(doc)
    specs = lower_exam(_exam(), profile)
    # group specs by question head boundaries
    heads = [i for i, s in enumerate(specs) if s.is_question_head]
    assert len(heads) == 2
    q1_specs = specs[heads[0]:heads[1]]
    assert all(s.keep_with_next for s in q1_specs[:-1])
    assert q1_specs[-1].keep_with_next is False
    # literal number prefix + placeholder preserved verbatim
    assert specs[heads[0]].text.startswith("1.")
    assert any("[그림1]" in s.text for s in specs)


def test_stem_placeholder_rendered_exactly_once():
    # Regression: the parser leaves [그림N] inline in the stem AND lists it in
    # Question.placeholders. The composer must render the marker once (from the
    # stem) and must NOT also emit a standalone placeholder paragraph, or it
    # appears twice in the body. (compose.py _lower_question)
    doc = HwpxDocument.open(FIX / "A_form.hwpx")
    profile = profile_form(doc)
    ph = ir.Placeholder(id="그림1", kind="img", raw_text="[그림1]")
    q = ir.Question(number="1", stem="도형 [그림1] 을 보고", choices=("① 가", "② 나"),
                    placeholders=(ph,))
    specs = lower_exam(ir.ExamDoc(title="t", blocks=(q,)), profile)
    occurrences = sum(s.text.count("[그림1]") for s in specs)
    assert occurrences == 1, f"placeholder should render once, got {occurrences}"


def test_replace_body_region_inserts_into_body_and_preserves_admin_box_and_tail():
    doc = HwpxDocument.open(FIX / "A_form.hwpx")
    profile = profile_form(doc)
    section = doc.sections[0]
    admin_before = copy.deepcopy(section.paragraphs[0].element)
    tail_index = profile.body_end + 1
    tail_before = (
        copy.deepcopy(section.paragraphs[tail_index].element)
        if tail_index < len(section.paragraphs) else None
    )

    specs = lower_exam(_exam(), profile)
    anchors = replace_body_region(doc, profile, specs)

    # 관리박스 para[0] byte-identical (Lossless VII).
    # Note: compare detached copies because lxml serialises in-tree elements with all
    # ancestor namespace declarations; deepcopy detaches the element so only its own
    # declared namespaces appear.  The element CONTENT must be byte-identical; the
    # namespace context difference is a serialisation artefact, not a content change.
    import copy as _copy
    from lxml import etree
    after_admin = _copy.deepcopy(doc.sections[0].paragraphs[0].element)
    assert etree.tostring(after_admin) == etree.tostring(admin_before)
    # preserved tail still present & identical (if the form has body-stream footer paras).
    # Same namespace-serialisation note: compare detached copies for both sides.
    if tail_before is not None:
        tails = [etree.tostring(_copy.deepcopy(p.element)) for p in doc.sections[0].paragraphs]
        assert etree.tostring(tail_before) in tails
    # the composed 문항 text now lives in the body (round-trips through save/open)
    import io
    buf = io.BytesIO(); doc.save(buf)
    text = "".join(p.text or "" for p in HwpxDocument.open(io.BytesIO(buf.getvalue())).paragraphs)
    assert "발문 하나" in text and "발문 둘" in text and "[그림1]" in text
    assert set(anchors) == {"1", "2"}
