# Nested tables in byte-preserving edits

## Filling cells

`hwpx.table_patch.fill_cells` resolves each cell from that cell's own address
and span. Nested table metadata is masked during both boundary discovery and
address lookup. A table with overlaps, holes or inconsistent declared dimensions
is skipped with `table grid is invalid`, consistent with the planning resolver.

A cell that holds a table (a parent cell) is filled like any other: its own
visible text becomes the requested text and every nested table keeps its bytes.

- Line k goes to the cell's k-th own text paragraph; lines past the last one go
  into it as `hp:lineBreak`; later own paragraphs are emptied (they stay, as in
  flat cells). This also fixes flat cells, which used to drop the extra lines.
- A paragraph holding a nested table is never re-serialised. Its own `hp:t`
  outside the table are emptied, and its own line cache is dropped when its text
  changes. When the cell has no other text paragraph, the text beside the table
  is replaced in place so the cell keeps its layout.
- A paragraph holding an object with its own paragraphs (a text box, a
  footnote) is handled like a table holder: the object's paragraphs keep their
  bytes and only the cell's own text around it changes.
- A cell with only table paragraphs gets one new paragraph before the first,
  with the holder's paragraph shape and first run's character shape.
- Line caches are dropped only for the cell's own changed paragraphs; nested
  tables keep theirs. Font shrink (`max_lines`/`fit_max_lines`) reads and remaps
  only the cell's own runs.

An inner table can still be selected by its own `table_index`; byte table
indices include nested tables in opening-tag order. They are distinct from the
object namespace's top-level `doc.tables` indexing. A parent fill and fills of
its inner table's cells may go in one call.

## Structure edits

`apply_table_ops` row, column and cell edits, `split_table` and `merge_table`
work on a table whose cells hold tables. For the edit each nested table is
hidden behind a marker and put back byte for byte afterwards, so it moves with
its cell (reordered or shifted rows and columns, a merge), goes with it (a
deleted row or column) or stays in the first part of a split cell.

- Cloning a cell with its content copies its nested tables with fresh paragraph
  and table ids. Nested content with other identities (bookmarks, fields,
  pictures) refuses as flat cell content does; `blank` clones hold no table.
- An edit that would leave a cell narrower than the table nested in it (its
  width plus the cell's side margins) refuses, unless the cell was already that
  narrow. `autofit_columns` holds such a column at that width.
- `merge_table` merges with the next table on the same nesting level.

## Evidence and downstream use

Synthetic inputs cover text beside, above, below and without text around the
nested table, multi-line text, shrink options, three nesting levels and every
structure op. Hancom-saved inputs check that non-target tables and other ZIP
members keep their bytes. The desktop overlap gate compares each edited file
with a copy stripped of every line cache, opened in Hangul.

Downstream exclusions of overlapping numeric coordinates or parent cells can be
removed once a published core with this support is installed and the
application's regressions pass. Inspect both `applied` and `skipped`; a source
merge alone does not update installed packages.
