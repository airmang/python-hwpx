# Visual QA fixture and annotation contract v1

`hwpx.visual-fixture-manifest/v1` is the immutable corpus contract for S-069.
It contains page-only PNG inputs, their SHA-256 digests, provenance, and human
ground-truth annotations. Page indexes are zero-based everywhere. Bounding
boxes are `[x0, y0, x1, y1]` fractions of page width and height.

Fixture evidence is not renderer evidence. A fixture receipt always has
`assurance: fixture`, `renderChecked: false`, and `realHancom: false`. The core
contract rejects `assurance=fixture` with `renderChecked=true`. MCP/provider
results and repair rounds belong in a separate
`hwpx.visual-repair-ledger/v1`, referencing the corpus schema, case ID, and
exact page hashes. They must not rewrite ground truth or introduce another
fixture-manifest schema.

## Frozen taxonomy

Taxonomy version: `hwpx-visual-defects/1.0`.

- `text_clipping_overlap`
- `cell_overflow`
- `unexpected_blank_page`
- `leftover_guidance_placeholder_sample`
- `empty_required_field`
- `orphan_bullet_heading`
- `table_grid_border_anomaly`
- `font_color_alignment_inconsistency`
- `image_seal_misplacement`
- `header_footer_page_number_loss`
- `implausible_whitespace_density`

Critical findings are hard gates. No aggregate score, provider agreement, or
clean finding can cancel them. Missing, unreadable, duplicate, or unexpected
pages produce `unverified`, never `pass`.

## Annotation procedure

1. Labelers inspect the entire page independently, without detector output.
2. Each finding receives category, severity, and the tightest normalized bbox
   that still contains the evidence. Whole-page defects use `[0,0,1,1]`.
3. Before both labels exist, use `labelStatus: pending` and do not include the
   case in acceptance metrics.
4. If labels differ, retain both and use `labelStatus: disagreement`; do not
   silently choose the detector-favorable label.
5. After adjudication, use `labelStatus: adjudicated` and retain at least two
   distinct labeler IDs. Only adjudicated cases count toward recall, precision,
   false-acceptance, and confidence intervals.
6. Never include document text, names, or other PII in IDs or provenance.

The committed corpus includes a clean page, a page-only preservation of the
historical `slot_overprint.hwpx` failure morphology, and injected clipping and
blank-page defects. Run `tests/fixtures/visual_qa_v1/generate.py` to reproduce
the PNG bytes and manifest hashes. The historical page is explicitly described
as a deterministic fixture—not a captured Hancom render. Its human annotation
is intentionally still `pending`; that limitation must remain visible until
two independent labels are actually collected.
