# Known-leak migration contract

The layer leak guard (see [product-boundary.md](./product-boundary.md)) lists
genre and policy logic that still lives in core as `known-leak`. This document
is the contract for moving it to `python-hwpx-automation`: for each group, who
owns it afterwards, what core keeps, what callers use instead, and how the core
names are retired. [`known-leak-migration.json`](./known-leak-migration.json)
holds the same decisions in machine-readable form, and
`tests/test_known_leak_migration_contract.py` keeps it in step with
`tests/data/layer_leak_allowlist.json`.

Nothing has moved yet. The owner chose how the core names are retired (option
A under *Compatibility* below): they keep working through 6.x, warn in the next
major and go in the major after it. Releases are named only relative to each
other; nothing here promises a version number or a date.

The placement test is the one in product-boundary.md: generic HWPX capability
stays in core; a deterministic workflow or policy built from core primitives
goes to automation. Core never imports automation, so every move below hands
core a neutral primitive and puts the policy on the automation side, where it is
passed in or applied before calling core.

The additive neutral core seams are implemented in this source tree:
`hwpx.tools.doc_diff.paragraph_texts`, the rich exporter's `heading_detector`
callback, and `hwpx.table_patch.strip_trailing_table_text(predicate=...)`.
Application consumer routing is still pending. Existing core names and defaults
continue without new warnings; all eight compatibility leak entries remain.
See [neutral primitives](../neutral-migration-primitives.md).

## The four groups

The eight allowlist names (six `known-leak` entries, two `undetected`) fall
into four groups. `_SAFE_FILENAME_RE` and `_OUTLINE_NAME_RE` are
`format-vocabulary` and stay.

### official-reference-policy — official-document reference rules

- **Core names:** `tools/doc_diff.py` `_ATTACHMENT_LINE_RE`,
  `_ATTACHMENT_REFERENCE_RE`, `_TABLE_NUMBER_RE`, `_FIGURE_NUMBER_RE`, and the
  checks and repair hints built on them in `inspect_reference_consistency`.
- **Canonical owner:** `hwpx_automation.office.compliance`.
- **Core keeps:** `diff_paragraphs` and `doc_diff` over documents, paths, text
  and paragraph sequences; reading a document's paragraph texts.
- **Replacement:** `hwpx_automation.office.compliance.inspect_reference_consistency(source)`
  with the same `reference-consistency-v1` report; the MCP tool of the same
  name routes there.
- **Core surface affected:** `hwpx.inspect_reference_consistency` and
  `REFERENCE_CONSISTENCY_REPORT_VERSION` are **stable** names.

### document-plan-input — automation plan interpretation

- **Core name:** `tools/doc_diff.py` `_paragraphs_from_document_plan` and the
  `{"sections": ...}` branch of the source dispatch it serves.
- **Canonical owner:** `hwpx_automation.office.document_ops`.
- **Core keeps:** documents, paths, text, paragraph sequences and
  `{"paragraphs"}`/`{"text"}` mappings as diff and check input.
- **Replacement:** an automation function that turns a document plan
  (`sections`/`blocks`/`children`, heading and paragraph text, table rows) into
  the paragraph sequence core takes; automation's comparison and
  reference-check entry points call it first.
- **Core surface affected:** an input shape of two stable functions — behaviour
  rather than a name.

### report-heading-guess — report headings guessed in Markdown export

- **Core names:** `tools/markdown_export.py` `ARABIC_HEAD`, `ROMAN_HEAD`
  (undetected) and `_detect_heading`, which promote plain text and 1×1 tables to
  `#`/`##`.
- **Canonical owner:** `hwpx_automation.office.authoring.report_parser`, which
  already owns the report heading policy. Whether its rule matches the
  exporter's exactly has not been checked; the move must pin the exporter's
  current output with regression tests first.
- **Core keeps:** `export_markdown` and `HwpxMarkdownConverter` for text,
  tables, images and notes, headings read from recorded structure, and a
  genre-neutral hook through which a caller passes its own heading detector
  (paragraph text → Markdown heading or `None`).
- **Replacement:** the report rule as an automation detector passed to that
  hook by automation's entry points. Today the rule reaches automation through
  document ingest (`DocumentIngestor.default()` → `HwpxMarkdownConverter`);
  `doc.text.markdown()` uses the plain exporter and does not guess headings.
- **Core surface affected:** the `detect_headings=True` default of
  `export_markdown` and of `HwpxMarkdownConverter`.

### evalplan-caption-cleanup — evaluation-plan caption cleanup

- **Core name:** `table_patch.py` `strip_trailing_table_captions` (its
  `(N) word` pattern has no Hangul, so it is listed as undetected).
- **Canonical owner:** `hwpx_automation.office.evalplan`.
- **Core keeps:** a byte-preserving primitive that removes caller-selected text
  from the trailing run of a table's wrapper paragraph, never crossing a
  paragraph or table boundary, through the same open-safety finalize path.
- **Replacement:** the `(N) short word` selection rule as an automation
  predicate passed to that primitive.
- **Core surface affected:** `hwpx.table_patch.strip_trailing_table_captions`.

## Sequence

1. Automation adds each replacement owner and switches its consumers. Core is
   unchanged and keeps answering old callers.
2. Core adds the neutral primitives (the heading-detector hook and the
   caller-selected trailing-text removal) in a minor release. The old names
   delegate to them with today's rule, so their output does not change.
3. In the next major, every affected core name and behaviour emits a
   `DeprecationWarning` that names its automation replacement. Output does not
   change.
4. In the major after it, the release that removes a core name also removes its
   allowlist or undetected entries and its group here. From then on the layer
   leak guard fails if the pattern comes back.

Every step keeps a core-only installation working for the generic features:
`diff_paragraphs`, document diff, Markdown export, and table and package
preservation. Regression tests for the current report, plan input, heading
promotion and caption removal — including body text that only looks numbered
and text after an ordinary table — come with the step that moves each group.

## Compatibility — owner decision: option A

[stable-api.md](../stable-api.md) lets a stable name break only at a major
boundary, after a `DeprecationWarning` in an earlier major. Two of the affected
names are stable; the others are module-level public names. The owner chose
option A for all of them, which is the stable-name policy as written:

| Release | What the affected core names and behaviours do |
|---|---|
| 6.x | Keep working without a warning. Automation replacements ship, and core may add the neutral primitives in a minor; the old names delegate to them with today's rule. |
| next major | Emit a `DeprecationWarning` that names the automation replacement. Output does not change. |
| the major after it | Removed, with their allowlist and undetected entries. Only the neutral primitives stay in core. |

"Affected" means everything listed under *Core surface affected* above: the
stable `inspect_reference_consistency` and `REFERENCE_CONSISTENCY_REPORT_VERSION`,
the document-plan input of `doc_diff` and the reference check, the
`detect_headings=True` default of `export_markdown` and `HwpxMarkdownConverter`,
and `strip_trailing_table_captions`.

The options that were weighed, for the record:

- **A.** Keep every core name working through 6.x, warn in the next major,
  remove in the major after it. *(chosen)*
- **B.** Warn from a 6.x minor once the automation replacements ship, remove in
  the next major. This needs an explicit exception to the stable-name policy for
  `inspect_reference_consistency` and the plan input of `doc_diff`.
- **C.** Never remove: freeze the core copies as compatibility code without
  feature work and keep their allowlist entries.

`compatibility.decision` in the JSON is `A` and `compatibility.schedule` holds
the table above. The contract test keeps the schedule relative: it rejects any
version number or date in the contract.
