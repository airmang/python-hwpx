"""Exam re-typesetting (조판): authored exam Markdown -> school form .hwpx body."""
from __future__ import annotations

from .compose import ComposePlan, ParaSpec, lower_exam, replace_body_region
from .ir import ExamDoc, Placeholder, Question, QuestionSet
from .measure import (
    SplitReport,
    column_x_bounds,
    group_question_blocks,
    measure_question_splits,
)
from .parser import ExamParseError, parse_exam_markdown
from .profile import FormProfile, FormProfileError, ResolvedStyle, profile_form

__all__ = [
    "ExamDoc", "Placeholder", "Question", "QuestionSet",
    "ExamParseError", "parse_exam_markdown",
    "FormProfile", "FormProfileError", "ResolvedStyle", "profile_form",
    "column_x_bounds", "group_question_blocks", "measure_question_splits", "SplitReport",
    "ParaSpec", "lower_exam", "replace_body_region", "ComposePlan",
]
