"""``hwpx.experimental.estimate_pages``: the pages and line positions Hancom lays a document out on.

Each ``pages_*.hwpx`` fixture is a document Hancom opened, laid out and saved. Its line caches
(``hp:linesegarray``) hold where Hancom put every line of a paragraph (``vertpos``, from the top
of the column), and ``HANCOM_PAGES`` the number of pages Hancom drew.
"""

from __future__ import annotations

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
    "pages_fixed_width_spaces": 2,  # rows of a syllable and a fixed-width space: a quarter em that hangs
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
    "pages_text_12pt_160": 5,             # 12 pt text, line spacing 160%
    "pages_spacing_20_20": 3,             # spacing before and after paragraphs
    "pages_boundary_widow_on": 2,         # widow/orphan control at the page end
    "pages_line_ends_at_page_foot": 2,    # a line ending right at the body's foot goes on
    "pages_empty_line_ends_at_page_foot": 2,  # an empty one too
    "pages_line_ends_200_above_page_foot": 2,  # one ending 200 above it stays
    "pages_line_ends_1_above_page_foot": 2,    # and one ending 1 above it
    "pages_line_ends_100_above_page_foot": 2,  # and 100 above it: no room is kept below lines
    "pages_keep_keep_with_next": 3,       # keep with next
    "pages_columns_2_break": 4,           # two columns and a column break
    "pages_footnotes_6": 3,               # footnotes at the page foot
    "pages_table_flow_repeat_header": 3,  # a table flowing with the text, header row repeated
    "pages_table_repeated_header_second_cell_marked": 2,  # only its second cell a header cell: repeated
    "pages_table_flow_multiline_cells": 4,  # a flowing table split between cell lines
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
    "pages_table_caption_above": 1,  # a caption of one line above a flowing table: the line and a gap of 850
    "pages_table_caption_below": 1,  # the same below it
    "pages_table_caption_above_over_pages": 2,  # above a table going over the page end: on its first page
    "pages_table_as_character_caption_two_lines": 1,  # two lines above a table set as a character
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
    "pages_table_merged_rows_tall": 1,    # a table set as a character, a merged cell taller than its rows
    "pages_table_merged_rows_short": 1,   # the same, the merged cell shorter than its rows
    "pages_table_flow_merged_rows": 2,    # a table flowing with the text, cells merged over rows
    "pages_table_flow_tall_row_carried": 2,  # a row declared taller than its text, cut at the page end
    "pages_table_flow_tall_row_dropped": 2,  # the same, the rest too short to go on
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
    "pages_table_nested_row_declared_cut": 2,  # the same row declared 16000: cut above the foot, the rest goes on
    "pages_table_nested_row_declared_cut_near_foot": 2,  # declared 24000, cut 3579 below its top
    "pages_table_nested_row_declared_first_line_100_above_page_foot": 2,  # its first line ends 100 above
                                                                          # the page's foot: it goes on whole
    "pages_table_nested_row_declared_first_line_101_above_page_foot": 2,  # 101 above it: cut there
    "pages_objects_among_text_table": 2,  # a full-width table set as a character among text
    "pages_objects_among_text_equation": 1,  # equations set as characters among text
    "pages_objects_after_text_rectangle": 1,  # rectangles set as characters after text
    "pages_table_anchored_after_text": 1,  # a top-and-bottom table anchored after three lines of text
    "pages_picture_anchored_before_text": 1,  # a top-and-bottom picture anchored before the text
    "pages_table_anchored_offset_before_text": 1,  # 3000 down from the first line: the third line goes below
    "pages_table_anchored_offset_after_text": 1,   # 3000 down from the last line: the next paragraph's second
    "pages_picture_anchored_offset_next_paragraph": 1,  # 1600 down: the next paragraph's first line
    "pages_picture_anchored_small_offset": 1,  # 500 down: the line it stands on goes below it
    "pages_table_offset_flowing_split_by_cell": 2,  # a flowing table 500 down over the page end:
                                                    # the line it stands on goes below its end
    "pages_table_offset_flowing_row_by_row": 2,  # the same moved row by row
    "pages_table_offset_flowing_second_line": 2,  # 2000 down: the second line goes below its end
    "pages_table_offset_flowing_next_paragraph": 2,  # the next paragraph's first line does
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


@pytest.mark.parametrize("fixture", ["pages_table_nested_top_and_bottom_alone",
                                     "pages_table_nested_top_and_bottom_before_text", "pages_table_nested_among_text"])
