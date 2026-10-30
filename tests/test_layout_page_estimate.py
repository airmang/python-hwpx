"""``hwpx.experimental.estimate_pages``: the pages and line positions Hancom lays a document out on.

Each ``pages_*.hwpx`` fixture is a document Hancom opened, laid out and saved. Its line caches
(``hp:linesegarray``) hold where Hancom put every line of a paragraph (``vertpos``, from the top
of the column), and ``HANCOM_PAGES`` the number of pages Hancom drew.
"""

from __future__ import annotations

import copy
import io
import re
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.experimental import EstimatedLine, PageEstimate, estimate_pages
from hwpx.layout import pages as page_layout

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
FIXTURES = Path(__file__).parent / "fixtures" / "hancom_saved"
HANCOM_PAGES = {
    # A picture (or a rectangle) placed top and bottom alone in an empty paragraph whose spacing after is 1000,
    # the next paragraph's spacing before 600, the empty line 1600 tall with its spacing: unless the object
    # moves with the text, may overlap and starts above the line's foot, the empty line stays at the paragraph's
    # top and the next paragraph starts below the object's foot or the line with both spacings, whichever is
    # lower; such an object pushes the empty line itself below its foot instead.
    "pages_empty_paragraph_object_staying_short": 1,  # staying on its page, 600 tall: the spacings decide
    "pages_empty_paragraph_object_staying_tall": 1,  # 19595 tall: its foot decides, the spacings inside it
    "pages_empty_paragraph_object_no_overlap_tall": 1,  # moving with the text, not overlapping
    "pages_empty_paragraph_object_no_overlap_short_offset": 1,  # ... 500 down, 600 tall
    "pages_empty_paragraph_object_overlap_short": 1,  # moving and overlapping, at the top: the line below it
    "pages_empty_paragraph_object_overlap_tall_offset": 1,  # ... 500 down, 19595 tall
    "pages_empty_paragraph_object_overlap_below_its_line": 1,  # ... 2000 down, below the line: the line stays
    "pages_empty_paragraph_rectangle_staying": 1,  # a rectangle staying, 500 down, 600 tall
    # ... moving and overlapping, 600 tall: the line goes below it when it starts above the line's characters'
    # foot (10 pt: 1000, 20 pt: 2000), not above the line with its spacing
    "pages_empty_paragraph_object_overlap_10pt_999": 1,
    "pages_empty_paragraph_object_overlap_10pt_1000": 1,
    "pages_empty_paragraph_object_overlap_20pt_1999": 1,
    "pages_empty_paragraph_object_overlap_20pt_2000": 1,
    # An empty paragraph holding a table set as a character and a table placed top and bottom from its top (6000
    # tall), the line 42520 wide: a character table wider than the line takes that line alone, the placed
    # table's anchor going on that line (anchor first) or on an empty line of its own below it (anchor last),
    # the placed table at that line's top; one as wide as the line shares its line with the anchor.
    # Five pictures 20000 x 11000 set as characters, each in its own paragraph (one page bare), with an effect:
    # Hancom lays each out as large as it and its glow (the radius on each side) or its outer shadow (moved its
    # distance in its direction, spread by its radius), the line that much taller
    "pages_picture_effect_glow1000": 2,  # each line 13000
    "pages_picture_effect_glow300": 1,  # 11600
    "pages_picture_effect_shadow_down": 2,  # 1500 below, spread 600: 13100
    "pages_picture_effect_shadow_up": 2,  # 1500 above: 13100
    "pages_picture_effect_shadow_right": 2,  # 1500 to the right: only its spread, 12200
    "pages_picture_effect_shadow_inside": 1,  # an inner shadow takes no room
    "pages_picture_effect_text_and_glow": 2,  # a picture among text with a glow
    # a glow 600 and a shadow 800 down-right at 45 degrees, spread 400 -- in whole pixels (75 HWPUNIT), so as 450
    "pages_picture_effect_glow_and_diagonal_shadow": 2,  # 13215
    # A rectangle 5000 tall (or 3000) placed top and bottom from the top of an empty paragraph, its vertOffset up
    # (kept as an unsigned 32-bit number), after eleven lines: Hancom places it from where the paragraph's top
    # would be and moves the lines before it that reach into its band to its foot, the rest following
    "pages_para_shape_unsigned_offset": 1,  # 1500 up: the line before goes below it
    "pages_para_shape_unsigned_offset_500": 1,  # 500 up: no line reaches it, the paragraph's line below its foot
    "pages_para_shape_unsigned_offset_3000": 1,  # 3000 up: the line before; the one before that ends at its top
    "pages_para_shape_unsigned_offset_4900": 1,  # 4900 up: the three lines before
    "pages_para_shape_unsigned_offset_1500_h3000": 1,
    "pages_wide_table_as_character_anchor_first": 1,  # 44000 x 3000
    "pages_wide_table_as_character_anchor_last": 1,
    "pages_wide_table_as_character_tall_anchor_first": 3,  # 44000 x 60000: on the next page's top, the anchor on its line
    "pages_wide_table_as_character_tall_anchor_last": 2,  # the placed table's rows flowing on to the next page
    "pages_line_wide_table_as_character_anchor_first": 1,  # 42520 x 3000
    "pages_line_wide_table_as_character_anchor_last": 1,
    # ... with three characters of text: the anchor stays at the end of the line holding the character before
    # it, the placed table at that line's top
    "pages_wide_table_as_character_after_text_and_anchor": 1,  # text, anchor, wide table: on the text's line
    "pages_wide_table_as_character_text_then_anchor": 1,  # wide table, text, anchor: on the text's line below it
    "pages_wide_table_as_character_between_text_and_anchor": 1,  # text, wide table, anchor: on the table's line
    # A table placed top and bottom anchored in text, 43 characters fitting the first line: after 43 the anchor
    # stays at that line's end, the table at its top; after 44 behind a picture placed behind the text, which
    # takes eight places in the line cache as the anchor does, it falls on the second line
    "pages_table_anchored_at_the_end_of_a_line_of_text": 1,
    "pages_table_anchored_after_a_line_of_text_behind_a_picture": 1,
    # A table 30000 wide placed top and bottom at the top of a paragraph after a line of text, the paragraph's
    # first line not fitting below it: one fitting there (6000 tall, beside a table set as a character 60000
    # tall, before or after it; or one moved row by row) goes on with that line to the next page's top; one
    # split cell by cell ending at the page foot (three rows 21000 tall, the last one's room to spare cut) goes
    # on with it too (one set not to split with no room: test_an_unsplit_table_without_room_goes_on_alone)
    "pages_flowing_table_then_tall_table_as_character": 3,
    "pages_tall_table_as_character_then_flowing_table": 3,
    "pages_row_split_table_then_tall_table_as_character": 3,
    "pages_cell_split_table_ending_at_the_foot_above_its_line": 3,
    # A rectangle placed top and bottom 2000 down from an empty paragraph's top, 20000 x 8000 (one column
    # 48188 wide): the next paragraph's line reaching it goes below it, the whole width, even holding objects
    # set as characters (a group or a picture 44633 x 648, which do not make it taller than its text):
    "pages_push_band_text": 1,  # a character alone
    "pages_push_band_group_as_character": 1,  # a character, a group and a polygon in front of the text
    "pages_push_band_picture_as_character": 1,
    "pages_push_band_group_as_character_alone": 1,  # the group and the polygon, no text
    # A picture wrapped square from an empty paragraph's left, 41631 x 27112, leaving 6557 beside it; the
    # next paragraph holds a table set as a character alone:
    # An empty paragraph holding a picture wrapped square 14000 from its left, text on both sides: an empty
    # line reaching the picture is two empty pieces beside it, one above it (the picture placed lower than
    # the line's foot) is one line
    "pages_square_picture_reaching_an_empty_line": 1,  # placed 900 below the line's top: two pieces
    "pages_square_picture_just_below_an_empty_line": 1,  # 1100 below: one line
    "pages_square_picture_far_below_an_empty_line": 1,  # 8000 below: one line
    "pages_square_band_table_as_character_alone": 1,  # 47058 wide: beside it all the same, reaching past the room
    "pages_square_band_narrow_table_as_character_alone": 1,  # 5000 wide: beside it, and the lines after
    # ... or text whose lines in the room beside the picture are as wide as it, and an object set as a
    # character among it: a line holding one stays beside the picture, one wider than the room alone on its
    # line, reaching past it.
    "pages_square_band_table_as_character_among_text": 1,  # a table 47058 wide
    "pages_square_band_narrow_table_as_character_among_text": 1,  # 5000 wide
    "pages_square_band_picture_as_character_among_text": 1,  # a picture 47058 x 5000
    # A picture 20000 x 27112 wrapped square in the middle of the column (10 pt text spaced 160%), flowing with
    # the text, its band past the body's foot: Hancom sets it alone at the next page's body top, whatever its
    # offset, the lines of its own page the whole width and the lines on the next page whose top is above its
    # foot beside it, in two pieces:
    "pages_square_picture_moved_to_the_next_page": 2,  # short lines beside it there, each ending in its first
                                                       # piece: the second one empty
    "pages_square_picture_moved_text_going_on_beside_it": 3,  # a paragraph going on to the next page
    "pages_square_picture_moved_at_the_left": 3,  # at the column's left: the lines one piece on its right
    "pages_square_picture_moved_its_paragraph_going_on": 2,  # its own paragraph going on beside it
    "pages_square_picture_moved_from_8000_down": 3,  # placed 8000 down from its paragraph: at the top too
    "pages_square_table_not_split_moved_to_the_next_page": 3,  # a table of six rows at the column's left,
                                                                # set not to split: the same
    # A table wrapped square at the column's left (rows of two columns, 10 pt text spaced 160%), flowing with
    # the text and allowed to split, its band past the body's foot: Hancom splits it over the page end as a
    # flowing table, and the lines on each page it reaches go beside its part there:
    "pages_square_table_split_between_cell_lines": 3,  # 15000 wide, split between the lines of a row of four
    "pages_square_table_split_in_a_merged_cell": 3,  # the same through a cell merged over three rows
    "pages_square_table_split_over_three_pages": 3,  # 25 rows: all the lines of the page it fills beside it
    "pages_square_table_1548_down_split": 3,  # placed 1548 down: its paragraph's line above it the whole width
    "pages_square_table_split_text_on_both_sides": 3,  # in the middle: the lines in two pieces
    "pages_square_table_wide_split_text_beside_it": 2,  # 45626 wide, 2562 left beside it: two characters a
                                                        # line there
    # A table 30000 x 20000 wrapped square at the column's left from its paragraph 8000 down (10 pt text spaced
    # 160%), its control after 16 characters, on the paragraph's first line laid out the column's whole width:
    # Hancom places it from the paragraph's top as one before the text, the lines reaching it beside it:
    "pages_square_table_after_text": 1,  # the paragraph's own lines beside it, 12 characters a line
    "pages_square_table_after_text_2383_down": 1,  # placed 2383 down: the paragraph's line above it the
                                                   # whole width, the paragraphs after beside it
    "pages_square_table_before_text": 1,  # its control before the text: the same
    "pages_square_table_after_text_on_the_second_line": 1,  # after 60 characters, on the second line laid
                                                            # out the whole width: from that line's top (9600),
                                                            # the first line the whole width
    "pages_square_table_after_a_full_first_line": 1,  # after 43, which fill the first line: on that line, where
                                                      # its text ends, so from the paragraph's top
    "pages_square_table_after_two_full_lines": 1,  # after 86: on the second line, from its top
    "pages_picture_1319_down_moved_to_the_next_page": 3,  # a picture 8000 tall placed top and bottom 1319
                                                          # below its empty paragraph's line: alone at the
                                                          # next page's top, the line staying, the lines
                                                          # there reaching it below it
    # A picture 4000 tall placed top and bottom at its paragraph's top (offset 0), its foot past the body's:
    "pages_picture_at_the_paragraph_top_moved_to_the_next_page": 2,  # alone at the next page's top, the
                                                                     # empty line staying, the lines there
                                                                     # below it
    "pages_picture_at_the_paragraph_top_with_text": 2,  # in a paragraph of text: the same, its line staying
    "pages_picture_at_the_paragraph_top_not_flowing": 2,  # not flowing with the text: it stays on its page
                                                          # past the foot, the empty line there, the next
                                                          # paragraph at the next page's top
    "pages_picture_at_the_paragraph_top_fitting": 2,  # one that fits: the next paragraph at its foot
    # A rectangle 30000 x 5000 set as a character alone in its paragraph (10 pt lines spaced 160% around it):
    # its line is as tall as it and its parallel shadow's move up or down, offsetY + 600 for a shadow at the
    # bottom and offsetY - 600 at the top (the line's width adds nothing):
    "pages_char_shape_no_shadow": 1,
    "pages_char_shape_shadow_right_bottom_283": 1,  # 883 down
    "pages_char_shape_shadow_right_bottom_minus_283": 1,  # 317 down (written "-283")
    "pages_char_shape_shadow_left_bottom_283": 1,  # 883 down
    "pages_char_shape_shadow_left_top_283": 1,  # 317 up: the rectangle drawn that much lower
    "pages_char_shape_shadow_left_top_1000": 1,  # 400 down
    "pages_char_shape_shadow_thick_line": 1,  # a 283 line and a shadow 883 down
    # Such a picture gone on to the next page's top, then a table placed top and bottom (cells split):
    "pages_picture_moved_then_a_table_moved_whole": 2,  # no room for its first row: it starts below the
                                                         # picture, its paragraph's line staying behind
    "pages_picture_moved_then_a_table_split": 2,  # split: its rest goes on at the page's top over the picture,
                                                   # the text after below both
    "pages_picture_moved_then_a_table_split_picture_right": 2,  # the picture right of the table
    "pages_picture_moved_then_a_table_paragraph_moved": 2,  # its paragraph's line going on too: as at the
                                                             # page's top below the picture
    "pages_picture_pushing_its_first_line_above_the_foot": 2,  # a picture 30000 tall 1319 below a paragraph of
                                                               # 14 pt text: its line goes below the picture,
                                                               # which ends above the foot, and stays there
    "pages_line_pushed_below_a_tall_picture_past_the_foot": 2,  # one 1319 below a line of text: the next line
                                                                # goes below it, past the foot, to the next
                                                                # page's top
    # A picture 15000 x 8000 placed top and bottom 1000 below its anchor line, the second of a paragraph of
    # two, low on the page: it stands that far below the anchor line's top
    "pages_line_pushed_below_a_picture_past_the_foot": 2,  # it fits; the next paragraph's first line, going
                                                           # below it past the foot, starts the next page
    "pages_picture_offset_from_an_anchor_line_on_the_next_page": 2,  # the anchor line goes on to the next
                                                                     # page's top, the picture with it
    "pages_square_picture_above_the_foot_short_lines_beside_it": 2,  # its band above the foot: short lines
                                                                     # beside it in two pieces
    "pages_square_picture_staying_short_lines_beside_it": 2,  # not flowing with the text, it stays on its
                                                              # page: the empty line of its paragraph and
                                                              # short lines beside it, in two pieces
    "pages_square_band_table_as_character_below_a_short_band": 1,  # the picture 5000 tall: the table's line
                                                                   # comes after the band anyway
    # A rectangle 20000 x 3000 wrapped square 1000 below a line of text, a line beside it, then a paragraph
    # holding a table placed top and bottom before its text: Hancom sets the table at its own offset whatever
    # the band, and the paragraph's line below the table, past the band:
    "pages_square_band_then_a_table_below_the_band": 1,  # 600 down, the paragraph's top 200 above the band's
                                                         # foot
    "pages_square_band_then_a_table_in_the_band": 1,  # at its top: drawn over the rectangle
    "pages_square_band_then_a_table_high_in_the_band": 1,  # the paragraph's top 2000 above the band's foot
    "pages_square_band_then_a_table_margin_top": 1,  # the rectangle's top outer margin 1417 in its band
    "pages_square_band_then_a_table_after_the_band": 1,  # the paragraph after the band
    "pages_fixed_width_spaces": 2,  # rows of a syllable and a fixed-width space: a quarter em that hangs
    # Tables of short sentences, one cell holding "… " among its words: Hancom starts a line with the ellipsis after
    # a space (attached to the character before it, it keeps to that one).
    "pages_ellipsis_starts_a_cell_line": 4,
    # Paragraphs of sentences among which " 」" or " %" stands after a space: Hancom starts a line with the mark
    # there, as with any closing punctuation after a space (attached to a character, it moves down with it).
    "pages_closing_bracket_after_a_space_starts_a_line": 2,
    "pages_percent_after_a_space_starts_a_line": 2,
    "pages_no_break_spaces": 2,  # rows of "가나" and a no-break space: each is half an em and keeps the row
                                  # one word
    "pages_typed_ideographic_spaces": 5,  # cells of "가나다라마" and a U+3000 typed in the text, a full em
                                           # that hangs however many follow, or fixed-width spaces
    "pages_empty_run_ending_after_a_larger_first_line": 1,  # 20 pt on the first line, 10 pt text on the
                                                             # last before an empty 14 pt run: 14 pt tall
    "pages_empty_run_ending_after_larger_text_amid": 1,  # the same with the 20 pt run amid the 10 pt text
    "pages_empty_run_ending_a_paragraph": 2,  # spaces or text before an empty run of another size (and
                                               # after one): the one ending a paragraph makes its last line
                                               # as tall as itself when larger
    # A run of 14 pt before a line of 10 pt text (함초롬바탕, spaced 160%): one holding nothing but controls
    # makes the line as tall as itself (1400, spaced 840), an empty one takes no room:
    "pages_section_controls_run_taller_than_the_text": 1,  # the section's and the columns' definitions
    "pages_page_number_run_taller_than_the_text": 1,  # a page number
    "pages_auto_number_run_taller_than_the_text": 1,  # an auto number (the page's)
    "pages_footer_run_taller_than_the_text": 1,  # a footer
    "pages_page_hiding_run_taller_than_the_text": 1,  # a page-number hiding
    "pages_empty_run_taller_than_the_text": 1,  # an empty run: the line 1000 tall (Hancom drops the run)
    "pages_section_controls_run_after_the_text": 1,  # the controls after the text: Hancom moves them first
                                                      # and leaves an empty 14 pt run ending the line
    "pages_text_12pt_160": 5,             # 12 pt text, line spacing 160%
    # 10 pt text in a paragraph shape taking its line height from the font (fontLineHeight), line spacing 160%:
    # each line as tall as its face's ascent and descent, spaced from that height; at the size the lines
    # would all fit on the first page:
    "pages_font_line_height_hamchorom_lines": 2,  # 36 one-line paragraphs in 함초롬바탕: 1300 tall, 2080 apart
    "pages_font_line_height_malgun_lines": 2,  # in 맑은 고딕: 1331 tall, 2127 apart
    "pages_font_line_height_long_paragraph": 2,  # one paragraph of 35 lines in 함초롬바탕
    "pages_font_line_height_cell": 2,  # 25 such lines in a cell, then 10 paragraphs of 10 pt text
    "pages_font_line_height_at_least": 2,  # 52 one-line paragraphs, line spacing at least 1200: 1300 apart
    "pages_spacing_20_20": 3,             # spacing before and after paragraphs
    "pages_boundary_widow_on": 2,         # widow/orphan control at the page end
    "pages_line_ends_at_page_foot": 2,    # a line ending right at the body's foot goes on
    "pages_empty_line_ends_at_page_foot": 2,  # an empty one too
    "pages_line_ends_200_above_page_foot": 2,  # one ending 200 above it stays
    "pages_line_ends_1_above_page_foot": 2,    # and one ending 1 above it
    "pages_line_ends_100_above_page_foot": 2,  # and 100 above it: no room is kept below lines
    # Documents of paragraphs, tables, pictures, shapes and footnotes whose paragraphs set to stay with the next
    # follow each other (a chain): a paragraph of the chain reaching the page's foot splits there, the chain
    # before it staying; one that has to go on to the next page whole (its next paragraph's first line, or a
    # table, no longer fits) takes the whole chain before it along, footnotes of the chain taking their room.
    "pages_keep_with_next_chain_goes_on": 2,
    "pages_keep_with_next_chain_before_a_table": 4,
    "pages_keep_with_next_chain_splits_at_the_foot": 2,
    "pages_keep_with_next_chain_with_a_footnote": 7,
    "pages_keep_with_next_chain_of_several_lines_goes_on": 2,
    "pages_keep_keep_with_next": 3,       # keep with next
    # Two columns whose gap is written 2**32 - 2**15: a signed 32-bit number, -32768, so the columns overlap and
    # each is (42520 + 32768) / 2 wide, as Hancom lays them out.
    "columns_gap_wrapped": 1,
    "pages_columns_2_break": 4,           # two columns and a column break
    # Columns changing inside the section (10 pt lines spaced 160%): three lines in one column, a paragraph
    # starting two columns (gap 1200) and the lines after it, then one starting one column and three lines.
    # Hancom starts each area of columns 1134 below the lowest line of the one before, counts its lines from
    # its top, and balances an area followed by another on its last page, by height:
    "pages_columns_change_newspaper_short": 1,  # six lines: four and three (the empty starting line counts)
    "pages_columns_change_newspaper_long": 1,  # thirty: sixteen and fifteen
    "pages_columns_change_newspaper_over_a_page": 2,  # ninety: full columns, then the rest balanced
    "pages_columns_change_newspaper_break_over_a_page": 2,  # a column break among them
    "pages_columns_change_balanced_break": 1,  # balanced columns: a column break starts a balanced block
    "pages_columns_change_tall_empty_line": 1,  # the starting line 20 pt: three lines and four
    "pages_columns_change_after_text": 1,  # the definitions behind their paragraphs' text: areas, no columns
    "pages_columns_change_text_after_definition": 1,  # ahead of it
    "pages_columns_change_text_after_definition_break": 1,  # thirty lines with a column break
    "pages_footnotes_6": 3,               # footnotes at the page foot
    "pages_table_flow_repeat_header": 3,  # a table flowing with the text, header row repeated
    # A table set as a character alone in its paragraph (split by cell, header row repeated) whose line ends
    # just above the body's foot (65762) or at it: it never splits; one that does not end above the foot goes
    # on whole to the next page's top, whatever the spacing after it:
    "pages_char_table_at_the_page_end_room_1": 2,  # 54400 + 11361: it stays (the spacing past the foot)
    "pages_char_table_at_the_page_end_room_0": 2,  # 11362 tall: on whole to the next page
    "pages_char_table_past_the_page_end_page_break_table": 2,  # split by table: the same
    "pages_char_table_fixed_spacing_room_1": 1,  # fixed spacing (the line after it over it): it stays
    "pages_char_table_fixed_spacing_room_0": 2,  # on to the next page
    "pages_char_table_taller_than_a_page": 3,  # 80000: at the next page's top, cut; the text after on the next
    "pages_table_repeated_header_second_cell_marked": 2,  # only its second cell a header cell: repeated
    "pages_table_flow_multiline_cells": 4,  # a flowing table split between cell lines
    # A cell 20000 wide declared 282 tall (its lines make its row) holding 30 "가" (29160) in 10 pt
    # 함초롬바탕: one whose text never breaks into lines (hp:subList@lineWrap SQUEEZE or KEEP) keeps each
    # paragraph on one line but for its line breaks, pressed into the cell when drawn:
    "pages_table_cell_squeezed_on_one_line": 1,  # SQUEEZE: one line, the row 1282 tall
    "pages_table_cell_kept_on_one_line": 1,  # KEEP: the same
    "pages_table_cell_broken_into_lines": 1,  # BREAK: two lines (20 and 10), the row 2882 tall
    "pages_table_cell_squeezed_after_a_line_break": 1,  # 10, a line break, 30: two lines
    "pages_table_cell_squeezed_paragraphs": 1,  # two paragraphs of 30: a line each
    "pages_table_cell_kept_after_a_line_break": 1,  # KEEP, 10, a line break, 30: two lines
    "pages_cell_paragraphs_split_s600_400_b0": 3,  # one cell of 25 paragraphs of 3 lines, spaced 600 before
                                                   # and 400 after, split over pages: the spacing counts,
                                                   # and a part starting with a paragraph keeps 600 above it
    "pages_cell_paragraphs_split_s600_400_b30": 4,  # the same after 30 lines
    "pages_cell_paragraphs_split_s0_400_b30": 3,  # spaced 400 after only: a paragraph whose first line fits
                                                  # only without that spacing goes on
    "pages_object_pushing_characters_off500": 1,  # no text, a rectangle set as a character and one top
                                                  # and bottom 500 down from the paragraph's top: the
                                                  # line goes below it, as a line of text would
    "pages_object_pushing_characters_off1398": 1,  # the same 1398 down
    "pages_object_pushing_characters_off1398_char3000": 1,  # with a rectangle 3000 tall set as a character
    # Objects set as characters in a paragraph of a cell of a flowing table, 10 pt text spaced 160%:
    "pages_cell_picture_as_character_alone": 1,  # a picture 3000 x 4000 alone: one line 4000 tall
    "pages_cell_rectangle_as_character_alone": 1,  # a rectangle 3000 x 2000
    "pages_cell_equation_alone": 1,  # an equation
    "pages_cell_picture_before_text": 1,  # the picture before two lines of text: the first line as tall
    "pages_cell_picture_among_text": 1,  # among them
    "pages_cell_picture_after_text": 1,  # after them: the second line as tall
    "pages_cell_two_pictures_on_one_line": 1,  # two that fit side by side
    "pages_cell_two_pictures_on_two_lines": 1,  # two that do not: a line each
    "pages_cell_picture_alone_fixed_spacing": 1,  # alone, line spacing fixed at 1600
    "pages_cell_picture_in_a_table_as_character": 1,  # alone, in a table set as a character
    "pages_cell_picture_then_a_line": 1,  # alone, then a paragraph of a line: spaced from the text size
    # A table set as a character in a cell paragraph, and beside it an object 5000 x 3000 placed 1000 down from
    # the paragraph and reaching below the table: it takes no room, the line is the table's
    "pages_cell_table_as_character_and_a_drawing_in_front_of_the_text": 1,  # a rectangle in front of the text
    "pages_cell_table_as_character_and_a_picture_behind_the_text": 1,  # a picture behind it
    # the rectangle, and text after the table on its line:
    "pages_cell_table_as_character_then_text_and_a_drawing_in_front_of_the_text": 1,
    # A section hiding a page's first empty lines (hp:visibility@hideFirstEmptyLine), its first page full:
    "pages_hide_empty_lines_one": 2,  # an empty paragraph past the foot stays there, the text after it
                                      # starts the next page
    "pages_hide_empty_lines_two": 2,  # two, one on the other
    "pages_hide_empty_lines_four": 2,  # four: the third and fourth start the next page
    "pages_hide_empty_lines_page_break": 2,  # one with a page break is not hidden
    "pages_hide_empty_lines_space": 2,  # nor one holding a space
    "pages_hide_empty_lines_column_end": 1,  # two at the end of the first of two columns
    "pages_hide_empty_lines_20pt": 2,  # one of 20 pt
    "pages_hide_empty_lines_spaced_past_the_foot": 2,  # the last line ending 200 above the foot, the
                                                       # empty one spaced 562 before it
    "pages_hide_empty_lines_ending_the_document": 1,  # two ending the document: no second page
    "pages_hide_empty_lines_off": 2,  # two, the setting off: they start the next page
    "pages_joined_rows_over_pages_n100": 3,  # 100 one-line rows joined by a cell merged down all of them,
                                             # split between cell lines: what is left is split again at
                                             # each page end
    "pages_joined_rows_over_pages_label150": 4,  # 60 such rows and a merged cell of 150 lines: the cell
                                                 # goes on alone over the last two pages
    "pages_joined_rows_over_pages_mixed": 3,  # rows of one and three lines: a row split between its lines
    "pages_joined_rows_over_pages_declared_cell": 3,  # 8 rows joined by a cell declared 80000 tall, after 20
                                                      # rows: its room cut at each page end, 10 rows after
    "pages_joined_rows_over_pages_empty_declared_cell": 3,  # an empty cell over 8 rows declared 75000 tall
                                                            # after 36 lines: cut over three pages
    # A table whose cells of a column are not all as wide (``hp:cellSz``), every cell declared 282 tall so that
    # its lines make its row (10 pt 함초롬바탕, "가" 972 wide), then three lines of text: Hancom lays a cell out
    # on the table's grid, its columns stacked from the left, each as wide as its widest cell of its own, and a
    # merged cell wider than its columns widening the last of them:
    "pages_table_column_as_wide_as_its_widest_cell": 1,  # 30000, 32000 and 31000 wide: the first's 31
                                                         # characters on one line
    "pages_table_column_of_equal_cells": 1,  # all 30000: on two lines
    "pages_table_columns_stacked_from_the_left": 1,  # rows of 8000 and 30000, 7683 and 30500: both second
                                                     # cells 30500 wide, 31 characters on one line
    "pages_table_merged_cell_widening_its_last_column": 1,  # 10000 and 20000 below a merged 31000: the
                                                            # second 21000 wide, 21 characters on one line
    # Rows 1-5 joined by a cell merged down them (4 lines), declared taller than their text, the page end
    # falling among them:
    "pages_joined_rows_declared_rest_with_a_line": 2,  # in row 1: its rest is the line going on with the
                                                       # cell margins, taller than the declared rest
    "pages_joined_rows_declared_cut_in_a_later_row": 2,  # in row 2: its declared rest, taller than the line
    "pages_joined_rows_declared_first_line_not_fitting": 2,  # in row 3, before its first line: whole on the
                                                             # next page
    "pages_joined_rows_text_height_split": 2,  # in row 1, the rows as tall as their text: lines and margins
    "pages_table_row_split_a_first_line_not_fitting": 2,  # the first 8 pt line of one cell fits, the 16 pt
                                                            # line of the other does not: it goes on whole
    "pages_table_row_split_every_first_line_fitting": 2,  # room for both: split after two 8 pt lines
    "pages_table_flow_starts_next_page": 2,  # its first row does not fit: the text goes on under the anchor
    "pages_table_flow_starts_next_page_long": 4,  # the same over two pages: text resumes under the table
    "pages_table_cell_first_paragraph_spaced_before": 1,  # six lines spaced 900 before in a cell declared 1000
                                                         # tall: the row as tall as the spacing, lines, margins
    "pages_table_cell_two_paragraphs_spaced_before": 1,  # 900 before three lines, 600 before three more
    "pages_table_as_character_cell_first_paragraph_spaced_before": 1,  # in a table set as a character
    "pages_table_cell_first_paragraph_spaced_before_over_two_pages": 2,  # 60 lines split between lines: the
                                                                        # part on the next page not spaced
    "pages_table_cells_first_paragraphs_spaced_before_row_by_row": 3,  # three rows of 25, each spaced
    # An empty paragraph's flowing table of rows 3000 tall, from 8000 down, then a paragraph of two lines:
    "pages_table_over_two_pages_then_text": 2,  # right under the table's end on the second page
    "pages_table_over_two_pages_then_text_spaced_before": 2,  # spaced 1500 before: still right under it
    "pages_table_over_two_pages_then_a_column_break": 2,  # the same: the column after the anchor line's
    "pages_table_over_two_pages_then_a_column_break_spaced_before": 2,
    "pages_table_on_one_page_then_a_column_break": 2,  # a table ending on its page: the next page's top
    "pages_table_over_two_pages_then_a_page_break": 3,  # the page after the table's last
    "pages_table_over_three_pages_then_a_page_break": 4,
    # An object placed top and bottom from its empty paragraph's top, a space after it or not:
    "pages_table_then_nothing": 1,  # the line on the table's top, no room taken: the text after under the table
    "pages_table_then_a_space": 1,  # a space is text: its line goes under the table, at full width
    "pages_table_then_two_spaces": 1,
    "pages_picture_then_a_space": 1,
    "pages_table_as_character_then_a_space": 1,  # set as a character: the table and the space on one line
    "pages_table_cell_holding_a_table_then_a_space": 1,  # in a cell: the space's line under the inner table
    "pages_picture_alone_in_a_plain_paragraph": 1,  # a picture alone: the line on its top, no room taken
    "pages_picture_alone_in_a_bulleted_paragraph": 1,  # a bullet is text: the line under the picture
    "pages_picture_alone_in_a_numbered_paragraph": 1,  # so is a number
    "pages_table_alone_in_a_bulleted_paragraph": 1,
    # The same 60762 down (10 pt text spaced 160%), the table (rows 8000, 1282 and 1282 tall) not starting
    # there: it starts at the next page's top, the paragraph's line staying, a space after the table or not,
    # and the text after goes on under that line.
    "pages_table_then_nothing_starting_on_the_next_page": 2,
    "pages_table_then_a_space_starting_on_the_next_page": 2,
    "pages_table_not_split_then_a_space_starting_on_the_next_page": 2,  # set not to split: the same
    # Sixteen times on a page of their own, after 33 to 40 lines: such a table (4 rows, 12900 tall, moved row by row
    # or split by cells) then a space. Moved row by row and not starting there, it starts at the next page's top and
    # the paragraph's line stays where it fits; where the line does not fit either, it goes on with the table, below it
    "pages_table_then_a_space_past_the_page_foot": 33,
    # One-cell tables 2000 tall holding one, three or six lines, set as a character or placed top and bottom, set not
    # to change size (hp:sz@protect) or not: one so set keeps its rows as declared, its text cut off below, and goes
    # on over a page end whole; one not so set grows to hold its text
    "pages_tables_set_not_to_change_size": 2,
    # A cell of a flowing table, a picture 20000 x 10000 placed top and bottom from a paragraph of it:
    "pages_table_cell_picture_first": 1,  # alone in the first: the line on its top, the row as tall as it
    "pages_table_cell_picture_second": 1,  # alone in the second, after a line: from that paragraph's top
    "pages_table_cell_picture_second_text": 1,  # with text after it: the text under it
    "pages_table_cell_picture_up_first": 1,  # placed 5000 up: at the cell's top all the same
    "pages_table_cell_picture_up_second": 1,  # 1000 up from the second paragraph: at its top
    "pages_table_cell_picture_up_second_far": 1,  # 30000 up: at its top too
    "pages_table_cell_picture_in_a_bulleted_paragraph": 1,  # alone in a bulleted paragraph: the bullet under it
    "pages_picture_alone_after_a_line": 1,  # in the body: the line on its top, the text after under it
    # An empty paragraph 8000 down holding a table 6659 tall (outer margins 283 above and 1417 below) or a
    # picture as tall placed top and bottom from its top, and a picture 10000 x 5000 in front of or behind the
    # text: Hancom sets the empty line below the object (16359), as the whole width, as for a space or a label;
    # without the floating picture on the object's top, taking no room (8000).
    "pages_empty_paragraph_table_and_a_picture_behind_on_the_paper": 1,  # the picture placed on the paper
    "pages_empty_paragraph_table_and_a_picture_behind_from_it": 1,  # placed from the paragraph, over the table
    "pages_empty_paragraph_table_and_a_picture_in_front": 1,
    "pages_empty_paragraph_picture_and_a_picture_behind": 1,  # a picture placed top and bottom
    "pages_empty_paragraph_table_alone": 1,
    "pages_cell_table_top_and_bottom_and_a_drawing_behind_the_text": 1,  # in a cell, a rectangle behind the
                                                                         # text: the cell's line under the
                                                                         # table too
    # A table set as a character (a row 1282 tall) 200 to 2000 narrower than the column (42520; 10 pt text spaced
    # 160%, a space 500 wide), spaces after it: the two right after it stay on its line wherever they start, a
    # further one starting at or past the margin goes on to the next line, the paragraph after below them:
    "pages_table_as_character_200_short_then_a_space": 1,
    "pages_table_as_character_200_short_then_two_spaces": 1,  # the second starting 300 past the margin
    "pages_table_as_character_200_short_then_three_spaces": 1,  # the third on a line of its own
    "pages_table_as_character_600_short_then_three_spaces": 1,  # the third starting 400 past the margin
    "pages_table_as_character_1000_short_then_three_spaces": 1,  # the third starting at the margin
    "pages_table_as_character_2000_short_then_three_spaces": 1,  # all three fit beside it
    "pages_table_as_character_200_short_then_three_12pt_spaces": 1,  # of 12 pt: the third's line 1200 tall
    "pages_table_as_character_200_short_after_two_spaces": 1,  # two before it: the table on the next line
    # A table set as a character (a row 1282 tall) 1000 wider than the column (42520), alone in its paragraph
    # but for a page-number control: a control before it stands on the table's line, one after it on an empty
    # line of the text under it.
    "pages_page_number_then_a_table_wider_than_the_line": 1,  # the control first: the table's line alone
    "pages_table_wider_than_the_line_then_a_page_number": 1,  # the table first: the control's line under it
    "pages_page_number_then_a_table_that_fits": 1,  # 1000 narrower than the column: one line
    "pages_table_wider_than_the_line_alone": 1,  # no control: one line
    "pages_section_start_then_a_table_wider_than_the_line": 1,  # the section's and columns' controls before
                                                                # it: one line
    # The same table beside one of the other controls: the same lines, whichever the control. Before the
    # table, on its line; after it, on an empty line under it -- but a number shown as a character before it
    # takes an empty line 1600 down of its own, the table's line under it.
    "pages_page_hiding_then_a_table_wider_than_the_line": 1,  # a hidden page number
    "pages_table_wider_than_the_line_then_a_page_hiding": 1,
    "pages_auto_number_then_a_table_wider_than_the_line": 1,  # a page's number shown as a character
    "pages_table_wider_than_the_line_then_an_auto_number": 1,
    "pages_new_number_then_a_table_wider_than_the_line": 1,  # a new page number
    "pages_table_wider_than_the_line_then_a_new_number": 1,
    "pages_page_number_control_then_a_table_wider_than_the_line": 1,  # page numbering on both sides
    "pages_table_wider_than_the_line_then_a_page_number_control": 1,
    "pages_header_then_a_table_wider_than_the_line": 1,  # a header
    "pages_table_wider_than_the_line_then_a_header": 1,
    "pages_footer_then_a_table_wider_than_the_line": 1,  # a footer
    "pages_table_wider_than_the_line_then_a_footer": 1,
    "pages_bookmark_then_a_table_wider_than_the_line": 1,  # a bookmark
    "pages_table_wider_than_the_line_then_a_bookmark": 1,
    "pages_click_here_field_then_a_table_wider_than_the_line": 1,  # an empty click-here field, its start and end
    "pages_table_wider_than_the_line_then_a_click_here_field": 1,
    "pages_index_mark_then_a_table_wider_than_the_line": 1,  # an index mark
    "pages_table_wider_than_the_line_then_an_index_mark": 1,
    "pages_bookmark_around_a_table_wider_than_the_line": 1,  # before and after it: the table's line, the empty
    "pages_click_here_field_around_a_table_wider_than_the_line": 1,  # line under it
    # Tabs: a tab reaches the next default tab stop, every 4000 from the column's left edge (the first line
    # starting at the left margin and a first-line indent, a hanging indent off the other lines), and a line may
    # start on either side of one. 90 paragraphs of 바탕 10 pt Hangul, a tab, then two-syllable words, after 0-9
    # syllables and at left margins 0, 1417 and 2835 with indents 0, 850 and -850:
    "pages_tab_stops_after_hangul_and_indents": 10,
    "pages_tab_stops_one_size": 1,  # labels, two tabs and text, at margins and indents
    "pages_tab_stops_mixed_sizes": 2,  # runs of 9 to 20 pt
    "pages_tab_stops_mixed_faces": 1,  # runs of six faces
    # A line break: the line after it is no first line, its room the other lines' (a first-line indent not
    # taken off it), in runs of several sizes
    "pages_line_breaks_mixed_sizes_indented": 2,
    "pages_tabs_breaks_sizes_faces": 1,  # tabs, line breaks, sizes and faces together
    # Paragraphs with tab stops of their own (left, right, centre, decimal, some past the line's end, with the
    # automatic tabs or not) after labels, numbers and words: a tab reaches the first stop past it whose text
    # can be aligned there without starting before the tab or passing the line's end (a left stop past it is
    # taken all the same), the automatic tab at the end being a right stop there; then the default stops,
    # which give the tab no width past a stop it could not take when the text has no room after them.
    "pages_tab_stops_own_centre_then_default": 1,
    "pages_tab_stops_own_left_past_the_line": 1,
    "pages_tab_stops_own_decimal_passed_over": 1,
    "pages_tab_stops_own_automatic_right": 1,
    "pages_tab_stops_own_right_no_room": 1,
    # ... past a stop it could not take, a left stop past the line's end (or whose text would pass it) ends the
    # text at the end; a tab at the line's end goes on to the next line
    "pages_tab_stops_own_left_past_a_passed_stop": 1,
    "pages_tab_stops_own_tab_at_the_margin": 1,
    # ... but the automatic tab at the end with no text after it stays on its line, a tab after it starting the
    # next: 220 paragraphs of 2-42 syllables, justified and left-aligned, ending in a tab, a space and a tab, two
    # tabs, or a tab and text
    "pages_tab_stops_automatic_right_at_the_end": 4,
    "pages_picture_as_character_300_short_then_three_spaces": 1,  # a picture 3000 tall: the same
    "pages_table_cell_table_as_character_300_short_then_three_spaces": 1,  # in a cell of a flowing table
    "pages_table_as_character_then_a_line_break": 1,  # a line break after it: an empty line below it
    "pages_table_as_character_after_a_line_break": 1,  # one before it: the table on the next line, the empty
                                                        # line above going down as one of text
    "pages_picture_as_character_after_a_line_break": 1,  # the same before a picture 3000 tall
    "pages_table_caption_above": 1,  # a caption of one line above a flowing table: the line and a gap of 850
    "pages_table_caption_below": 1,  # the same below it
    # Eight times, 0 to 3 empty paragraphs down a page: a table of 40 rows split between cell lines, with a caption of
    # one line below it 141 or 850 away: every page it goes on from keeps the caption's room at its foot
    "pages_table_split_between_cell_lines_keeping_its_caption_room": 16,
    "pages_table_caption_above_over_pages": 2,  # above a table going over the page end: on its first page
    "pages_table_as_character_caption_two_lines": 1,  # two lines above a table set as a character
    # A caption whose paragraph is spaced 900 before: its line starts 900 down, the room taken with it.
    "pages_table_caption_above_spaced_before": 1,  # above a flowing table
    "pages_table_as_character_caption_above_spaced_before": 1,  # above a table set as a character
    "pages_table_as_character_caption_below_spaced_before": 1,  # below it
    "pages_table_as_character_caption_of_two_paragraphs_spaced": 1,  # the second spaced 600 before (between
                                                                       # them) and 500 after (taking no room)
    "pages_table_as_character_between_spaces_of_two_sizes": 1,  # a space of 11 pt before it, 10 pt after:
                                                                  # the line spaced from 11 pt
    "pages_table_as_character_in_a_larger_run": 1,  # alone in a run of 20 pt, a space of 10 pt after it
    "pages_table_as_character_among_text_in_a_larger_run": 1,  # in a run of 20 pt among 10 pt text
    "pages_table_caption_below_ends_100_above_page_foot": 2,  # the last row and the caption below end 100
                                                                # above the foot: both go on
    "pages_table_caption_below_ends_101_above_page_foot": 2,  # 101 above it: they stay
    "pages_table_offset_down_from_a_line_past_the_foot": 2,  # a table top and bottom 1517 down from a line
                                                             # that does not fit: both on the next page
    "pages_table_offset_down_its_top_past_the_foot": 2,  # 2000 down, the line fitting: the table at the
                                                         # next page's top, the text after below it
    "pages_table_offset_down_its_first_row_past_the_foot": 2,  # moved row by row, its first row not fitting:
                                                               # the same, a line of the text after on the page


    "pages_table_cell_holding_a_drawing_top_and_bottom": 1,  # a cell paragraph holding only a rectangle 10000
                                                             # tall placed top and bottom from it: the row is
                                                             # as tall as it with the cell's margins
    "pages_table_as_character_cell_holding_a_drawing_top_and_bottom": 1,  # in a table set as a character
    "pages_table_cell_holding_a_drawing_500_down": 1,  # 500 down from the paragraph's top
    "pages_table_cell_holding_a_drawing_wrapped_square": 1,  # wrapped square, narrow: the line beside it
    "pages_table_cell_holding_a_picture_top_and_bottom": 1,  # a picture
    "pages_table_cell_holding_a_drawing_after_a_line": 1,  # in the cell's second paragraph, after a line


    "pages_table_joined_rows_end_at_the_foot": 2,  # the last two rows joined by a merged cell reach 300 past the
                                                   # foot within the last one's room to spare: they end there,
                                                   # the paragraph after the table at the next page's top
    "pages_table_joined_rows_end_at_the_foot_before_a_page_break": 2,  # the paragraph after it starts a page
    "pages_table_joined_rows_rest_over_1282_goes_on": 2,  # 1500 past it: the rest goes on
    "pages_table_joined_rows_line_goes_on": 2,  # two lines, taller than declared: the second line goes on


    "pages_table_caption_below_a_spare_last_row_cut": 2,  # the last row declared taller than its line, the
                                                          # caption 1000 past the foot: the row's room to spare
                                                          # is cut above the caption, the rest dropped
    "pages_table_caption_below_a_spare_last_row_cut_near_the_foot": 2,  # 669 past it, 2000 to spare
    "pages_table_caption_below_a_spare_last_row_too_little_spare": 2,  # 2269 past it, 2000 to spare: the row
                                                                       # goes on with the caption
    "pages_table_caption_below_a_spare_last_row_split": 2,  # 3000 past it: the rest (more than 1282) goes on
                                                            # with the caption
    "pages_table_caption_below_a_spare_last_row_moved_row_by_row": 2,  # moved row by row (TABLE): no cut
    "pages_table_alone_offset_500": 1,  # a flowing table alone in its paragraph, 500 down: it starts there
    "pages_table_alone_spacing_before_10pt": 1,  # its paragraph 10 pt apart: the table above that spacing,
                                                   # the next paragraph (10 pt apart too) under the table
    "pages_table_alone_spacing_before_20pt": 1,  # 20 pt apart, 500 down: the next paragraph 20 pt under the
                                                   # anchor line, lower than the table's end
    # An empty paragraph (the fourth line, 10 pt spaced 160%) holding only a table or a picture 6000 tall placed
    # top and bottom d down from it, thirty lines after it: the empty line stays where it is (an empty piece
    # where the band starts above its foot), and the lines after go below the band only from the first one
    # reaching it (its spacing not counted):
    "pages_empty_paragraph_table_down_0": 1,
    "pages_empty_paragraph_table_down_500": 1,
    "pages_empty_paragraph_table_down_1000": 1,  # the band starts at the empty line's foot
    "pages_empty_paragraph_table_down_1600": 1,
    "pages_empty_paragraph_table_down_3000": 1,  # the next line above the band, the second below it
    "pages_empty_paragraph_table_down_10000": 1,  # five lines above it
    "pages_empty_paragraph_table_down_18196": 1,  # ten
    "pages_empty_paragraph_table_down_18196_long": 2,  # sixty lines: on over the page end
    "pages_empty_paragraph_picture_down_0": 1,
    "pages_empty_paragraph_picture_down_500": 1,
    "pages_empty_paragraph_picture_down_1000": 1,
    "pages_empty_paragraph_picture_down_1600": 1,
    "pages_empty_paragraph_picture_down_3000": 1,
    "pages_empty_paragraph_picture_down_10000": 1,
    "pages_empty_paragraph_picture_down_18196": 1,
    # ... a paragraph of one space instead is text: its own line goes below the band when it reaches it
    "pages_space_paragraph_table_down_0": 1,
    "pages_space_paragraph_table_down_500": 1,
    "pages_space_paragraph_table_down_3000": 1,
    "pages_space_paragraph_picture_down_3000": 1,
    "pages_table_alone_offset_2000_over_pages": 2,  # 2000 down, over the page end
    "pages_table_alone_after_offset_table": 2,  # after a table flowing 2300 down: its line goes below that
    "pages_table_alone_offset_500_after_offset_table": 2,  # and the table flows 500 below the line
    "pages_table_alone_placed_up_after_offset_table_over_pages": 2,  # the first over the page end, the
                                                                       # second 122 up: at the line
    "pages_table_page_break_after_table": 2,  # a page break on the paragraph of a flowing table after another
    "pages_table_page_break_after_text": 2,  # the same, rows moved whole (TABLE), after text
    "pages_table_page_break_after_long_table": 3,  # after a table ending on the next page: the page after
    "pages_table_multiline_cells": 3,     # a table set as a character
    "pages_picture_floating_tall": 4,     # top-and-bottom pictures
    "pages_cell_column_settings": 3,      # one-column settings in a table cell's paragraph
    "pages_mixed_sizes_percent": 3,       # 10 pt and 20 pt runs in a paragraph, line spacing 160%
    "pages_mixed_sizes_fixed": 3,         # 12 pt and 30 pt runs, fixed line spacing (lines overlap)
    "pages_mixed_sizes_at_least": 2,      # 8 pt and 16 pt runs, line spacing at least 18 pt
    "pages_picture_before_text_percent": 2,  # a picture set as a character before the text, 160%
    "pages_picture_before_text_fixed": 2,    # a picture taller than the fixed line spacing
    # Paragraphs each of a table set as a character (10000 wide, 3000 or 10000 tall) and nothing else, the
    # table affecting the line spacing (on) or not (off): in percent, an affecting table's line is spaced from
    # its own height (160%: 1800 below one 3000 tall), any other from the characters (600); a fixed spacing
    # keeps the next line 2400 down below either (the tables overlap), an at-least one (1200) at the table's
    # height.
    "pages_table_affecting_line_spacing_percent160_3000_on": 2,
    "pages_table_affecting_line_spacing_percent160_3000_off": 1,
    "pages_table_affecting_line_spacing_percent160_10000_on": 2,
    "pages_table_affecting_line_spacing_percent160_10000_off": 1,
    "pages_table_affecting_line_spacing_percent130_3000_on": 2,
    "pages_table_affecting_line_spacing_percent130_3000_off": 1,
    "pages_table_affecting_line_spacing_percent130_10000_on": 2,
    "pages_table_affecting_line_spacing_percent130_10000_off": 1,
    "pages_table_affecting_line_spacing_fixed2400_3000_on": 1,
    "pages_table_affecting_line_spacing_fixed2400_3000_off": 1,
    "pages_table_affecting_line_spacing_fixed2400_10000_on": 1,
    "pages_table_affecting_line_spacing_fixed2400_10000_off": 1,
    "pages_table_affecting_line_spacing_at_least1200_3000_on": 1,
    "pages_table_affecting_line_spacing_at_least1200_3000_off": 1,
    "pages_table_affecting_line_spacing_at_least1200_10000_on": 1,
    "pages_table_affecting_line_spacing_at_least1200_10000_off": 1,
    "pages_table_merged_rows_tall": 1,    # a table set as a character, a merged cell taller than its rows
    "pages_table_merged_rows_short": 1,   # the same, the merged cell shorter than its rows
    "pages_table_flow_merged_rows": 2,    # a table flowing with the text, cells merged over rows
    "pages_table_flow_tall_row_carried": 2,  # a row declared taller than its text, cut at the page end
    "pages_table_flow_tall_row_dropped": 2,  # the same, the rest too short to go on
    # Tables of two columns with cell spacing 0, 200 or 850 between and around their cells: one of 20 rows
    # (1282 tall) flowing with the text from 10 rows above the page end, split between rows (cell) or moved
    # row by row (table) alike -- the rows that fit with a spacing above each and one below the last, the
    # rest on the next page the same way -- and one of a row set as a character on the last line that fits
    # it without the spacing, as tall as its rows and the spacings above and below them.
    "pages_table_cell_spacing_0_cell": 2,
    "pages_table_cell_spacing_0_table": 2,
    "pages_table_cell_spacing_0_inline": 2,
    "pages_table_cell_spacing_200_cell": 2,
    "pages_table_cell_spacing_200_table": 2,
    "pages_table_cell_spacing_200_inline": 2,
    "pages_table_cell_spacing_850_cell": 2,
    "pages_table_cell_spacing_850_table": 2,
    "pages_table_cell_spacing_850_inline": 2,
    "pages_table_flow_tall_row_rest_1282": 2,  # a rest of 1282 is dropped
    "pages_table_flow_tall_row_rest_1283": 2,  # a rest of 1283 goes on
    "pages_table_flow_tall_row_cell_margins_0": 2,    # the cells' own margins 0: 1283 goes on
    "pages_table_flow_tall_row_cell_margins_500": 2,  # the cells' own margins 500: 1290 goes on
    "pages_table_flow_tall_row_table_margins_500": 2,  # the table's inner margins 500: 1290 goes on
    "pages_table_flow_tall_row_bottom_aligned": 2,    # cells aligned to the bottom: 1290 goes on
    "pages_table_flow_tall_row_16pt": 2,              # 16 pt text: 1283 goes on
    "pages_table_declared_row_cut_line_left_rest_1082": 2,  # its third line does not fit: it goes on
    "pages_table_declared_row_cut_line_left_rest_582": 2,   # with the cell's margins, rest or no rest
    "pages_table_flow_row_ends_100_above_foot": 2,    # a row of two lines ending 100 above the foot: split
    "pages_table_flow_row_ends_101_above_foot": 2,    # the same ending 101 above it stays
    "pages_table_flow_moved_row_ends_100_above_foot": 2,  # moved row by row: 100 above the foot goes on
    "pages_table_flow_moved_row_ends_101_above_foot": 2,  # and 101 above it stays
    "pages_table_outer_margin_top_1000_row_moved": 2,  # top outer margin 1000: the moved row goes on 1000 down
    "pages_table_outer_margin_bottom_283_row_ends_383_above_page_foot": 2,  # bottom margin 283: 383 above goes on
    "pages_table_outer_margin_bottom_283_row_ends_384_above_page_foot": 2,  # and 384 above it stays
    "pages_table_outer_margins_283_declared_row_cut": 2,  # margins 283: cut 283 + 101 above, going on 283 down
    "pages_table_outer_margin_bottom_1000_row_split_between_lines": 3,  # a cell line in the bottom margin goes on
    "pages_table_not_adjusted_row_ends_1_above_page_foot": 2,  # a table not adjusted (noAdjust): 1 above goes on
    "pages_table_not_adjusted_row_ends_2_above_page_foot": 2,  # and 2 above it stays
    "pages_table_not_adjusted_moved_row_ends_2_above_page_foot": 2,  # the same moved row by row (TABLE)
    "pages_table_not_adjusted_declared_row_cut": 2,  # a declared row cut 2 above the foot
    "pages_table_not_adjusted_row_split_2_above_page_foot": 2,  # a cell line whose cut row ends 2 above stays
    "pages_table_flow_anchor_on_next_page": 2,  # the table's anchor line has no room: both go on
    "pages_table_merged_rows_held": 1,    # a cell merged over rows 0-3 holding one over rows 1-2
    "pages_table_merged_rows_staggered": 1,  # merged over rows 0-1 and 1-2: row 1 has no cell of its own
    "pages_table_merged_rows_ending_first": 1,  # merged over rows 0-2 and 2-3: the one ending first first
    "pages_table_flow_merged_rows_moved_whole": 2,  # moved row by row: rows 1-2 merged go on as one
    "pages_table_flow_merged_three_rows_moved_whole": 2,  # the same with rows 1-3
    "pages_table_flow_merged_rows_split_by_cell": 2,  # split between cell lines: the merged cell's rest goes on
    "pages_table_flow_merged_three_rows_split_by_cell": 2,  # the rest over two rows, what they lack in the last
    "pages_table_flow_merged_rows_declared_row_cut": 2,  # a row under merged rows declared 14000: its rest goes on
    "pages_table_flow_merged_rows_declared_row_dropped": 2,  # the same declared 6000: a rest of 503 is dropped
    "pages_table_flow_merged_cell_declared_cut": 2,  # the merged cell declared 6000: its rest goes on
    "pages_table_flow_merged_cell_declared_rest_1282": 2,  # the merged cell's rest of 1282 is dropped
    "pages_table_flow_merged_cell_declared_rest_1283": 2,  # and one of 1283 goes on
    "pages_table_flow_merged_cell_declared_lines_cut": 2,  # the page end among its 6 lines: cut the same
    "pages_table_anchored_merged_rows_split_by_cell": 2,  # a table anchored in text: merged rows split the same
    "pages_table_nested_after_text": 1,  # a table in a cell of a flowing table, after a line of text
    "pages_table_nested_alone": 1,       # a table alone in a cell of a flowing table
    "pages_table_nested_in_table_as_character": 1,  # a table in a cell of a table set as a character
    "pages_table_nested_row_split": 2,  # a row holding a table splits after its first line of text
    "pages_table_nested_row_moved": 2,  # none of a row holding a table fits: it goes on whole
    # A table of ten rows nested in the second row of a flowing table, its third row at the page's foot:
    "pages_nested_table_split_cell": 2,  # set as a character: it never splits, going on whole with the
                                         # outer row's lines after it
    "pages_nested_table_split_inner_table_break": 2,  # the same, set to move row by row
    "pages_nested_table_split_inner_no_break": 2,  # the same, set not to split
    "pages_nested_table_split_three_line_rows": 2,  # the same, three lines a row
    "pages_nested_table_split_header_repeated": 2,  # the same, its first row a repeated header
    "pages_nested_table_split_outer_table_break": 2,  # the outer table moving row by row: the row goes on
                                                      # whole
    "pages_nested_table_split_fitting": 1,  # one that fits on the page
    "pages_nested_table_split_top_and_bottom": 2,  # placed top and bottom: it splits between its rows
    "pages_nested_table_split_top_and_bottom_table_break": 2,  # set to move row by row: the same
    "pages_nested_table_split_top_and_bottom_three_line_rows": 2,  # three lines a row: between a row's
                                                                   # lines too, the cell margins around
                                                                   # each part
    "pages_nested_table_split_top_and_bottom_header_repeated": 2,  # its header row again above the rest
    # A flowing table whose first column holds vertical text (10 pt, spaced 160%): Hancom lays its lines down
    # the cell's height, side by side across it, and cuts what does not fit; the row stays as declared:
    "pages_table_vertical_cell_short_text": 1,  # three characters in a cell 3000 x 4000: one line
    "pages_table_vertical_cell_text_past_its_height": 1,  # thirty: ten lines, the row still 4000 tall
    "pages_table_vertical_cell_text_past_its_width": 1,  # sixty in a cell 1500 wide: twenty lines
    "pages_table_vertical_cell_merged_over_rows": 1,  # ten in a cell merged over four rows 2000 tall
    "pages_table_merged_cells_over_the_page_end": 2,  # twenty rows, cells of four merged, horizontal text:
                                                     # the table splits at the page end
    # Twenty rows of one line (10000 and 30000 wide), the first column's cells of rows 9 to 12 merged, the page
    # ending in row 10:
    "pages_table_rows_merged_at_the_page_end": 2,  # the part on the page reaches down to its foot, the
                                                   # merged cell's lines split there; row 10 goes on whole
    "pages_table_rows_merged_at_the_page_end_taller_text": 2,  # eight lines in the merged cell: its last
                                                               # row grows
    "pages_table_rows_merged_at_the_page_end_moved_row_by_row": 2,  # the merged rows go on together
    "pages_table_rows_merged_at_the_page_end_staggered": 2,  # rows 7 to 10 merged in the first column,
                                                             # 10 to 13 in the second
    "pages_table_rows_merged_taller_than_a_page": 2,  # rows 2 to 40 merged in a table of forty
    "pages_table_rows_merged_after_the_page_end": 2,  # the page ending before the merged rows
    "pages_table_nested_top_and_bottom_alone_then_a_line": 1,  # a table placed top and bottom alone in
                                                              # a cell paragraph, then a line: right
                                                              # below the table
    "pages_table_nested_top_and_bottom_1000_down_alone": 1,  # the table 1000 down: the empty line stays
                                                            # above it, its foot at the table's top
    "pages_table_nested_top_and_bottom_1000_down_before_text": 1,  # 1000 down before three lines: the first
                                                                  # stays above it, the others below it
    "pages_table_nested_top_and_bottom_placed_up_before_text": 1,  # 1000 up before them: at the paragraph's
                                                                  # top, every line below it
    "pages_table_nested_row_declared_cut": 2,  # the same row declared 16000: cut above the foot, the rest goes on
    "pages_table_nested_row_declared_cut_near_foot": 2,  # declared 24000, cut 3579 below its top
    "pages_table_nested_row_declared_first_line_100_above_page_foot": 2,  # its first line ends 100 above
                                                                          # the page's foot: it goes on whole
    "pages_table_nested_row_declared_first_line_101_above_page_foot": 2,  # 101 above it: cut there
    # A cell of a flowing table (10 pt text spaced 160%) holding tables set as characters, of two columns and
    # rows 1282 tall:
    "pages_table_cell_two_tables_as_characters": 1,  # of two rows and three, 15000 wide: side by side on one
                                                     # line as tall as the taller
    "pages_table_cell_two_tables_as_characters_on_two_lines": 1,  # 25000 wide each: the second on the next
    "pages_table_cell_table_as_character_then_text": 1,  # two rows, then text: the table and the text's
                                                         # start on one line, three lines of text below
    "pages_table_cell_text_then_a_table_as_character": 1,  # two lines of text, then three rows on the next
    "pages_table_cell_tables_as_characters_among_text_split": 2,  # seven paragraphs, each a table of four
                                                                  # rows among text: the row splits
                                                                  # between them
    "pages_table_cell_holding_a_header_with_a_table": 1,  # a header control in a cell paragraph, a table
                                                          # in the header: drawn there, not in the cell
    "pages_objects_among_text_table": 2,  # a full-width table set as a character among text
    "pages_objects_among_text_equation": 1,  # equations set as characters among text
    "pages_objects_after_text_rectangle": 1,  # rectangles set as characters after text
    "pages_text_box_grown_by_its_text": 1,  # a rectangle 3000 tall set as a character holding five lines of
                                             # text: Hancom draws it as tall as its current size (curSz), 7966
    "pages_text_box_grown_by_its_text_among_text": 1,  # the same between two words
    "pages_text_box_grown_by_its_text_in_a_cell": 1,  # in a cell, a line after it: the row grows with it
    "pages_text_box_grown_by_its_text_top_and_bottom": 1,  # placed top and bottom alone in a paragraph
    "pages_text_box_grown_by_its_text_upside_down": 1,  # scaled upside down: its current size written -7966
    "pages_text_box_fitting_its_text": 1,  # holding one line: as tall as its size, its current size being 0
    "pages_text_box_grown_by_three_lines": 1,  # 4766: three lines of 10 pt and the margins of 283
    "pages_text_box_grown_by_two_lines_current_size_one_less": 1,  # two: 3166, its current size written 3165
    "pages_table_anchored_after_text": 1,  # a top-and-bottom table anchored after three lines of text
    "pages_picture_anchored_before_text": 1,  # a top-and-bottom picture anchored before the text
    "pages_table_anchored_offset_before_text": 1,  # 3000 down from the first line: the third line goes below
    "pages_table_anchored_offset_after_text": 1,   # 3000 down from the last line: the next paragraph's second
    "pages_picture_anchored_offset_next_paragraph": 1,  # 1600 down: the next paragraph's first line
    "pages_picture_anchored_small_offset": 1,  # 500 down: the line it stands on goes below it
    # Paragraphs at 10000 holding objects placed top and bottom (offset 0 unless said) and objects set as
    # characters: the placed ones stack from the paragraph's top and the line of the others goes below them;
    # one placed below the text's lines leaves them, and pushes the lines after that reach it below its foot.
    "pages_tb_and_char_table_then_picture": 1,  # a table 6000 tall from its top, a picture: the line under the table
    "pages_tb_and_char_picture_then_table": 1,  # the picture first in the runs: the same
    "pages_tb_and_char_table_then_two_pictures": 1,  # two pictures side by side on that line
    "pages_tb_and_char_two_tables_then_picture": 1,  # two tables, one below the other, the line under both
    "pages_tb_and_char_small_table_then_table": 1,  # a small table set as a character on the line
    "pages_tb_and_char_small_table_then_table_up": 1,  # 44 up from the top: Hancom takes a table at the top
    # An empty paragraph at 20000 after lines of text holding a table (three rows, 4000 tall) placed top and
    # bottom 0, 500, 1000, 1500 or 3000 up from its top (kept unsigned), and one 8000 tall 1500 up: Hancom lays
    # each out and draws it at the top, the empty line there with no width and the next paragraph at its foot.
    "pages_empty_paragraph_table_offset_0": 1,
    "pages_empty_paragraph_table_offset_500": 1,
    "pages_empty_paragraph_table_offset_1000": 1,
    "pages_empty_paragraph_table_offset_1500": 1,
    "pages_empty_paragraph_table_offset_3000": 1,
    "pages_empty_paragraph_table_offset_1500_h8000": 1,
    "pages_tb_and_char_text_picture_small_table": 1,  # text, a picture 4640 down, a small table in the text
    "pages_tb_and_char_text_picture_tall_table": 2,  # the table 56000 tall: its line on the next page
    # A 9 pt paragraph P with a table placed top and bottom 616 down (seven rows), three 9 pt paragraphs and a
    # 15 pt paragraph Q with a table 2124 down: the paragraphs after P start at its table's foot, and P's own
    # line stays at its top when P is empty, goes below the table when P holds text, spaces included.
    "pages_band_then_empty_paragraphs": 1,  # P empty: its line stays at its top, the paragraphs after
    "pages_band_then_text_paragraphs": 1,  # the same, the three of text
    "pages_band_then_empty_paragraphs_then_band": 1,  # then Q, empty, and its table 2124 down
    "pages_band_then_text_paragraphs_then_band": 1,  # the three of text
    "pages_band_at_zero_then_empty_paragraphs_then_band": 1,  # P's table at its top
    "pages_band_empty_again_then_empty_paragraphs_then_band": 1,  # P empty again, saved anew
    "pages_band_text_then_empty_paragraphs_then_band": 1,  # P of text: its line goes below its table
    "pages_band_spaces_then_empty_paragraphs_then_band": 1,  # P of two spaces: the same, spaces are text
    "pages_band_space_then_empty_paragraphs_then_band": 1,  # P of one space: the same
    "pages_band_text_split_then_empty_paragraphs_then_band": 2,  # P of text, its table over the page end: its
                                                                 # line at the foot of the table's part on the next page
    "pages_table_offset_flowing_split_by_cell": 2,  # a flowing table 500 down over the page end:
                                                    # the line it stands on goes below its end
    "pages_table_offset_flowing_row_by_row": 2,  # the same moved row by row
    "pages_table_offset_flowing_second_line": 2,  # 2000 down: the second line goes below its end
    "pages_table_offset_flowing_next_paragraph": 2,  # the next paragraph's first line does
    # Two paragraphs each of a line of text and a flowing table 2000 down from it: the second paragraph starts
    # at the foot of the first table (of its last part), its own table 2000 below its top, and the text after
    # at that table's foot.
    "pages_table_past_the_end_then_text_and_a_short_table": 2,  # the first table over the page end: the second
    "pages_table_past_the_end_then_text_and_a_long_cell": 3,  # the second table's one row over the page end too
    "pages_table_ending_then_text_and_a_short_table": 1,  # the first table ending on its page
    "pages_picture_square_left": 2,       # a picture wrapped square on the left, text beside it into the next paragraph
    "pages_picture_square_right": 2,      # a wide picture wrapped square on the right
    "pages_picture_square_alone": 2,      # a picture wrapped square alone in its paragraph
    "pages_picture_square_wider_than_column": 2,  # no room beside it: the text goes below
    "pages_picture_square_520_room_on_its_right": 1,  # 42000 wide at the column's left: 520 is no room, the
                                                      # text goes below it
    "pages_table_square_520_room_on_its_right": 1,  # a table the same, as tall as its rows
    "pages_table_square_alone_520_room_on_its_right": 1,  # alone: its empty line at its top, the next
                                                          # paragraph below it
    "pages_table_square_right_520_room_on_its_left": 1,  # at the column's right
    "pages_table_square_1000_and_920_room_beside_it": 1,  # 1000 from the left: no room on either side
    "pages_table_square_larger_side_only_520_room": 1,  # the text going to the larger side only
    "pages_table_square_520_room_on_its_right_3000_down": 1,  # 3000 below the paragraph's top: the lines
                                                              # reaching it go below it
    "pages_picture_square_520_room_on_its_right_3000_down": 2,  # a picture the same
    "pages_table_square_520_room_over_the_page_end": 3,  # 40 rows after 10 paragraphs: split between cell
                                                         # lines over the page ends like a top-and-bottom table
    "pages_table_square_520_room_over_the_page_end_row_by_row": 3,  # moved row by row
    "pages_table_square_520_room_over_the_page_end_with_text": 3,  # text after it: below its end
    "pages_picture_square_offset": 2,     # a picture wrapped square 3000 below the paragraph's top
    "pages_table_square_alone": 1,        # a table wrapped square alone, as tall as its rows
    "pages_table_above_a_table_as_character": 1,  # a 3-row table top and bottom from its paragraph's top and a
                                                  # table set as a character: the character's line below it
    "pages_table_above_a_table_as_character_and_text": 1,  # the same with text after the character
    "pages_table_above_a_table_as_character_over_a_page": 2,  # a 12-row one at the page end: it flows over
                                                             # it, the character's line below its end
    "pages_bullet_and_number_labels": 16,  # fourteen blocks of rows under bullets and numbers of every
                                             # label setting: each label takes its room off the lines
    # Outline paragraphs (the template's levels 1 to 7, labels without a character shape of their own) of two
    # to four runs, the first and the last of different sizes, some ending in an empty run: Hancom measures the
    # label in the paragraph end's shape, and that size counts in the first line's height.
    "pages_outline_labels_paragraph_end_shape": 2,
    "pages_outline_labels_paragraph_end_shape_sizes": 2,
    "pages_outline_labels_paragraph_end_shape_empty_run": 2,
    "pages_bullet_in_its_own_20pt_shape": 1,  # three-line paragraphs of 10 pt text under a bullet in its own
                                              # 20 pt shape, at 160 %: the first line as tall as the bullet
    "pages_bullet_in_its_own_8pt_shape": 1,   # an 8 pt one: no line taller
    "pages_number_in_its_own_16pt_shape": 1,  # a number in its own 16 pt shape
    "pages_bullet_in_its_own_20pt_shape_fixed_spacing": 1,  # a fixed line spacing of 16 pt: the next line
                                                            # 16 pt down all the same
    "pages_bullet_in_its_own_20pt_shape_between_lines": 1,  # 5 pt between lines: below the 20 pt line
    "pages_bullet_in_its_own_20pt_shape_at_least": 1,  # at least 16 pt: the 20 pt line's own height
    "pages_picture_square_text_on_both_sides": 2,  # a picture 9100 from the column's left: each line
                                                    # beside it is two pieces at one height
    "pages_picture_square_text_on_the_larger_side": 2,  # the same, text on the larger side only
    "pages_picture_square_text_on_the_left_only": 2,    # text on the left only
    "pages_picture_square_from_the_paper_narrow_left": 2,  # 235 right of the column's edge, from the
                                                            # paper's left: the left side takes no text
    "pages_picture_square_left_side_1439_empty": 2,   # a side 1439 wide takes no text
    "pages_picture_square_left_side_1440_takes_text": 2,  # one 1440 wide does
    "pages_drop_cap_3200_two_lines_beside": 1,    # a drop cap 3200 tall, 10 pt text at 160%: two lines
                                                  # beside it (a line's top 3200 down is not above its foot)
    "pages_drop_cap_3201_three_lines_beside": 1,  # 3201 tall: three
    "pages_drop_cap_spacing_250_5000_two_lines_beside": 1,    # at 250%, 5000 tall: two
    "pages_drop_cap_spacing_250_5001_three_lines_beside": 1,  # 5001 tall: three
    "pages_cell_paragraph_with_margins": 1,  # a cell paragraph with margins of 5 mm: narrower lines
    "pages_cell_paragraph_with_hanging_indent": 1,  # a hanging indent of 3 mm: narrower second lines
    # Thirty characters (10 pt, six to a line) in a cell 6000 wide inside its margins, the paragraph indented:
    # an indent that leaves its line less than 1440 is dropped, every line the cell's width; from 1440 on it is
    # kept, a line too narrow for a character holding one anyway.
    "pages_cell_no_indent": 1,  # six on each of five lines
    "pages_cell_hanging_indent_8000": 1,  # 2000 short of nothing left: dropped, the lines as without it
    "pages_cell_hanging_indent_6000": 1,  # nothing left: dropped
    "pages_cell_hanging_indent_5000": 1,  # 1000 left: dropped
    "pages_cell_hanging_indent_4600": 1,  # 1400 left: dropped
    "pages_cell_hanging_indent_4580": 1,  # 1420 left: dropped
    "pages_cell_hanging_indent_4560": 1,  # 1440 left: kept, a character a line after the first
    "pages_cell_hanging_indent_4540": 1,  # 1460 left: kept
    "pages_cell_hanging_indent_4520": 1,  # 1480 left: kept
    "pages_cell_hanging_indent_4500": 1,  # 1500 left: kept
    "pages_cell_hanging_indent_4000": 1,  # 2000 left: two a line
    "pages_cell_hanging_indent_3000": 1,  # 3000 left: three a line
    "pages_cell_first_line_indent_5000": 1,  # a first-line indent leaving 1000: dropped
    "pages_cell_first_line_indent_4500": 1,  # leaving 1500: one character on the first line
    "pages_cell_first_line_indent_4000": 1,  # leaving 2000: two on the first line
    "pages_cell_20pt_hanging_indent_10580": 1,  # 20 pt in a cell 12000 wide, 1420 left: dropped
    "pages_cell_20pt_hanging_indent_10560": 3,  # 1440 left, narrower than a character: one a line
    "pages_cell_20pt_hanging_indent_10000": 3,  # 2000 left: one a line
    "pages_cell_20pt_hanging_indent_9100": 3,  # 2900 left
    "pages_cell_20pt_hanging_indent_9000": 3,  # 3000 left
    "pages_cell_20pt_hanging_indent_8900": 3,  # 3100 left
    "pages_body_hanging_indent_42000": 1,  # in the body, 520 left of the column: dropped
    "pages_body_hanging_indent_41000": 4,  # 1520 left: kept, a character a line
    "pages_cell_runs_of_two_sizes": 1,   # runs of 10 and 14 pt in a cell: each character at its size
    "pages_cell_runs_of_two_sizes_with_margins": 1,  # the same with margins of 5 mm
    "pages_table_not_split_fits": 1,     # a table set not to split: the text goes below it
    "pages_table_not_split_moves_to_next_page": 2,  # it does not fit: it moves to the next page's top,
                                                     # the text after it goes on under its anchor line
    "pages_table_not_split_with_outer_margins_moves": 2,  # the same with outer margins 140 and 852
    "pages_table_not_split_before_text_moves_with_it": 2,  # at the top of a paragraph of text: the
                                                            # paragraph goes on with it
    "pages_picture_in_front_of_text": 1,  # a picture in front of three lines of text: no line moves
    "pages_rectangle_behind_text_alone": 1,  # a rectangle behind the text alone: an empty line
    "pages_table_as_character_beside_rectangle_in_front": 1,  # beside a rectangle in front, on the paper
    "pages_picture_behind_text_past_page_foot": 2,  # a picture behind the text past the page foot
    "pages_rectangle_on_paper_pushes_its_line": 1,  # top and bottom 15000 below the paper's top: the
                                                     # second line of its paragraph goes below it
    "pages_rectangle_on_paper_at_page_top": 2,  # 4000 below it, anchored mid-page: the page's first
                                                 # lines, in paragraphs before its own, go below it
    "pages_table_on_paper_pushes_a_later_line": 1,  # a table 40000 below it: a line of a later paragraph
    "pages_rectangle_on_paper_across_two_columns": 2,  # across both columns, anchored in the second:
                                                        # the lines of both columns go below it
    "pages_rectangle_on_paper_over_the_left_column": 2,  # 15000 wide over the first of two columns: its
                                                          # lines go below it, the second's start at the top
    "pages_rectangle_on_paper_over_the_right_column": 2,  # over the second only
    "pages_rectangle_on_paper_partly_over_two_columns": 2,  # 30000 wide, centred: partly over each, the
                                                             # lines of both go below it
    "pages_rectangle_on_paper_400_narrower_than_two_columns": 2,  # 400 narrower than the text, centred
    "pages_table_on_paper_400_narrower_than_two_columns": 2,  # a table so
    "pages_rectangle_on_paper_over_the_left_column_from_the_right": 2,  # anchored in the second column
    "pages_rectangle_on_paper_over_the_middle_of_three_columns": 2,  # the middle one of three only
    "pages_rectangle_on_paper_100_into_the_second_column": 2,  # its right edge 100 into the second: both
    "pages_rectangle_on_paper_ending_in_the_column_gap": 2,  # its right edge 100 short of the second, in
                                                              # the gap: the first only
    "pages_rectangle_on_page_5000_below_its_top": 2,   # top and bottom 5000 below the body's top
    "pages_rectangle_on_page_5000_above_its_foot": 2,  # 5000 above the body's foot: the lines reaching it
                                                        # go below it
    # An empty paragraph among lines of text holding a picture (15000 x 14000) placed top and bottom and centred
    # up and down on the page (its body) or on the paper, moved by its offset:
    "pages_centred_on_the_page": 2,  # centred on the body: the line reaching it goes below it
    "pages_centred_on_the_page_up_4090": 2,  # 4090 up from there (the offset kept unsigned)
    "pages_centred_on_the_page_down_3000": 2,  # 3000 down
    "pages_centred_on_the_page_wide_bottom": 2,  # a bottom margin of 30 mm: centred on the shorter body
    "pages_centred_table_on_the_page": 2,  # a table of seven rows the same
    "pages_centred_on_the_paper": 2,  # centred on the paper
    "pages_centred_on_the_paper_up_4090": 2,  # 4090 up
    "pages_centred_on_the_paper_wide_bottom": 2,  # a bottom margin of 30 mm: where it was
    "pages_centred_on_the_paper_up_4090_wide_bottom": 2,  # the same 4090 up
    "pages_rectangle_on_page_at_its_foot": 2,          # at the body's foot: the lines reaching it go on to
                                                        # the next page
    "pages_rectangle_on_paper_5000_above_its_bottom": 2,  # 5000 above the paper's bottom, into the body
    "pages_table_on_page_at_its_foot": 2,              # a table at the body's foot
    "pages_exam_header_over_a_question_with_text": 1,  # a header table from the paper's top over the body's
                                                       # top, wrapped square across the text, and a 5-row table
                                                       # top and bottom from the first paragraph's top: the
                                                       # table right below the header, the text below it
    "pages_exam_header_pushing_earlier_lines": 1,  # the same header anchored in the third paragraph: the lines
                                                   # of the first two go below it
    "pages_exam_header_over_a_table_alone": 1,  # the 5-row table alone in the first paragraph: below the
                                                # header, the paragraph's empty line below the table
    "pages_exam_header_top_and_bottom_over_a_table_alone": 1,  # a header set top and bottom
    "pages_exam_header_over_a_table_alone_two_columns": 1,  # in two columns
    "pages_exam_header_then_a_table_alone": 1,  # the table alone in the next paragraph: its line at its top
    "pages_table_alone_in_the_first_paragraph": 1,  # no header: the empty line at the table's top
    "pages_square_picture_on_paper_below_the_lines": 1,  # a picture wrapped square from the paper's top at the
                                                         # text's left, a line's room on its right, 400 below
                                                         # the fifth line: no line moves
    "pages_square_picture_on_paper_touching_the_last_line": 1,  # its top at the fifth line's foot
    "pages_square_picture_on_paper_in_the_last_paragraph": 1,  # anchored in the fifth paragraph
    "pages_square_picture_on_paper_at_the_right": 1,  # at the text's right, room on its left
    "pages_square_picture_on_paper_then_a_page_break": 4,  # the next pages' lines across its height
    "pages_composed_characters": 1,     # circled numbers among three lines of text
    "pages_compose_spread_rows": 1,     # rows of composed 가나 spread, paragraphs 0 to 7 mm narrower:
                                         # each as wide as a Hangul syllable
    "pages_compose_overlap_digits_rows": 1,  # 12 overlapping: as wide as a digit
    "pages_compose_overlap_latin_rows": 1,   # AB overlapping: as wide as the A
    "pages_compose_framed_rows": 2,     # 1 overlapping in a circle: as wide as a Hangul syllable
    "pages_compose_in_a_cell": 1,       # forty composed characters on two lines of a cell
    "pages_ruby_text": 1,               # ruby text above a word
    "pages_ruby_above_15pt": 1,         # ruby text above 15 pt text: its line 2248 tall
    "pages_ruby_above_10_5pt_ratio_30": 1,  # above 10.5 pt text, the ruby 30%: 1360
    "pages_ruby_below_9pt": 1,          # below 9 pt text: 1264
    "pages_ruby_below_13pt": 1,         # below 13 pt text: 1828
    "pages_ruby_above_beside_larger_text": 1,  # above 10 pt text beside 14 pt text: the ruby's line
    "pages_ruby_below_beside_larger_text": 1,  # below it, beside 14 pt text
    "pages_ruby_longer_than_its_text": 2,  # six syllables of ruby over one: as wide as the one
    "pages_ruby_below_in_a_cell": 1,    # ruby text below text in a cell
    # Paragraphs without text of two or three runs at 10, 14 and 20 pt, each an empty text or a bookmark: the
    # line is as tall as the largest of the runs holding a control and the last run (an empty text run before
    # it counts for nothing), each paragraph followed by one of 10 pt
    "pages_empty_paragraphs_of_runs_of_two_sizes": 1,
    "pages_empty_paragraphs_of_larger_runs_first": 1,
    # A picture set as a character, 500 to 3000 tall, in a run of 8 to 20 pt between 10 or 15 pt text, line
    # spacing 150 %: the line is as tall as its text and the picture, its spacing reckoned from the largest of
    # the text's and the picture run's sizes
    "pages_inline_picture_in_a_run_of_another_size": 3,
    # A table-of-contents mark (hp:titleMark) alone in a run of 8, 12 or 22 pt before, inside, after or without
    # 10 or 18 pt text, one and three lines long: a character of no width, its line as tall as the mark's run
    "pages_title_marks_in_runs_of_other_sizes": 4,
    # A picture in front of the text, 1000 to 4500 tall and 0 or 800 below its paragraph's top, in the first cell
    # of a table set as a character, its rows 1500 tall: moving with the text, it pushes no line aside but the
    # row grows to hold it below the cell's top margin; one that stays put leaves the row as it is
    "pages_floating_pictures_in_cells": 4,
    # A rectangle in front of the text, 1000 to 3000 tall, at the top of the first paragraph of a table's cell,
    # whose spacing before is 500: the row grows to hold it from the cell's top, above that spacing, not from the
    # paragraph's first line
    "pages_cell_front_object_spacing_before": 2,
    # Thirteen times, after 0 to 12 lines: a table flowing with the text (CELL) whose one cell holds 40 paragraphs
    # with 600 of spacing before and a small table set as a character in the fourth: going on over the page end,
    # the part on the next page starts below its first paragraph's spacing before, as in a cell without a table
    "pages_nested_cell_split_spacing_before": 27,
    # Fourteen times on a page of its own: a 2 × 2 table flowing with the text or set as a character, a footnote of
    # one to three lines in its first or last cell (none in two), then 60 paragraphs: the note takes room at the
    # page's foot as one anchored in the table's paragraph would, and the page ends that much higher
    "pages_footnotes_in_table_cells": 28,
    # Seven times on a page of its own: a table whose cell holds four paragraphs of a picture set as a character,
    # 10 pt and 11 pt text (one line or two), each ended by a run without characters at 9, 11, 12 or 15 pt (or by
    # none): as in the body, the run ending a paragraph makes its last line as tall as itself when it is larger
    "pages_cell_objects_ending_in_an_empty_larger_run": 7,
    # The same with the cell's first paragraph spaced 0 before and the others 600: the part on the next page starts
    # below the spacing before of the paragraph it starts with, though the cell's first paragraph has none
    "pages_nested_cell_split_with_its_first_paragraph_unspaced": 27,
    # Left and right margins of 8503 (42522 left of the page's width): tables set as characters 42518 to 42523
    # wide, alone or followed by a page number. The one column is 42520 wide, its width rounded down to a multiple
    # of 4 as each of several columns is, and the page number goes below a table wider than that
    "pages_one_column_width_rounded_down_to_four": 2,
    # Empty paragraphs whose shape takes the line height from the font (fontLineHeight), in 맑은 고딕, 함초롬바탕,
    # 바탕, 굴림 and HY헤드라인M at 11 and 20 pt, alone, after a line of 바탕 text and with a connected border: an
    # empty line keeps the character size (맑은 고딕 11 pt 1100, not the 1464 a line of its characters takes)
    "pages_empty_paragraphs_font_line_height": 2,
    # A table set as a character 3000 tall and 42238, 42300 or 42600 wide (the line is 42520) followed by a page
    # number in a run of 14 or 20 pt and text of 10 or 13 pt, the page number before the table or after it, on its
    # own page or after 33 lines: past a table wider than the line, the page number goes on the line after it, which
    # is as tall as the page number's run, and the table's line is spaced without it
    "pages_controls_after_a_wide_table": 51,
    # A table or a rectangle set as a character, 3000 tall and 42238 or 42600 wide (the line is 42520), alone or
    # after text, then a page number in a run of 14 pt with or without text of 10 pt after it: the page number is a
    # character of no width as tall as its run, on the object's line when the object fits (the line spaced from the
    # page number's size), on the next line past an object wider than the line, whatever the object
    "pages_controls_beside_objects_wider_than_the_line": 2,
    # A table 20000 x 3000 placed top and bottom alone in an empty paragraph, 0 or 500 down from its top, set to
    # split by cell, by table or not at all, allowed to overlap or not: allowed, it sends the paragraph's empty line
    # below it (one not fitting on the page goes on to the next page's top, the line staying); not allowed, the
    # line stays beside it and the next paragraph comes below the table
    "pages_overlapping_tables_alone_in_empty_paragraphs": 2,
    # A table 30000 x 1000 or a rectangle as large placed top and bottom 2000 or 5000 down from a paragraph of one or
    # four lines with 0 or 1000 of spacing before, its control before or after the text, then six short paragraphs:
    # on the first line, the object stands that far below the paragraph's top, above its spacing; on a later line,
    # below that line's top; the lines reaching it go below it
    "pages_objects_offset_down_from_a_paragraph_with_spacing_before": 8,
    # A table placed top and bottom at its paragraph's top or a rectangle in front of the text, in a run of 16 pt
    # after, in the middle of or after the spaces of 10 pt text one or three lines long: the line its place falls on
    # is as tall as a 16 pt character and spaced from it, and the table stands at that line's top
    "pages_object_runs_after_the_text": 2,
    # Thirty-eight times, on a page of its own after 38 lines: a table split by cell 500 to 2300 down from its
    # paragraph, two rows, the second's middle cell eight lines of 10 pt and the last cell a line of 20 pt, the
    # first column merged over both rows or not: where the 20 pt line does not fit above the page end, the row goes
    # on to the next page whole, its other cells too
    "pages_merged_rows_split_with_a_larger_cell": 76,
    # A table set as a character whose cell holds two lines and a table set as a character with no caption or one of
    # one or two lines below or above it: the cell's line is as tall as the table and its caption with their gap
    "pages_captioned_tables_in_cells": 1,
    # Forty-eight times, on a page of its own after 33 to 40 lines: a table 7696 tall placed top and bottom 0, 1166 or
    # 3000 down from a paragraph of text, split by cell or moved row by row, then an empty paragraph and two of text:
    # a table moved row by row with no room for its first row on the page goes on to the next page's top whole, the
    # paragraph's line and those after staying where they fit, the rest going below the table there; a page break
    # after a table that went on to the next page's top starts the page after that
    "pages_tables_offset_down_past_the_page_foot": 97,
    # Eight times, on a page of its own after 39 or 40 lines: a paragraph of text holding a table split cell by cell
    # (three rows of two lines) placed top and bottom 1000 to 3000 down, then an empty paragraph and two of text:
    # when not one line of its first row fits under the anchor, the table starts at the next page's top, as one
    # moved row by row, the empty paragraph staying under the anchor's line where it fits
    "pages_cell_split_tables_with_no_line_under_the_anchor": 16,
    # Thirteen times at a page's top: a table split cell by cell holding 30 to 42 lines, then a table on its own of
    # four rows, its last holding a table of six rows on its own in turn, then three lines: a page end among the
    # innermost table's rows splits there, each piece of it kept a table's cut for each table it is in and the bottom
    # margin of the row holding it above the foot
    "pages_nested_table_rows_holding_tables_split": 26,
    # The same, the last row holding six tables of two rows set as characters, one per paragraph: it splits between
    # them as between lines, a table being one
    "pages_nested_table_rows_holding_tables_as_characters_split": 26,
    # Twenty-one times at a page's top: a table split cell by cell, its inner margins 510, holding 34 lines, then
    # "표 뒤 글" with a table 1488 below its top (12 rows of three cells, their bottom margins 100 to 1300, header rows
    # repeated, outer margins 141): the part of the inner table going on to the next page starts below its top
    # margin again, as a table flowing in the body does
    "pages_nested_tables_going_on_below_their_top_margin": 42,
    # Thirty-eight times: the inner table on its own, or 1488 below "표 뒤 글", its rows declared 466 taller than their
    # text: a row whose text fits stays on the page, the room it declares to spare under the text cut at the page
    # end, as a flowing table's row's
    "pages_nested_table_rows_with_room_to_spare_at_the_page_foot": 76,
    # Eight times, 0 to 21 empty paragraphs down a page: a flowing table split cell by cell, its two rows joined by
    # a merged cell, the other cell of the first row holding 60 paragraphs, every fifth at 12 pt and the rest at
    # 10 pt: the part of that cell going on to the next page is as tall as its own lines, each at its size
    "pages_merged_rows_with_cells_of_mixed_line_sizes_split": 18,
    # Sixteen times, 30 to 51 empty paragraphs down a page: a flowing table split between cell lines, each of its six
    # rows a cell of two lines of text and one of an empty line and a table set as a character, both declared as
    # tall as the table fills its cell, or 300 taller: the row splits by the cell its text fills most, the part going
    # on as tall as its lines left or as what it declares below the page end, whichever is taller
    "pages_table_rows_split_by_the_cell_their_text_fills_most": 32,
    # The same with the 60 paragraphs all at 10 pt, each spaced 200 before: the part of that cell going on to the
    # next page starts below its first paragraph's spacing before, as at the cell's top
    "pages_merged_rows_with_cells_spaced_before_split": 20,
    # Twenty-seven times, the page end 1118 to 1518 below a block of five rows joined by a merged cell holding one
    # line, its paragraph spaced 0 or 200 before (top or centred), in a table split between cell lines: the line
    # fits above the page end only with its spacing before; when it does not, the merged cell goes on whole
    "pages_merged_rows_split_by_a_cell_spaced_before": 54,
    # Every face whose ascent and descent do not make up its em, at every 50 HWPUNIT from 500 to 4000, in paragraphs
    # taking their line height from the font: each line as tall as Hancom lays it out, a few units off the ascent and
    # descent rounded up at many sizes
    "pages_font_line_heights_by_size": 102,
    # A rectangle placed top and bottom 0 or 1213 down from an empty paragraph after 31 lines, its foot one unit above
    # the body's foot or right at it: it stays on the page, its paragraph's line too (a line of text ending right at
    # the foot goes on to the next page, see pages_line_ends_at_page_foot), the next paragraph on the next page
    "pages_object_ending_at_the_page_foot": 9,
    # A page number in a run of 20 pt, a header of 10 pt and a page number again before a table set as a character in a
    # run of 12 pt, 48553 wide (the line is 48188), the paragraph's line spacing 160 %: one line, as tall as the
    # table and spaced from the page numbers' size
    "pages_controls_before_a_table_wider_than_the_line": 1,
    # A rectangle 3000 tall placed top and bottom 0 or 500 down alone in an empty paragraph with 0 or 1000 of spacing
    # before, mid-page or at the top of a page after a page break: it stands that far below the paragraph's top,
    # above its spacing, and the next paragraph comes below its foot
    "pages_empty_paragraph_objects_below_spacing_before": 5,
    # Five times: 39 lines, then two empty paragraphs each holding a table split cell by cell (50 rows under two
    # header rows it repeats, its first column merged over them and 60 lines long), 1000 or 1500 and 0 or 394 down,
    # the first placed top and bottom or square, neither's header rows fitting under its anchor; then four lines or a
    # page break: the first table starts at the next page's top, the second at the top of the page after the first's
    # foot, and the lines after go on below the first table's foot
    "pages_tables_starting_past_their_anchors_on_one_page": 27,
    # Eleven times at a page's top: a table split cell by cell, one row of two cells, the second holding 30 to 40
    # lines, then a table placed top and bottom on its own (12 rows of one line, 1282 tall each), then three lines:
    # the page end falls among the inner table's rows, which stay on the page only ending a table's cut (101)
    # above the foot the lines of text go down to, the rest going on at the next page's top
    "pages_nested_table_rows_a_cut_above_the_page_foot": 22,
    # The same twelve times (28 to 39 lines), the inner table's bottom margin 1417: its rows stay on the page only
    # ending that margin and a table's cut above the foot
    "pages_nested_table_rows_with_a_bottom_margin_above_the_page_foot": 24,
    # The same eleven times, the inner table's first column merged over rows 0-1, 2-3, 4-6 and 7-9 (two or three
    # lines each, taller than the rows they span): a page end among rows so joined splits them cell by cell, as in a
    # table flowing in the body, each cell keeping the lines that end a table's cut above the foot
    "pages_nested_tables_with_merged_rows_split_cell_by_cell": 22,
    # The merged inner table twelve times (29 to 40 lines), its bottom margin 1417 and "표 뒤 글" after it in its
    # paragraph: the table splits as one on its own, the text going below it on the next page; when nothing of it
    # stays, the text stays where the table would have started and the table goes on alone
    "pages_nested_tables_before_text_with_merged_rows_split": 24,
    # A table 20000 x 3000 or a rectangle 3000 x 3000 placed top and bottom at the top of a paragraph with 300 of
    # spacing before, in a run of 10, 14 or 20 pt, then a space of 8 pt and text of 10 pt: the object stands at the
    # paragraph's top, above its spacing, the text right below it, and the line is as tall as the object's run
    "pages_objects_on_a_text_paragraphs_top": 1,
    # A chart wrapped square in a run's hp:switch (Hancom saves every chart in one), 20000 or 8000 wide, with a
    # picture 8000 or 20000 wide in its hp:default: the lines beside it are as narrow as the chart leaves them
    "pages_chart_case_wider_than_its_default": 1,
    "pages_chart_case_narrower_than_its_default": 1,
    # "'15.", a fixed-width space and "10월" in 굴림 11 pt at 자간 -8 % in cells 4250 to 4380 wide: one line from
    # 4300, the fixed-width space taking its 자간; the same with a space, and without one, for comparison
    "pages_fixed_width_space_line_ends": 4,
    # A picture placed top and bottom or square, 1000 or 3000 tall, from the top of a paragraph in the first
    # cell of a table set as a character (its rows 1500 tall): its control before, among or after one to five
    # lines of text or alone, in the cell's first or second paragraph, offset 0 to 3000 below (or up), outer
    # margins 0 or 300, 5000 to 12000 wide from the cell's left or right, spacing 400 before and 300 after or
    # lines 200 % apart. It stands its offset below the top of its control's line (of the paragraph, above its
    # spacing, for the first line); the lines from there on, of its paragraph and the next, reaching a
    # top-and-bottom one go below its foot and those beside a square one break in the room beside it (none
    # below 1440). One that stays put (flowWithText 0) pushes nothing
    "pages_wrapped_pictures_in_cells": 12,
    # Pictures set as characters, 6000 x 3000, with a caption above, below, left or right of them (gap 283, 3000
    # wide beside), empty or of several lines in 1 pt or 10 pt, alone in their paragraph or after "앞 글 " with 36
    # characters after them, and alone in the cell of a table: above or below, the caption's lines and gap make the
    # picture's line taller (3000 + 283 + 100 for an empty 1 pt caption); beside, its width and gap make the picture
    # wider (the text after it breaks onto a second line), its line staying 3000 tall
    "pages_captions_on_inline_pictures": 4,
    # Paragraph shapes giving one margin in unit="CHAR" (hp:case; hp:default holds 2v+1 in HWPUNIT) where 바탕글's
    # characters are 15 pt, in paragraphs of style 0 and of a style whose characters are 24 pt: spacing after and
    # before 80, left and right margins 200, an indent of 200 and -200. Hancom counts each two-hundredths of
    # 바탕글's character size (600 and 1500 here), whatever the paragraph's own style or characters
    "pages_margins_in_character_units": 3,
    # Numbered and bulleted paragraphs, empty or with text in 10 or 15 pt, each label in its own 8, 13 or 20 pt
    # character shape or none: an empty numbered paragraph's line is as tall as its number when that is larger, as
    # one with text is; a bullet's character shape never makes a line taller
    "pages_empty_numbered_paragraphs": 2,
    # Three times on A4: 37 lines, an empty paragraph holding a table flowing with the text (8 rows, moved row by
    # row) whose first row has no room under it, so that it starts on the next page, two empty lines, then a
    # paragraph that does not fit at the page end. When the table ends 64768 down the body (65762), the line of an
    # empty paragraph holding another such table goes on to the page after, at its top; when it ends at 64760 the
    # line still fits below it there. A paragraph of text after a table ending at 65560 also goes to the page after
    "pages_anchor_lines_past_a_moved_table": 9,
    # Four times on A4, each from a page break: lines of text, then a paragraph holding a table (20000 tall) placed
    # top and bottom at the foot of the page's body or of the paper and kept on its paragraph's page
    # (pos@holdAnchorAndSO="1"), then three lines. When the paragraph's first line with its spacing reaches the
    # table's band on its page (44400 + 1600 past 45762, 52800 + 1600 past 54266, an empty one at 46400), Hancom
    # puts that paragraph and its table on the next page, at its top, and leaves the lines above where they are,
    # even one standing where the band would have been; when it fits (44000 + 1600) only the lines after go on
    "pages_held_bottom_object_anchors": 8,
}


