# SPDX-License-Identifier: Apache-2.0
"""Flow measurement and pagination implementation for :mod:`.pages`.

The facade remains the owner of shared helpers. Resolving them at call time
preserves existing private monkeypatch hooks without a circular from-import.
"""
from __future__ import annotations


def _drawn_lines(measure: _pages._Measure, paragraphs: list[_pages.Any], width: int | None = None, cell: int | None = None
                 ) -> tuple[tuple[tuple[int, int], ...], tuple[_pages._Reach, ...]]:
    """(height, advance) of every line of *paragraphs* as Hancom placed them, when every paragraph keeps a
    valid layout cache; the last line reaches down to the foot of any top-and-bottom or square-wrapped
    object placed from its paragraph that moves with the text. A picture or drawing stands from the top of
    the line its control falls on (see :meth:`_Measure.wrapped_lines`): in a cell *width* wide, the line
    laid out at the whole width, which is the first one narrower than that when the lines beside the object
    broke again (for a table, so in a cell *cell* wide too). A table, with a caption above or below it, stands
    from its paragraph's top (where the first line would stand without it) on the first line, and from the top
    of the line its control falls on, where that line would follow the one before, on a later one; so does one
    in front of or behind the text moving with it (from the paragraph's top above its spacing before on the
    first line), which pushes no line but makes the cell reach its foot.
    A row that went on over a page end has its cell's lines start over at the top of the next page: a
    line above where it would follow the one before (that one's height and spacing below it, or the
    paragraph's top for a paragraph's first line, the part starting at that top) stands where it would
    in the unsplit cell, and so does a line that starts the part below a table placed top and bottom on it
    (the table went on with it). A paragraph's first line below an object placed from its top takes the room
    above it, and so does a later line below a table placed top and bottom on it. Empty otherwise; not followed
    when a table on a later line, or in front of or behind the text, is not as tall as its rows (Hancom split
    it over a page end). Also where those tables stand among the lines (see :class:`_Reach`)."""

    if not paragraphs or not all(_pages._cached_metrics(paragraph) for paragraph in paragraphs):
        return (), ()
    tops: list[int] = []
    heights: list[int] = []
    reaches: list[_pages._Reach] = []
    foot, after, base = 0, 0, 0  # after: where the next paragraph's first line would stand
    for paragraph in paragraphs:
        shape = measure.shape(paragraph.get("paraPrIDRef"))
        start = after if tops else 0  # the paragraph's top, above its spacing before
        top = start + shape.prev if tops else 0
        first = len(tops)  # the paragraph's first line's index
        segments = paragraph.findall(f"{_pages.HP}linesegarray/{_pages.HP}lineseg")
        runs = paragraph.findall(f"{_pages.HP}run")
        objects = []
        floats = []  # tables in front of or behind the text
        for obj in (child for run in runs for child in run if _pages._local(child) in _pages._OBJECTS):
            pos = obj.find(f"{_pages.HP}pos")
            if pos is None or pos.get("treatAsChar") == "1":
                continue
            if _pages._floating(obj):
                if _pages._local(obj) == "tbl":
                    if pos.get("flowWithText") == "0" or pos.get("vertRelTo") != "PARA" \
                            or pos.get("vertAlign", "TOP") != "TOP":
                        return (), ()
                    floats.append(obj)
                continue
            if obj.get("textWrap") not in ("TOP_AND_BOTTOM", "SQUARE") or pos.get("vertRelTo") != "PARA":
                return (), ()
            if _pages._local(obj) != "tbl" and pos.get("flowWithText") == "0":  # stays put: pushes no line, the row
                continue  # as it is
            objects.append(obj)
        lines = {id(obj): _pages._anchor_line(measure, paragraph, runs, "", obj, [], 0, None, ((0, 0),), len(segments))
                 for obj in (*objects, *floats) if _pages._local(obj) == "tbl"}
        whole = width if width is not None else cell
        if whole is not None:  # the lines beside a table Hancom broke anew, narrower: it stands from the line it
            full = whole - shape.left - shape.right  # fell on at the cell's whole width, the first of them
            lines = {key: next((index for index, segment in enumerate(segments[:line])
                                if int(segment.get("horzsize", 0)) < full - (abs(shape.indent) if index == 0 else 0)),
                               line) for key, line in lines.items()}
        pushing: dict[int, _pages.Any] = {}  # a later line: the table placed top and bottom on it (or so wrapped square)
        for obj in (*objects, *floats):
            if _pages._local(obj) != "tbl" or not lines[id(obj)] and obj not in floats:
                continue
            if int(obj.find(f"{_pages.HP}sz").get("height", 0)) != _pages._inline_table_height(measure, obj):
                raise _pages._Unsupported("a table in a cell not as tall as its rows (split over a page end)")
            if obj in objects and (obj.get("textWrap") == "TOP_AND_BOTTOM"
                                   or whole is not None and _pages._wraps_top_and_bottom(obj, whole)):
                pushing[lines[id(obj)]] = obj
        follows: list[int] = []  # where each line would follow the one before
        moved: set[int] = set()  # the lines below a table on a later line
        below = top  # where the paragraph's next line would stand
        for index, segment in enumerate(segments):
            vertpos = int(segment.get("vertpos", 0))
            follows.append(below)
            table = pushing.get(index)
            if table is not None and vertpos == _pages._cell_extent(measure, table) + _pages._down(table.find(f"{_pages.HP}pos")) \
                    and base < below:  # the next page's part of a split row, starting below the table that went
                base = below  # on with the line
            elif tops and vertpos + base < below:  # the next page's part of a split row: the lines start over
                base = (top if index == 0 else below) - (0 if index == 0 else vertpos)
            tops.append(vertpos + base)
            heights.append(int(segment.get("textheight", segment.get("vertsize", 0))))
            below = tops[-1] + int(segment.get("vertsize", 0)) + int(segment.get("spacing", 0))
            if index == 0 and tops[-1] > top:  # below an object placed from the paragraph's top: the line
                heights[-1] += tops[-1] - top  # takes the room above it, and goes on to a next page with it
                tops[-1] = top
            elif table is not None and tops[-1] > follows[-1]:  # so below a table on a later line
                heights[-1] += tops[-1] - follows[-1]
                tops[-1] = follows[-1]
                moved.add(index)
        for obj in (*objects, *floats):
            if _pages._local(obj) == "tbl":
                line = lines[id(obj)]
                if not line and obj not in floats:  # from the paragraph's top
                    foot = max(foot, top + _pages._down(obj.find(f"{_pages.HP}pos")) + _pages._extent(obj, "height", measure)
                               + sum(_pages._caption(measure, obj)))
                    continue
                up = (start if line == 0 else follows[line]) + _pages._down(obj.find(f"{_pages.HP}pos"))
                foot = max(foot, up + _pages._cell_extent(measure, obj))
                if pushing.get(line) is obj:  # it pushes that very line
                    reaches.append(_pages._Reach(follows[line], up, up + _pages._cell_extent(measure, obj), _pages._table_first(measure, obj),
                                          follows[line] if line in moved else None,
                                          int(segments[line].get("textheight", 0)), *_pages._split_rows(measure, obj)))
                else:
                    reaches.append(_pages._Reach(follows[line] if line else top, up, up + _pages._cell_extent(measure, obj)))
                continue
            # a picture or drawing stands its offset below the top of the line its control falls on, where
            # that line would follow the one before (Hancom then moves it clear), or of the paragraph, above
            # its spacing before, on its first line
            line = _pages._anchor_line(measure, paragraph, paragraph.findall(f"{_pages.HP}run"), "", obj, [], 0, None,
                                ((0, 0),), len(segments))
            if width is not None:  # the lines beside it Hancom broke anew, narrower: it stands from the line
                full = width - shape.left - shape.right  # it fell on at the cell's whole width, the first of them
                line = next((index for index, segment in enumerate(segments[:line])
                             if int(segment.get("horzsize", 0)) < full - (abs(shape.indent) if index == 0 else 0)),
                            line)
            up = start if line == 0 else \
                tops[first + line - 1] + heights[first + line - 1] + int(segments[line - 1].get("spacing", 0))
            foot = max(foot, up + _pages._down(obj.find(f"{_pages.HP}pos")) + _pages._extent(obj, "height", measure))
        last = segments[-1]
        after = int(last.get("vertpos", 0)) + base + int(last.get("textheight", 0)) + int(last.get("spacing", 0)) \
            + shape.next
    if any(later < earlier for earlier, later in zip(tops, tops[1:])):  # noqa: RUF007 - preserve the existing layout implementation
        return (), ()
    heights[-1] = max(heights[-1], foot - tops[-1])
    return tuple((height, (nxt - top) if nxt is not None else height)
                 for height, top, nxt in zip(heights, tops, [*tops[1:], None])), tuple(reaches)