def test_a_cell_holding_a_table_among_text_or_top_and_bottom_is_as_tall_as_hancom_drew_it(fixture: str) -> None:
    # A table in a cell of a flowing table, placed top and bottom alone in its paragraph (the cell
    # reaches down to its foot) or before text (the text goes below it), or set as a character among
    # text: the lines of the cell's caches. Without the caches the estimate does not follow such a cell.
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 1)
    assert estimate_pages(_without_caches(data)).unsupported == ("section 0: a nested table",)


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


def test_the_multi_column_sample_breaks_its_lines_at_each_column_width_without_caches() -> None:
    # hwpxlib's MultiColumn sample, columns of unequal width: two pages, with its caches or without them.
    data = (Path(__file__).parent / "fixtures" / "hwpxlib_corpus" / "reader_writer__MultiColumn.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 2)
    _assert_like_hancom(estimate_pages(_without_caches(data)), data, 2)


def test_a_footnote_in_a_paragraph_without_a_cache_in_columns_of_unequal_width_is_not_followed() -> None:
    document = HwpxDocument.new()
    document.set_columns(2, same_size=False, column_widths=[(10632, 873), (21263, 0)])
    document.notes.add_footnote("각주", document.add_paragraph("각주가 달린 문단"))

    assert estimate_pages(document).unsupported == (
        "section 0: objects, composed characters, ruby text or footnotes in a paragraph without a layout cache "
        "in columns of unequal width",)


@pytest.mark.parametrize("fixture", ["pages_table_row_split_in_first_paragraph",
                                     "pages_table_row_split_after_nested_table",
                                     "pages_table_row_split_moves_nested_table",
                                     "pages_table_row_split_moves_nested_table_above_text"])
def test_a_row_holding_a_nested_table_split_over_a_page_splits_where_hancom_split_it(fixture: str) -> None:
    # A flowing table (split by cell) whose row 1 holds, in one cell, six lines, a 2x2 table placed top and
    # bottom (alone in its paragraph, or above a line of text) and six lines more, going on over the page
    # end among the first six lines, after the nested table, or at it (the nested table goes on to the
    # next page, with the text below it). Hancom's caches of the cell start over at the next page's top.
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 2)
    assert estimate_pages(_without_caches(data)).unsupported == ("section 0: a nested table",)


@pytest.mark.parametrize("fixture", ["pages_table_nested_square_alone", "pages_table_nested_square_beside_text"])
def test_a_cell_holding_a_table_wrapped_square_is_as_tall_as_hancom_drew_it(fixture: str) -> None:
    # A table wrapped square at the left of a paragraph in a cell of a flowing table, alone (the cell
    # reaches down to its foot) or beside text (the lines beside it are narrower, the rest go below
    # it): the lines of the cell's caches. Without the caches the estimate does not follow such a cell.
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 1)
    assert estimate_pages(_without_caches(data)).unsupported == ("section 0: a nested table",)


@pytest.mark.parametrize("fixture", ["pages_table_nested_top_and_bottom_placed_up_alone",
                                     "pages_table_nested_square_placed_up_alone"])
def test_a_table_placed_up_from_its_paragraph_in_a_cell_stands_at_the_paragraph_top(fixture: str) -> None:
    # A table alone in a cell's paragraph after two lines, placed top and bottom or wrapped square 1000
    # up from the paragraph's top (a negative offset, kept as an unsigned number): Hancom puts it at the
    # paragraph's top, and the cell reaches down to its foot from there.
    data = (FIXTURES / f"{fixture}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 1)


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
        "pages_picture_square_past_the_page_foot_mid_paragraph",  # its paragraph's first line the page's last
        "pages_table_square_past_the_page_foot",  # a table wrapped square alone in its paragraph
    ],
)
def test_a_square_object_past_the_page_foot_moves_no_line_keeping_its_cache(name: str) -> None:
    # A picture or table wrapped square from its paragraph's top, 8000 tall, its band past the body's
    # foot: Hancom sets it alone at the next page's top, the lines beside it there narrower and the lines
    # left above the foot as wide as the column. It takes no line's height, so the lines keeping their
    # caches stay where the caches put them; without the caches, where each line breaks is not followed.
    data = (FIXTURES / f"{name}.hwpx").read_bytes()

    _assert_like_hancom(estimate_pages(data), data, 2)
    assert estimate_pages(_without_caches(data)).unsupported == (
        "section 0: a square-wrapped or offset top-and-bottom object past the page foot",)


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


def test_a_document_with_endnotes_is_unsupported() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("본문")
    document.notes.add_endnote("미주", paragraph)

    estimate = estimate_pages(document)

    assert estimate.pages is None
    assert estimate.lines == ()
    assert estimate.unsupported == ("section 0: endnotes",)