def _hancom_lines(data: bytes) -> list[list[int]]:
    """The ``vertpos`` of each cached line of every body paragraph, sections in order."""

    lines = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = [name for name in archive.namelist() if re.fullmatch(r"Contents/section\d+\.xml", name)]
        for name in sorted(names, key=lambda name: int(re.findall(r"\d+", name)[0])):
            root = etree.fromstring(archive.read(name))
            lines += [
                [int(seg.get("vertpos")) for seg in paragraph.findall(f"{HP}linesegarray/{HP}lineseg")]
                for paragraph in root.findall(f"{HP}p")
            ]
    return lines


def _with_outer_margins(data: bytes, value: int) -> bytes:
    """*data* with every table's top and bottom outer margins set to *value*."""

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section"):
                root = etree.fromstring(payload)
                for margin in root.iter(f"{HP}outMargin"):
                    if etree.QName(margin.getparent()).localname == "tbl":
                        margin.set("top", str(value))
                        margin.set("bottom", str(value))
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, payload)
    return out.getvalue()


def _without_caches(data: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section"):
                root = etree.fromstring(payload)
                for cache in list(root.iter(f"{HP}linesegarray")):
                    cache.getparent().remove(cache)
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, payload)
    return out.getvalue()


def _as_an_older_hancom_wrote_it(data: bytes, xml_version: str) -> bytes:
    """*data* without line caches, each paragraph shape's margins and line spacing written outside hp:switch
    as hp:default holds them (doubled), and version.xml giving *xml_version*."""

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(_without_caches(data))) as source, \
            zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Contents/header.xml":
                root = etree.fromstring(payload)
                for shape in root.iter(f"{HH}paraPr"):
                    for switch in shape.findall(f"{HP}switch"):
                        default = switch.find(f"{HP}default")
                        if default is None or default.find(f"{HH}margin") is None:
                            continue
                        at = list(shape).index(switch)
                        for child in reversed(list(default)):
                            shape.insert(at, child)
                        shape.remove(switch)
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif info.filename == "version.xml":
                payload = re.sub(rb'xmlVersion="[^"]*"', b'xmlVersion="' + xml_version.encode() + b'"', payload)
            target.writestr(info, payload)
    return out.getvalue()


