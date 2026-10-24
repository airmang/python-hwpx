<p align="center">
  <h1 align="center">python-hwpx</h1>
  <p align="center">
    <strong>Read, edit, and create Hangul documents (HWPX and HWP) in Python, without Hancom Office</strong>
  </p>
  <p align="center">
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/v/python-hwpx?color=blue&label=PyPI" alt="PyPI"></a>
    <a href="https://pepy.tech/project/python-hwpx"><img src="https://static.pepy.tech/badge/python-hwpx/month" alt="Downloads"></a>
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/pyversions/python-hwpx" alt="Python"></a>
    <a href="https://github.com/airmang/python-hwpx/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow/status/airmang/python-hwpx/tests.yml?branch=main&label=tests" alt="Tests"></a>
    <a href="https://airmang.github.io/python-hwpx/corpus-metrics.html"><img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fairmang.github.io%2Fpython-hwpx%2F_static%2Fbadge-hancom-open.json" alt="Hancom open"></a>
    <a href="https://github.com/airmang/python-hwpx/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue" alt="License"></a>
  </p>
</p>

<p align="center"><a href="README.md">한국어</a> | English</p>

HWPX is XML (OWPML) inside a ZIP file, so Python alone can work with it; Hancom Office is not needed.
python-hwpx runs on Windows, macOS, Linux, and CI, and its only dependency is `lxml`. HWP 5.0 (`.hwp`)
files open and save through the same API.

We open our output in Hancom Office 2024 and publish what we see, with dates,
[below](#how-close-to-hangul).

## Getting started

```bash
pip install python-hwpx      # Python 3.10+
```

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

doc = HwpxDocument.new()
doc.add_heading("2026 Operating Plan", level=1)
doc.add_paragraph("Background", style="개요 2")  # Hangul numbers it "가."
doc.save_to_path("plan.hwpx")
```

Styles are picked by name. A name that does not exist fails at that line.
To edit an existing file, start from `HwpxDocument.open("report.hwpx")`. An `.hwp` file opens the
same way, and `save_to_path("report.hwp")` writes HWP 5.0.

For higher-level workflows (document authoring, form filling, exam typesetting), install
[`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation) alongside it.

> For older install commands, `pip install "python-hwpx[visual]"` still works, but the `visual`
> extra is empty and installs no render/PDF dependencies. That runtime belongs to
> `python-hwpx-automation[oracle]`.

## What it does

- Read and extract: text, HTML and Markdown export that keeps formatting, nested tables and footnotes.
- Edit: paragraphs, tables, pictures, headers and footers, memos, footnotes; line spacing, margins, page numbers.
- Fill forms: find a cell by its label and change only the value; parts you did not touch keep their bytes.
  FormFit decides whether a value should wrap or shrink to fit its cell, measuring with Hangul's glyph widths.
- Edit table structure: insert and delete rows and columns, split and merge cells; get a table by number
  with `doc.tables[0]`.
- Create and batch: new documents, tables of contents and cross-references, mail merge, document diff,
  tracked changes.
- HWP 5.0: read an `.hwp` file as HWPX, edit it with the same API, and save it as `.hwp`. Anything that
  could not be carried over is listed in `document.conversion_report`.
- Layout estimates (experimental): `estimate_pages` estimates the page count and each line's page and
  vertical position without Hangul. `write_line_caches` writes the line layout data Hangul saves, but only for
  paragraphs where it is sure to match Hangul. Viewers such as rhwp, which place pictures from that data, then
  show them too. By default nothing is written.
- Verify and stay safe: a package-structure validation CLI, an open-safety check before saving, and a save
  report (`return_report=True`).

