# Hancom-saved fixtures

Documents laid out and saved by Hancom's Hangul. Tests compare what python-hwpx writes, reads or estimates
with what Hangul stored in them: line layout caches (`hp:linesegarray`), table and object sizes, field and
style values.

## Saved on Windows

Every file but `equation_*.hwpx` was saved by Hangul for Windows (`os="2"` in `version.xml`), and so was
`memos_in_fields.hwp`.

Before a file was committed, only what names its author, the program version and the dates was removed;
every other part keeps the bytes Hangul wrote.

- `.hwpx`
  - `version.xml`: `appVersion` emptied.
  - `Contents/content.hpf`: the `creator`, `lastsaveby`, `CreatedDate`, `ModifiedDate` and `date` metas
    emptied.
  - An embedded OLE object (`BinData/*.ole`, a chart): the times of its compound file's root entry zeroed.
  - The zip repacked with its entries in the same order and compression, dated 1980-01-01 as Hangul
    dates them.
- `.hwp`
  - The summary information stream (`\x05HwpSummaryInformation`): the author, the last saver, the program
    version, the created and last saved times and the date text emptied. The last printed time is zero as
    Hangul writes it.
  - The compound file rebuilt; every other stream is as Hangul saved it.

## Equations saved on macOS

`equation_*.hwpx` were cut from documents opened and saved by Hangul for macOS (`os="10"` in
`version.xml`). Each keeps the section's first paragraph and one equation paragraph byte for byte; the
preview image was left out and the author and dates emptied (#351).

The three font-command matrices (`equation_attached_font_commands.hwpx`,
`equation_font_command_boundaries.hwpx`, `equation_font_command_case.hwpx`) retain
their complete synthetic sections: 76, 27 and 48 equations respectively. They
were opened, displayed and saved in Mac Hangul12.30.0 build6446 on2026-10-30
(#591). Only the preview image and the metadata listed above were removed;
all equation scripts, geometry and section bytes are untouched. Input, raw-save,
sanitized-fixture and section hashes are in
`tests/data/equation_font_boundary_provenance.json`.

## Objects turned by Hangul 2024

`turn_*.hwpx` are synthetic documents made by python-hwpx (rectangles, a text box, an ellipse holding text and
two groups) in which Hangul 2024 for Windows (`os="1"` in `version.xml`) turned one object through its public
automation -- the object selected, then its turn-by-90-degrees command (`*_by_90`) or its object dialog with an
angle of 30 (`*_by_30`) -- and saved the document. `turn_shapes_*`, `turn_again_*`, `turn_resized_group_*`,
`turn_group_in_group_*` and `turn_flipped_rect_*` were turned through the object dialog only, at the angle in
the name (`turn_flipped_rect_by_30` after the flip-left-right command); the dialog also drew the group in
`turn_shapes_group_resized_by_90` at 7200 x 7200. `flip_*.hwpx` and `turn_group_in_resized_group_by_30.hwpx`
were changed the same way with Hangul's flip-left-right / flip-up-down commands (`ShapeObjHorzFlip`,
`ShapeObjVertFlip`) and then the dialog's angle, as their names say (`_back`: turned back to 0 after 45);
`tests/test_flip_shapes_and_groups.py` says what each shows. `flip_turned_*`, `flip_ellipse_*`, `flip_polygon_*`
and `flip_line_*` were made the same way from a text box and a group already turned 30 degrees, an ellipse, a
polygon and a line (the dialog's size boxes given back the object's own size). `tests/test_turn_text_shapes_and_groups.py` says what each
shows. The preview image was left out and the metadata listed above emptied; every other part keeps Hangul's
bytes.

## Adding a file

`formfit_hft_ascii_myeongjo_grid.hwpx` and `formfit_hft_ascii_gothic_grid.hwpx`
contain 480 paragraphs each in the named face (94 printable ASCII glyphs and
26 Hangul syllables at 9,10,11,12pt). Tests assert the resolved face as well as
the saved tab positions. The initial PR filenames were swapped; the corrected
names and metadata-only redaction are linked to the original section hashes in
`tests/data/formfit_hft_ascii_provenance.json` (#623).

For any new Hancom-saved file, remove the information listed above before
committing it, and say in the test what behaviour of Hangul the file shows.