def _assert_like_hancom(estimate: PageEstimate, data: bytes, pages: int) -> None:
    assert estimate.unsupported == ()
    assert estimate.pages == pages
    hancom = _hancom_lines(data)
    estimated = [[line.vertpos for line in lines] for lines in estimate.lines]
    assert len(estimated) == len(hancom)
    assert [mine for mine, theirs in zip(estimated, hancom) if theirs] == [theirs for theirs in hancom if theirs]
    assert max(line.page for lines in estimate.lines for line in lines) == pages - 1


@pytest.mark.parametrize("name", sorted(HANCOM_PAGES))
def test_the_estimate_puts_every_line_where_hancom_did(name: str) -> None:
    data = (FIXTURES / f"{name}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, HANCOM_PAGES[name])


@pytest.mark.parametrize("name", sorted(HANCOM_PAGES))
def test_without_line_caches_formfit_breaks_the_lines_the_same(name: str) -> None:
    data = (FIXTURES / f"{name}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(_without_caches(data)), data, HANCOM_PAGES[name])


def test_a_text_box_grown_for_other_text_is_laid_out_anew() -> None:
    # The rectangle holding three lines of text, its current size written 9966 instead of the 4766 Hancom grew it
    # to, as a document saved with other fonts or text has it: Hancom lays the box's text out anew and draws the
    # rectangle as tall as that text and its margins, whatever the current size says.
    data = (FIXTURES / "pages_text_box_grown_by_three_lines.hwpx").read_bytes()
    stale = _without_caches(data)
    with zipfile.ZipFile(io.BytesIO(stale)) as source:
        parts = {info: source.read(info.filename) for info in source.infolist()}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info, payload in parts.items():
            if info.filename == "Contents/section0.xml":
                payload = payload.replace(b'<hp:curSz width="0" height="4766"/>', b'<hp:curSz width="0" height="9966"/>')
                assert b'height="9966"' in payload
            target.writestr(info, payload)

    _assert_like_hancom(estimate_pages(out.getvalue()), data, 1)


def test_cells_keeping_their_caches_hold_their_wrapped_pictures_where_hancom_put_them() -> None:
    # A Hancom Office 2024 save of 50 tables set as characters, every paragraph keeping the layout cache Hancom
    # wrote, a picture placed top and bottom or square in the first cell of each: its control after the text of a
    # long paragraph (on its last line, or on the line it falls on laid out the cell's whole width, before the lines
    # beside the picture broke again), in a paragraph with spacing before, margins, an indent or wider line
    # spacing, a second picture in the paragraph after, or a picture that does not move with the text (pushing
    # nothing). Each row reaches down to the picture's foot as Hancom drew it, and the later lines follow.
    data = (FIXTURES / "pages_wrapped_pictures_in_cached_cells.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 11)


def test_an_opening_bracket_moves_down_with_the_syllable_after_it() -> None:
    # Hancom laid out "%(평가", ")(평가", "a(평가", "%(34)" and the like after a tab, a space, a syllable or a digit,
    # breaking between any two syllables, the line ending at the closing mark, at the bracket or at the character
    # after it: each paragraph's lines start where Hancom's do (a tab counts eight in textpos).
    root = HwpxDocument.open(io.BytesIO((FIXTURES / "pages_opening_brackets_at_line_ends.hwpx").read_bytes()))._root
    measure = page_layout._Measure(root)
    page = page_layout._page(root.sections[0].element)

    for paragraph in root.sections[0].element.findall(f"{HP}p")[1:]:
        runs = paragraph.findall(f"{HP}run")
        size, refs, _ = page_layout._text_size(measure, runs)
        style = measure.style(paragraph.get("paraPrIDRef"), refs, paragraph)
        shape = measure.shape(paragraph.get("paraPrIDRef"))
        widths = page_layout._indented(page.column_width - shape.left - shape.right, shape, style)
        text = page_layout._run_text(runs)

        starts = measure.line_starts(text, widths, size, style)

        textpos = [sum(8 if ch == "\t" else 1 for ch in text[:start]) for start in starts]
        assert textpos == [int(segment.get("textpos"))
                           for segment in paragraph.findall(f"{HP}linesegarray/{HP}lineseg")], text


def test_margins_in_character_units_break_lines_where_hancom_does() -> None:
    # The line count alone does not show a narrower line: the paragraphs with a margin or an indent in unit="CHAR"
    # start each line where Hancom's do (an indent of 200 takes 1500 off the first line at 바탕글's 15 pt).
    root = HwpxDocument.open(io.BytesIO((FIXTURES / "pages_margins_in_character_units.hwpx").read_bytes()))._root
    measure = page_layout._Measure(root)
    page = page_layout._page(root.sections[0].element)
    checked = 0

    for paragraph in root.sections[0].element.findall(f"{HP}p")[1:]:
        runs = paragraph.findall(f"{HP}run")
        text = page_layout._run_text(runs)
        if len(text) < 40:  # the short paragraphs measure spacing, not line breaks
            continue
        size, refs, _ = page_layout._text_size(measure, runs)
        style = measure.style(paragraph.get("paraPrIDRef"), refs, paragraph)
        shape = measure.shape(paragraph.get("paraPrIDRef"))
        widths = page_layout._indented(page.column_width - shape.left - shape.right, shape, style)

        starts = measure.line_starts(text, widths, size, style)

        assert starts == [int(segment.get("textpos"))
                          for segment in paragraph.findall(f"{HP}linesegarray/{HP}lineseg")], text[:20]
        checked += 1
    assert checked == 8


@pytest.mark.parametrize("name", ["pages_closing_bracket_after_a_space_starts_a_line",
                                  "pages_percent_after_a_space_starts_a_line"])
def test_a_closing_mark_after_a_space_may_start_a_line(name: str) -> None:
    # The line count alone does not show where a line starts: each paragraph's lines start where Hancom's do.
    root = HwpxDocument.open(io.BytesIO((FIXTURES / f"{name}.hwpx").read_bytes()))._root
    measure = page_layout._Measure(root)
    page = page_layout._page(root.sections[0].element)

    for paragraph in root.sections[0].element.findall(f"{HP}p")[1:]:
        runs = paragraph.findall(f"{HP}run")
        size, refs, _ = page_layout._text_size(measure, runs)
        style = measure.style(paragraph.get("paraPrIDRef"), refs, paragraph)
        shape = measure.shape(paragraph.get("paraPrIDRef"))
        widths = page_layout._indented(page.column_width - shape.left - shape.right, shape, style)

        starts = measure.line_starts(page_layout._run_text(runs), widths, size, style)

        assert starts == [int(segment.get("textpos")) for segment in paragraph.findall(f"{HP}linesegarray/{HP}lineseg")]


@pytest.mark.parametrize(
    "name",
    [
        "pages_repeated_header_of_five_lines_without_room",
        "pages_repeated_header_holding_a_table_without_room",  # a line and a table of two rows in it
        "pages_repeated_header_holding_a_taller_table_without_room",  # a line and a table of six rows
        "pages_repeated_header_moved_row_by_row_without_room",  # a header of three lines, the table moved row
        "pages_two_repeated_headers_moved_row_by_row_without_room",  # by row; two such headers, the first fitting
    ],
)
def test_a_repeated_header_row_without_room_is_not_split(name: str) -> None:
    # A flowing table of 41 to 61 rows split cell by cell or moved row by row, its first rows a header
    # repeated on every page, under 35 to 39 lines: with no room for the header rows, Hancom does not split
    # them but starts the table on the next page, the header rows drawn there once, and the paragraph after
    # it goes on under the anchor line on the first.
    data = (FIXTURES / f"{name}.hwpx").read_bytes()

    for source in (data, _without_caches(data)):
        estimate = estimate_pages(source)

        assert (estimate.unsupported, estimate.pages) == ((), 3)
        assert [[line.vertpos for line in lines] for lines in estimate.lines] == _hancom_lines(data)


@pytest.mark.parametrize("number_format", ["KOREAN_DIGIT", "HANGUL"])
def test_a_number_label_in_a_format_the_text_export_does_not_write_is_estimated(number_format: str) -> None:
    # The bullet and number labels above, every number measured, in a character shape of its own and in a
    # format of Hancom's own documents that the text export does not write: such a number counts as a syllable
    # instead of failing the estimate.
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO((FIXTURES / "pages_bullet_and_number_labels.hwpx").read_bytes())) as source, \
            zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Contents/header.xml":
                payload = re.sub(rb'numFormat="[A-Z_]+"', f'numFormat="{number_format}"'.encode(), payload)
                payload = re.sub(rb'useInstWidth="\w+"', b'useInstWidth="1"', payload)
                payload = re.sub(rb'(<hh:paraHead [^>]*)charPrIDRef="\d+"', rb'\1charPrIDRef="0"', payload)
            target.writestr(info, payload)

    for source_bytes in (out.getvalue(), _without_caches(out.getvalue())):
        estimate = estimate_pages(source_bytes)

        assert estimate.unsupported == ()
        assert estimate.pages >= 1


@pytest.mark.parametrize(
    "name",
    ["pages_paragraph_margins_of_an_older_hancom", "pages_paragraph_margins_and_fixed_spacing_of_an_older_hancom"],
)
def test_an_older_hancoms_paragraph_margins_outside_a_switch_read_halved(name: str) -> None:
    # Twelve paragraphs with left margins, first-line indents and hanging ones, spacing above and below, and in
    # the second document fixed line spacing. Hancom laid them out from a copy written as an older Hancom
    # writes it: the margins and spacing outside hp:switch, doubled as hp:default holds them, version.xml
    # giving xmlVersion 1.0. It reads them halved there; in a document of xmlVersion 1.31 or later, as they are.
    data = (FIXTURES / f"{name}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(_as_an_older_hancom_wrote_it(data, "1.0")), data, 2)
    _assert_like_hancom(estimate_pages(_as_an_older_hancom_wrote_it(data, "1.3")), data, 2)
    newer = estimate_pages(_as_an_older_hancom_wrote_it(data, "1.31"))
    assert [[line.vertpos for line in lines] for lines in newer.lines] != _hancom_lines(data)


def test_an_unsplit_table_without_room_goes_on_alone() -> None:
    # The table above, 63000 tall, set not to split: with no room below the line's top, it goes alone to the
    # next page's top and the paragraph's lines, and those after, stay where they stood on the first page.
    data = (FIXTURES / "pages_unsplit_table_without_room_above_its_line.hwpx").read_bytes()

    for source in (data, _without_caches(data)):
        estimate = estimate_pages(source)

        assert (estimate.unsupported, estimate.pages) == ((), 2)
        assert {line.page for lines in estimate.lines for line in lines} == {0}
        assert [[line.vertpos for line in lines] for lines in estimate.lines] == _hancom_lines(data)


# The same five pictures with a reflection below (hp:reflection, its share of the picture in hp:pos), saved by
# Hancom: each takes about that share of the picture's height (with its glow, and a pixel round it) less a pixel,
# and its distance, below it, which the estimate follows to within a pixel or so (Hancom rounds the parts
# differently with the size and the distance). All take the fifth picture on to the next page.
REFLECTION_PAGES = {
    "pages_picture_reflection_quarter": 2,  # a quarter, no gap: each line 13737
    "pages_picture_reflection_half_spaced": 2,  # half, 1000 below: 17500
    "pages_picture_reflection_tenth_spaced": 2,  # a tenth, 1000 below: 13040
    "pages_picture_reflection_quarter_with_glow": 2,  # a quarter of the picture with a glow 500: 13962
    "pages_picture_reflection_quarter_among_text": 2,
}


@pytest.mark.parametrize("name", sorted(REFLECTION_PAGES))
@pytest.mark.parametrize("caches", [True, False])
def test_a_picture_reflection_takes_about_its_share_of_the_picture_below_it(name: str, caches: bool) -> None:
    data = (FIXTURES / f"{name}.hwpx").read_bytes()
    estimate = estimate_pages(data if caches else _without_caches(data))
    hancom = _hancom_lines(data)

    assert estimate.unsupported == ()
    assert estimate.pages == REFLECTION_PAGES[name]
    tops = [(line.page, line.vertpos) for lines in estimate.lines for line in lines]
    theirs = [top for lines in hancom for top in lines]
    assert len(tops) == len(theirs)
    assert max(abs(mine[1] - top) for mine, top in zip(tops, theirs)) <= 100


def test_a_shape_placed_up_from_its_paragraph_takes_no_more_than_its_foot() -> None:
    # A rectangle 5000 tall placed top and bottom 1500 up from the top of its paragraph (vertOffset kept as the
    # unsigned 32-bit 4294965796), saved by Hancom: one page. Read as unsigned, the paragraph's line was four
    # billion tall and the document three pages.
    data = (FIXTURES / "pages_para_shape_unsigned_offset.hwpx").read_bytes()

    for estimate in (estimate_pages(data), estimate_pages(_without_caches(data))):
        assert estimate.unsupported == ()
        assert estimate.pages == 1


@pytest.mark.parametrize(
    ("name", "pages"),
    [
        ("pages_margin_negative_header_one_page", 1),
        ("pages_margin_negative_header_two_pages", 2),
        ("pages_margin_negative_footer_one_page", 1),
        ("pages_margin_negative_footer_two_pages", 2),
        ("pages_margin_negative_both_one_page", 1),
        ("pages_margin_negative_both_two_pages", 2),
    ],
)
def test_a_negative_page_margin_kept_unsigned_counts_as_negative(name: str, pages: int) -> None:
    # Header margin -1400, footer margin -3600 and both (-4000 and -3600), kept as unsigned 32-bit numbers
    # (4294965896 ...) as a converted .hwp has them, saved by Hancom: the body grows by them, so the one-page
    # files hold just as many one-line paragraphs as fit it and the two-page ones one more. Read as unsigned,
    # the body was negative and the estimate never ended.
    data = (FIXTURES / f"{name}.hwpx").read_bytes()

    for estimate in (estimate_pages(data), estimate_pages(_without_caches(data))):
        assert estimate.unsupported == ()
        assert estimate.pages == pages


@pytest.mark.parametrize(("side", "written"), [("header", "-1400"), ("header", "-4000"), ("top", "-1000")])
def test_a_page_margin_written_with_a_minus_sign_takes_the_new_page_margin(side: str, written: str) -> None:
    # Header margin written "-1400" (not the unsigned form), 46 one-line paragraphs: Hancom reads the minus sign as
    # no margin it knows, lays the page with the new-page header margin 4252 and saves that -- two pages, where
    # -1400 would have held them on one. The fixture is that save; written back with the minus sign (on the header
    # or, with the new-page top 5668 it saves, the top), the estimate gives Hancom's two pages.
    data = (FIXTURES / "pages_margin_minus_sign_header.hwpx").read_bytes()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Contents/section0.xml":
                root = etree.fromstring(payload)
                (margin,) = [m for m in root.iter(f"{HP}margin") if m.getparent().tag == f"{HP}pagePr"]
                assert margin.get(side) == {"header": "4252", "top": "5668"}[side]
                margin.set(side, written)
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, payload)
    minus = out.getvalue()

    for estimate in (estimate_pages(data), estimate_pages(minus), estimate_pages(_without_caches(minus))):
        assert estimate.unsupported == ()
        assert estimate.pages == 2


def test_an_object_in_a_switch_is_laid_out_as_its_case() -> None:
    # A chart in a run's hp:switch, wrapped square, with the OLE object standing for it in hp:default: Hancom lays
    # the following lines out beside the chart of the hp:case requiring the 2016 chart namespace, as if it stood in
    # the run itself.
    def with_switch(branches: tuple[tuple[str, str, str], ...]) -> bytes:
        document = HwpxDocument.new()
        document.add_paragraph("앞 문단")
        paragraph = document.add_paragraph("곁 문단 " * 60)
        run = paragraph.element.find(f"{HP}run")
        holders = [run] if len(branches) == 1 else []
        if not holders:
            switch = etree.Element(f"{HP}switch")
            run.insert(0, switch)
        for branch, name, width in branches:
            if branch != "run":
                attributes = {f"{HP}required-namespace": "http://www.hancom.co.kr/hwpml/2016/ooxmlchart"}                     if branch == "case" else {}
                holders.append(etree.SubElement(switch, f"{HP}{branch}", attributes))
            obj = etree.Element(f"{HP}{name}", {"textWrap": "SQUARE"})
            holders[-1].insert(0, obj)
            etree.SubElement(obj, f"{HP}sz", {"width": width, "height": "9000"})
            etree.SubElement(obj, f"{HP}pos", {"treatAsChar": "0", "vertRelTo": "PARA", "horzRelTo": "COLUMN",
                                               "vertAlign": "TOP", "horzAlign": "LEFT"})
        document.oxml.sections[0].mark_dirty()
        return document.to_bytes()

    switched = estimate_pages(with_switch((("case", "chart", "20000"), ("default", "ole", "8000"))))
    as_its_case = estimate_pages(with_switch((("run", "chart", "20000"),)))
    as_its_default = estimate_pages(with_switch((("run", "ole", "8000"),)))

    assert switched.unsupported == ()
    assert switched.lines == as_its_case.lines != as_its_default.lines


def test_page_margins_leaving_no_body_are_unsupported() -> None:
    data = (FIXTURES / "pages_margin_negative_header_one_page.hwpx").read_bytes()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Contents/section0.xml":
                root = etree.fromstring(payload)
                (margin,) = [m for m in root.iter(f"{HP}margin") if m.getparent().tag == f"{HP}pagePr"]
                margin.set("top", "90000")
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, payload)

    estimate = estimate_pages(out.getvalue())
    assert estimate.pages is None
    assert any("no room for the body" in reason for reason in estimate.unsupported)


@pytest.mark.parametrize("text_width", [1, 2, 3])
def test_one_column_rounding_to_zero_is_unsupported_without_cache_mutation(text_width: int) -> None:
    from hwpx.layout.line_cache import write_line_caches

    document = HwpxDocument.new()
    document.add_paragraph("너비 없는 줄")
    page = next(document.oxml.sections[0].element.iter(HP + "pagePr"))
    page.set("width", str(text_width))
    margin = page.find(HP + "margin")
    for side in ("left", "right", "gutter"):
        margin.set(side, "0")
    before = document.to_bytes()

    estimate = estimate_pages(document)
    report = write_line_caches(document)

    assert estimate.pages is None and estimate.lines == ()
    assert estimate.unsupported == ("section 0: column width leaving no room for the body",)
    assert report.unsupported == estimate.unsupported and report.written == 0
    assert document.to_bytes() == before


def test_an_offset_written_with_a_minus_sign_is_read_as_zero() -> None:
    # The same rectangle written vertOffset="-1500" (not the unsigned form): Hancom reads it as 0, draws the
    # rectangle at the paragraph's top and saves 0. The fixture is that save; written back with the minus sign,
    # the lines go where Hancom put them.
    data = (FIXTURES / "pages_para_shape_signed_offset.hwpx").read_bytes()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Contents/section0.xml":
                root = etree.fromstring(payload)
                (pos,) = [rect.find(f"{HP}pos") for rect in root.iter(f"{HP}rect")]
                pos.set("vertOffset", "-1500")
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, payload)
    signed = out.getvalue()

    for estimate in (estimate_pages(signed), estimate_pages(_without_caches(signed))):
        assert estimate.unsupported == ()
        assert estimate.pages == 1
        assert [[line.vertpos for line in lines] for lines in estimate.lines] == _hancom_lines(data)


