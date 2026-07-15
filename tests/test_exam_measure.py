
from hwpx.visual.oracle import WordBox
from hwpx.exam.measure import column_x_bounds, group_question_blocks


def _g(text, x, y, page=0, line=0):
    return WordBox(x0=x, y0=y, x1=x + 8, y1=y + 12, text=text, page=page, block=0, line=line, word_no=0)


def test_column_x_bounds_splits_left_right_at_gutter():
    glyphs = [_g("가", 10, 10), _g("나", 20, 10), _g("다", 330, 10), _g("라", 340, 10)]
    bounds = column_x_bounds(glyphs)
    assert len(bounds) == 2
    assert bounds[0][1] < bounds[1][0]  # left max-x < right min-x


def test_group_question_blocks_slices_on_number_marker():
    # line 0: "1." marker ; line 1: choice ; line 2: "2." marker
    glyphs = [
        _g("1", 10, 10, line=0), _g(".", 18, 10, line=0),
        _g("①", 10, 30, line=1), _g("가", 18, 30, line=1),
        _g("2", 10, 50, line=2), _g(".", 18, 50, line=2),
    ]
    blocks = group_question_blocks(glyphs)
    assert [b.id for b in blocks] == ["1", "2"]
    assert len(blocks[0].glyphs) == 4  # "1." + choice line belong to Q1


def test_valid_ids_ignores_chrome_numbers_and_detects_curve_export():
    # A "2026." chrome line (a year in the form's preserved 관리박스) plus a real
    # composed "1." 문항. With valid_ids scoped to the composed numbers, the
    # chrome year is NOT a marker; with NO composed 문항 present, n_blocks == 0
    # (the signal the driver reads as a curve-export / unverifiable render).
    chrome = [
        _g("2", 10, 10, line=0), _g("0", 16, 10, line=0), _g("2", 22, 10, line=0),
        _g("6", 28, 10, line=0), _g(".", 34, 10, line=0),
    ]
    q1 = [_g("1", 10, 40, line=1), _g(".", 18, 40, line=1), _g("가", 26, 40, line=1)]

    # unscoped: the chrome "2026." opens a spurious block (set — order depends on
    # the column/reading-order heuristic, which is not what this test pins)
    assert {b.id for b in group_question_blocks(chrome + q1)} == {"2026", "1"}
    # scoped to composed {"1"}: only the real 문항 is a block; chrome ignored
    assert [b.id for b in group_question_blocks(chrome + q1, valid_ids={"1"})] == ["1"]
    # chrome only, scoped to composed {"1".."14"}: zero blocks -> curve-export signal
    assert group_question_blocks(chrome, valid_ids={str(i) for i in range(1, 15)}) == []
