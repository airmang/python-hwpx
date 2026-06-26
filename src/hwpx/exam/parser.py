"""Parse the recommended exam-md convention into the Exam IR.

The skill authors this md, so the grammar is strict and any unattributable
line fails loud (Constitution VI/IX — no silently wrong layout)."""
from __future__ import annotations

import re

from hwpx.tools.table_cleanup import normalize_cell_text

from .ir import ExamDoc, Placeholder, Question, QuestionSet

_TITLE_RE = re.compile(r"^#\s+(?P<t>.*\S)\s*$")
_Q_RE = re.compile(r"^##\s+(?P<n>\d+)\.\s*(?:\((?P<p>\d+)\s*점\))?\s*$")
_SET_RE = re.compile(r"^##\s+(?P<a>\d+)\s*[~∼-]\s*(?P<b>\d+)\.\s*세트\s*$")
_MEMBER_RE = re.compile(r"^###\s+(?P<n>\d+)\.\s*(?:\((?P<p>\d+)\s*점\))?\s*$")
_CHOICE_RE = re.compile(r"^\s*(?P<mark>[①②③④⑤⑥⑦⑧⑨⑩])\s*(?P<t>.*)$")
_PLACEHOLDER_RE = re.compile(r"\[(?P<k>그림|표|식)\s*(?P<n>\d+)\]")

_KIND = {"그림": "img", "표": "table", "식": "equation"}


class ExamParseError(ValueError):
    def __init__(self, line_no: int, text: str, reason: str) -> None:
        super().__init__(f"line {line_no}: {reason}: {text!r}")
        self.line_no = line_no
        self.text = text
        self.reason = reason


class _QBuf:
    """Accumulates one 문항 across lines, then freezes to a Question."""

    def __init__(self, number: str, points: str | None) -> None:
        self.number = number
        self.points = points
        self.stem_lines: list[str] = []
        self.choices: list[str] = []
        self.placeholders: list[Placeholder] = []

    def add_text(self, text: str) -> None:
        for m in _PLACEHOLDER_RE.finditer(text):
            pid = f"{m.group('k')}{m.group('n')}"
            self.placeholders.append(Placeholder(id=pid, kind=_KIND[m.group("k")], raw_text=m.group(0)))
        self.stem_lines.append(text)

    def add_choice(self, mark: str, text: str) -> None:
        self.choices.append(f"{mark} {text}".rstrip())

    def freeze(self) -> Question:
        return Question(
            number=self.number,
            stem=normalize_cell_text(" ".join(self.stem_lines)),
            choices=tuple(self.choices),
            points=self.points,
            placeholders=tuple(self.placeholders),
        )


def parse_exam_markdown(md: str, *, title: str = "") -> ExamDoc:
    blocks: list[Question | QuestionSet] = []
    cur_q: _QBuf | None = None
    set_open = False
    set_rng = ""
    set_passage: list[str] = []
    set_members: list[Question] = []

    def flush_q() -> None:
        nonlocal cur_q
        if cur_q is None:
            return
        q = cur_q.freeze()
        if set_open:
            set_members.append(q)
        else:
            blocks.append(q)
        cur_q = None

    def flush_set() -> None:
        nonlocal set_open, set_rng, set_passage, set_members
        if not set_open:
            return
        blocks.append(
            QuestionSet(
                passage=normalize_cell_text(" ".join(set_passage)),
                rng=set_rng,
                members=tuple(set_members),
            )
        )
        set_open, set_rng, set_passage, set_members = False, "", [], []

    for i, raw in enumerate(md.splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip():
            continue

        m_set = _SET_RE.match(line)
        if m_set:
            flush_q()
            flush_set()
            set_open = True
            set_rng = f"{m_set.group('a')}∼{m_set.group('b')}"
            continue

        m_member = _MEMBER_RE.match(line)
        if m_member:
            if not set_open:
                raise ExamParseError(i, line, "'### N.' member outside a 세트 header")
            flush_q()
            cur_q = _QBuf(m_member.group("n"), m_member.group("p"))
            continue

        m_q = _Q_RE.match(line)
        if m_q:
            flush_q()
            flush_set()
            cur_q = _QBuf(m_q.group("n"), m_q.group("p"))
            continue

        m_title = _TITLE_RE.match(line)
        if m_title and not blocks and cur_q is None and not set_open:
            title = title or normalize_cell_text(m_title.group("t"))
            continue

        m_choice = _CHOICE_RE.match(line)
        if m_choice:
            # A 답항(choice) cannot exist without an active 문항. Even inside an
            # open 세트, a choice before the first member must fail loud rather
            # than be silently swallowed into the set passage.
            if cur_q is None:
                raise ExamParseError(i, line, "답항(choice) outside any 문항")
            cur_q.add_choice(m_choice.group("mark"), normalize_cell_text(m_choice.group("t")))
            continue

        # plain content line: belongs to the current 문항 stem, or the set passage
        if cur_q is not None:
            cur_q.add_text(line.strip())
        elif set_open:
            set_passage.append(line.strip())
        else:
            raise ExamParseError(i, line, "content before any 문항 / 세트 header")

    flush_q()
    flush_set()
    return ExamDoc(title=title, blocks=tuple(blocks))