# Objects placed top and bottom from the top of an empty paragraph after four lines (10 pt, spaced 160%), the
# lines after it of text, laid out and saved by Hancom: its pages, and the page of the paragraph's line and
# the lines after when not the first:
STACKED_PAGES: dict[str, int | tuple[int, int]] = {
    "pages_stacked_two_tables": 1,  # both 0 down: one right below the other, the line below both
    "pages_stacked_three_tables": 1,
    "pages_stacked_second_table_1230_down": 1,  # still right below the first
    "pages_stacked_second_table_5000_down": 1,  # below a gap, which takes the paragraph's line
    "pages_stacked_first_table_2000_down": 1,  # the line above it, the next line below both
    "pages_stacked_four_tables_with_margins": 1,  # outer margins 140
    "pages_stacked_two_pictures": 1,
    "pages_stacked_pictures_side_by_side": 1,  # each at its own offset, the lines above them staying there
    "pages_stacked_picture_and_table": 1,
    "pages_stacked_two_pictures_past_the_foot": 2,  # the second alone on the next page, the text on the first
    "pages_stacked_two_tables_past_the_foot": 2,
    "pages_stacked_middle_table_past_the_foot_cell": 2,  # the second on the next page, the third below the first
    "pages_stacked_middle_table_past_the_foot_table": 2,  # (split row by row, the same)
    "pages_stacked_table_taller_than_a_page_cell": 3,  # split between lines over the two pages after the first
    "pages_stacked_table_taller_than_a_page_table": 3,  # row by row
    "pages_stacked_four_tables_over_four_pages": 4,  # the third below the first, 1230 down buried; the fourth
                                                     # past the second page, row by row over the last two
    "pages_stacked_tables_filling_the_second_page": 2,  # the third below the second, on the second page
    "pages_stacked_second_table_on_the_next_page": 2,  # outer margins 141: the second from the next page's top
    # The paragraph low on its page, the first table not fitting under it: it flows from there.
    "pages_stacked_low_two_tables_cell": (2, 1),  # split at the foot, the second below its end, then the line
    "pages_stacked_low_two_tables_table": (2, 1),  # its first row alone on the first page
    "pages_stacked_low_small_second_table": (2, 1),  # the small second one not back on the first page
    "pages_stacked_low_table_taller_than_a_page": (3, 2),  # no room left for the line: the next page's top
    # After an empty paragraph whose second table of two went on to the next page:
    "pages_stacked_in_two_paragraphs": 2,  # another such paragraph: its tables below the first's line
    "pages_stacked_in_two_paragraphs_over_four_pages": (4, 3),  # four tables, then two more from where the
                                                           # first's line leaves off: the first of them split
                                                           # over the next page's top across the other's, the
                                                           # second below it, the line on the fourth page
    "pages_stacked_then_a_flowing_table": 2,  # a paragraph holding one flowing table: under its line
    "pages_stacked_then_text_over_two_pages": (3, 2),  # 60 lines, going on below the second table
    # After an empty paragraph whose second table went alone to the top of the next page, filling it but for 1500:
    "pages_stacked_then_text_below_a_nearly_filled_page": (3, 2),  # 60 lines: one in those 1500, the rest after
    "pages_stacked_then_text_past_a_filled_page": (3, 2),  # 900 left, less than a line: the lines skip that page
    "pages_stacked_then_a_table_as_character_past_a_filled_page": (3, 2),  # one 55000 tall skips it too
    "pages_stacked_then_a_table_as_character_below_a_short_one": (2, 1),  # under a second table 5762 tall
}


