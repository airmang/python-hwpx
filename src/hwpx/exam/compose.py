"""Lower the Exam IR into the school form's body region.

Strategy (Phase-0 grounded): map each role onto the form's EXISTING style,
attach keepWithNext (column cohesion) to every paragraph of a 문항 except its
last, and INSERT into the body region [body_start..body_end] — never append
(Hancom drops appended content)."""
from __future__ import annotations

from dataclasses import dataclass

from hwpx.document import HwpxDocument
from hwpx.form_fit.wordbox import detect_overflow, extract_cell_clips, extract_glyph_boxes
from hwpx.visual.oracle import resolve_oracle

from .ir import ExamDoc, Question, QuestionSet
from .measure import measure_question_splits
from .parser import parse_exam_markdown
from .profile import FormProfile, ResolvedStyle, profile_form


@dataclass(slots=True)
class ParaSpec:
    text: str
    role: str               # key into FormProfile.role_styles
    keep_with_next: bool
    is_question_head: bool
    question_number: str | None


def _choice_role(n_choices: int, idx: int) -> str:
    # answer-row styles encode a "rows" hint; default to choice1, fall back gracefully
    return "choice1"


def _lower_question(q: Question) -> list[ParaSpec]:
    specs: list[ParaSpec] = [
        ParaSpec(
            text=f"{q.number}. {q.stem}".rstrip(),
            role="number",
            keep_with_next=True,
            is_question_head=True,
            question_number=q.number,
        )
    ]
    for i, choice in enumerate(q.choices):
        specs.append(ParaSpec(text=choice, role=_choice_role(len(q.choices), i),
                              keep_with_next=True, is_question_head=False, question_number=q.number))
    for ph in q.placeholders:
        # keep the literal placeholder on its own line so a human can find it
        specs.append(ParaSpec(text=ph.raw_text, role="normal", keep_with_next=True,
                              is_question_head=False, question_number=q.number))
    if specs:
        specs[-1].keep_with_next = False  # last para of the 문항 may break before the next
    return specs


def lower_exam(exam: ExamDoc, profile: FormProfile) -> list[ParaSpec]:
    specs: list[ParaSpec] = []
    for block in exam.blocks:
        if isinstance(block, QuestionSet):
            specs.append(ParaSpec(text=block.passage, role="box", keep_with_next=True,
                                  is_question_head=False, question_number=None))
            for member in block.members:
                specs.extend(_lower_question(member))
        else:
            specs.extend(_lower_question(block))
    # drop roles the form lacks -> fall back to "normal"
    for s in specs:
        if s.role not in profile.role_styles:
            s.role = "normal"
    return specs


def _keep_para_pr(doc: HwpxDocument, base: ResolvedStyle, keep: bool, cache: dict) -> str | None:
    key = (base.name, keep)
    if key in cache:
        return cache[key]
    pid = doc.oxml.headers[0].ensure_paragraph_format(
        base_para_pr_id=base.para_pr_id,
        break_setting={"keep_with_next": keep, "keep_lines": True},
    )
    cache[key] = pid
    return pid


@dataclass(slots=True)
class ComposePlan:
    """Snapshot of a pending composition: specs + the target profile.

    Passed to replace_body_region when the caller wants to defer materialization
    (e.g. inspect specs before writing to the document)."""
    specs: list[ParaSpec]
    profile: FormProfile


