import pytest

from hwpx.exam import ExamDoc, Question, QuestionSet
from hwpx.exam.parser import ExamParseError, parse_exam_markdown

SAMPLE = """# 중간고사

## 1. (3점)
다음 설명으로 옳은 것은?
① 가
② 나
③ 다
④ 라
⑤ 마

## 2.
[그림1]
그림을 보고 답하시오.
① 하나
② 둘

## 3∼4. 세트
다음 글을 읽고 물음에 답하시오.
### 3. (2점)
발문 셋
① 가
② 나
### 4.
발문 넷
① 가
② 나
"""


def test_parses_title_questions_set_points_choices_placeholder():
    doc = parse_exam_markdown(SAMPLE)
    assert isinstance(doc, ExamDoc)
    assert doc.title == "중간고사"
    assert len(doc.blocks) == 3  # Q1, Q2, set(3∼4)

    q1 = doc.blocks[0]
    assert isinstance(q1, Question) and q1.number == "1" and q1.points == "3"
    assert q1.stem == "다음 설명으로 옳은 것은?"
    assert q1.choices == ("① 가", "② 나", "③ 다", "④ 라", "⑤ 마")

    q2 = doc.blocks[1]
    assert q2.number == "2" and q2.points is None
    assert q2.placeholders[0].id == "그림1" and q2.placeholders[0].kind == "img"

    qset = doc.blocks[2]
    assert isinstance(qset, QuestionSet) and qset.rng == "3∼4"
    assert qset.passage == "다음 글을 읽고 물음에 답하시오."
    assert [m.number for m in qset.members] == ["3", "4"]
    assert qset.members[0].points == "2"

    # flatten reaches every 문항 in order
    assert [q.number for q in doc.iter_questions()] == ["1", "2", "3", "4"]


def test_content_before_any_question_header_fails_loud():
    with pytest.raises(ExamParseError) as exc:
        parse_exam_markdown("본문이 문항 헤더 없이 먼저 나온다.\n## 1.\n발문\n")
    assert exc.value.line_no == 1


def test_choice_inside_set_before_any_member_fails_loud():
    # A 답항(choice) cannot exist without an active 문항. Inside an open 세트
    # but before the first '### N.' member, a circled-digit line must raise —
    # it must NOT be silently swallowed into the set passage.
    md = "## 3∼4. 세트\n다음 글을 읽고 물음에 답하시오.\n① 가\n### 3.\n발문\n"
    with pytest.raises(ExamParseError) as exc:
        parse_exam_markdown(md)
    assert exc.value.line_no == 3
    assert exc.value.text == "① 가"