def _paragraph(measure: _pages._Measure, page: _pages._Page, paragraph: _pages.Any, wrap: _pages._Wrap | None = None,
               square: _pages.Any = None, stacked: tuple[_pages.Any, ...] = ()) -> _pages._Para:
    runs = paragraph.findall(f"{_pages.HP}run")
    objects = [obj for obj in _pages._placed_objects(runs)
               if obj is not square and all(obj is not other for other in stacked)]
    if page.unequal and any(obj.find(f"{_pages.HP}pos").get("treatAsChar") != "1" for obj in objects):
        raise _pages._Unsupported("an object not set as a character in columns of unequal width")
    reflow = page.unequal and not _pages._cached_metrics(paragraph)  # its lines depend on the column's width
    if reflow and (objects or _pages._marks(runs) or _pages._note_anchors(runs)):
        raise _pages._Unsupported("objects, composed characters, ruby text or footnotes in a paragraph without a "
                           "layout cache in columns of unequal width")
    text = _pages._run_text(runs)
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    headed = bool(objects) and not text and measure.headed(paragraph)  # its label is text too
    beside = bool(objects) and not text and _pages._beside_floating(runs)  # its empty line goes below the object
    anchored = _pages._anchored_object(objects, text, page.column_width, headed or beside)
    marks = _pages._marks(runs) and not _pages._cached_metrics(paragraph)  # to lay out like characters
    if marks:
        if anchored is not None or wrap is not None or square is not None:
            raise _pages._Unsupported("composed characters or ruby text beside an object placed otherwise")
        _pages._check_ruby_spacing(runs, shape)
    among = anchored is None and (marks or bool(objects) and (len(objects) > 1 or bool(text.strip())))
    beside = anchored is not None and len(objects) > 1  # objects set as characters on the lines below it
    alone = bool(objects) and not among and anchored is None  # an object with no text: one line as tall
    cached = () if alone else _pages._cached_metrics(paragraph)
    size, refs, sizes = _pages._text_size(measure, runs, paragraph)
    style = measure.style(paragraph.get("paraPrIDRef"), refs, paragraph)
    widths: list[float] = _pages._indented(page.column_width - shape.left - shape.right, shape, style)
    end = _pages._end_size(measure, runs, sizes)
    head = _pages._head_size(measure, paragraph, sizes)
    held = _pages._held_sizes(measure, runs, sizes)
    mixed = len(set(sizes)) > 1 or bool(end) or bool(head) or bool(held) or (shape.font_line and bool(sizes))
    looks = _pages._char_styles(measure, paragraph, runs)
    lead = 0  # how far the paragraph's first line goes down below a square-wrapped object's band
    anchor_line = None  # the line the anchored object stands at, when the lines laid out here put it there
    if alone and wrap is None:  # spaces besides it, those that do not fit going on to the next line
        spread = measure.spread_lines(paragraph, runs, page.column_width, end, head, caches=True)
        alone, cached = (False, spread) if spread else (alone, cached)
    if among or beside:
        apart = (*stacked, *(() if square is None or square.get("textWrap") != "TOP_AND_BOTTOM" else (square,)))
        inline_text, inline_sizes, inline_looks, placed, marked = _pages._inline_content(measure, paragraph, runs, anchored,
                                                                                  apart)
        if wrap is not None:
            if beside or wrap.split or marked:
                raise _pages._Unsupported("objects set as characters among text beside a square-wrapped object")
            looks_or_none = inline_looks if len(set(inline_looks)) > 1 else None
            lines, lead = _pages._banded_object_lines(measure, inline_text, widths, inline_sizes, style, shape, wrap, placed,
                                               looks_or_none, end, head)
            cached = _pages._cached_jumps(paragraph, cached) if cached else lines
        elif not cached:
            looks_or_none = inline_looks if len(set(inline_looks)) > 1 else None
            tall = _pages._controls_after_wide(measure, runs, objects, widths[0])
            cached = _pages._line_metrics(measure, inline_text, widths, inline_sizes, style, shape, placed, looks_or_none,
                                   marked, end, 0 if tall else head)
            if tall and len(cached) > 1 and tall > cached[1][0]:  # the controls on the line after the table
                cached = (cached[0], (tall, _pages._pitch(shape.kind, shape.value, tall)), *cached[2:])
            if anchored is not None:
                cached, anchor_line = _pages._apart_from_wide(measure, inline_text, widths, inline_sizes, style, placed,
                                                       looks_or_none, marked, cached, size, shape,
                                                       _pages._inline_place(runs, anchored, apart))
    elif not cached and wrap is not None and not alone and text:
        if anchored is not None:
            raise _pages._Unsupported("a top-and-bottom object beside a square-wrapped object")
        widths, firsts = _pages._wrapped_widths(measure, text, widths, size, style, shape, wrap, sizes if mixed else None,
                                         looks)
        cached = _pages._at_one_height(_pages._line_metrics(measure, text, widths, sizes, style, shape, {}, looks, end=end,
                                              head=head, held=held), firsts)
    elif not cached and not alone and (mixed or looks is not None):
        cached = _pages._line_metrics(measure, text, widths, sizes, style, shape, {}, looks, end=end, head=head, held=held)
    count = len(cached) or measure.lines(text, widths, size, style)
    pitch = _pages._pitch(shape.kind, shape.value, size)
    table, moves, floor = None, 0, 0
    if alone:
        if wrap is not None:
            raise _pages._Unsupported("an object beside a square-wrapped object")
        controls = _pages._controls_beside(objects[0], runs, widths[0])
        if controls is not None:  # a table too wide for the line beside controls: spaced from its own run's
            size = max(measure.char_height(run.get("charPrIDRef"))  # characters, or those of the runs holding the
                       for run in (controls[0], *controls[1]))  # controls before it on its line when larger
            pitch = _pages._pitch(shape.kind, shape.value, size)
        elif objects[0].find(f"{_pages.HP}pos").get("treatAsChar") == "1":  # spaced from the largest character size
            size = max(measure.char_height(run.get("charPrIDRef")) for run in runs)  # of any of its runs
            pitch = _pages._pitch(shape.kind, shape.value, size)
        own, own_pitch = size, pitch  # the paragraph's own line, as tall as its characters
        count, size, pitch, table = _pages._object_line(measure, objects[0], count, size, pitch, page.column_width, shape)
        if controls is not None:  # the controls after it on an empty line of their own, as tall as the largest
            before, after = controls[1], controls[2]  # characters of the runs holding them; those before it too
            if not any(child.find(f"{_pages.HP}autoNum") is not None for run in before for child in run  # when they draw
                       if _pages._local(child) == "ctrl"):  # a number, else they stand on the table's line
                before = []
            heights = [max(measure.char_height(run.get("charPrIDRef")) for run in side) if side else None
                       for side in (before, after)]
            empty = [None if height is None else (height, _pages._pitch(shape.kind, shape.value, height))
                     for height in heights]
            cached = tuple(line for line in (empty[0], (size, pitch), empty[1]) if line is not None)
            count = len(cached)
        pos = objects[0].find(f"{_pages.HP}pos")
        offset = _pages._pos_offset(pos, "vertOffset")
        if table is None and pos.get("treatAsChar") != "1" and 0 <= offset < 1 << 31:
            if pos.get("flowWithText") != "0":  # from the paragraph's top down: past the body's foot it goes on
                moves = size if offset or page.alone_at_top else 0  # to the next page's top alone, the line staying
                if controls is None and not cached and not text:
                    if pos.get("allowOverlap") == "1" and offset < own:  # starting on the line: it goes below its foot
                        lead, size, pitch = size, own, own_pitch
                    else:  # the empty line stays: the next paragraph comes below its foot or the line's advance
                        floor, pitch = size, own_pitch
            else:  # it stays on its page, past the foot if it must: only the paragraph's line has to fit there,
                cached = ((own, size),)  # the next paragraph coming below the object
                if controls is None and not text:
                    cached, floor = ((own, own_pitch),), size  # (_Para.floor)
    anchor = None if anchored is None else _pages._anchor(measure, paragraph, runs, text, anchored, widths, size, style,
                                                   cached, count, anchor_line)
    around = 0 if square is None or not text else _pages._anchor_line(measure, paragraph, runs, text, square, widths,
                                                                size, style, cached, count)
    if among and _pages._note_anchors(runs, in_tables=True):
        raise _pages._Unsupported("footnotes in a paragraph with objects among its text")
    notes = _pages._anchored_notes(measure, runs, text, widths, size, style, page.column_width, sizes if mixed else None,
                            looks)
    flags = shape.flags
    para = _pages._Para(count, size, pitch, shape.prev + lead, shape.next, _pages._on(flags, "pageBreakBefore"),
                 _pages._on(flags, "keepLines"), _pages._on(flags, "keepWithNext"), _pages._on(flags, "widowOrphan"),
                 paragraph.get("pageBreak") == "1",
                 paragraph.get("columnBreak") == "1", table, notes, cached, anchor, wrap_anchor=around,
                 hides=page.hide_empty and _pages._holds_nothing(runs))
    if anchored is not None and text and not text.strip(" ") and para.lines == 1:
        para = _pages.replace(para, spaced=True)
    if reflow and text:
        again = _pages._Reflow(measure, text, tuple(sizes), None if looks is None else tuple(looks), style, shape)
        return again.at(para, page.column_width, 0)
    if moves:
        para = _pages.replace(para, moves=moves, own=own)
    if floor:
        para = _pages.replace(para, floor=floor)
    if alone and table is not None and controls is None and not text and pos.get("allowOverlap") == "1"             and 0 <= offset < own:  # allowed to overlap, starting on the line: the line goes below it
        para = _pages.replace(para, under=True)
    if alone and table is None and controls is None and not text and _pages._rises(objects[0], page.column_width):
        up = _pages._pos_offset(objects[0].find(f"{_pages.HP}pos"), "vertOffset") - (1 << 32)
        para = _pages.replace(para, rises=(up, _pages._extent(objects[0], "height", measure), own, own_pitch))
    if page.rebreak and not _pages._cached_metrics(paragraph) and not objects and not marks and not notes:
        if not text:
            return _pages.replace(para, blank=True)
        return _pages.replace(para, reflow=_pages._Reflow(measure, text, tuple(sizes), None if looks is None else tuple(looks),
                                            style, shape, width=page.column_width, end=end, head=head))
    return para


