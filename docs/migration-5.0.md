# Migrating to python-hwpx 5.0

`python-hwpx` 5.0 is the HWPX object model, OPC/OXML, and the format-native
primitives built on them. The application workflows that grew inside the library
— agent editing, document authoring, form-fill, eval-plan, exam typesetting,
institutional lint, and Hancom rendering — now live in `python-hwpx-automation`, which
has owned their canonical implementation since the 4.x line.

Nothing here is discontinued. Every removed import has a named replacement, and
`python-hwpx` 4.x keeps all of it for anyone who needs time.

## If you use the MCP server or the skill

Nothing to do. The tool names, schemas, and results are unchanged; only the
implementation's address moved, and it moved before this release.

## If you import `hwpx` directly

Install the companion package and change the import path:

```bash
pip install python-hwpx-automation
```

The tables below give the exact replacement for each removed surface.

### Rolling back

`pip install "python-hwpx<5"` restores every 4.x surface. The 4.x line stays
available; it is not a deprecated dead end you are being pushed off.

---

## Removed surfaces

### Exam typesetting — `hwpx.exam`

Question parsing, block measurement, and composition into a form.

| removed | replacement |
|---|---|
| `hwpx.exam.compose_exam_into_form` | `hwpx_automation.office.exam.compose.compose_exam_into_form`, or the MCP `compose_exam` tool |
| `hwpx.exam.measure` | `hwpx_automation.office.exam.measure`, or the MCP `verify_question_splits` tool |
| `hwpx.exam.parser` | `hwpx_automation.office.exam.parser` |
| `hwpx.exam.ir` | `hwpx_automation.office.exam.ir` |
| `hwpx.exam.profile` | `hwpx_automation.office.exam.profile` |

The `examples/compose_exam.py` script is removed with it; the skill's exam
workflow covers the same ground through the MCP tools.

*Why it moved:* laying out exam questions to fit a specific form is a document
genre, not a property of the HWPX format. The primitives it stands on — tables,
paragraphs, page geometry, package preservation — are all still core, which is
why the MCP owner builds on them rather than carrying its own copy.

### Agent editing — `hwpx.agent` and the `hwpx` command

| removed | replacement |
|---|---|
| `hwpx.agent.*` | `hwpx_automation.office.agent` |
| `hwpx` console command | the same command, declared by `python-hwpx-automation` |

MCP declares `hwpx` in the train that raises its core floor to 5.0, so no valid
install ever has two packages claiming the name. Install the companion package
and the command keeps working with the same subcommands.

### Authoring — `hwpx.authoring`, `builder`, `design`, `presets`

| removed | replacement |
|---|---|
| `create_document_from_plan`, `validate_document_plan`, `normalize_document_plan` | `hwpx_automation.office.authoring`, or the MCP `validate_document_plan` → `create_document_from_plan` tools |
| `hwpx.builder.Document`, `Section`, `Paragraph`, `Table`, `Header`, `Footer` | `hwpx_automation.office.authoring.builder` |
| `hwpx.design`, `hwpx.presets` | `hwpx_automation.office.authoring.design` / `.presets` |
| `hwpx.tools.report_parser.parse_government_report_text` | `hwpx_automation.office.authoring`, or the MCP tool of the same name |

*Why:* a document plan is a genre description, and a Korean government report is
an institutional form. Core still gives you paragraphs, runs, tables, headers and
page geometry — the builder composes those, it does not extend the format.

### Form fill and eval plans

| removed | replacement |
|---|---|
| `hwpx.form_fill`, `hwpx.formfill_quality`, `hwpx.fill_residue`, `hwpx.guidance_scan`, `hwpx.template_formfit` | `hwpx_automation.office.form_fill`, or `analyze_form_fill` → `apply_form_fill` → `verify_form_fill` |
| `hwpx.evalplan_fill` | `hwpx_automation.office.evalplan`, or `apply_evalplan_fill` |

The measurement contract stayed: `hwpx.form_fit` — policy, measure, engine,
report, apply — is still core, because core's own table and field APIs call it.
What left is the seal placement, the PDF extraction, and the institutional rules.

### Compliance, quality, utilities

| removed | replacement |
|---|---|
| `hwpx.tools.official_lint` | `hwpx_automation.office.compliance.official_lint` |
| `hwpx.tools.pii` | `hwpx_automation.office.compliance.pii` |
| `hwpx.tools.table_compute` | `hwpx_automation.office.utilities` |
| `hwpx.tools.style_profile`, `hwpx.tools.advanced_generators` | `hwpx_automation.office.authoring` |

### Mail merge — a default that changed

`hwpx.tools.mail_merge.mail_merge` is gone. Use `merge_template_rows`, which is
now public.

```python
# 4.x — masking was on by default, through rules core no longer carries
mail_merge(template, rows, output_dir=out)

# 5.0 — the caller supplies the sanitizer, and the choice is visible
from hwpx.tools.mail_merge import merge_template_rows
merge_template_rows(template, rows, output_dir=out, value_sanitizer=my_masker)
```

This is the one removal that changes a *default* rather than an address, so it
is worth being explicit: the old wrapper masked personal information unless you
opted out. Rather than flip that default to "do nothing" — which would leak
quietly for anyone who did not read this page — the wrapper is gone, and the
generic function has always required you to say what sanitizing means.

`hwpx_automation.office.compliance` provides a policy you can pass straight in.

### Rendering and PDF reading — injected, not discovered

Core no longer looks for a Hancom installation or an imaging stack.

```python
# 4.x — core resolved an oracle behind your back
verify_redline(before, after)

# 5.0 — the companion layer supplies the backend
from hwpx_automation.office.rendering import resolve_hancom_backend
verify_redline(before, after, oracle=resolve_hancom_backend())
```

Without a backend the report is `render_checked=False` and `opensClean=None`.
That is deliberate: an unverified result should say so rather than look like a
pass. The same applies to `verify_fill`, and to
`toc_fidelity.toc_verify(..., extract=...)`.

### `python-hwpx[visual]` is now an empty extra

`pip install "python-hwpx[visual]"` still succeeds — the extra is kept
deliberately so existing install commands and lockfiles do not break — but in
5.0 it installs nothing. In 4.2.0 it pulled in pymupdf, pillow and numpy.

pip does not warn about a declared-but-empty extra, so an upgrade takes the
imaging stack away silently and you find out later at the first `import fitz`.
If you were relying on it, move to the companion:

| 4.x | 5.0 |
|---|---|
| `python-hwpx[visual]` | `python-hwpx-automation[oracle]` (render/PDF) or `python-hwpx-automation[vision]` |

Core owns no imaging runtime in 5.0; that is the same boundary the rendering
change above describes.

### Removed from the wheel

`hwpx.benchmark` and `hwpx.conformance` no longer ship, and the
`hwpx-conformance` command is gone with them. They are repository QA assets. If
you were running the conformance campaign, work from a checkout.

The complete 77-path removal inventory is machine-pinned for both source and
built distributions. See
[`architecture/product-boundary.md`](architecture/product-boundary.md) for the
ownership, dependency, and non-resurrection contract.