def replace_body_region(doc: HwpxDocument, profile: FormProfile, specs: list[ParaSpec]) -> dict[str, int]:
    section = doc.sections[0]
    paragraphs = section.paragraphs
    start, end = profile.body_start, profile.body_end
    old_slots = [paragraphs[i] for i in range(start, end + 1)]  # capture wrappers up front

    cache: dict = {}
    temp = []
    for spec in specs:
        style = profile.role_styles.get(spec.role) or profile.role_styles["normal"]
        para_pr_id = _keep_para_pr(doc, style, spec.keep_with_next, cache)
        temp.append(
            section.add_paragraph(  # appended to tail; cloned into body below, then removed
                spec.text,
                para_pr_id_ref=para_pr_id,
                style_id_ref=style.style_id,
                char_pr_id_ref=style.char_pr_id,
                inherit_style=False,
            )
        )

    inserted = section.insert_paragraphs(start, temp)   # deep-clone into the body
    for wrapper in reversed(temp):
        section.remove_paragraph(wrapper)               # drop the temporary tail copies
    for wrapper in old_slots:
        section.remove_paragraph(wrapper)               # drop the old form slots
    section.mark_dirty()

    # `inserted` is index-aligned with `specs`; each 문항 head now lives at
    # body-region offset `start + offset`. Build the convergence anchor map.
    anchors: dict[str, int] = {}
    for offset, spec in enumerate(specs):
        if spec.is_question_head and spec.question_number is not None:
            anchors[spec.question_number] = start + offset
    return anchors


# ---------------------------------------------------------------------------
# Convergence driver (Task 8)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ComposeResult:
    out_path: str
    render_checked: bool
    splits: int | None
    overflow: int | None
    placeholders_ok: bool
    rounds: int
    needs_review: bool
    notes: tuple[str, ...]


def _insert_break(section, head_index: int, kind: str) -> None:
    attr = "pageBreak" if kind == "page" else "columnBreak"
    section.paragraphs[head_index].element.set(attr, "1")
    section.mark_dirty()


def compose_exam_into_form(
    form_path: str,
    exam_md: str,
    out_path: str,
    *,
    oracle=None,
    max_rounds: int = 2,
    role_style_names=None,
) -> ComposeResult:
    notes: list[str] = []
    exam = parse_exam_markdown(exam_md)
    expected_ph = {ph.raw_text for q in exam.iter_questions() for ph in q.placeholders}

    doc = HwpxDocument.open(form_path)
    prof = profile_form(doc, role_style_names=role_style_names)
    specs = lower_exam(exam, prof)
    anchors = replace_body_region(doc, prof, specs)
    doc.save_to_path(out_path)
    notes.append(
        f"composed {len(list(exam.iter_questions()))} 문항 into body"
        f" [{prof.body_start}..{prof.body_end}]"
    )

    if oracle is None:
        oracle = resolve_oracle()
    if not oracle.available():
        notes.append("oracle unavailable -> render_checked=false, needs_review=true (no silent true)")
        return ComposeResult(out_path, False, None, None, True, 0, True, tuple(notes))

    rounds = 0
    splits = overflow = None
    placeholders_ok = True
    while rounds < max_rounds:
        rounds += 1
        pdf = oracle.render_pdf(out_path)
        if not pdf:
            notes.append(f"round {rounds}: render returned None -> render_checked=false")
            return ComposeResult(out_path, False, None, None, True, rounds, True, tuple(notes))
        report = measure_question_splits(pdf)
        glyphs = extract_glyph_boxes(pdf)
        clips = extract_cell_clips(pdf)
        rendered_text = "".join(g.text for g in glyphs)
        placeholders_ok = all(
            ph.replace(" ", "") in rendered_text.replace(" ", "")
            for ph in expected_ph
        )
        overflow = len(detect_overflow(glyphs, clips))
        splits = report.n_splits
        notes.append(
            f"round {rounds}: splits={splits} kinds={report.kinds}"
            f" overflow={overflow} ph_ok={placeholders_ok}"
        )
        if splits == 0:
            break
        # fix: force a break on each straddling 문항's head paragraph, then re-render
        section = doc.sections[0]
        for block_id in report.split_ids:
            head_index = anchors.get(block_id)
            if head_index is None:
                notes.append(f"round {rounds}: split id {block_id!r} has no anchor (skipped)")
                continue
            kind = "page" if report.kinds.get("page") else "column"
            _insert_break(section, head_index, kind)
        doc.save_to_path(out_path)

    needs_review = splits is None or splits > 0 or not placeholders_ok
    return ComposeResult(out_path, True, splits, overflow, placeholders_ok, rounds, needs_review, tuple(notes))