def _wrapped_paragraph(measure: _pages._Measure, page: _pages._Page, paragraph: _pages.Any, wrap: _pages._Wrap | None, moved: bool = False) -> tuple[_pages._Para, _pages._Wrap | None]:
    """The paragraph with the lines beside a square-wrapped object's band narrower, and the band as the
    next paragraph sees it. With *moved*, the object went on to the next page's top: none here."""

    runs = paragraph.findall(f"{_pages.HP}run")
    objects = _pages._placed_objects(runs)
    stacked = _pages._stacked_objects(objects, runs, page.column_width)
    if stacked:
        if wrap is not None or page.unequal:
            raise _pages._Unsupported("objects placed top and bottom one below another beside other objects")
        para = _pages._paragraph(measure, page, paragraph, stacked=tuple(stacked))
        shape = measure.shape(paragraph.get("paraPrIDRef"))
        return _pages.replace(para, stack=_pages._stack(measure, stacked, page.column_width, shape)), None
    square = _pages._square_object(objects, runs, page.column_width)
    bare = len(objects) == 1 and not _pages._run_text(runs) and not _pages._marks(runs) and not _pages._note_anchors(runs) \
        and not measure.headed(paragraph)
    pusher = _pages._pushing_object(objects, _pages._run_text(runs), page.column_width, bare)
    if bare and pusher is not None and not _pages._clear_of_its_band(measure, page, paragraph, pusher):
        pusher = None  # the next line reaches the object's band anyway: laid out as the object alone
    if moved:  # the object went on to the next page's top: the paragraph's lines as if it were not there
        # the object: wrapped square, pushing the lines below it, or alone below the empty line (a table that
        # may split goes on over the page end instead; of tables, only one set not to split, wrapped square or
        # alone at its paragraph's top, is followed)
        alone = objects[0] if len(objects) == 1 and objects[0].find(f"{_pages.HP}pos").get("treatAsChar") != "1" else None
        obj = square if square is not None else pusher if pusher is not None else alone
        if obj is not None and obj is square and wrap is None and _pages._local(obj) == "tbl" \
                and obj.get("pageBreak", "CELL") != "NONE":  # it splits over the page end instead
            return _pages.replace(_pages._paragraph(measure, page, paragraph, None, obj), spans=_pages._spans(measure, page, obj)), None
        at_top = obj is alone and pusher is None
        if obj is None or wrap is not None or _pages._local(obj) == "tbl" and (
                obj is not square and not at_top
                or obj.get("pageBreak", "CELL") not in ("NONE", "TABLE" if at_top else "NONE")):  # one moved row by
            # row goes on whole too, when it is its paragraph's top (see _Paginator._anchored)
            raise _pages._Unsupported("a square-wrapped or offset top-and-bottom object past the page foot")
        tall = _pages._extent(obj, "height", measure)
        if _pages._local(obj) == "tbl":  # as tall as its rows
            tall += _pages._rows_height(measure, obj) - int(obj.find(f"{_pages.HP}sz").get("height", 0))
        if obj is square:
            left, right = _pages._square_sides(square, page)
            band = _pages._Wrap(0, tall, page.column_width - left - right, split=left if left and right else 0)
        else:  # the lines reaching it go below it
            band = _pages._Wrap(0, tall, 0, push=True)
        return _pages.replace(_pages._paragraph(measure, page, paragraph, None, obj), moved=band), None
    shape = measure.shape(paragraph.get("paraPrIDRef"))
    placed = [obj for obj in objects if obj.find(f"{_pages.HP}pos").get("treatAsChar") != "1"]
    if wrap is not None:
        wrap = wrap.lower(shape.prev)
        if wrap is not None and not wrap.push and square is None and _pages._below_the_band(measure, runs, wrap):
            wrap = None  # every line of the paragraph goes below its object's foot, under the band
        if wrap is not None and (square is not None or pusher is not None or (wrap.push and placed)
                                 or _pages._on(shape.flags, "pageBreakBefore")
                                 or paragraph.get("pageBreak") == "1" or paragraph.get("columnBreak") == "1"):
            raise _pages._Unsupported("a page break or another object beside a square-wrapped object")
    if pusher is not None:
        para = _pages.replace(_pages._paragraph(measure, page, paragraph, None, pusher), bare=bare)
        offset = _pages._pos_offset(pusher.find(f"{_pages.HP}pos"), "vertOffset")
        if not para.wrap_anchor:  # on the first line: from the paragraph's top, above its spacing (on a later
            offset -= para.prev  # line, from that line's top)
        if _pages._local(pusher) == "tbl" and pusher.get("pageBreak", "CELL") in ("CELL", "TABLE"):  # it flows
            rows, cells = _pages._table_rows(measure, pusher)
            ends = _pages._table_ends(pusher)
            table = _pages._FlowTable(rows, _pages._page_break(pusher), pusher.get("repeatHeader") == "1", ends,
                               tuple(cells), caption=_pages._caption(measure, pusher), cut=_pages._spare_cut(pusher))
            return _pages.replace(para, band=_pages._Band(para.wrap_anchor, offset, table)), None
        top = para.span(0, para.wrap_anchor) + offset
        tall = _pages._extent(pusher, "height", measure)
        if _pages._local(pusher) == "tbl":  # as tall as its rows
            tall += _pages._rows_height(measure, pusher) - int(pusher.find(f"{_pages.HP}sz").get("height", 0))
        return _pages._push(para, _pages._Wrap(top, top + tall, 0, push=True), starts=True)
    if wrap is not None and wrap.push:  # objects set as characters on a line reaching it go below it with it
        return _pages._push(_pages._paragraph(measure, page, paragraph), wrap, starts=False)
    if wrap is not None and objects and not placed and not _pages._run_text(runs).strip():
        para = _pages._paragraph(measure, page, paragraph)  # one object set as a character, alone: beside it, even
        if len(objects) > 1:  # wider than the room
            raise _pages._Unsupported("objects set as characters beside a square-wrapped object")
        beside = sum(1 for line in range(para.lines) if para.span(0, line) < wrap.bottom)
        return _pages.replace(para, wrap_lines=beside, wrap_stays=wrap.stays, wrap_free=wrap.stays), \
            wrap.lower(para.span(0, para.lines) + para.next)
    starts = square is not None
    if square is not None:
        top = _pages._pos_offset(square.find(f"{_pages.HP}pos"), "vertOffset")
        line = _pages._square_anchor_line(measure, page, paragraph, runs, square)
        if line:  # after text: from the top of its line, the lines above it the column's whole width
            top += _pages._paragraph(measure, page, paragraph, None, square).span(0, line)
        left, right = _pages._square_sides(square, page)
        if not left and not right:
            raise _pages._Unsupported(f"{_pages._local(square)} wrapped square leaving little room for text")
        tall = _pages._extent(square, "height", measure)
        if _pages._local(square) == "tbl":  # as tall as its rows
            tall += _pages._rows_height(measure, square) - int(square.find(f"{_pages.HP}sz").get("height", 0))
        stays = square.find(f"{_pages.HP}pos").get("flowWithText") == "0"
        if left and right:
            wrap = _pages._Wrap(top, top + tall, page.column_width - left - right, split=left, stays=stays)
        else:
            wrap = _pages._Wrap(top, top + tall, page.column_width - left - right, stays=stays)
    para = _pages._paragraph(measure, page, paragraph, wrap, square)
    if wrap is not None and (para.anchor is not None or para.table is not None):
        raise _pages._Unsupported("an object beside a square-wrapped object")
    if wrap is None:
        return para, None
    lead = para.prev - shape.prev  # its first line moved below the band
    if wrap.split and not para.cached and para.lines == 1 and lead < wrap.bottom and not _pages._run_text(runs) \
            and lead + para.height(0) > wrap.top \
            and all(obj is square for obj in objects):  # an empty line beside it: two empty pieces
        para = _pages._in_two_pieces(para)
    beside = sum(1 for line in range(para.lines) if lead + para.span(0, line) < wrap.bottom)
    para = _pages.replace(para, wrap_lines=beside, wrap_bottom=wrap.bottom if starts else 0,
                   wrap_fixed=bool(_pages._cached_metrics(paragraph)), wrap_stays=wrap.stays,
                   wrap_free=wrap.stays and (bool(_pages._cached_metrics(paragraph)) or not _pages._run_text(runs).strip()))
    return para, wrap.lower(lead + para.span(0, para.lines) + para.next)


