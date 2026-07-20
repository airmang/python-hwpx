<p align="center">
  <h1 align="center">python-hwpx</h1>
  <p align="center">
    <strong>Read, edit, generate, and structurally validate HWPX documents in Python — without Hancom Office.</strong>
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
Hancom Office**, not by claims (frozen corpus N=497, 2026-07-19; details and caveats
in the
[measured corpus metrics](https://airmang.github.io/python-hwpx/corpus-metrics.html)):

- **Hancom open-acceptance rate 100%** (476/476 all-pass, lower bound ≥99.4%) · parsing 96.2%
- **Byte preservation of untouched regions 100%** (497/497, patch path) · **personal-info 0-leak**
- 416 render-verified cases + an honesty bucket (PDF export of tracked-change documents is refused by Hancom itself — published as a measured limitation)
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
