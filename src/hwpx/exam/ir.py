"""Normalized exam model (Exam IR). Metadata lives in the form's 관리박스, NOT here."""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Placeholder:
    id: str           # e.g. "그림1"
    kind: str         # "img" | "table" | "equation"
    raw_text: str     # literal marker preserved verbatim, e.g. "[그림1]"


@dataclass(frozen=True, slots=True)
class Question:
    number: str                                  # literal 문항 number text, e.g. "1"
    stem: str                                    # 발문
    choices: tuple[str, ...] = ()                # 답항 ①~⑤, literal markers included
    points: str | None = None                    # 배점, e.g. "3"; None if absent
    placeholders: tuple[Placeholder, ...] = ()   # [그림N]/[표N]/[식N] referenced by this 문항


@dataclass(frozen=True, slots=True)
class QuestionSet:                               # 세트문제 (shared 공통지문)
    passage: str
    rng: str                                     # e.g. "3∼4"
    members: tuple[Question, ...] = ()


@dataclass(frozen=True, slots=True)
class ExamDoc:
    title: str = ""
    blocks: tuple[Question | QuestionSet, ...] = ()

    def iter_questions(self) -> Iterator[Question]:
        for block in self.blocks:
            if isinstance(block, QuestionSet):
                yield from block.members
            else:
                yield block