class _Paginator:
    """Frames (a page's columns, in order) and vertical positions of every line of a section."""

    def __init__(self, body: int, columns: int, notes: _pages._NoteShape,
                 bands: dict[int, list[tuple[int, int]]] | None = None, widths: tuple[int, ...] = (),
                 sides: dict[int, list[tuple[int, int]]] | None = None, alone_at_top: bool = True) -> None:
        self.body = body
        self.alone_at_top = alone_at_top  # see _Page.alone_at_top
        self.widths = widths  # each column's width when they differ
        #: frame -> (top, bottom) of the objects placed on the paper there: no line in them
        self.bands = {frame: list(found) for frame, found in (bands or {}).items()}  # stacked objects add theirs
        #: frame -> left, right, top, bottom of the objects stacked in empty paragraphs that went there
        self.stacked: dict[int, list[tuple[int, int, int, int]]] = {}
        #: frame -> (top, bottom) of the ones leaving a line's room beside them, and whether a line without
        #: a layout cache, a table or an object reaches one of them (set beside it by Hancom, which is not
        #: followed: a line keeping its cache stays where it is)
        self.sides = sides or {}
        self.beside = False
        self.columns = columns
        self.notes = notes
        self.out: list[tuple[int, int]] = []
        self.counts: list[int] = []  # lines per paragraph
        self.laid: _pages._Para | None = None  # the paragraph _lay placed last, as it broke its last lines
        self.frame = 0
        self.last_vp: int | None = None
        self.last_pitch = 0
        self.pending_next = 0
        self.object_floor: tuple[int, int] | None = None  # (frame, where the next paragraph starts at the highest): an empty paragraph's object
        self.table_end = 0      # the last frame a flowing table reaches
        self.reserved: dict[int, int] = {}  # frames a table starting past its anchor takes: where text starts
        self.wrap_frame = -1                  # the frame a square-wrapped object's band is on
        self.wrap_moved = False  # that band passed the body's foot: the object went on to the next page
        #: frame -> the bands of square-wrapped objects there that the text there is broken beside: one that
        #: went on to its top (see :attr:`_Para.moved`), the parts of tables split over its ends
        self.squares: dict[int, list[_pages._Wrap]] = {}
        #: frames whose band is a top-and-bottom object that went on to their top (see :meth:`_move_band`)
        self.moved_tops: set[int] = set()
        #: a flowing table's band no line has reached yet: its frame, top, bottom there (None when it goes
        #: on over the page end), and the frame and position where the lines after it go on
        self.band: tuple[int, int, int | None, int, int] | None = None
        self.page_notes = [0, 0]  # height and count of the notes on the current page
        self.carry = 0          # height of notes going on over the page end
        self.floor: int | None = None  # where the next paragraph starts at the highest: a table's end
        self.under: int | None = None  # where the next paragraph starts, whatever its spacing: a table's end
        self.hidden = 0  # empty paragraphs just hidden below the current frame's foot

    def run(self, paras: list[_pages._Para]) -> int:
        """Lay *paras* out; the number of frames used."""

        for index, para in enumerate(paras):
            first = len(self.out)
            self._paragraph(index, paras, para)
            self.counts.append(len(self.out) - first)
        return max(self.out[-1][0] if self.out else 0, self.table_end) + 1

    def _paragraph(self, index: int, paras: list[_pages._Para], para: _pages._Para) -> None:
        hidden, self.hidden = self.hidden, 0
        start = para.prev if self.last_vp is None else self.last_vp + self.last_pitch + self.pending_next + para.prev
        if para.grid:  # its first line on the line grid, at the first step from where it would go
            start = -(-start // para.grid) * para.grid
        if self.object_floor is not None and self.object_floor[0] == self.frame:  # below an empty paragraph's
            start = max(start, self.object_floor[1])                             # object (_Para.floor)
        self.object_floor = None
        if self.under is not None:  # the table before went on past its anchor line's page: the line reaching it
            # goes right under its end, as under any object's band, and a column break lands there, in the
            # column after the anchor line's (or the first one clear of the table)
            start, self.under = self.under, None
            if para.column_break and not para.page_break and not para.break_before:
                para = _pages.replace(para, column_break=False)
        if self.floor is not None:
            start, self.floor = max(start, self.floor), None
        if (para.stack or para.band is not None or para.table is not None or para.anchor is not None) \
                and (self.frame in self.squares or self.frame + 1 in self.squares):
            raise _pages._Unsupported("objects or a table beside a square-wrapped object moved to the next page")
        if para.rises is not None and self.last_vp is not None:
            para, start = self._below_a_rising_object(index, paras, para, start)
        if para.stack:
            self._stacked(index, paras, para, start)
            return
        if self.band is not None and (para.page_break or para.break_before) and not para.column_break \
                and para.band is None and para.table is None and para.anchor is None and not para.notes \
                and not para.wrap_bottom:  # a page break before a table's band comes: the table stays where it
            # stands and the paragraph starts the page after the one the table ends on
            end_frame = self.band[3]
            self.band = None
            if end_frame != self.frame:
                self.frame, self.page_notes = end_frame, [0, 0]
        if para.band is not None or self.band is not None:
            self._banded(index, paras, para, start)
            return
        if para.anchor is not None:
            self._anchored(index, paras, para, start)
            return
        start, broke = self._breaks(para, start)  # a flowing table in the paragraph starts there too
        if para.hides and not broke and hidden < 2 and self.last_vp is not None and not self._fits(start, 1, para):
            # Hancom hides an empty paragraph that would start the next page or column, and a second one after
            # it, where it would stand below this one's foot: it takes no room and starts no page.
            self.out.append((self.frame, start))
            self.hidden = hidden + 1
            return
        table = para.table
        if table is not None:
            self._flow(para, table, start)
            return
        reach = para.wrap_bottom - para.wrap_shift if para.wrap_push else para.moves
        anchor = para.wrap_anchor if para.wrap_push else 0
        ahead = para.span(0, anchor)  # its anchor line below the paragraph's first, the object offset from it
        if anchor and start + para.span(0, anchor - 1) + para.height(anchor - 1) <= self.body \
                < start + ahead + para.height(anchor):  # the anchor line goes on to the next page, the object
            if self.reserved.get(self.frame + 1, 0) + reach - ahead > self.body:  # with it, from its top there
                raise _pages._Unsupported("a square-wrapped or offset top-and-bottom object past the page foot")
        elif reach and start + reach > self.body and self.columns == 1 and start < self.body \
                and (para.wrap_push or start + para.own <= self.body):  # the empty line fits where it stands:
            raise _pages._BandMoves(index)  # its object goes on to the next page's top, its lines stay (starting past
            # the foot, the paragraph goes on to the next page, the object with it)
        first = len(self.out)
        if self._lay(index, paras, para, start, broke):
            last = self.laid or para
            self.last_vp, self.last_pitch, self.pending_next = self.out[-1][1], last.advance(last.lines - 1), para.next
            if para.floor:
                self.object_floor = (self.out[-1][0], self.out[-1][1] + para.floor)
        if para.wrap_bottom:  # the band starts here: it stays on the page of its anchor line
            self.wrap_frame, line = self.out[first + anchor]
            self.wrap_moved = line - ahead + para.wrap_bottom - para.wrap_shift > self.body \
                and not para.wrap_stays
        if self.wrap_moved and not para.wrap_fixed and (para.wrap_bottom or para.wrap_lines):
            if para.wrap_bottom and self.columns == 1:  # its object goes on to the next page's top: again
                raise _pages._BandMoves(index)
            raise _pages._Unsupported("a square-wrapped or offset top-and-bottom object past the page foot")
        beside = self.out[first + anchor:first + para.wrap_lines]  # (the lines before its anchor line above it)
        if not para.wrap_fixed and not para.wrap_free and any(frame != self.wrap_frame for frame, _ in beside):
            raise _pages._Unsupported("a page break beside a square-wrapped or offset top-and-bottom object")

    def _below_a_rising_object(self, index: int, paras: list[_pages._Para], para: _pages._Para, start: int) -> tuple[_pages._Para, int]:
        """Hancom places an object top and bottom up from its paragraph's top (``_Para.rises``) from where that
        top would be, and moves the lines before it on the page that reach into its band (their foot below its
        top) to its foot, the lines after them following as they stood; the paragraph's own line then comes
        after them, clear of the object. (The paragraph, where it starts.)"""

        up, tall, own, own_pitch = para.rises  # type: ignore[misc]
        top, foot = start + up, start + up + tall
        lines: list[tuple[int, int]] = []  # (place in self.out, its line's height), newest first
        at = len(self.out)
        for before in range(index - 1, -1, -1):
            count = self.counts[before]
            for line in range(count - 1, -1, -1):
                at -= 1
                lines.append((at, paras[before].height(line)))
            if at <= 0 or self.out[at][0] != self.frame or self.out[at][1] + paras[before].height(0) <= top:
                break
        reaching = [place for place, height in lines
                    if self.out[place][0] == self.frame and self.out[place][1] + height > top]
        if not reaching:
            return para, start
        first = min(reaching)
        moved = [place for place, _ in lines if place >= first]
        owners = {before for before in range(index) if sum(self.counts[:before]) <= max(moved)
                  and sum(self.counts[:before + 1]) > first}
        if any(paras[before].table is not None or paras[before].anchor is not None or paras[before].band is not None
               or paras[before].stack or paras[before].notes or paras[before].rises is not None for before in owners):
            raise _pages._Unsupported("objects among the lines a top-and-bottom object placed up moves below it")
        shift = foot - self.out[first][1]
        heights = dict(lines)
        for place in moved:
            frame, line_top = self.out[place]
            if line_top + shift + heights[place] > self.body:
                raise _pages._Unsupported("lines a top-and-bottom object placed up moves past the page foot")
            self.out[place] = (frame, line_top + shift)
        self.last_vp = self.out[-1][1]
        start = self.last_vp + self.last_pitch + self.pending_next + para.prev
        return _pages.replace(para, size=own, pitch=own_pitch), start

    def _flow(self, para: _pages._Para, table: _pages._FlowTable, start: int) -> None:
        if self.last_vp is not None and start + para.height(0) > self.body:  # the anchor line goes on
            start = self._next_frame(para, 0, True)                         # to the next page
            if self.reserved.get(self.frame) and start + para.height(0) > self.body:  # below a table started
                start = self._next_frame(para, 0, True)  # past its anchor there, ending too low for it: the page after
        if self._below_bands(start) != start:
            if self.frame not in self.moved_tops:
                self._flow_below_band(para, table, self._below_bands(start))
                return
            start = self._below_bands(start)  # below an object that went on to this page's top: as at the top
        if para.under and not _pages._starts_later(table, start - para.prev + table.offset + table.above, self.body):
            self._flow_below_band(para, table, start - para.prev)  # from the paragraph's top, the line below it
            return
        self.out.append((self.frame, start))  # the anchor paragraph's line, under the table's top
        if not para.kept:
            self._reach(self.frame, start, start + para.height(0))
        before = self.frame
        top = start - para.prev + table.offset + table.above  # from the paragraph's top, above its spacing
        # the notes already on the page keep their room at its foot, all but the separator's width: the rows
        # end above them there, as if they started that much lower (on the pages after, the table goes on
        # below the header as ever)
        noted = self.notes.area(*self.page_notes) - (self.notes.line if self.page_notes[1] else 0)
        frame, end = _pages._flow_table(table, self.frame, top + noted, self.body)
        if frame == self.frame:
            end -= noted
        later = start + para.height(0) <= self.body and _pages._starts_later(table, top + noted, self.body)
        if self.frame + 1 in self.moved_tops and frame > self.frame and (later or (frame, end) == _pages._flow_table(
                table, self.frame + 1, _pages._repeated_header(table) + table.margins[0], self.body)):  # it goes on to
            below = max(bottom for _, bottom in self.bands[self.frame + 1])  # the next page whole: below the
            frame, end = _pages._flow_table(table, self.frame + 1, below + table.above, self.body)  # object there
        if para.notes and frame == self.frame:
            height = self.page_notes[0] + sum(note[0] for note in para.notes.values())
            many = self.page_notes[1] + sum(note[1] for note in para.notes.values())
            if end > self.body - self.notes.area(height, many):
                raise _pages._Unsupported("a flowing table overlapping its footnotes")
        self._clear_of_paper(before, frame, start, end)
        self.table_end = max(self.table_end, frame)
        if later:
            self._starts_next_page(para, table, start, frame, end)
            return
        self.frame = frame
        if self.frame != before:
            self.page_notes = [0, 0]
            self.last_vp, self.last_pitch, self.pending_next = end + table.below, 0, para.next
            self.under = end + table.below
        else:  # the next paragraph goes below the anchor line or the table, whichever is lower
            self.last_vp, self.last_pitch, self.pending_next = start, para.advance(0), para.next
            self.floor = end + table.below
            for height, many, _ in para.notes.values():  # the notes in its cells take room at the page's foot
                self.page_notes = [self.page_notes[0] + height, self.page_notes[1] + many]

    def _flow_below_band(self, para: _pages._Para, table: _pages._FlowTable, top: int) -> None:
        """A band of an object placed on the paper pushed the table's anchor line down to *top*: the table
        stands there, and the line goes below the table."""

        frame, end = _pages._flow_table(table, self.frame, top + table.offset + table.above, self.body)
        self._clear_of_paper(self.frame, frame, top, end, below=True)
        line = end + table.below
        self.page_notes = [0, 0] if frame != self.frame else self.page_notes
        self.frame, self.table_end = frame, max(self.table_end, frame)
        self.out.append((self.frame, line))
        if not para.kept:
            self._reach(self.frame, line, line + para.height(0))
        self.last_vp, self.last_pitch, self.pending_next = line, para.advance(0), para.next

    def _stacked(self, index: int, paras: list[_pages._Para], para: _pages._Para, start: int) -> None:
        """Objects stacked in a paragraph holding nothing else go one by one to the first page, from the
        paragraph's on, where they fit below the earlier ones there they overlap across (see
        :meth:`_stack_spot`), those of earlier such paragraphs included. The first, not fitting on the
        paragraph's page, flows from where it stands (a table split at the page's foot, going on at the next
        page's top whatever is there); a later one, fitting on no page holding objects, starts at the top of
        the page after, a table taller than a page split over the pages after. A page a table goes on from is
        full. No line goes into them: the paragraph's line takes the first place clear of them, on a later
        page when its own has none, and the lines after follow it."""

        if self.columns > 1:
            raise _pages._Unsupported("objects placed top and bottom one below another in columns")
        if self.band is not None or para.notes or self.page_notes[1]:
            raise _pages._Unsupported("objects placed top and bottom one below another beside notes or a table's band")
        start, _ = self._breaks(para, start)
        if self.last_vp is not None and start + para.height(0) > self.body:  # its line goes on to the next
            start = self._next_frame(para, 0, True)                         # page, the objects with it
        home, top = self.frame, start - para.prev
        placed = {frame: list(boxes) for frame, boxes in self.stacked.items() if frame >= home}
        last = home
        for number, obj in enumerate(para.stack):
            end = last if number == 0 else max([last, *placed])
            spot = self._stack_spot(placed, obj, home, end, top)
            if spot is None:  # the first from where it stands, a later one from the top of the page after
                spot = (end + 1, 0) if number else (home, max([top + obj.offset] + self._below(placed, obj, home)))
                if obj.table is None and spot[1] + obj.height > self.body:
                    raise _pages._Unsupported("an object placed top and bottom past the page's foot")
            frame, y = spot
            end_frame, bottom = frame, y + obj.height
            if bottom > self.body:  # a table split over the pages from there
                assert obj.table is not None
                end_frame, end = _pages._flow_table(obj.table, frame, y + obj.table.above, self.body)
                bottom = end + obj.table.below
            for page in range(frame, end_frame + 1):
                placed.setdefault(page, []).append(
                    (obj.left, obj.right, y if page == frame else 0, bottom if page == end_frame else self.body))
            last = max(last, end_frame)
        for frame, boxes in placed.items():
            if self.bands.get(frame) and frame not in self.stacked or self.sides.get(frame) \
                    or frame != home and self.reserved.get(frame):
                raise _pages._Unsupported("objects placed top and bottom one below another on a page with other objects")
            self.bands[frame] = [(above, below) for _, _, above, below in boxes]
            self.stacked[frame] = boxes
        self.table_end = max(self.table_end, last)
        frame, y, height = home, start, para.height(0)
        while True:  # the paragraph's line, at the first place clear of them
            hits = [below for above, below in self.bands.get(frame, ()) if y < below and y + height > above]
            if hits:
                y = max(hits)
            elif y + height <= self.body:
                break
            else:
                frame, y = frame + 1, self.reserved.get(frame + 1, 0) + para.prev
        if frame != home:
            self.page_notes = [0, 0]
        self.frame, self.laid = frame, para
        self.out.append((frame, y))
        self._reach(frame, y, y + height)
        self.last_vp, self.last_pitch, self.pending_next = y, para.advance(0), para.next

    def _stack_spot(self, placed: dict[int, list[tuple[int, int, int, int]]], obj: _pages._Stacked, home: int, last: int,
                    top: int) -> tuple[int, int] | None:
        """The first of the pages *home* to *last* where *obj* fits below the objects *placed* there it overlaps
        across (on *home* at its offset below *top* or lower, on a later page from its top), and where; ``None``
        when it fits on none."""

        for frame in range(home, last + 1):
            y = max([top + obj.offset if frame == home else 0] + self._below(placed, obj, frame))
            if y + obj.height <= self.body:
                return frame, y
        return None

    @staticmethod
    def _below(placed: dict[int, list[tuple[int, int, int, int]]], obj: _pages._Stacked, frame: int) -> list[int]:
        """The bottoms of the objects *placed* on *frame* that *obj* overlaps across."""

        return [box[3] for box in placed.get(frame, ()) if box[0] < obj.right and obj.left < box[1]]

    def _anchored(self, index: int, paras: list[_pages._Para], para: _pages._Para, start: int) -> None:
        """The lines before the anchor's line, the object at that line's top, then the rest of the
        paragraph below the object."""

        anchor = para.anchor
        assert anchor is not None
        if para.notes:
            raise _pages._Unsupported("footnotes in a paragraph anchoring a top-and-bottom object")
        start, broke = self._breaks(para, start)
        head = _pages._lines_of(para, 0, anchor.line, prev=para.prev, after=0)
        tail = _pages._lines_of(para, anchor.line, para.lines - anchor.line, prev=0, after=para.next)
        top = start
        if head.lines:
            if not self._lay(index, paras, head, start, broke):
                raise _pages._Unsupported("footnotes in a paragraph anchoring a top-and-bottom object")
            top = self.out[-1][1] + head.advance(head.lines - 1)
        else:  # at the top of the paragraph's first line: from the paragraph's top, above its spacing before,
            # below an object placed on the paper, as the line
            top = self._below_bands(top - para.prev)
        if anchor.table is not None:
            table = anchor.table
            later = _pages._starts_later(table, top + table.above, self.body)
            if later and para.spaced and not head.lines:  # spaces only: as the table alone in its paragraph,
                line = para.cached[0][0] if para.cached else para.size  # its line staying where it fits
                if start + line <= self.body:
                    self._flow(_pages.replace(para, anchor=None, table=table), table, start)
                    return
                top, later = self._next_frame(para, 0, True) - para.prev, False  # where it does not: the line
                # goes on with the table, below it
            moves = not head.lines and top != self.reserved.get(self.frame, 0)
            whole = table.mode == "NONE" or later and table.mode in ("TABLE", "CELL")  # moved row by row or
            # split cell by cell, its first row with no room on this page: it goes on as one, as one set not to
            # split
            if moves and whole and later and self.alone_at_top and self.columns == 1 \
                    and top + tail.height(0) <= self.body:  # with no room below the line's top:
                raise _pages._BandMoves(index)  # to the next page's top alone, the paragraph's lines staying
            if moves and whole:  # set not to split
                moves = later or top + table.above + sum(row.height for row in table.rows) + table.below \
                    + tail.height(0) > self.body
            elif moves:  # ending on this page (a row split by cells: its room to spare cut there) but not the line
                frame, end = _pages._flow_table(table, self.frame, top + table.above, self.body)
                moves = frame == self.frame and end + table.below + tail.height(0) > self.body
            if moves:  # it goes on with the line below it
                top, later = self._next_frame(para, 0, True), False
            if later:
                raise _pages._Unsupported("a top-and-bottom table anchored in text that starts on the next page")
            frame, end = _pages._flow_table(table, self.frame, top + table.above, self.body)
            self._clear_of_paper(self.frame, frame, top, end, below=True)
            self.frame, self.table_end, end = frame, max(self.table_end, frame), end + table.below
        else:
            if top + anchor.height > self.body and top > 0:
                if self.alone_at_top and not anchor.stays and self.columns == 1 \
                        and top + tail.height(0) <= self.body:  # it goes on
                    raise _pages._BandMoves(index)  # to the next page's top alone, the paragraph's lines staying
                raise _pages._Unsupported("a top-and-bottom object anchored in text at a page end")
            end = top + anchor.height
            self._reach(self.frame, top, end)
        self.last_vp, self.last_pitch, self.pending_next = end, 0, 0
        if self._lay(index, paras, tail, end, False):
            self.last_vp, self.last_pitch, self.pending_next = self.out[-1][1], tail.advance(tail.lines - 1), para.next

    def _banded(self, index: int, paras: list[_pages._Para], para: _pages._Para, start: int) -> None:
        """A paragraph starting a flowing table's band (the table flows from its anchor line's top plus the
        offset), or one after it: its lines above the band stay, and the first line reaching the band and
        the lines after go on below the table's end."""

        if para.notes or para.anchor is not None or para.wrap_bottom \
                or (para.table is not None and (self.band is None or para.band is not None)) \
                or (self.band is not None and (para.page_break or para.break_before or para.column_break)):
            raise _pages._Unsupported("a page break or another object beside a top-and-bottom table's band")
        start, broke = self._breaks(para, start)
        if self.band is not None and para.band is not None:  # its own table's band after another's
            frame, top, bottom, end_frame, end = self.band
            if self.frame != frame or start + para.height(0) <= top:
                raise _pages._Unsupported("a page break or another object beside a top-and-bottom table's band")
            self.band = None
            if bottom is None or start < bottom:  # its first line reaches the other table: the paragraph goes
                if end_frame != self.frame:  # below that table's end, its own table placed from there
                    self.frame, self.page_notes = end_frame, [0, 0]
                start = end + para.prev
            self._banded(index, paras, para, start)
            return
        if para.table is not None:  # a flowing table alone in its paragraph: its line goes below the band
            frame, top, bottom, end_frame, end = self.band
            if self.frame != frame or start + para.height(0) <= top or (bottom is not None and start >= bottom):
                raise _pages._Unsupported("a page break or another object beside a top-and-bottom table's band")
            self.band = None
            if end_frame != self.frame:
                self.frame, self.page_notes = end_frame, [0, 0]
            self._flow(para, para.table, end + para.prev)
            return
        if para.band is not None:
            band, table = para.band, para.band.table
            if not band.line and self.last_vp is not None and start + para.height(0) > self.body:
                start = self._next_frame(para, 0, True)  # the line goes on to the next page, its table with it
            top = start + para.span(0, band.line) + band.offset
            if start + para.span(0, band.line) + para.height(band.line) > self.body:
                raise _pages._Unsupported("a top-and-bottom table offset down from a line at a page end")
            if top + table.above >= self.body or _pages._starts_later(table, top + table.above, self.body):
                if band.line:
                    raise _pages._Unsupported("a top-and-bottom table offset down from a line at a page end")
                self._band_on_next_page(index, paras, para, table, top, start, broke)
                return
            frame, end = _pages._flow_table(table, self.frame, top + table.above, self.body)
            self._clear_of_paper(self.frame, frame)
            self.table_end = max(self.table_end, frame)
            bottom = end + table.below
            self.band = (self.frame, top, bottom if frame == self.frame else None, frame, bottom)
        assert self.band is not None
        frame, top, bottom, end_frame, end = self.band
        if self.frame != frame:
            raise _pages._Unsupported("a page break beside a top-and-bottom table's band")
        reaching = [line for line in range(para.lines)
                    if start + para.span(0, line) + para.height(line) > top
                    and (bottom is None or start + para.span(0, line) < bottom)
                    and not (line == 0 and para.bare and para.band is not None)]  # its own empty line stays
        if not reaching:  # every line above the band, or past it
            if self._lay(index, paras, para, start, broke):
                self.last_vp, self.last_pitch, self.pending_next = self.out[-1][1], para.advance(para.lines - 1), \
                    para.next
            if self.frame != frame:
                raise _pages._Unsupported("a page break beside a top-and-bottom table's band")
            if bottom is not None and start + para.span(0, para.lines - 1) >= bottom:
                self.band = None
            return
        first = reaching[0]
        head = _pages._lines_of(para, 0, first, prev=para.prev, after=0)
        tail = _pages._lines_of(para, first, para.lines - first, prev=0, after=para.next)
        if head.lines:
            self._lay(index, paras, head, start, broke)
            if self.frame != frame:
                raise _pages._Unsupported("a page break beside a top-and-bottom table's band")
        self.band = None
        if end_frame != self.frame:
            self.frame, self.page_notes = end_frame, [0, 0]
        if self._lay(index, paras, tail, end, False):
            self.last_vp, self.last_pitch, self.pending_next = self.out[-1][1], tail.advance(tail.lines - 1), para.next

    def _band_on_next_page(self, index: int, paras: list[_pages._Para], para: _pages._Para, table: _pages._FlowTable, top: int,
                           start: int, broke: bool) -> None:
        """A table offset down from a paragraph's first line whose top falls past the page's foot, or whose first
        row (moved row by row) does not fit under it: it starts at the next page's top, and the paragraph's lines
        go on under its line, on the pages the table takes below the table."""

        frame, end = _pages._flow_table(table, self.frame, top + table.above, self.body)
        self._clear_of_paper(self.frame + 1, frame)
        taken = range(self.frame + 1, frame + 1)
        if frame == self.frame or any(page in self.reserved for page in taken):
            raise _pages._Unsupported("a top-and-bottom table offset down from a line at a page end")
        self.reserved.update(dict.fromkeys(taken, self.body))
        self.reserved[frame] = end + table.below
        self.table_end = max(self.table_end, frame)
        if self._lay(index, paras, para, start, broke):
            self.last_vp, self.last_pitch, self.pending_next = self.out[-1][1], para.advance(para.lines - 1), para.next

    def _clear_of_paper(self, first: int, last: int, top: int = 0, end: int | None = None,
                        below: bool = False) -> None:
        """A table from its anchor line's *top* in frame *first* to *end* in frame *last* (the whole frames
        without them) reaching the band of an object placed on the paper or the page, or starting right
        below one (but for a table moved *below* it), is not followed."""

        for frame in range(first, last + 1):
            if frame in self.moved_tops:  # an object that went on to its top: a table starts below it, and one
                continue                  # going on from the page before goes on over it
            low = top if frame == first else 0
            high = end if frame == last and end is not None else self.body
            self._reach(frame, low, high)
            touching = below and frame == first
            if any(above < high and (low < bottom if touching else low <= bottom)
                   for above, bottom in self.bands.get(frame, ())):
                stacked = frame in self.stacked
                raise _pages._Unsupported("a table on a page with objects stacked in an empty paragraph" if stacked
                                   else "a table on a page with an object placed on the paper")

    def _reach(self, frame: int, top: int, bottom: int) -> None:
        """Note whether something from *top* to *bottom* in *frame* reaches the band of an object placed on
        the paper that leaves a line's room beside it."""

        if any(top < foot and bottom > head for head, foot in self.sides.get(frame, ())):
            self.beside = True

    def _below_bands(self, top: int) -> int:
        """*top* in the current frame, below the band of any object placed on the paper that it falls in."""

        for above, bottom in sorted(self.bands.get(self.frame, ())):
            if above <= top < bottom:
                top = bottom
        return top

    def _band_hit(self, para: _pages._Para, first: int, count: int, start: int) -> tuple[int, int] | None:
        """(how many lines from line *first* come before it, its bottom) of the first object placed on the
        paper of this frame that one of *count* lines laid from *start* reaches, or ``None``."""

        bands = self.bands.get(self.frame)
        if not bands:
            return None
        for line in range(count):
            top = start + para.span(first, line)
            if top >= self.body:
                return None
            reached = [bottom for above, bottom in bands if top < bottom and top + para.height(first + line) > above]
            if reached:
                return line, max(reached)
        return None

    def _starts_next_page(self, para: _pages._Para, table: _pages._FlowTable, start: int, frame: int, end: int) -> None:
        """The anchor line fits but the table's first row does not, so the table starts on the next page
        and ends in *frame* at *end*. The text after it goes on under the anchor line, and on the pages the
        table takes, below the table. Another such table from the same page starts on the page after the last
        the one before it takes, at its top."""

        taken = range(self.frame + 1, frame + 1)
        if any(page in self.reserved for page in taken):  # one did before it from this page: it starts at the
            first = max(page for page in self.reserved if page > self.frame) + 1  # top of the page after that one's
            frame, end = _pages._flow_table(table, first, table.margins[0], self.body)
            taken = range(first, frame + 1)
            self.table_end = max(self.table_end, frame)
        self.reserved.update(dict.fromkeys(taken, self.body))
        self.reserved[frame] = end + table.below
        self.last_vp, self.last_pitch, self.pending_next = start, para.advance(para.lines - 1), para.next

    def _breaks(self, para: _pages._Para, start: int) -> tuple[int, bool]:
        if self.last_vp is None:
            return start, False
        if para.page_break or para.break_before:
            self.frame = (self.frame // self.columns + 1) * self.columns
            while self.frame in self.moved_tops or self.frame in self.reserved:  # a page an object or a table
                self.frame += self.columns  # started past its anchor went on to: the break starts after it
        elif para.column_break:
            self.frame += 1
        else:
            return start, False
        self.page_notes = [0, 0]
        return self._free_top() + para.prev, True

    def _lay(self, index: int, paras: list[_pages._Para], para: _pages._Para, start: int, broke: bool) -> bool:
        """Place the lines of *para*; False when its notes ended the page after it."""

        if para.spans is not None:  # a table wrapped square going on over the page end: its bands, page by page
            self._span_bands(para.spans, start)
            para = _pages.replace(para, spans=None)
        para = self._at_band(self._at_width(para, 0), 0, start)
        remaining, first_chunk = para.lines, True
        fresh = self.last_vp is None or broke
        below = False  # the next line was moved below an object's band
        while remaining:
            done = para.lines - remaining
            if para.held is not None and first_chunk and not fresh and start < self.body \
                    and start + para.advance(0) > para.held:
                start, below = self.body, True  # its object's band, on this page, takes its first line: both go on
                continue
            hit = self._band_hit(para, done, remaining, start)
            if hit is not None and hit[0] == 0:  # the line reaches an object placed on the paper: below it
                start, below = hit[1], True
                continue
            count = self._chunk(index, paras, para, start, remaining, done, first_chunk)
            if count == 0 and (self.last_vp is None or fresh) and not below and not self.reserved.get(self.frame):
                count = 1  # a line taller than the page still takes an empty page (and overflows it)
            if para.moved is not None:  # its object goes on to the next page's top
                if count == 0:
                    raise _pages._Unsupported("a square-wrapped object past the page foot, its paragraph on the next page")
                self._move_band(para.moved)
                para = _pages.replace(para, moved=None)
            if hit is not None and hit[0] < count:  # the lines above it stay, the next goes below it
                count = hit[0]
                self.out.extend((self.frame, start + para.span(done, j)) for j in range(count))
                self._place(para, done, count)
                remaining, start, first_chunk, below = remaining - count, hit[1], False, True
                continue
            self.out.extend((self.frame, start + para.span(done, j)) for j in range(count))
            self._place(para, done, count)
            remaining -= count
            if not remaining and self.carry:  # the page ends with this paragraph's notes
                self.frame += 1
                self.page_notes = [self.carry, 1]
                self.last_vp, self.last_pitch, self.pending_next = None, 0, 0
                self.laid = para
                return False
            if remaining:
                start, below = self._next_frame(para, count, first_chunk), False
                line = para.lines - remaining
                again = self._at_width(para, line)
                if again is not para:
                    para, remaining, line = again, again.lines, 0
                again = self._at_band(para, line, start)
                if again is not para:
                    para, remaining = again, again.lines
            fresh = bool(remaining)
            first_chunk = False
        self.laid = para
        return True

    def _at_width(self, para: _pages._Para, line: int) -> _pages._Para:
        """*para* with its lines from *line* on broken at the width of the current frame's column, when
        the columns differ in width and the paragraph has no layout cache."""

        if para.reflow is None or not self.widths:
            return para
        width = self.widths[self.frame % self.columns]
        return para if width == para.reflow.width else para.reflow.at(para, width, line)

    def _at_band(self, para: _pages._Para, line: int, start: int) -> _pages._Para:
        """*para* with its lines from *line* on, laid from *start* down, broken again beside the band of a
        square-wrapped object set at the current frame's top when they reach it."""

        bands = sorted((band for band in self.squares.get(self.frame, ()) if band.bottom > start),
                       key=lambda band: band.top)
        if not bands:
            return para
        band = bands[0]
        if para.blank:  # an empty line reaching it: two empty pieces beside an object with text on both sides
            reaches = start + para.height(line) > band.top
            return _pages._in_two_pieces(para) if reaches and band.split and para.lines == 1 and not para.cached else para
        if para.reflow is None:
            raise _pages._Unsupported("objects, notes or a layout cache beside a square-wrapped object moved to the next page")
        again = para.reflow.banded(para, line, _pages.replace(band, top=band.top - start, bottom=band.bottom - start))
        if len(bands) > 1 and start + again.span(0, again.lines) > bands[1].top:
            raise _pages._Unsupported("a paragraph beside two square-wrapped objects on a page")
        return again

    def _span_bands(self, spans: tuple[_pages._FlowTable, int, _pages._Wrap], start: int) -> None:
        """The bands of a table wrapped square, anchored in the paragraph being laid from *start*, that goes
        on over the page end: it flows as a flowing table from its top, and on each page it reaches the lines
        go beside its part there -- on its first page from its top to the foot, on a page it fills the whole
        page, on its last page from the top down to its end."""

        table, offset, band = spans
        top = start + offset
        last, end = _pages._flow_table(table, self.frame, top + table.above, self.body)
        for frame in range(self.frame, last + 1):
            part = _pages.replace(band, top=top if frame == self.frame else 0,
                           bottom=end + table.below if frame == last else self.body)
            if self.bands.get(frame) or self.sides.get(frame) or frame in self.reserved \
                    or any(other.top < part.bottom and part.top < other.bottom for other in self.squares.get(frame, ())):
                raise _pages._Unsupported("a square-wrapped table going on over the page end beside other objects")
            self.squares.setdefault(frame, []).append(part)
        self.table_end = max(self.table_end, last)

    def _move_band(self, band: _pages._Wrap) -> None:
        """A square-wrapped object anchored in the paragraph being laid, flowing with the text, went past the
        body's foot: Hancom sets it at the next page's body top whatever its offset, the lines there whose top
        is above its foot beside it, and that page is used even when no line goes there."""

        target = self.frame + 1
        if band.bottom > self.body or self.bands.get(target) or self.sides.get(target) or target in self.reserved \
                or any(other.top < band.bottom for other in self.squares.get(target, ())):
            raise _pages._Unsupported("an object going on to the next page's top beside other objects")
        if band.push:  # a top-and-bottom one: the lines reaching it go below it
            self.bands[target] = [(band.top, band.bottom)]
            self.moved_tops.add(target)
        else:
            self.squares.setdefault(target, []).append(band)
        self.table_end = max(self.table_end, target)

    def _next_frame(self, para: _pages._Para, count: int, first_chunk: bool) -> int:
        self.frame += 1
        self.page_notes = [self.carry, 1] if self.carry else [0, 0]
        return self._free_top() + (para.prev - para.lead if count == 0 and first_chunk else 0)

    def _free_top(self) -> int:
        """Where text starts in the current frame: below a table that starts past its anchor, the frames
        the table fills skipped."""

        while self.reserved.get(self.frame, 0) >= self.body:
            self.frame += 1
        return self.reserved.get(self.frame, 0)

    def _chunk(self, index: int, paras: list[_pages._Para], para: _pages._Para, start: int, remaining: int, done: int,
               first_chunk: bool) -> int:
        """How many of the paragraph's remaining lines stay in this frame."""

        count = self._fits(start, remaining, para, done)
        if not first_chunk:
            return count
        if count < remaining:
            count = self._keep_rules(para, start, remaining, count)
        if count == remaining and para.keep_next and index + 1 < len(paras):
            count = self._keep_with_next(para, paras[index + 1:], start, remaining, count)
        return count

    def _keep_rules(self, para: _pages._Para, start: int, remaining: int, count: int) -> int:
        if para.keep_lines and self._fits(para.prev, para.lines, para) == para.lines and start != para.prev:
            return 0
        if para.widow_orphan:
            if count == 1 and remaining > 1:
                return 0
            if remaining - count == 1 and count > 1:
                return count - 1
        return count

    def _keep_with_next(self, para: _pages._Para, following: list[_pages._Para], start: int, remaining: int, count: int) -> int:
        """*count*, or 0 when the paragraph set to stay with the next has to go on to the next frame. Its last
        line stays with the next paragraph's first line (two under the widow and orphan rule); so does each
        paragraph after it set so too (a chain). A paragraph of the chain that reaches the frame's foot
        splits there as any other, the chain before it staying; one that has to go on to the next frame
        whole takes the whole chain before it along. A paragraph at the frame's top stays."""

        if start == para.prev:
            return count
        saved, carry = list(self.page_notes), self.carry
        try:
            return self._chain_stays(para, following, start, remaining, count)
        finally:
            self.page_notes, self.carry = saved, carry

    def _chain_stays(self, para: _pages._Para, following: list[_pages._Para], start: int, remaining: int, count: int) -> int:
        for line in range(remaining):  # the notes of the lines placed take room below the chain
            height, many, _ = para.notes.get(line, (0, 0, 0))
            self.page_notes = [self.page_notes[0] + height, self.page_notes[1] + many]
        after = start + para.span(0, remaining) + para.next
        for item in following:
            after += item.prev
            if not item.keep_next or item.table is not None or item.page_break or item.break_before \
                    or item is following[-1]:
                need = 2 if item.widow_orphan and item.lines > 1 else 1
                return count if self._fits(after, need, item) >= need else 0
            fit = self._fits(after, item.lines, item)
            if fit == item.lines:
                after += item.span(0, item.lines) + item.next
                for height, many, _ in item.notes.values():
                    self.page_notes = [self.page_notes[0] + height, self.page_notes[1] + many]
                continue
            # it splits at the foot, its first lines staying with the paragraph before; or it goes on whole
            return count if fit and not item.keep_lines else 0
        return count

    def _fits(self, start: int, count: int, para: _pages._Para, first: int = 0) -> int:
        """How many of *count* lines (from line *first*) from *start* stay in the frame, each ending above
        the note area including the notes anchored in it. A line whose notes fit only in part (at least
        their first line) still stays, and ends the frame."""

        fitting, height, many = 0, self.page_notes[0], self.page_notes[1]
        self.carry = 0
        while fitting < count:
            note_height, notes, head = para.notes.get(first + fitting, (0, 0, 0))
            bottom = start + para.span(first, fitting) + para.height(first + fitting)
            limit = self.body - self.notes.area(height + note_height, many + notes)
            if bottom < limit or para.moves and para.own and start + para.own < limit and bottom == limit:
                # (an object alone in an empty paragraph may end at the foot, its own line not)
                height, many, fitting = height + note_height, many + notes, fitting + 1
                continue
            if notes and bottom < self.body - self.notes.area(height + head, many + notes):
                room = self.body - bottom - self.notes.area(height, many + notes) + note_height
                self.carry = max(note_height - room, 0)
                fitting += 1
            break
        return fitting

    def _place(self, para: _pages._Para, first: int, count: int) -> None:
        """Count the notes of *count* lines from line *first*, just placed."""

        for line, (frame, top) in zip(range(first, first + count), self.out[len(self.out) - count:]):
            note_height, notes, _ = para.notes.get(line, (0, 0, 0))
            self.page_notes[0] += note_height
            self.page_notes[1] += notes
            if not para.kept:
                self._reach(frame, top, top + para.height(line))



# Import after definitions so either private module or facade can be imported first.
from . import pages as _pages
