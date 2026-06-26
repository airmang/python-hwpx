from hwpx.visual.oracle import WordBox, Block, detect_block_splits

LEFT = (0.0, 300.0)
RIGHT = (320.0, 620.0)


def _g(x, page=0):
    return WordBox(x0=x, y0=10, x1=x + 8, y1=22, text="가", page=page,
                   block=0, line=0, word_no=0)


def test_block_wholly_in_one_column_is_not_a_split():
    block = Block(id="q1", glyphs=[_g(10), _g(20), _g(30)])
    assert detect_block_splits([block], [LEFT, RIGHT], page_height=800.0) == []


def test_block_straddling_two_columns_is_flagged():
    block = Block(id="q2", glyphs=[_g(10), _g(330)])  # left + right column
    splits = detect_block_splits([block], [LEFT, RIGHT], page_height=800.0)
    assert [s.block_id for s in splits] == ["q2"]
    assert splits[0].kind == "column"


def test_block_straddling_two_pages_is_flagged():
    block = Block(id="q3", glyphs=[_g(10, page=0), _g(20, page=1)])
    splits = detect_block_splits([block], [LEFT, RIGHT], page_height=800.0)
    assert splits[0].kind == "page"