@pytest.mark.parametrize("name", sorted(STACKED_PAGES))
def test_objects_stacked_in_an_empty_paragraph_go_where_hancom_put_them(name: str) -> None:
    # Each goes to the first page, from the paragraph's on, where it fits below the earlier ones it overlaps
    # across; one fitting on none starts at the top of the page after the last one used. The lines take the
    # first places clear of them. A last page holding only objects has no line, hence no HANCOM_PAGES entry.
    data = (FIXTURES / f"{name}.hwpx").read_bytes()
    hancom = _hancom_lines(data)
    pages, lines_page = STACKED_PAGES[name] if isinstance(STACKED_PAGES[name], tuple) else (STACKED_PAGES[name], 0)

    for source in (data, _without_caches(data)):
        estimate = estimate_pages(source)
        estimated = [[line.vertpos for line in lines] for lines in estimate.lines]

        assert (estimate.unsupported, estimate.pages) == ((), pages)
        assert [lines[-1].page for lines in estimate.lines][-1] == lines_page
        assert [mine for mine, theirs in zip(estimated, hancom) if theirs] == [theirs for theirs in hancom if theirs]


@pytest.mark.parametrize(("index", "height"), [(0, 60000), (1, 70000)])  # the first not fitting, a later on no page
def test_a_stacked_picture_past_the_page_foot_is_not_followed(index: int, height: int) -> None:
    out = io.BytesIO()
    data = (FIXTURES / "pages_stacked_two_pictures.hwpx").read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section"):
                root = etree.fromstring(payload)
                list(root.iter(f"{HP}pic"))[index].find(f"{HP}sz").set("height", str(height))
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, payload)

    assert estimate_pages(out.getvalue()).unsupported == (
        "section 0: an object placed top and bottom past the page's foot",)


