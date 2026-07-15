# Markdown export fixtures

These two synthetic HWPX packages exercise merged/nested tables and embedded binary extraction in
`tests/test_markdown_export.py`. They were moved from the obsolete cross-repository `shared/hwpx`
operating tree so their only supported role is explicit: deterministic pytest input.

- `30_table_merge_min.hwpx`: compact merged-table and image extraction fixture.
- `99_all_in_one_stress.hwpx`: nested-table recursion stress fixture.

They contain no workstation paths or private-origin markers and are not included in the package
wheel.
