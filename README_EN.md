<p align="center">
  <h1 align="center">python-hwpx</h1>
  <p align="center">
    <strong>A Python layer for safely automating HWPX without Hancom — minimal-scope edits, verified authoring, a receipt on every write.</strong>
  </p>
  <p align="center">
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/v/python-hwpx?color=blue&label=PyPI" alt="PyPI"></a>
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/pyversions/python-hwpx" alt="Python"></a>
    <a href="https://github.com/airmang/python-hwpx/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License"></a>
    <a href="https://airmang.github.io/python-hwpx/"><img src="https://img.shields.io/badge/docs-Sphinx-8CA1AF" alt="Docs"></a>
  </p>
</p>

<p align="center"><a href="README.md">한국어</a> | English</p>

---

> **python-hwpx is a Python layer for safely automating HWPX without Hancom.** It
> edits existing documents in the minimal scope, generates new documents in a form
> verified to be accepted by real Hancom, leaves change/preservation/verification
> receipts on every write, and can delegate full interpretation and rendering to
> specialized backends.

- **Minimal-scope edits** — untouched parts stay byte-for-byte on save (byte
  preservation 497/497 on the patch path, frozen corpus v2 · 2026-07-19).
- **Verified authoring** — from-scratch generation lands in a form real Hancom
  accepts (produced-output Hancom open 476/476 all-pass, authoring quality gate 58/58).
- **A receipt on every write** — the representative save paths return a
  [Safe Write Contract](docs/safe-write-contract.md) `MutationReport`
  (`hwpx.mutation-report/v1`) that **measures** the actual write mode, preservation
  grade, and verification result.

---

## 🧩 HWPX Stack (3 components)