def test_objects_set_as_characters_among_text_on_both_sides_of_a_square_wrapped_object_are_not_followed() -> None:
    # The picture of pages_square_band_table_as_character_among_text moved 3000 from the column's left: text goes
    # on both sides of it, each line in two pieces, and an object among it is not followed there.
    out = io.BytesIO()
    data = (FIXTURES / "pages_square_band_table_as_character_among_text.hwpx").read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section"):
                root = etree.fromstring(payload)
                square = next(pic for pic in root.iter(f"{HP}pic") if pic.get("textWrap") == "SQUARE")
                square.find(f"{HP}pos").set("horzOffset", "3000")
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, payload)

    assert estimate_pages(_without_caches(out.getvalue())).unsupported == (
        "section 0: objects set as characters among text beside a square-wrapped object",)


def test_a_typed_ideographic_space_is_not_a_fixed_width_one() -> None:
    # 맑은 고딕 10 pt cells of narrowing widths, laid out and saved by Hancom: rows of "가나다라마" each followed
    # by one or two ideographic spaces typed in the text (U+3000), or by fixed-width spaces (hp:fwSpace, which
    # python-hwpx reads as U+3000 too). The typed space is a full em, a line may start after it, and at a line
    # end it hangs however many follow each other; a fixed-width space is a quarter em, and one starting at or
    # past the margin begins the next line, even right after a word.
    doc = HwpxDocument.open((FIXTURES / "pages_typed_ideographic_spaces.hwpx").read_bytes())
    cells = list(doc.oxml.sections[0].element.iter(f"{HP}tc"))
    typed = 0
    for cell in cells:
        paragraph = cell.find(f"{HP}subList/{HP}p")
        runs = paragraph.findall(f"{HP}run")
        ref = next(run.get("charPrIDRef") for run in runs if run.find(f"{HP}t") is not None)
        style = page_layout.text_style_from_refs(doc.oxml, paragraph.get("paraPrIDRef"), [ref])
        segs = paragraph.findall(f"{HP}linesegarray/{HP}lineseg")
        widths = [int(seg.get("horzsize")) for seg in segs]
        starts = page_layout.hancom_line_starts(page_layout._run_text(runs), widths, 10, style)
        assert starts == [int(seg.get("textpos")) for seg in segs], widths[0]
        typed += "\u3000" in "".join(t.text or "" for t in paragraph.iter(f"{HP}t"))
    assert (len(cells), typed) == (30, 22)


def _with_wider_tables_set_as_characters(data: bytes, wider: int) -> bytes:
    """*data* with every table set as a character *wider* wider (narrower when negative)."""

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section"):
                root = etree.fromstring(payload)
                for table in root.iter(f"{HP}tbl"):
                    if table.find(f"{HP}pos").get("treatAsChar") == "1":
                        size = table.find(f"{HP}sz")
                        size.set("width", str(int(size.get("width")) + wider))
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, payload)
    return out.getvalue()


@pytest.mark.parametrize(
    ("name", "wider"),
    [
        ("pages_table_as_character_2000_short_then_three_spaces", 1800),  # one line: 200 short, the third space
                                                                          # would go on to a line of its own
        ("pages_table_cell_table_as_character_300_short_then_three_spaces", -2000),  # two lines in a cell: 2300
                                                                                    # short, all would fit
    ],
)
def test_a_paragraph_of_an_object_and_spaces_keeps_its_cached_lines(name: str, wider: int) -> None:
    # A table set as a character and three spaces after it in its paragraph, laid out by Hancom, then the
    # table made wider or narrower: with the caches the paragraph keeps Hancom's lines, as Hancom does when
    # it opens the file, whatever FormFit would make of the new width.
    data = (FIXTURES / f"{name}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(_with_wider_tables_set_as_characters(data, wider)), data, 1)


def test_a_table_placed_up_from_a_paragraph_of_spaces_stands_at_its_top() -> None:
    # The paragraph of two spaces with its table 616 down, then put 616 up (kept unsigned) and at 0: a table
    # placed up stands at the paragraph's top, so the paragraph lays out as with the table at 0, its line below
    # the table; it does not push from four billion units down.
    def with_offset(offset: int) -> bytes:
        data = (FIXTURES / "pages_band_spaces_then_empty_paragraphs_then_band.hwpx").read_bytes()
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                payload = source.read(info.filename)
                if info.filename.startswith("Contents/section"):
                    root = etree.fromstring(payload)
                    next(root.iter(f"{HP}tbl")).find(f"{HP}pos").set("vertOffset", str(offset))
                    payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
                target.writestr(info, payload)
        return _without_caches(out.getvalue())

    up, top = estimate_pages(with_offset((1 << 32) - 616)), estimate_pages(with_offset(0))

    assert up.unsupported == top.unsupported == ()
    assert [[line.vertpos for line in lines] for lines in up.lines] == \
        [[line.vertpos for line in lines] for lines in top.lines]


def test_a_header_wrapped_square_with_room_beside_it_is_not_followed() -> None:
    # The exam header 3000 narrower: a line fits beside it, and the lines reaching it are not followed.
    out = io.BytesIO()
    data = (FIXTURES / "pages_exam_header_over_a_table_alone.hwpx").read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section"):
                root = etree.fromstring(payload)
                header = next(table for table in root.iter(f"{HP}tbl") if table.get("textWrap") == "SQUARE")
                size = header.find(f"{HP}sz")
                size.set("width", str(int(size.get("width")) - 3000))
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, payload)

    assert estimate_pages(out.getvalue()).unsupported == ("section 0: text beside an object placed on the paper",)


