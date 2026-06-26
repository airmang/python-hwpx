from hwpx.exam import ir


def test_iter_questions_flattens_sets_in_order():
    q1 = ir.Question(number="1", stem="발문1")
    q3 = ir.Question(number="3", stem="발문3")
    q4 = ir.Question(number="4", stem="발문4")
    qset = ir.QuestionSet(passage="공통지문", rng="3∼4", members=(q3, q4))
    doc = ir.ExamDoc(title="중간고사", blocks=(q1, qset))
    assert [q.number for q in doc.iter_questions()] == ["1", "3", "4"]


def test_question_is_frozen_and_carries_choices_points_placeholders():
    ph = ir.Placeholder(id="그림1", kind="img", raw_text="[그림1]")
    q = ir.Question(number="2", stem="발문", choices=("① 가", "② 나"), points="3", placeholders=(ph,))
    assert q.points == "3" and q.choices[0] == "① 가" and q.placeholders[0].kind == "img"
    import dataclasses, pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        q.points = "5"  # type: ignore[misc]