| Layer | Repo | Role |
|---|---|---|
| 📦 Library | **[`python-hwpx`](https://github.com/airmang/python-hwpx)** | Pure-Python HWPX parsing / editing / generation core |
| 🔌 MCP server | [`hwpx-mcp-server`](https://github.com/airmang/hwpx-mcp-server) | Manipulate HWPX from MCP clients (Claude Desktop, VS Code, etc.) |
| 🎯 Agent skill | [`hwpx-plugin`](https://github.com/airmang/hwpx-plugins) | First-party plugin / skill bundle that lets agents use HWPX directly |

`python-hwpx` is the core library providing HWPX parsing, editing, and generation,
while `hwpx-mcp-server` and `hwpx-plugin` are first-party integration components
maintained directly by the same project.
"First-party" refers to the project's maintenance relationship; it does not imply
official certification by Hancom or any third party.

The current public PyPI release is `python-hwpx 3.6.0`. A plain
`pip install python-hwpx` installs this release.
The current package classifier is `Development Status :: 3 - Alpha`. This classifier
reflects the maturity of the API and product; it does not stand in for the public
version or the minimum compatible version of the plugin.

---

## We speak in measurements — Published Corpus

The outputs of this stack are verified by **exhaustive measurement against real
Hancom Office**, not by claims (frozen corpus v2, N=497 produced outputs, 2026-07-19,
real Hancom 12.0.0.3288 COM/GUI oracle; details and caveats in the
[measured corpus metrics](https://airmang.github.io/python-hwpx/corpus-metrics.html)):

- **Hancom open-acceptance 476/476 all-pass** (frozen corpus v2 · 2026-07-19 · real
  Hancom COM `Open()` · rule-of-three lower bound 99.37%) · parsing 96.2% (458/476)
- **Byte preservation of untouched regions 497/497** (patch path only, zip-part diff ·
  no oracle needed) · **personal-info 0-leak** (35 docs / 140 synthetic values)
- 416/476 render-verified (real Hancom `SaveAs("PDF")`) + honesty bucket of 43 (PDF
  export of tracked-change documents is refused by Hancom itself — a measured
  limitation) + 17 unverified
- Form-fill differential is 49.2% on wild public forms — **we publish the low number as-is** and record it as remaining work

> These numbers are on the *output acceptance* axis (does real Hancom accept the files we produce).
> This is a different axis from document *parsing recall*, so do not compare it side by side with parser-project figures.

---

## Why python-hwpx

- **No Hancom Office required for core editing** — HWPX is a ZIP+XML (OWPML/OPC) structure, so pure Python reads and writes it anywhere: Windows, macOS, Linux, CI.
- **From reading to generation in one core** — text/format extraction, paragraph/table/form editing, new-document generation, and XSD schema validation are all handled by one API.
- **Agent- and automation-friendly** — `hwpx-mcp-server` and `hwpx-plugin`, maintained by the same project, connect to the core.

Document parsing, editing, and generation can be done in pure Python. However, to
assert final visual quality — page breaks, table overflow, font substitution, and so
on — you separately use a real Hancom render oracle as needed.

## Quick start

```bash
pip install python-hwpx      # Python 3.10+ · lxml ≥ 4.9
```

```python
from hwpx import HwpxDocument

# Open an existing document → edit → save
doc = HwpxDocument.open("보고서.hwpx")
doc.add_paragraph("자동화로 추가한 문단입니다.")
doc.save_to_path("보고서-수정.hwpx")

# Create a new document
new = HwpxDocument.new()
new.add_paragraph("python-hwpx로 만든 새 문서")
new.save_to_path("새문서.hwpx")
```

> 💡 A context manager is also supported — resources are cleaned up automatically on leaving the `with` block:
> ```python
> with HwpxDocument.open("보고서.hwpx") as doc:
>     doc.add_paragraph("자동으로 리소스가 정리됩니다.")
>     doc.save_to_path("결과물.hwpx")
> ```

Once you have the `open`/`new` → `edit`/`extract` → `save_to_path` flow, you can expand into the rest as needed.

## What it does

### 🔍 Read · Extract
- Text/HTML/Markdown export — `export_text()` · `export_html()` · `export_markdown()`
- **Rich Markdown** — `export_rich_markdown()` preserves inline formatting (`**bold**` · `*italic*` · `~~strikethrough~~`), nested tables (colspan/rowspan safe), shape text, images, footnotes/endnotes, hyperlinks, and heading auto-detection (`#`/`##`)
- **Document ingest gateway** — `hwpx.ingest.DocumentIngestor` detects HWPX and normalizes it into rich Markdown plus section/table metadata
- `TextExtractor` / `ObjectFinder` — iterate sections/paragraphs, find objects by tag/attribute/XPath (`hp:tab` is preserved as `\t`, roundtrip-safe)

```python
doc = HwpxDocument.open("보고서.hwpx")
md = doc.export_rich_markdown(
    image_dir="out/images",       # extract BinData images to disk
    image_ref_prefix="images/",   # prefix for ![](images/...) paths in the markdown
    detect_headings=True,         # auto #/## based on Ⅰ./1. patterns
)
```

### ✏️ Edit
- Add/remove/format paragraphs, run-level bold/italic/underline/color
- Add/remove sections (`add_section(after=)` · `remove_section()`, manifest managed automatically)
- Create tables, cell text, merge/split, nested tables, image embedding, headers/footers, memos (anchor-based), footnotes/endnotes, bookmarks/hyperlinks, multi-column editing
- **Edit formatting of existing documents** — alignment · line spacing · indentation · paragraph spacing, paper · margins · orientation, page numbers, bullets/numbering
- **Style-based replacement** — filter runs by color · underline · `charPrIDRef` and replace selectively (`replace_text_in_runs` · `find_runs_by_style`)

```python
# Find and replace only red text
doc.replace_text_in_runs("임시", "확정", text_color="#FF0000")
```

### 🖊️ Form filling (byte-preserving)
- Query and format-preserving fill of click-here (누름틀) fields, label-based cell lookup (`find_cell_by_label`) · path-based fill (`fill_by_path`)
- **Byte-preserving structural editing** — cell filling / row·column·table delete·insert / column-width autofit / shrink-to-fit fonts performed without reassembling the document, preserving the form's formatting exactly. Untouched regions are left byte-for-byte intact by `hwpx.patch`, which splices section XML bytes

```python
doc = HwpxDocument.open("신청서.hwpx")
result = doc.fill_by_path({
    "성명 > right": "홍길동",
    "소속 > right": "플랫폼팀",
})
doc.save_to_path("신청서-작성완료.hwpx")
print(result["applied_count"], result["failed_count"])
```

### 🏗️ Generation · Official-document tools
- `hwpx.builder` — assembly-style generation of Section/Heading/Table/Image/Header + a hard-gated save report
- Official-document tools — `official_lint` (item-marker hierarchy · "끝." marker · attachments · date lint), approval-block presets
- `advanced_generators` — photo boards (image_grid) · meeting nameplates · table-based org charts
- `mail_merge` — bulk generation of N copies from template + data, table sum/average computation
- `doc_diff` — paragraph LCS diff · old/new comparison tables · reference-consistency lint
- `style_profile` — extract and apply reference-document profiles, template registry

### ✅ Validation · Safety · Low-level
- XSD schema + package structure validation — CLI `hwpx-validate` · `hwpx-validate-package`, `hwpx-analyze-template`
- `validate_editor_open_safety` — gate for save/pack/repair/builder output, returns `openSafety` evidence
- `hwpx.tools.fuzz` (seeded deterministic scenarios · triple oracle) · `hwpx.tools.layout_preview` (page-box approximation HTML/PNG, self-verifying) · `opc.security` (XML entity · ZIP compression-bomb guards)
- Directly manipulate OWPML schema ↔ Python objects via `hwpx.oxml` dataclasses, with automatic HWPML 2016→2011 namespace normalization

```bash
hwpx-validate-package 보고서.hwpx
hwpx-analyze-template 보고서.hwpx
```

> For the full list of features, classes, and methods, see the [usage guide](docs/usage.md) and the [API reference](https://airmang.github.io/python-hwpx/api_reference.html).

## Safe Write Contract

The representative save paths (`save_to_path` · `save_to_stream` · `to_bytes`)
**decide the requested preservation grade before writing and return a receipt that
measures what actually changed.**

```python
from hwpx.mutation_report import PreservationDowngradeError

# Save with a receipt — picks the strongest achievable grade (mode="auto" default)
report = doc.save_to_path("result.hwpx", return_report=True)
print(report.actual_mode)                                     # "patch" | "rebuild"
print(report.preservation.untouched_part_payloads.to_dict())  # {"verified": 17, "changed": 0}

# Force patch grade — writes nothing and raises if it can't be met (fail-closed)
try:
    doc.save_to_path("result.hwpx", mode="patch", fallback="error")
except PreservationDowngradeError as exc:
    print(exc.offending_parts, exc.suggestion)
```

- `mode="patch" | "rebuild" | "auto"` (default `auto`) · `fallback="error" | "rebuild"` (default `error`).
- With `mode="patch"` + `fallback="error"`, if an untouched part cannot stay
  byte-identical the save writes **nothing** and raises `PreservationDowngradeError`
  (no silent rebuild).
- `MutationReport` reports `requestedMode`/`actualMode`/`fallbackUsed`, changed parts
  with coordinate-tagged byte ranges, three preservation layers (part payload · ZIP
  record · whole package), and three verification values (`passed`/`failed`/`not_performed`)
  — all **measured**, never asserted.

> Full parameters and the `MutationReport` schema are in the [Safe Write Contract doc](docs/safe-write-contract.md).

## Support matrix

Actual per-capability grade (frozen corpus v2 · 2026-07-19 · real Hancom 12.0.0.3288
oracle). Status vocabulary: **Parse / Preserve / Edit / Create / Render-verified /
Unsupported-but-preserved / Unsupported-and-rejected**.

| Capability | Status | Evidence |
|---|---|---|
| Paragraph·table authoring/editing | Parse·Preserve·Edit·Create·Render-verified | open 476/476 · authoring gate 58/58 · render 416 |
| Table structure change (row·col·table, autofit) | Preserve·Edit | `hwpx.table_patch` · byte preservation 497/497 |
| Form filling (byte-splice) | Preserve·Edit | `hwpx.patch`·`table_patch`·`body_patch` · byte preservation 497/497 (wild fidelity after the structural-defect fix: silent breakage 16.7%, typed refusals 35/66, produced pass 17/28; remaining work) |
| Picture insert/replace | Edit·Create | `add_picture`·`replace_picture` (verify complex objects in Hancom) |
| Chart | Unsupported-but-preserved | no create API · existing chart parts patch-preserved |
| Equation | Parse·Unsupported-but-preserved | no authoring API · existing equations parsed·patch-preserved |
| Tracked changes (redline) | Edit·Create | `add_tracked_*` · real Hancom `IsTrackChange=1` (Hancom refuses PDF export → `render_unavailable`, honestly bucketed) |
| Memo (comment) | Edit·Create·Render-verified | `add_memo*` · verified on real Windows Hancom |
| Footnote/endnote | Edit·Create | `add_footnote`·`add_endnote` (no independent render gate) |
| Native TOC / cross-reference | Create·Render-verified | `add_native_toc`·`toc_verify` · structure 15/15 · page alignment 5/5 |
| Encrypted HWPX | Unsupported-and-rejected | no decryption · encrypted parts rejected at parse |
| HWP 5.x binary | Unsupported-and-rejected | not a ZIP → `BadZipFile` on open (convert to HWPX first) |
| Click-here field (누름틀) creation | Parse·Edit | existing fields queried·format-preservingly filled · **no dedicated new-field creation tool** |

> Grade rationale and detailed evidence pointers are in the [support matrix doc](docs/support-matrix.md).

## Comparison with competing libraries

| | python-hwpx | pyhwpx | pyhwp |
|---|---|---|---|
| **Target format** | `.hwpx` (OWPML/OPC) | `.hwpx` | `.hwp` (v5 binary) |
| **Hancom install** | Not required | Required (Windows COM) | Not required |
| **Cross-platform** | ✅ Linux / macOS / Windows / CI | ❌ Windows only | ✅ |
| **Edit/generate API** | ✅ | ✅ (COM) | ❌ mostly read-only |
| **Schema validation** | ✅ | ❌ | ❌ |
| **AI agent integration (MCP)** | ✅ `hwpx-mcp-server` | ❌ | ❌ |

> HWP (v5 binary) files are not supported. Convert to HWPX in Hancom Office first.

## Known limitations

- `add_shape()` / `add_control()` do not generate every child element Hancom requires. When adding complex objects, verify by opening in Hancom.
- Image binary embedding is supported, but full automatic generation of the `<hp:pic>` element is not provided.
- Encryption/decryption of encrypted HWPX files is not supported.

## More

- **[🚀 Quick start](docs/quickstart.md)** · **[📚 Usage guide](docs/usage.md)** — from opening your first file to editing paragraphs/tables/memos/sections and text extraction/validation
- **[💡 Examples](docs/examples.md)** · [`examples/`](examples/) — `build_release_checklist.py` (generate HWPX with memo/style edits), `extract_text.py` (CLI text extraction), `find_objects.py` (trace OWPML nodes), and more
- **[📐 Schema overview](docs/schema-overview.md)** · **[🔧 Install verification](docs/installation.md)**
- **[🔬 HWPX internals field guide](docs/internals/)** — HWPUNIT · layout cache · TOC fields · OPC repacking · memos · oracle limits, verified against real Hancom behavior
- **[📖 Full docs (Sphinx)](https://airmang.github.io/python-hwpx/)** — API reference · 50+ practical patterns · FAQ
- **[📝 CHANGELOG](CHANGELOG.md)** · **[🤝 CONTRIBUTING](CONTRIBUTING.md)** · **[👥 CONTRIBUTORS](CONTRIBUTORS.md)**

## Contributing

Bug reports, feature proposals, and PRs are all welcome.

```bash
git clone https://github.com/airmang/python-hwpx.git
cd python-hwpx
pip install -e ".[dev]"
pytest
```

## Acknowledgements

This project is indebted to the following open standards and projects.

- **[OWPML — Open Word-processor Markup Language (KS X 6101)](https://www.kssn.net/search/stddetail.do?itemNo=K001010119985)** — the Korean industrial standard HWPX is based on
- **[hancom-io/hwpx-owpml-model](https://github.com/hancom-io/hwpx-owpml-model)** — reference model for OWPML element structure · **[neolord0/hwpxlib](https://github.com/neolord0/hwpxlib)** — oracle sample corpus
- **[edwardkim/rhwp](https://github.com/edwardkim/rhwp)** — inspiration for idempotence / verification-gate design
- **범정부오피스 (Whole-of-government Office)** — ideas for official-document editing workflows

## License

Apache License 2.0. See LICENSE and NOTICE.

## Maintainer

Primary maintainer/contact: **Kohkyuhyun** ([@airmang](https://github.com/airmang))

- ✉️ [kokyuhyun@hotmail.com](mailto:kokyuhyun@hotmail.com)
- 🐙 [@airmang](https://github.com/airmang)