def test_a_line_reaching_a_picture_on_the_paper_with_room_beside_it_keeps_its_cached_place() -> None:
    # The picture's top 100 above the fifth line's foot: Hancom sets that line beside it, narrower, at the
    # same height. Keeping its cache, it is followed; without it, where it breaks is not.
    data = (FIXTURES / "pages_square_picture_on_paper_reaching_the_last_line.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 1)
    assert estimate_pages(_without_caches(data)).unsupported == (
        "section 0: text beside an object placed on the paper",)


@pytest.mark.parametrize(
    ("name", "pages"),
    [
        ("pages_square_picture_on_paper_lines_beside_it", 2),  # at the text's left, 800 below its top
        ("pages_square_picture_on_paper_lines_on_both_sides", 2),  # at its middle: two pieces a line
        ("pages_square_picture_on_paper_lines_beside_it_on_page_2", 5),  # anchored after a page break
    ],
)
def test_lines_keeping_their_caches_beside_a_picture_on_the_paper_stay_where_hancom_put_them(name: str,
                                                                                            pages: int) -> None:
    # A picture wrapped square from the paper's top with room beside it, long paragraphs flowing beside
    # it (the line of the paragraph before its anchor too): each line keeps its height and spacing there,
    # narrower. Without the caches, where the lines beside it break is not followed.
    data = (FIXTURES / f"{name}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, pages)
    assert estimate_pages(_without_caches(data)).unsupported == (
        "section 0: text beside an object placed on the paper",)


@pytest.mark.parametrize(("name", "pages"), [("pages_square_picture_staying_above_the_foot", 2),
                                             ("pages_square_picture_staying_457_past_the_foot", 2),
                                             ("pages_square_picture_staying_5000_past_the_foot", 2),
                                             ("pages_square_picture_staying_20000_past_the_foot", 3)])
def test_a_square_picture_not_flowing_with_the_text_stays_on_its_page_past_the_foot(name: str, pages: int) -> None:
    # A picture 20000 x 27112 wrapped square from its paragraph's top, text on both sides, set not to flow with
    # the text (flowWithText="0"), its foot 500 above the body's or 457, 5000, 20000 below it: it stays on its
    # page, the lines beside it in two pieces down to that page's foot, the lines after going on at the next
    # page's top at full width. Each line keeps its cache there.
    data = (FIXTURES / f"{name}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, pages)


def test_without_caches_lines_beside_a_square_picture_staying_past_the_foot_are_followed_on_its_page() -> None:
    # 457 past the foot, every line beside the picture stays on its page: laid out again at the pieces' widths,
    # they go where Hancom put them.
    data = (FIXTURES / "pages_square_picture_staying_457_past_the_foot.hwpx").read_bytes()
    _assert_like_hancom(estimate_pages(_without_caches(data)), data, 2)
    # 5000 or 20000 past it, text beside it goes on over the page end, where Hancom lays it out at full width: a
    # paragraph without its cache is not followed there.
    for name in ("pages_square_picture_staying_5000_past_the_foot", "pages_square_picture_staying_20000_past_the_foot"):
        data = (FIXTURES / f"{name}.hwpx").read_bytes()
        assert estimate_pages(_without_caches(data)).unsupported == (
            "section 0: a page break beside a square-wrapped or offset top-and-bottom object",)


def _with_empty_runs_in_cells(data: bytes) -> bytes:
    """*data* without line caches, each paragraph of a table cell starting with an empty run of character
    shape 0 (10 pt), as a paragraph written empty and given runs after."""

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(_without_caches(data))) as source, \
            zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section"):
                root = etree.fromstring(payload)
                for paragraph in root.iter(f"{HP}p"):
                    if any(ancestor.tag == f"{HP}tc" for ancestor in paragraph.iterancestors()):
                        run = etree.Element(f"{HP}run", {"charPrIDRef": "0"})
                        etree.SubElement(run, f"{HP}t")
                        paragraph.insert(0, run)
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, payload)
    return out.getvalue()


@pytest.mark.parametrize("name", ["pages_table_row_split_a_first_line_not_fitting",
                                  "pages_table_row_split_every_first_line_fitting"])
def test_an_empty_run_before_a_cells_text_takes_no_room(name: str) -> None:
    # Cells of 8 pt and 16 pt text in a row at the page end, each cell paragraph starting with an empty 10 pt
    # run: without the caches the cells' lines are as tall as their text, and the row splits where Hancom split
    # it, as when the paragraphs hold the text alone.
    data = (FIXTURES / f"{name}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(_with_empty_runs_in_cells(data)), data, HANCOM_PAGES[name])


@pytest.mark.parametrize(
    ("fixture", "pages"),
    [
        ("m2_corpus/public_official_table.hwpx", 5),       # merged rows
        ("m3_gongmun_gold/mpm_recruitment_notice.hwpx", 1),  # a nested table
    ],
)
def test_a_table_set_as_a_character_hancom_laid_out_keeps_its_saved_height(fixture: str, pages: int) -> None:
    # Hancom-made documents: every paragraph in the table keeps its layout cache.
    estimate = estimate_pages(FIXTURES.parent / fixture)

    assert estimate.unsupported == ()
    assert estimate.pages == pages


def test_a_drop_cap_takes_the_lines_beside_it() -> None:
    # The corpus's drop cap: wrapped square at its paragraph's left, the text on its right only. The
    # lines whose top is above its foot are narrower by its width and right outer margin.
    data = (FIXTURES.parent / "hwpxlib_corpus" / "error__20230809__test.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 1)
    _assert_like_hancom(estimate_pages(_without_caches(data)), data, 1)


def test_an_object_wrapped_square_mid_column_on_its_own_takes_no_line() -> None:
    # An OLE object wrapped square 9100 from its paragraph's left, text on both sides, and no text.
    data = (FIXTURES.parent / "hwpxlib_corpus" / "reader_writer__SimpleOLE.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 1)


def test_a_picture_on_the_paper_below_the_text_takes_no_line() -> None:
    # A picture wrapped square, placed 1855 below the body's top from the paper's, 235 from the text's
    # left: room for lines on its right, but the one line of its page ends above it.
    data = (FIXTURES.parent / "hwpxlib_corpus" / "reader_writer__SimplePicture.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 1)
    _assert_like_hancom(estimate_pages(_without_caches(data)), data, 1)


def test_the_cells_of_a_form_break_their_lines_like_hancom_without_caches() -> None:
    # A form whose cells hold runs of several sizes: without the caches every line, in the body and
    # below the tables, is where Hancom put it.
    data = (FIXTURES.parent / "m2_corpus" / "form_002.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 10)
    _assert_like_hancom(estimate_pages(_without_caches(data)), data, 10)


def test_the_evaluation_plan_form_lays_out_like_hancom_without_caches() -> None:
    # A form whose narrow cells hold bullet paragraphs, some ending in an empty run of a larger size: without
    # the caches every line, in the body and below the tables, is where Hancom put it.
    data = (FIXTURES.parent / "m105_evalplan" / "blank_form_3hak.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 15)
    _assert_like_hancom(estimate_pages(_without_caches(data)), data, 15)


@pytest.mark.parametrize("height", [str((1 << 32) - 633), str((1 << 32) - 1)])
def test_a_negative_cell_height_kept_unsigned_counts_as_none(height: str) -> None:
    # A 3x2 table whose row-2 cell was written with the height -633 kept unsigned (4294966663), saved by Hancom:
    # it gives the cell its top and bottom margins (282) and grows it to fit the text, one page. Written back
    # unsigned, the cell is not four billion tall: the estimate gives Hancom's page.
    data = (FIXTURES / "pages_cell_height_negative.hwpx").read_bytes()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "Contents/section0.xml":
                root = etree.fromstring(payload)
                cell = list(root.iter(f"{HP}tc"))[2]
                assert cell.find(f"{HP}cellSz").get("height") == "282"
                cell.find(f"{HP}cellSz").set("height", height)
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, payload)
    negative = out.getvalue()

    for estimate in (estimate_pages(data), estimate_pages(negative), estimate_pages(_without_caches(negative))):
        assert estimate.unsupported == ()
        assert estimate.pages == 1


@pytest.mark.parametrize("name", ["pages_table_with_cell_spacing", "pages_table_without_cell_spacing"])
def test_a_table_with_cell_spacing_lays_its_cells_out_at_their_own_widths(name: str) -> None:
    # A table 46196 wide: one cell over its three columns, then cells of 15000, 21000 and 9800 with a cell
    # spacing of 198 (10196 without it), the last holding ten "가" (9720), every cell declared 282 tall. With
    # the spacing the second row's cells add up to the first row's, and Hancom lays each cell out at its own
    # width: the ten characters on two lines (one line without the spacing). The height it saved is its rows',
    # each with the spacing above it, and the spacing below the last.
    doc = HwpxDocument.open(_without_caches((FIXTURES / f"{name}.hwpx").read_bytes()))
    table = next(doc.oxml.sections[0].element.iter(f"{HP}tbl"))
    rows = page_layout._rows(page_layout._Measure(getattr(doc, "_root")), table)
    spacing = int(table.get("cellSpacing"))

    assert [row.lines for row in rows] == [1, 2 if spacing else 1]
    assert sum(row.height for row in rows) + spacing == int(table.find(f"{HP}sz").get("height"))


def test_a_table_set_not_to_split_taller_than_a_page_takes_the_next_one() -> None:
    # 50 rows under its anchor line: it moves on to the next page, which holds nothing else, and the text
    # after it stays under its anchor line on the first page.
    data = (FIXTURES / "pages_table_not_split_taller_than_a_page.hwpx").read_bytes()

    for estimate in (estimate_pages(data), estimate_pages(_without_caches(data))):
        assert estimate.unsupported == ()
        assert estimate.pages == 2
        assert [[line.vertpos for line in lines] for lines in estimate.lines] == _hancom_lines(data)
        assert {line.page for lines in estimate.lines for line in lines} == {0}


def test_the_lines_around_a_nested_table_are_where_hancom_put_them() -> None:
    data = (FIXTURES.parent / "m3_gongmun_gold" / "mpm_recruitment_notice.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 1)


@pytest.mark.parametrize(("fixture", "followed"), [("pages_table_nested_top_and_bottom_alone", True),
                                                  ("pages_table_nested_two_top_and_bottom", False),
                                                  ("pages_table_nested_top_and_bottom_before_text", True),
                                                  ("pages_table_nested_among_text", True)])
def test_a_cell_holding_a_table_among_text_or_top_and_bottom_is_as_tall_as_hancom_drew_it(fixture: str,
                                                                                         followed: bool) -> None:
    # A table in a cell of a flowing table, placed top and bottom alone in its paragraph (the cell
    # reaches down to its foot) or before text (the text goes below it), or set as a character among
    # text: the lines of the cell's caches. Without the caches the estimate follows the cell when the
    # table is alone in its paragraph or before its text, as tall as its rows, and lays a table set as a
    # character among text out as in the body. Two tables 0 and 3000 down
    # in one paragraph put its empty line below the second (not beside the first): not followed without
    # the caches.
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 1)
    if followed:
        _assert_like_hancom(estimate_pages(_without_caches(data)), data, 1)
    else:
        assert estimate_pages(_without_caches(data)).unsupported == ("section 0: a nested table",)


@pytest.mark.parametrize("fixture", ["pages_table_vertical_cells_over_the_page_end",
                                     "pages_table_vertical_cell_of_all_rows_over_the_page_end",
                                     "pages_table_vertical_cell_in_every_row_over_the_page_end",
                                     "pages_table_vertical_cells_taller_than_a_page"])
def test_a_table_holding_vertical_text_moves_to_the_next_page_whole(fixture: str) -> None:
    # pages_table_merged_cells_over_the_page_end with vertical text in its first column (cells of four rows
    # merged, one of all twenty, or one in every row), and one of forty rows taller than a page: Hancom does
    # not split it but moves it whole to the next page's top (running past the page's foot when taller), the
    # anchor's line and the paragraphs after it staying on the first page.
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()
    hancom = _hancom_lines(data)

    for document in (data, _without_caches(data)):
        estimate = estimate_pages(document)
        estimated = [[line.vertpos for line in lines] for lines in estimate.lines]
        assert estimate.unsupported == ()
        assert estimate.pages == 2
        assert [mine for mine, theirs in zip(estimated, hancom) if theirs] == [theirs for theirs in hancom if theirs]
        assert {line.page for lines in estimate.lines for line in lines} == {0}


def test_a_negative_outer_margin_counts_as_none() -> None:
    # A table over two pages whose outer margins were -500 (kept as unsigned 32-bit numbers): Hancom laid it
    # out as one without them and saved them as 0. With the margins back at -500 the estimate is the same.
    data = (FIXTURES / "pages_table_outer_margins_saved_from_negative.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(_with_outer_margins(data, (-500) & 0xFFFFFFFF)), data, 2)


@pytest.mark.parametrize(("fixture", "pages"), [("pages_columns_unequal_narrow_first", 4),
                                               ("pages_columns_unequal_wide_first", 4),
                                               ("pages_columns_unequal_three", 4),
                                               ("pages_columns_unequal_column_break", 5)])
def test_columns_of_unequal_width_break_their_lines_at_each_column_width(fixture: str, pages: int) -> None:
    # Two columns, the first half as wide as the second or twice as wide, three of unequal width, and two
    # with a column break, paragraphs of several lines going on from one column into the next. With the
    # caches the lines flow down the columns as Hancom put them. Without them the lines a column holds
    # break at that column's width, and a paragraph going on into a column of another width breaks its
    # rest there again, from the first character the column holds: where Hancom broke them.
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, pages)
    _assert_like_hancom(estimate_pages(_without_caches(data)), data, pages)


def test_columns_of_unequal_width_take_their_share_of_the_text_width_rounded() -> None:
    # hp:colSz 6552 + 873, 12234 + 873 and 12236 of 32768 over a text width of 42520 (8501.95, 15874.9 and
    # 15877.5): Hancom's lines in the three columns are 8502, 15875 and 15878 wide.
    with zipfile.ZipFile(FIXTURES / "pages_columns_unequal_three.hwpx") as package:
        section = etree.fromstring(package.read("Contents/section0.xml"))

    assert page_layout._columns(section, 42520) == (3, 8502, (8502, 15875, 15878), 0)  # no gap: unequal widths
    assert {int(seg.get("horzsize")) for seg in section.iter(f"{HP}lineseg")} == {8502, 15875, 15878}


def test_a_column_area_starts_at_a_definition_and_at_a_column_break_in_balanced_columns() -> None:
    # A paragraph's first column definition starts an area (behind its text: the columns before go on), and so
    # does a column break in balanced columns; the section's own definition, next to hp:secPr, starts none.
    section = etree.fromstring(
        f'<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="{HP[1:-1]}">'
        '<hp:p><hp:run><hp:secPr/><hp:ctrl><hp:colPr colCount="1"/></hp:ctrl></hp:run></hp:p>'
        '<hp:p><hp:run><hp:t>text</hp:t><hp:ctrl><hp:colPr colCount="2"/></hp:ctrl>'
        '<hp:ctrl><hp:colPr colCount="3"/></hp:ctrl></hp:run></hp:p>'
        '<hp:p><hp:run><hp:ctrl><hp:colPr colCount="2" type="BALANCED_NEWSPAPER"/></hp:ctrl><hp:t>a</hp:t></hp:run></hp:p>'
        '<hp:p columnBreak="1"><hp:run><hp:t>b</hp:t></hp:run></hp:p>'
        '</hs:sec>'
    )

    areas = page_layout._column_areas(section)

    assert [(index, None if found is None else found.get("colCount")) for index, found in areas] == \
        [(1, None), (2, "2"), (3, "2")]


def test_the_multi_column_sample_breaks_its_lines_at_each_column_width_without_caches() -> None:
    # hwpxlib's MultiColumn sample, columns of unequal width: two pages, with its caches or without them.
    data = (Path(__file__).parent / "fixtures" / "hwpxlib_corpus" / "reader_writer__MultiColumn.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 2)
    _assert_like_hancom(estimate_pages(_without_caches(data)), data, 2)


def test_columns_of_the_same_size_written_as_true_are_of_the_same_size() -> None:
    # hp:colPr@sameSz is an xs:boolean: "true" is "1" (Hancom writes "1"; other writers "true").
    document = HwpxDocument.new()
    document.page.set_columns(2)
    for number in range(80):
        document.add_paragraph(f"{number} 단 나누기 문단입니다")
    data = document.to_bytes()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section"):
                payload = re.sub(rb'(colCount="2"[^>]*)sameSz="1"', rb'\1sameSz="true"', payload)
            target.writestr(info, payload)
    assert b'sameSz="true"' in zipfile.ZipFile(out).read("Contents/section0.xml")

    ones, trues = estimate_pages(data), estimate_pages(out.getvalue())

    assert (trues.unsupported, trues.pages, trues.lines) == ((), ones.pages, ones.lines)


def test_a_footnote_in_a_paragraph_without_a_cache_in_columns_of_unequal_width_is_not_followed() -> None:
    document = HwpxDocument.new()
    document.set_columns(2, same_size=False, column_widths=[(10632, 873), (21263, 0)])
    document.notes.add_footnote("각주", document.add_paragraph("각주가 달린 문단"))

    assert estimate_pages(document).unsupported == (
        "section 0: objects, composed characters, ruby text or footnotes in a paragraph without a layout cache "
        "in columns of unequal width",)


@pytest.mark.parametrize(("fixture", "followed"), [("pages_table_row_split_in_first_paragraph", True),
                                                  ("pages_table_row_split_after_nested_table", True),
                                                  ("pages_table_row_split_moves_nested_table", True),
                                                  ("pages_table_row_split_moves_nested_table_above_text", True)])
def test_a_row_holding_a_nested_table_split_over_a_page_splits_where_hancom_split_it(fixture: str,
                                                                                   followed: bool) -> None:
    # A flowing table (split by cell) whose row 1 holds, in one cell, six lines, a 2x2 table placed top and
    # bottom (alone in its paragraph, or above a line of text) and six lines more, going on over the page
    # end among the first six lines, after the nested table, or at it (the nested table goes on to the
    # next page, with the text below it). Hancom's caches of the cell start over at the next page's top.
    # Without the caches the estimate splits the row there too: the table is one line, as tall as its
    # rows, and the text after it goes on below its foot.
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 2)
    if followed:
        _assert_like_hancom(estimate_pages(_without_caches(data)), data, 2)
    else:
        assert estimate_pages(_without_caches(data)).unsupported == ("section 0: a nested table",)


@pytest.mark.parametrize("fixture", ["pages_table_nested_square_alone", "pages_table_nested_square_beside_text"])
def test_a_cell_holding_a_table_wrapped_square_is_as_tall_as_hancom_drew_it(fixture: str) -> None:
    # A table wrapped square at the left of a paragraph in a cell of a flowing table, alone (the cell
    # reaches down to its foot) or beside text (the lines beside it are narrower, the rest go below
    # it): the lines of the cell's caches. Without the caches the estimate lays the lines out beside the
    # table, as it does beside a picture so placed.
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 1)
    _assert_like_hancom(estimate_pages(_without_caches(data)), data, 1)


@pytest.mark.parametrize(("fixture", "pages"), [("pages_table_nested_top_and_bottom_among_text", 2),
                                                ("pages_table_nested_square_among_text", 1),
                                                ("pages_table_nested_behind_text_among_text", 1),
                                                ("pages_table_nested_captioned_among_text", 2)])
def test_a_table_among_the_text_of_a_cell_stands_at_the_top_of_its_line(fixture: str, pages: int) -> None:
    # Tables in cells of flowing tables, each in a paragraph of no text, a line or two lines before it and
    # after it (nine cells a file; in the captioned file a caption above or below a table of one or four
    # rows, two kinds of text). Without the caches Hancom stands such a table at the top of the line its
    # control falls on (or of the paragraph, on its first line), its offset below that: placed top and bottom
    # that line and the rest go below it (as a picture so placed; the caption with it), wrapped square the
    # lines beside it are narrower, in the paragraph and the next ones, and behind the text it pushes no line
    # but the cell reaches its foot. The first file's last table goes on to the next page with the line below
    # it (that line does not fit, the table would).
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, pages)
    _assert_like_hancom(estimate_pages(_without_caches(data)), data, pages)


@pytest.mark.parametrize(("fixture", "pages"), [("pages_table_nested_captioned_before_text", 2),
                                                ("pages_table_nested_paragraph_shapes_around_text", 1)])
def test_a_captioned_table_in_a_cell_takes_its_caption_with_it(fixture: str, pages: int) -> None:
    # Tables of one or four rows placed top and bottom before a line or two of text (the last one going over
    # the page end, split between its rows), and cells of an empty paragraph holding such a table with a caption
    # above or below it, a paragraph with spacing before, margins or a 200 % line spacing around one, two such
    # paragraphs: the caption's lines and gap stand with the table, the lines below it. Without the caches the
    # estimate counted the table alone before, its rows only.
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(_without_caches(data)), data, pages)


def test_a_table_among_the_text_of_a_cell_splits_between_its_rows_over_a_page_end() -> None:
    # The same tables placed top and bottom 600 down, a line of text after each cell: the last but one goes
    # over the page end through its table, whose first row ends 101 above the foot or higher: Hancom splits the
    # table between its rows, the rest at the next page's top, the line below it under the rest, and saves the
    # table as tall as that rest. Without the caches the estimate splits it there too; with them, a table not
    # as tall as its rows is not followed.
    data = (FIXTURES / "pages_table_nested_split_at_a_table_among_text.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(_without_caches(data)), data, 2)
    assert estimate_pages(data).unsupported == ("section 0: a table in a cell not as tall as its rows (split over a "
                                                "page end)",)


@pytest.mark.parametrize("fixture", ["pages_table_nested_split_with_a_caption_among_text",
                                     "pages_table_nested_moved_alone_among_text"])
def test_a_table_among_the_text_of_a_cell_at_a_page_end_goes_on_as_hancom_moves_it(fixture: str) -> None:
    # One cell of two lines, a table of three rows placed top and bottom (400 down, a caption below it; or
    # right at the line's top) and two lines more, its row at the page end. With the caption below it the
    # rows that stay end 101 above the foot with room for the caption: two of them, the third, the caption
    # and the lines below it go on. Without one, when its first row does not end so high, the line its control
    # falls on stays where it is and the table goes on alone to the next page's top, the next line below it.
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(_without_caches(data)), data, 2)


@pytest.mark.parametrize(("fixture", "followed"), [("pages_table_nested_top_and_bottom_placed_up_alone", True),
                                                  ("pages_table_nested_square_placed_up_alone", True)])
def test_a_table_placed_up_from_its_paragraph_in_a_cell_stands_at_the_paragraph_top(fixture: str,
                                                                                  followed: bool) -> None:
    # A table alone in a cell's paragraph after two lines, placed top and bottom or wrapped square 1000
    # up from the paragraph's top (a negative offset, kept as an unsigned number): Hancom puts it at the
    # paragraph's top, and the cell reaches down to its foot from there; without the caches as well.
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 1)
    if followed:
        _assert_like_hancom(estimate_pages(_without_caches(data)), data, 1)
    else:
        assert estimate_pages(_without_caches(data)).unsupported == ("section 0: a nested table",)


def test_the_estimate_reads_a_paragraphs_tab_definition() -> None:
    # A paragraph whose tab definition sets a stop of its own takes it.
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가가가\t가가")
    doc.styles.apply_paragraph_format(paragraphs=[paragraph], tab_stops=[{"pos_mm": 50, "type": "RIGHT"}])
    root = HwpxDocument.open(io.BytesIO(doc.to_bytes()))._root
    element = root.sections[0].element.findall(f"{HP}p")[-1]

    style = page_layout._Measure(root).style(element.get("paraPrIDRef"), ["0"])

    assert style.tab_stops == ((14173, "RIGHT"),)


def test_the_lines_a_cell_splits_between_add_up_to_its_height() -> None:
    # A row of several paragraphs splits between their lines, one height and advance each: they add up to
    # the height the cell stacks the paragraphs to, a paragraph mixing character sizes included (each line
    # as tall as its largest character).
    root = HwpxDocument.open(io.BytesIO((FIXTURES / "pages_mixed_sizes_percent.hwpx").read_bytes()))._root
    measure = page_layout._Measure(root)
    paragraphs = root.sections[0].element.findall(f"{HP}p")

    lines = measure.stack_lines(paragraphs, 42520, caches=False)

    assert len({height for height, _ in lines}) > 1
    assert page_layout._lines_height(lines, ()) == measure.stack(paragraphs, 42520, caches=False)[0]


def test_a_row_taller_than_its_lines_goes_on_below_them_over_a_page_end() -> None:
    # A row split between its lines whose lines all fit above the page's foot, while the row reaches lower
    # (a cell taller than the lines it splits between): what is left goes on to the next page as room under
    # its text does, or is dropped when no taller than a line.
    row = page_layout._Row(5000, 2, 1600, 1000, 282, False, metrics=((1000, 1600), (1000, 1600)), first=1000)

    assert page_layout._flow_row("CELL", row, 0, 7000, 10000, 0) == (1, 5000 - (10000 - 101 - 7000))
    assert page_layout._flow_row("CELL", row, 0, 6000, 10000, 0) == (0, 10000)


def test_paragraphs_of_several_character_sizes_hancom_laid_out_follow_their_cached_lines() -> None:
    # A Hancom-made document of three sections whose paragraphs mix character sizes: each line is as
    # tall and as far apart as its layout cache says.
    data = (FIXTURES.parent / "hwpxlib_corpus" / "error__20230728__test.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 39)


def test_another_document_of_mixed_character_sizes_has_hancoms_page_count() -> None:
    estimate = estimate_pages(FIXTURES.parent / "hwpxlib_corpus" / "error__20240626__no_manifest.hwpx")

    assert estimate.unsupported == ()
    assert estimate.pages == 4


def _with_empty_first_runs(data: bytes) -> bytes:
    """Each paragraph starting with an empty run of the default character shape (10 pt), as a paragraph
    python-hwpx made and then added runs to does; Hancom drops such a run when it saves."""

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section"):
                root = etree.fromstring(payload)
                for paragraph in root.iter(f"{HP}p"):
                    first = paragraph.find(f"{HP}run")
                    if first is not None and first.get("charPrIDRef") != "0":
                        empty = etree.Element(f"{HP}run", charPrIDRef="0")
                        etree.SubElement(empty, f"{HP}t")
                        first.addprevious(empty)
                payload = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            target.writestr(info, payload)
    return out.getvalue()


def test_an_empty_run_takes_no_room_and_gives_no_character_shape() -> None:
    # 12 pt and 30 pt runs of 바탕 after an empty 10 pt 함초롬바탕 run: the lines are Hancom's.
    data = (FIXTURES / "pages_mixed_sizes_fixed.hwpx").read_bytes()

    estimate = estimate_pages(_without_caches(_with_empty_first_runs(data)))

    _assert_like_hancom(estimate, data, HANCOM_PAGES["pages_mixed_sizes_fixed"])


def _flowing_table_after(paragraphs: int, rows: int) -> tuple[HwpxDocument, object]:
    document = HwpxDocument.new()
    for index in range(paragraphs):
        document.add_paragraph(f"문단 {index}")
    table = document.add_paragraph("").add_table(rows, 2)
    table.set_treat_as_char(False)
    table.element.set("pageBreak", "CELL")
    for row in range(rows):
        for column in range(2):
            table.set_cell_text(row, column, "칸")
    return document, table


def test_a_merged_cell_declared_taller_than_two_pages_is_cut_at_each_page_end() -> None:
    # After 38 lines, a flowing table of 6 rows whose cell merged over rows 1-4 is declared 150000 tall, laid
    # out and saved by Hancom: the cell's room is cut 101 above each page's foot and the rest goes on, page
    # after page, the last row ending the table (and the document) on page 4. No line of text is on that
    # page, so the pages are checked here rather than in HANCOM_PAGES.
    data = (FIXTURES / "pages_joined_rows_over_pages_declared_150000.hwpx").read_bytes()
    hancom = _hancom_lines(data)

    for source in (data, _without_caches(data)):
        estimate = estimate_pages(source)
        estimated = [[line.vertpos for line in lines] for lines in estimate.lines]

        assert (estimate.unsupported, estimate.pages) == ((), 4)
        assert len(estimated) == len(hancom)
        assert [mine for mine, theirs in zip(estimated, hancom) if theirs] == [theirs for theirs in hancom if theirs]


@pytest.mark.parametrize(("height", "rest"), [(20000, 13221), (8029, 0), (8061, 0), (8062, 1283), (8079, 1300)])
def test_a_flowing_row_taller_than_its_text_is_cut_just_above_the_page_foot(height: int, rest: int) -> None:
    # The row starts 6880 above the foot: Hancom cuts it 101 above the foot and carries the rest to the
    # next page, unless the rest is 1282 or less (then the next row starts that page). The fixtures
    # pages_table_flow_tall_row_rest_1282 and _1283 are rows placed the same way, saved by Hancom.
    document, table = _flowing_table_after(35, 3)
    for cell in table.element.iter(f"{HP}tc"):
        if cell.find(f"{HP}cellAddr").get("rowAddr") == "1":
            cell.find(f"{HP}cellSz").set("height", str(height))
    document.add_paragraph("표 뒤")

    estimate = estimate_pages(document)

    assert estimate.unsupported == ()
    assert estimate.lines[-1] == (EstimatedLine(page=1, column=0, vertpos=rest + 1282),)


def test_a_flowing_table_whose_anchor_line_has_no_room_starts_on_the_next_page() -> None:
    document, _ = _flowing_table_after(40, 3)  # the anchor line would start 65600, 1000 tall
    document.add_paragraph("표 뒤")

    estimate = estimate_pages(document)

    assert estimate.lines[-2] == (EstimatedLine(page=1, column=0, vertpos=0),)
    assert estimate.lines[-1] == (EstimatedLine(page=1, column=0, vertpos=3 * 1282),)


def test_a_table_whose_row_addresses_skip_is_estimated_without_the_missing_rows() -> None:
    # Documents edited by other tools can number their rows with gaps (row 2 saved as row 5).
    document = HwpxDocument.new()
    table = document.add_table(3, 2)
    for cell in table.element.iter(f"{HP}tc"):
        address = cell.find(f"{HP}cellAddr")
        if address.get("rowAddr") == "2":
            address.set("rowAddr", "5")

    estimate = estimate_pages(document)

    assert estimate.unsupported == ()
    assert estimate.pages == 1


def test_a_page_break_in_a_row_holding_a_table_beside_a_taller_cell_is_unsupported() -> None:
    # Row 1's cell (1, 0) holds more lines than the cell beside it holding a table; the page end falls
    # among them.
    document, table = _flowing_table_after(38, 3)
    table.cell(1, 1).add_table(2, 2, width=18000)
    table.set_cell_text(1, 0, "칸 글 " * 150)

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.unsupported == ("section 0: a page break in a flowing table row holding a table",)


@pytest.mark.parametrize(
    "name",
    [
        "pages_picture_square_past_the_page_foot",  # its paragraph's three lines the page's last
        "pages_picture_square_past_the_page_foot_mid_paragraph",  # its first line the page's last
        "pages_table_square_past_the_page_foot",  # a table wrapped square alone in its paragraph
    ],
)
def test_a_square_object_past_the_page_foot_goes_on_at_the_next_page(name: str) -> None:
    # A picture wrapped square from its paragraph's top, 8000 tall, its band past the body's foot: Hancom
    # sets it alone at the next page's top, the lines beside it there narrower and the lines left above the
    # foot as wide as the column. A table wrapped square is split over the page end instead, its band going
    # on at the next page's top as tall as what is left of it. With the caches the lines stay where the
    # caches put them; without them they are broken again beside it there.
    data = (FIXTURES / f"{name}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 2)
    _assert_like_hancom(estimate_pages(_without_caches(data)), data, 2)


def test_a_top_and_bottom_table_not_split_offset_past_the_page_foot_is_unsupported() -> None:
    document, table = _flowing_table_after(38, 3)
    table.element.set("pageBreak", "NONE")
    table.element.find(f"{HP}pos").set("vertOffset", "3000")
    document.paragraphs[-1].add_run("앵커 문단 글")

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.unsupported == (
        "section 0: a square-wrapped or offset top-and-bottom object past the page foot",)


def test_ruby_text_spaced_otherwise_than_in_percent_is_not_followed_without_a_cache() -> None:
    # A line holding ruby text is spaced from its own height in percent; the estimate does not follow
    # another line spacing there.
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("앞 글 ")
    document.shapes.add_dutmal("본문", "덧말", paragraph=paragraph)
    shape = next(element for element in document.parts.headers[0].element.iter(f"{HH}paraPr")
                 if element.get("id") == paragraph.element.get("paraPrIDRef"))
    for spacing in shape.iter(f"{HH}lineSpacing"):
        spacing.set("type", "FIXED")
        spacing.set("value", "2000")

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.unsupported == ("section 0: ruby text in a paragraph with line spacing other than percent",)


def test_lines_of_two_columns_are_in_columns() -> None:
    estimate = estimate_pages(FIXTURES / "pages_columns_2_break.hwpx")

    assert {line.column for lines in estimate.lines for line in lines} == {0, 1}


def test_a_document_a_path_and_bytes_give_the_same_estimate() -> None:
    path = FIXTURES / "pages_footnotes_6.hwpx"

    assert estimate_pages(HwpxDocument.open(path)) == estimate_pages(path) == estimate_pages(path.read_bytes())


def test_a_new_document_is_one_page() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("첫 문단")

    estimate = estimate_pages(document)

    assert estimate.pages == 1
    assert estimate.lines[-1] == (EstimatedLine(page=0, column=0, vertpos=1600),)


def _with_object_on_the_paper(document: HwpxDocument) -> None:
    # A rectangle placed top and bottom 15000 below the paper's top: 5080 to 13080 in the body.
    paragraph = document.add_paragraph("종이 기준 개체 곁 글")
    rectangle = document.shapes.add_rectangle(20000, 8000, treat_as_char=True, paragraph=paragraph).element
    rectangle.set("textWrap", "TOP_AND_BOTTOM")
    for key, value in (("treatAsChar", "0"), ("vertRelTo", "PAPER"), ("horzRelTo", "PAPER"),
                       ("vertAlign", "TOP"), ("vertOffset", "15000")):
        rectangle.find(f"{HP}pos").set(key, value)


def test_a_flowing_table_reaching_an_object_placed_on_the_paper_is_unsupported() -> None:
    document, _ = _flowing_table_after(1, 8)  # from 3200 down past the object's top
    _with_object_on_the_paper(document)

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.unsupported == ("section 0: a table on a page with an object placed on the paper",)


def test_a_flowing_table_clear_of_an_object_placed_on_the_paper_is_followed() -> None:
    # The line before the table reaches the object and goes below it; the table flows under that line,
    # clear of the object.
    document, _ = _flowing_table_after(3, 3)
    _with_object_on_the_paper(document)

    estimate = estimate_pages(document)

    assert estimate.unsupported == ()
    assert estimate.pages == 1
    assert [lines[0].vertpos for lines in estimate.lines[3:5]] == [13080, 14680]


# Endnotes at the document's end (one to eight, of one or more lines), laid out and saved by Hancom: below the
# foot of the text's last line the note area's 850 above the separator and 567 below it, then the notes' lines,
# going on over the page end; after a page whose footnotes take room, on the next page. The pages the
# endnotes take may hold no body line.
ENDNOTE_PAGES = {
    "pages_endnotes_after_the_text": 1,
    "pages_endnotes_over_the_page_end": 2,
    "pages_endnotes_after_a_page_with_a_footnote": 2,
    "pages_endnotes_after_two_pages": 2,
}


@pytest.mark.parametrize("name", sorted(ENDNOTE_PAGES))
def test_endnotes_follow_the_documents_text(name: str) -> None:
    data = (FIXTURES / f"{name}.hwpx").read_bytes()
    hancom = _hancom_lines(data)

    for source in (data, _without_caches(data)):
        estimate = estimate_pages(source)

        assert (estimate.unsupported, estimate.pages) == ((), ENDNOTE_PAGES[name])
        assert [[line.vertpos for line in lines] for lines in estimate.lines] == hancom


# Endnotes placed at each section's end (END_OF_SECTION), laid out and saved by Hancom: a section's notes follow its
# own text, before the next section's page. Endnotes right beneath the text (beneathText, as here) are laid out the
# same way.
def test_endnotes_at_each_sections_end_follow_that_sections_text() -> None:
    data = (FIXTURES / "pages_endnotes_at_each_sections_end.hwpx").read_bytes()
    hancom = _hancom_lines(data)

    for source in (data, _without_caches(data)):
        estimate = estimate_pages(source)

        assert (estimate.unsupported, estimate.pages) == ((), 3)
        assert [[line.vertpos for line in lines] for lines in estimate.lines] == hancom


# One-line endnotes, each anchored in a paragraph of its own, as Hancom stacked them: 900 apart, as tall as their
# text, the line spacing below a note's last line not counted. Seventeen end 11 above the body's foot (one page),
# ten 89 below it (the last one goes on to a second page). Notes of two lines keep the spacing between their lines.
NOTE_LINE_PAGES = {
    "pages_endnotes_of_one_line_at_the_page_foot": 1,
    "pages_endnotes_of_one_line_past_the_page_foot": 2,
    "pages_endnotes_of_two_lines": 2,
}


@pytest.mark.parametrize("name", sorted(NOTE_LINE_PAGES))
def test_a_notes_last_line_takes_no_line_spacing(name: str) -> None:
    data = (FIXTURES / f"{name}.hwpx").read_bytes()
    hancom = _hancom_lines(data)

    for source in (data, _without_caches(data)):
        estimate = estimate_pages(source)

        assert (estimate.unsupported, estimate.pages) == ((), NOTE_LINE_PAGES[name])
        assert [[line.vertpos for line in lines] for lines in estimate.lines] == hancom


def test_endnotes_placed_otherwise_are_unsupported() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    document.notes.add_endnote("미주", paragraph)
    settings = next(document.sections[0].element.iter(f"{HP}endNotePr"))
    settings.find(f"{HP}placement").set("place", "SOMEWHERE_ELSE")

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.unsupported == (
        "section 0: endnotes placed otherwise than at the document's or the section's end",)


# Footnotes right beneath the text (beneathText="1"), laid out and saved by Hancom over five pages with page breaks
# before, paragraphs kept with the next and long notes going on over page ends: the body's lines go where they
# would with the notes at the page's foot.
def test_footnotes_beneath_the_text_take_the_room_they_take_at_the_foot() -> None:
    data = (FIXTURES / "pages_footnotes_beneath_the_text.hwpx").read_bytes()
    hancom = _hancom_lines(data)

    for source in (data, _without_caches(data)):
        estimate = estimate_pages(source)

        assert (estimate.unsupported, estimate.pages) == ((), 5)
        assert [[line.vertpos for line in lines] for lines in estimate.lines] == hancom


# A line grid (hp:grid@lineGrid), laid out and saved by Hancom: in a paragraph snapping to it (snapToGrid), each
# line's height and advance and the paragraph's spacing before and after take whole steps, rounded up, and the
# first line goes to the next step at or below where it would go; a line stays on its page while its top and
# rounded height are above the body's foot. A paragraph not snapping to it keeps its own spacing.
LINE_GRID_PAGES = {
    "pages_line_grid": 5,
    "pages_line_grid_partly_snapped": 3,
}


@pytest.mark.parametrize("name", sorted(LINE_GRID_PAGES))
def test_lines_on_a_line_grid(name: str) -> None:
    data = (FIXTURES / f"{name}.hwpx").read_bytes()
    hancom = _hancom_lines(data)

    for source in (data, _without_caches(data)):
        estimate = estimate_pages(source)

        assert (estimate.unsupported, estimate.pages) == ((), LINE_GRID_PAGES[name])
        assert [[line.vertpos for line in lines] for lines in estimate.lines] == hancom


def test_a_character_grid_is_followed_through_layout_caches_only() -> None:
    # A character grid (a manuscript paper's here) widens each character to whole steps: a paragraph keeping
    # Hancom's layout cache keeps its lines; without the caches the estimate does not break the lines so.
    data = (FIXTURES / "pages_character_grid.hwpx").read_bytes()

    estimate = estimate_pages(data)

    assert (estimate.unsupported, estimate.pages) == ((), 5)
    assert [[line.vertpos for line in lines] for lines in estimate.lines] == _hancom_lines(data)
    assert estimate_pages(_without_caches(data)).unsupported == (
        "section 0: a character grid in a paragraph without a layout cache",)


def test_a_line_grid_with_a_table_is_unsupported() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("격자 위 글")
    document.add_table(2, 2)
    next(document.sections[0].element.iter(f"{HP}grid")).set("lineGrid", "2000")

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.unsupported == (
        "section 0: a line or character grid in columns or with objects, tables or notes",)


def _one_section(data: bytes, settings_first: bool = True) -> HwpxDocument:
    """The document Hancom saved as two sections, as one section holding the second's settings in the paragraph it
    starts with (Hancom saves a later paragraph holding section settings as a section of its own); without
    *settings_first*, the first paragraph holds none (Hancom saved the paragraphs before with its default page)."""

    document = HwpxDocument.open(data)
    first, second = (section.element for section in document.sections)
    for paragraph in second.findall(f"{HP}p"):
        first.append(paragraph)
    document.remove_section(1)
    if not settings_first:
        run = first.find(f"{HP}p/{HP}run")
        for child in list(run):
            if child.tag == f"{HP}secPr" or child.tag == f"{HP}ctrl" and child.find(f"{HP}colPr") is not None:
                run.remove(child)
    return document


# Section settings in a later paragraph, laid out and saved by Hancom (as two sections): a new section on a new
# page with those settings -- here a landscape page of two columns after A4 --, and, when the first paragraph holds
# none, the paragraphs before on Hancom's default A4 page (59528 x 84188) -- here before a B5 page.
@pytest.mark.parametrize(("name", "settings_first", "pages"), [
    ("pages_section_settings_in_a_later_paragraph", True, 4),
    ("pages_section_settings_after_paragraphs_without", False, 2),
])
def test_section_settings_in_a_later_paragraph_start_a_section(name: str, settings_first: bool, pages: int) -> None:
    data = (FIXTURES / f"{name}.hwpx").read_bytes()
    hancom = _hancom_lines(data)

    for source in (data, _without_caches(data)):
        document = _one_section(source, settings_first)
        assert len(document.sections) == 1

        estimate = estimate_pages(document)

        assert (estimate.unsupported, estimate.pages) == ((), pages)
        assert [[line.vertpos for line in lines] for lines in estimate.lines] == hancom


def test_section_settings_deeper_in_a_later_paragraph_are_unsupported() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    table = document.add_table(1, 1)
    settings = copy.deepcopy(next(document.sections[0].element.iter(f"{HP}secPr")))
    next(table.element.iter(f"{HP}run")).insert(0, settings)

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.unsupported == ("section 0: section settings (hp:secPr) after the first paragraph",)


@pytest.mark.parametrize("mode", ["CELL", "TABLE"])
@pytest.mark.parametrize("top_margin", [0, 200])
def test_a_repeated_header_taller_than_the_remaining_half_page_moves_whole(mode: str, top_margin: int) -> None:
    from hwpx.layout.pages import _FlowTable, _Row, _flow_table, _starts_later

    header = _Row(height=6000, lines=6, pitch=1000, size=1000, margins=0, header=True)
    body = _Row(height=1000, lines=1, pitch=1000, size=1000, margins=0, header=False)
    table = _FlowTable([header, body], mode, True, (top_margin, 0), cut=0)

    assert _starts_later(table, 5000, 10000)
    assert _flow_table(table, 0, 5000, 10000) == (1, top_margin + 7000)
    assert not _starts_later(table, top_margin, 10000)
    assert _flow_table(table, 0, top_margin, 10000) == (0, top_margin + 7000)
    assert not _starts_later(table, 4000, 10000)
    assert _flow_table(table, 0, 4000, 10000) == (1, top_margin + 7000)


def _without_header(data: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            if item.filename == "Contents/header.xml":
                continue
            payload = src.read(item.filename)
            if item.filename == "Contents/content.hpf":
                payload = re.sub(rb"<opf:item [^>]*href=\"Contents/header.xml\"[^>]*/>", b"", payload)
            dst.writestr(item, payload)
    return out.getvalue()


def test_a_document_without_a_header_part_is_left_unsupported() -> None:
    # The paragraph and character shapes every paragraph names live in the header part; without it there is
    # nothing to lay the text out by, so the estimate says so instead of failing.
    document = HwpxDocument.new()
    document.add_paragraph("머리 정보가 없는 문서")
    data = _without_header(document.to_bytes())

    estimate = estimate_pages(data)

    assert estimate.pages is None and estimate.lines == ()
    assert estimate.unsupported == ("a document without a header part (Contents/header.xml)",)
    from hwpx.layout.line_cache import write_line_caches
    report = write_line_caches(HwpxDocument.open(io.BytesIO(data)))
    assert report.written == 0 and report.unsupported == estimate.unsupported


def test_a_paragraph_its_shape_squeezes_takes_one_line() -> None:
    # Paragraphs a line and a half to two and a half lines long, their shape's lineWrap BREAK, KEEP or SQUEEZE,
    # laid out and saved by Hancom: a squeezed one is pressed onto one line, a kept one breaks as BREAK does.
    data = (FIXTURES / "line_cache_squeezed.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(_without_caches(data)), data, 3)


def test_a_split_merged_cell_drops_its_first_paragraph_lead_after_consuming_a_line() -> None:
    # One fixed-pitch paragraph over seven pages: only its first part is spaced 200 before.
    cell = page_layout._Row(30200, 30, 1000, 1000, 0, False, first=1200)
    rows = [page_layout._Row(15100, 0, 1000, 1000, 0, False, joined=True),
            page_layout._Row(15100, 0, 1000, 1000, 0, False, merged=True)]
    table = page_layout._FlowTable(rows, "CELL", False, (0, 0), cells=((0, 2, cell),), cut=0)

    assert page_layout._flow_table(table, 0, 0, 5000) == (6, 1000)


def test_a_split_merged_cell_keeps_its_first_lead_when_no_line_was_consumed() -> None:
    cell = page_layout._Row(1200, 1, 1000, 1000, 0, False, first=1200)
    rows = [page_layout._Row(600, 0, 1000, 1000, 0, False, joined=True),
            page_layout._Row(600, 0, 1000, 1000, 0, False, merged=True)]
    table = page_layout._FlowTable(rows, "CELL", False, (0, 0), cells=((0, 2, cell),), cut=0)

    _, _, continued = page_layout._block_rest(table, 0, 1, 4000, 5000)

    assert len(continued) == 1
    assert continued[0][2].lines == 1
    assert continued[0][2].first == 1200
    assert page_layout._flow_table(table, 0, 4000, 5000) == (1, 1200)


@pytest.mark.parametrize("characters_before", [1, 35])
def test_a_note_in_a_table_among_text_is_left_for_hancom(characters_before: int) -> None:
    # Reuse Hancom's table-note fixture at a page boundary. The object can wrap after its preceding text, so
    # text-only line starts cannot locate its note. Refuse this combination until anchoring follows the object.
    document = HwpxDocument.open(_without_caches((FIXTURES / "pages_footnotes_in_table_cells.hwpx").read_bytes()))
    root = document.oxml
    paragraph = next(paragraph for paragraph in root.sections[0].element.findall(f"{HP}p")
                     if any(table.find(f"{HP}pos").get("treatAsChar") == "1"
                            and table.find(f".//{HP}footNote") is not None for table in paragraph.iter(f"{HP}tbl")))
    run = etree.Element(f"{HP}run", charPrIDRef="0")
    etree.SubElement(run, f"{HP}t").text = "가" * characters_before
    paragraph.insert(0, run)
    page = page_layout._Page(1600, 42520, 1)

    with pytest.raises(page_layout._Unsupported, match="footnotes in a paragraph with objects among its text"):
        page_layout._paragraph(page_layout._Measure(root), page, paragraph)


def test_a_flowing_table_reaching_its_footnotes_is_left_for_hancom() -> None:
    # Move Hancom's 2564-high flowing table near the page foot: its 2351-high note area starts at 10213,
    # while the table would end at 12364. Counting the notes only after placing the table must not leave a
    # supposedly supported layout where the table and its footnotes overlap.
    from dataclasses import replace

    document = HwpxDocument.open(_without_caches((FIXTURES / "pages_footnotes_in_table_cells.hwpx").read_bytes()))
    root = document.oxml
    element = next(paragraph for paragraph in root.sections[0].element.findall(f"{HP}p")
                   if any(table.find(f"{HP}pos").get("treatAsChar") == "0"
                          and table.find(f".//{HP}footNote") is not None for table in paragraph.iter(f"{HP}tbl")))
    para = page_layout._paragraph(page_layout._Measure(root), page_layout._Page(12564, 42520, 1), element)
    assert para.table is not None and para.notes
    shape = page_layout._note_shape(root.sections[0].element)
    paginator = page_layout._Paginator(12564, 1, shape)

    with pytest.raises(page_layout._Unsupported, match="flowing table overlapping its footnotes"):
        paginator._flow(para, para.table, 9800)

    # The same table without notes still fits. The unchanged fixture at the page top also remains supported.
    unnoted = replace(para, notes={})
    without_notes = page_layout._Paginator(12564, 1, shape)
    without_notes._flow(unnoted, unnoted.table, 9800)
    assert without_notes.frame == 0 and without_notes.floor == 12364
    at_top = page_layout._Paginator(12564, 1, shape)
    at_top._flow(para, para.table, 0)
    assert at_top.frame == 0 and at_top.floor < 12564 - shape.area(*at_top.page_notes)
