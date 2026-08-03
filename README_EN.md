<p align="center">
  <h1 align="center">python-hwpx</h1>
  <p align="center">
    <strong>A pure-Python library to read, edit, and create HWPX — no Hancom Office required</strong>
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

You don't need Hancom Office. HWPX is a ZIP+XML (OWPML) format, so pure Python
is enough to read, edit, and create documents — on Windows, macOS, Linux, CI,
and **inside a ChatGPT chat wherever Python runs**. Existing documents are
edited in place (untouched regions stay byte-identical), and new documents come
out in a form real Hancom Office opens.

<p align="center">
  <img src="https://raw.githubusercontent.com/airmang/python-hwpx/main/docs/assets/chatgpt-formfill.png" width="760" alt="Uploading an .hwpx form to a plain ChatGPT conversation and getting back a filled document with the original formatting preserved">
</p>
<p align="center"><sub>A plain ChatGPT conversation — upload a form <code>.hwpx</code>, ask in natural language, and get the filled document back with its formatting intact.</sub></p>

**Try it in ChatGPT** — upload your document along with a request like this:

```text
Open this .hwpx file with the python-hwpx library
(install it with: pip install python-hwpx).
Keep the form and formatting as-is, change only ○○, and return a new file.
```

Install to result file, all inside the conversation — no Python on your machine needed.
An [llms.txt](https://airmang.github.io/python-hwpx/llms.txt) is published so AI tools learn the real API.

| | Repo | Role |
|---|---|---|
| 📦 | [`python-hwpx`](https://github.com/airmang/python-hwpx) | Pure-Python engine that reads, edits, and creates HWPX documents |
| 🔌 | [`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation) | Authoring & form-filling workflows, the `hwpx` CLI, optional MCP server |
| 🎯 | [`hwpx-plugins`](https://github.com/airmang/hwpx-plugins) | Plugin/skill bundle that helps agents pick the right tool |

## Getting started

```bash
pip install python-hwpx      # Python 3.10+
```

<!-- standalone-python-example -->

```python
from hwpx import HwpxDocument

doc = HwpxDocument.new()
doc.add_heading("2026 Operating Plan", level=1)
doc.add_paragraph("A. Background", style="개요 2")
doc.save_to_path("plan.hwpx")
```

Styles are addressed by name, and a typo is reported at the call, not at save.
To edit an existing file, start from `HwpxDocument.open("report.hwpx")`.

To build a document from scratch, start from `HwpxDocument.new()` and fill
paragraphs, tables, and headers through the same API. For higher-level
workflows — document authoring, form filling, exam typesetting — install
[`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation)
alongside it.

> For compatibility with existing install commands,
> `pip install "python-hwpx[visual]"` still works — but the `visual` extra is
> empty and installs no render/PDF dependencies. That runtime belongs to
> `python-hwpx-automation[oracle]`.

## What it does

- **Read & extract** — text/HTML/Markdown export (formatting, nested tables, footnotes preserved)
- **Edit** — paragraphs, tables, images, headers/footers, memos, footnotes; line spacing, margins, page numbers
- **Form filling** — find cells by label and change values only; structural edits (rows, columns) stay byte-preserving
- **Create & batch** — new-document authoring, TOCs and cross-references, mail merge, text diff, tracked changes (redline)
- **Verify & safety** — package-structure validation CLI, open-safety gate, a receipt on every save (`MutationReport`)

More: [five-minute quickstart](docs/quickstart.md) · [usage guide](docs/usage.md) · [API reference](https://airmang.github.io/python-hwpx/) · [examples](docs/examples.md)

### Form filling — values change, formatting doesn't

```python
doc = HwpxDocument.open("application.hwpx")
result = doc.fill_by_path({
    "성명 > right": "홍길동",
    "소속 > right": "플랫폼팀",
})
doc.save_to_path("application-filled.hwpx")
```

Cells are located by their labels; everything you didn't touch keeps its
original bytes.

### Every save comes with a receipt

```python
report = doc.save_to_path("out.hwpx", return_report=True)
print(report.actual_mode)        # "patch" — saved without rebuilding the document
print(report.preservation.untouched_part_payloads.to_dict())
                                 # {"verified": 17, "changed": 0}
```

If the requested preservation grade can't be honored, nothing is written
(fail-closed). Full rules: [Safe Write Contract](docs/safe-write-contract.md).

*Blocks without a **Standalone example** label take your existing document as
input. The per-example Python-block status is frozen in the
[execution ledger](docs/python-example-ledger.json).*

## Measured, not claimed

Whether the files we produce open in real Hancom Office is measured and
published as-is, with the measurement stack and date next to every figure:

- **Hancom opens 120/120 · render-verified 120/120** — the current stack
  (5.7.0 · real Hancom 12.0.0.3288 · 2026-08-03), reduced scope: a baseline
  stratum plus the six authoring surfaces added in 4.x/5.x (footnotes, form
  fields, equations, charts, check boxes, edit plans). Receipts carry a
  per-row bucket, so every split reproduces with one line of `jq`
- **Hancom opens 476/476** — the full frozen corpus (N=497), measured on
  3.4.1 · real Hancom 12.0.0.3288 · 2026-07-19
- **Byte preservation of untouched regions 497/497** · personal-info 0-leak
- **Render-verified 416/476** — the 43 cases where Hancom itself refuses PDF export are counted, not hidden
- Full figures and caveats: [measured corpus metrics](https://airmang.github.io/python-hwpx/corpus-metrics.html) · per-capability grades: [support matrix](docs/support-matrix.md)

<p align="center">
  <img src="https://raw.githubusercontent.com/airmang/python-hwpx/main/docs/assets/hancom-open-generated.png" width="760" alt="An HWPX document generated with python-hwpx inside ChatGPT, opened in real Hancom Office">
</p>
<p align="center"><sub>A document generated inside a ChatGPT runtime, opened in real Hancom Office.</sub></p>

Development status is Alpha — the API may change.

> These numbers are on the *output acceptance* axis (does real Hancom accept the
> files we produce) — a different axis from document *parsing recall*, so do not
> compare them side by side with parser-project figures.

## Where you can run it

| Environment | What to do |
|---|---|
| A plain ChatGPT conversation | Upload the `.hwpx`, `pip install python-hwpx`, edit it in Python, get the file back |
| Local or server Python | `pip install python-hwpx` — scripts, batch jobs, CI |
| Python automation (no MCP) | `pip install python-hwpx-automation` — authoring, form filling, and verification workflows as plain Python |
| ChatGPT MCP app | Register the MCP adapter from [`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation) as a connector |
| Codex marketplace plugin | Install [`hwpx-plugins`](https://github.com/airmang/hwpx-plugins) |
| Claude Code · Hermes · OpenClaw | Register the same MCP server in each client ([`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation)) |

In practice: uploading an `.hwpx` to a plain ChatGPT conversation and asking for
python-hwpx produced a successful PyPI install, and the edited document came
back. Python execution and network access vary by plan and settings; where the
runtime has no network, uploading the wheel alongside the document gives the
same journey via an offline install.

## Comparison

| | python-hwpx | pyhwpx | pyhwp |
|---|---|---|---|
| **Target format** | `.hwpx` (OWPML/OPC) | `.hwpx` | `.hwp` (v5 binary) |
| **Hancom install** | Not required | Required (Windows COM) | Not required |
| **Cross-platform** | ✅ Linux / macOS / Windows / CI | ❌ Windows only | ✅ |
| **Edit/create API** | ✅ | ✅ (COM) | ❌ mostly read |
| **AI agent integration (MCP)** | ✅ via companion | ❌ | ❌ |

> HWP (v5 binary) files are not supported. Convert to HWPX in Hancom Office first.

## Known limitations

- `add_shape()` / `add_control()` are low-level escape hatches — a document
  saved as-is will not open in Hancom, and the only signal is a warning at call
  time. For shapes use `add_line()` / `add_rectangle()` / `add_ellipse()`.
- Pictures: simple picture objects can be generated; complex ones (groups,
  effects) cannot.
- Encrypted HWPX files are not supported.

## Contributing

[help wanted](https://github.com/airmang/python-hwpx/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) ·
[roadmap](https://github.com/airmang/python-hwpx/milestones) ·
[Discussions](https://github.com/airmang/python-hwpx/discussions) ·
[CONTRIBUTING](CONTRIBUTING.md)

New to HWPX internals? Start with the [internals field guide](docs/internals/) —
layout caches, TOC fields, OPC repacking and other behaviors verified against
real Hancom. The stable public surface is listed in
[stable API](docs/stable-api.md), and layer ownership in the
[product-boundary contract](docs/architecture/product-boundary.md).

## Acknowledgements

This project is indebted to the following open standards and projects.

- **[OWPML — Open Word-Processor Markup Language (KS X 6101)](https://www.kssn.net/search/stddetail.do?itemNo=K001010119985)** — the Korean industrial standard HWPX is built on
- **[hancom-io/hwpx-owpml-model](https://github.com/hancom-io/hwpx-owpml-model)** — OWPML element-structure reference model · **[neolord0/hwpxlib](https://github.com/neolord0/hwpxlib)** — oracle sample corpus
- **[edwardkim/rhwp](https://github.com/edwardkim/rhwp)** — inspiration for idempotency and verification gates
- **the Korean government office suite** — official-document workflow ideas

## License · Maintainer

Apache-2.0 ([LICENSE](LICENSE) · [NOTICE](NOTICE)) — **Kohkyuhyun** [@airmang](https://github.com/airmang) · [kokyuhyun@hotmail.com](mailto:kokyuhyun@hotmail.com)
