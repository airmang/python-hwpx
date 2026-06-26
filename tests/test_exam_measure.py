import re

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
