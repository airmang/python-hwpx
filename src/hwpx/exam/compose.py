"""Lower the Exam IR into the school form's body region.

Strategy (Phase-0 grounded): map each role onto the form's EXISTING style,
attach keepWithNext (column cohesion) to every paragraph of a 문항 except its
last, and INSERT into the body region [body_start..body_end] — never append
(Hancom drops appended content)."""
from __future__ import annotations

from dataclasses import dataclass

from hwpx.document import HwpxDocument

from .ir import ExamDoc, Question, QuestionSet
from .profile import FormProfile, ResolvedStyle


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
