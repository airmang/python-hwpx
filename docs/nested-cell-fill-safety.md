# Nested cells in byte-preserving fills

`hwpx.table_patch.fill_cells` resolves each cell from that cell's own address
and span. Nested table metadata is masked during both boundary discovery and
address lookup. A table with overlaps, holes or inconsistent declared dimensions
is skipped with `table grid is invalid`, consistent with the planning resolver.

The byte fill replaces a selected cell's text and may invalidate caches or
materialize a smaller font. Those operations cannot yet preserve every nested
descendant when applied to a parent cell containing a table. Such a parent is
therefore skipped **before any text, cache or header/font change**, with a
`cell contains a nested table` reason. Its bytes are unchanged and it is absent
from `applied`. This also covers clear/no-op-looking requests and shrink options.

Other cells in the outer table remain writable. An inner table can be selected
explicitly by its own `table_index`; byte table indices include nested tables
in opening-tag order. They are distinct from the object namespace's top-level
`doc.tables` indexing. At deeper nesting, the same rule applies at each level:
write ordinary cells directly and reject a cell that itself contains a table.

This is a preservation boundary, not a claim that direct parent-text editing is
implemented. A future scoped implementation must bound text replacement, cache
invalidation and font remapping together before enabling those writes.

## Evidence and downstream use

Independent synthetic inputs reproduced wrong-target edits and nested-content
loss on both public6.10.0 and the pre-fix source. The regression matrix covers
prefix aliases, metadata order, horizontal/vertical/rectangular merges, three
levels, malformed grids, empty/same/long parent text and shrink options. Existing
Hancom-saved input checks correct outer targeting plus byte identity of every
non-target table and unrelated ZIP member. No fresh Hancom UI observation is
claimed for this byte-edit correction.

Downstream broad exclusions of all overlapping numeric coordinates should remain
until a published core containing this fix is installed and the application's
regressions pass. Afterwards they can be narrowed to actual unsupported parent
cells and invalid grids. Keep explicit inner-table addressing and inspect both
`applied` and `skipped`; a source merge alone does not update installed packages.