More: [five-minute quickstart](docs/quickstart.md) · [usage guide](docs/usage.md) · [API reference](https://airmang.github.io/python-hwpx/) · [examples](docs/examples.md) · [support matrix](docs/support-matrix.md)

### Filling a form

```python
doc = HwpxDocument.open("application.hwpx")
values = {
    "성명 > right": "홍길동",
    "소속 > right": "플랫폼팀",
}
result = doc.tables.fill_by_path(values)
if result["failed_count"] or result["applied_count"] != len(values):
    raise ValueError(result["failed"])
report = doc.save_to_path("application-filled.hwpx", mode="patch", fallback="error", return_report=True)
```

Duplicate or missing labels come back as failures, so you can stop before saving. `mode="patch"` asks for
untouched ZIP parts to keep their bytes. What happens inside an edited part, and how the page looks, need
separate checks. To reopen the output and verify its content, follow the [safe write contract](docs/safe-write-contract.md).

*Blocks without a **Standalone example** label take your existing document as input. The per-example
Python-block status is frozen in the [execution ledger](docs/python-example-ledger.json).*

## How close to Hangul

We open the files we produce in real Hancom Office and report what we see, with the date and the program
version next to every figure.

**Layout: python-hwpx main after 6.9 · 2026-10-24**

| What | Compared with | Result |
|---|---|---|
| Paragraphs of 77 public real-world documents whose line breaks match | What Hancom Office 2024 (Windows) laid out and saved | 8,246 / 8,263 (99.8 %) |
| Of those 77, documents where every line sits on the same page at the same position | Same | 75 / 77 (the other 2: a broken table, a table inside a cell that is not supported) |
| Documents whose page count, estimated from a copy with the line layout data removed, matches (79 public · 522 private real-world · 780 feature test documents) | The page count of the Hangul that saved each document | 1,343 / 1,381 (17 not estimated) |

**Opening: Hancom Office 12 (macOS)**

- Hancom opens 120/120, render-verified 120/120: a baseline set plus six authoring features (footnotes,
  form fields, equations, charts, check boxes, edit plans), reduced scope (5.7.0 · 2026-08-03)
- Hancom opens 476/476: the full frozen corpus (N=497) (3.4.1 · 2026-07-19)
- Byte preservation of untouched regions 497/497, personal-information leaks 0
- Render-verified 416/476: the 43 cases where Hancom itself refuses PDF export are counted, not dropped.

<p align="center">
  <img src="https://raw.githubusercontent.com/airmang/python-hwpx/main/docs/assets/hancom-open-generated.png" width="760" alt="An HWPX document generated with python-hwpx inside ChatGPT, opened in real Hancom Office">
</p>
<p align="center"><sub>A document generated inside a ChatGPT runtime, opened in real Hancom Office.</sub></p>

Full figures and caveats are in [measured corpus metrics](https://airmang.github.io/python-hwpx/corpus-metrics.html),
per-feature grades in the [support matrix](docs/support-matrix.md). These numbers measure how Hangul takes the
files we produce. How well a parser reads documents is a separate measure.

Development status is Beta. What stays backward compatible is listed in [stable API](docs/stable-api.md);
`hwpx.experimental` and the features marked experimental above may change.

## Where you can run it

| Environment | How |
|---|---|
| Local or server Python | `pip install python-hwpx` (scripts, batch jobs, CI) |
| Python automation (no MCP) | `pip install python-hwpx-automation` (authoring, form filling and verification workflows) |
| A plain ChatGPT conversation | Upload the `.hwpx` together with the [Release wheel](https://github.com/airmang/python-hwpx/releases/latest) and install it in the chat ([guide](docs/ai-assistants.md)) |
| ChatGPT MCP app | Register the MCP adapter from [`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation) as a connector |
| Codex marketplace plugin | Install [`hwpx-plugins`](https://github.com/airmang/hwpx-plugins) |
| Claude Code · Hermes · OpenClaw | Register the same MCP server in each client ([`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation)) |

<p align="center">
  <img src="https://raw.githubusercontent.com/airmang/python-hwpx/main/docs/assets/chatgpt-formfill.png" width="760" alt="Uploading an .hwpx form to a plain ChatGPT conversation and getting back a filled document with the original formatting preserved">
</p>
<p align="center"><sub>In a plain ChatGPT conversation, upload a form <code>.hwpx</code> and ask; the document comes back with its formatting intact and only the values filled in.</sub></p>

The Python runtime in a ChatGPT chat cannot reach PyPI. Upload the `python_hwpx-*.whl` from the
[latest Release](https://github.com/airmang/python-hwpx/releases/latest) together with your document and ask:

```text
Install the attached python_hwpx-*.whl with pip
(pip install /mnt/data/python_hwpx-*.whl), then open this .hwpx file
with the python-hwpx library.
Keep the form and formatting as-is, change only ○○, and return a new file.
```

Everything from install to the result file happens inside the conversation, so you do not need Python on
your machine. The wheel's only dependency is `lxml`; if the runtime lacks it, upload an lxml wheel too.
An instruction block for agents is in [Using python-hwpx in AI chat sandboxes](docs/ai-assistants.md), and an
[llms.txt](https://airmang.github.io/python-hwpx/llms.txt) helps AI tools learn the real API.

| | Repo | Role |
|---|---|---|
| 📦 | [`python-hwpx`](https://github.com/airmang/python-hwpx) | Pure-Python engine that reads, edits, and creates HWPX documents |
| 🔌 | [`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation) | Authoring & form-filling workflows, the `hwpx` CLI, optional MCP server |
| 🎯 | [`hwpx-plugins`](https://github.com/airmang/hwpx-plugins) | Plugin/skill bundle that helps agents pick the right tool |

## Comparison

| | python-hwpx | pyhwpx | pyhwp |
|---|---|---|---|
| **Formats** | `.hwpx`, `.hwp` (HWP 5.0), read and write | `.hwpx` | `.hwp` (v5 binary) |
| **Hancom install** | Not required | Required (Windows COM) | Not required |
| **Platforms** | Linux / macOS / Windows / CI | Windows only | Linux / macOS / Windows |
| **Edit and create** | ✅ | ✅ (Hangul does it) | Mostly read |
| **Page estimate without Hangul** | ✅ (experimental) | Hangul computes it | ❌ |
| **AI agent integration (MCP)** | ✅ (via automation) | ❌ | ❌ |

## Known limitations

- `add_shape()` and `add_control()` are low-level escape hatches: a document saved as-is will not open in
  Hancom, and the only signal is a warning at call time. For shapes use the helpers that write every child
  Hancom needs: `add_line()`, `add_rectangle()`, `add_ellipse()`, `add_arc()`, `add_polygon()`,
  `add_curve()`, `add_connector()`, `add_container()` (groups); for controls, `add_column_definition()`,
  `add_bookmark()` and `add_hyperlink()`.
- Pictures take brightness, contrast, grayscale, black and white, transparency, a solid border, cropping
  (`crop`), and a shadow, glow, soft edge or reflection (`shadow`, `glow`, `soft_edge`, `reflection`) as
  `add_picture()` arguments. Flipping and rotation are not supported yet.
- Page estimates and line layout writing are experimental. When a document uses something they do not
  follow, such as a character grid, they return the reason instead of an estimate.
- Encrypted HWPX files and password-protected or distribution HWP files are refused (`Hwp5Error` for HWP).

## Contributing

[help wanted](https://github.com/airmang/python-hwpx/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) ·
[roadmap](https://github.com/airmang/python-hwpx/milestones) ·
[Discussions](https://github.com/airmang/python-hwpx/discussions) ·
[CONTRIBUTING](CONTRIBUTING.md)

New to HWPX internals? Start with the [internals field guide](docs/internals/): layout caches, TOC fields,
OPC repacking and other behaviors checked against real Hangul. The stable public surface is listed in
[stable API](docs/stable-api.md), and layer ownership in the [product-boundary contract](docs/architecture/product-boundary.md).

## Acknowledgements

This project is indebted to the following open standards and projects.

- [OWPML, Open Word-Processor Markup Language (KS X 6101)](https://www.kssn.net/search/stddetail.do?itemNo=K001010119985): the Korean industrial standard HWPX is built on
- [hancom-io/hwpx-owpml-model](https://github.com/hancom-io/hwpx-owpml-model): OWPML element-structure reference model
- [neolord0/hwpxlib](https://github.com/neolord0/hwpxlib): sample corpus
- [edwardkim/rhwp](https://github.com/edwardkim/rhwp): inspired the idempotency and verification gates; we also use it to check compatibility with other viewers
- The Korean government office suite: official-document workflow ideas

## License · Maintainer

Apache-2.0 ([LICENSE](LICENSE) · [NOTICE](NOTICE)) · Kohkyuhyun [@airmang](https://github.com/airmang) · [kokyuhyun@hotmail.com](mailto:kokyuhyun@hotmail.com)
