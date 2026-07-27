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

Existing documents are edited in place — untouched regions stay byte-identical.
New documents are produced in a form real Hancom Office accepts. HWPX is a
ZIP+XML (OWPML/OPC) format, so everything runs in pure Python on
Windows, macOS, Linux, and CI. Neither Hancom Office nor Windows is required,
so **you can create and edit HWPX documents from inside a ChatGPT chat** —
anywhere Python runs.

| | Repo | Role |
|---|---|---|
| 📦 | **`python-hwpx`** | Pure-Python HWPX core (this repo) |
| 🔌 | [`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation) | Document workflows, MCP server, and the `hwpx` application CLI |
| 🎯 | [`hwpx-plugin`](https://github.com/airmang/hwpx-plugins) | Plugin / skill bundle for agents |

The [product-boundary contract](docs/architecture/product-boundary.md) pins the
5.0 ownership split, removed-path non-resurrection rule, and import allowlist.

> **Python-block status:** every Python block in this current manual is frozen
> in the [execution ledger](docs/python-example-ledger.json) with an exact source
> digest. A block without a **Standalone example** label requires an existing
> input or prior walkthrough state and is not presented as a copy-paste program.

## Getting started

```bash
pip install python-hwpx      # Python 3.10+
```

> **5.x compatibility extra:** `pip install "python-hwpx[visual]"` remains
> accepted so existing install commands do not fail, but the `visual` extra is
> empty and installs no PDF or imaging dependencies. Render/PDF imaging runtime
> belongs to `python-hwpx-automation[oracle]`.

```python
from hwpx import HwpxDocument

doc = HwpxDocument.open("report.hwpx")
doc.add_paragraph("A paragraph added by automation.")
doc.save_to_path("report-edited.hwpx")
```

To build a document from scratch, start from `HwpxDocument.new()` and fill
paragraphs, tables, and headers through the same API, then `save_to_path()`.

For higher-level workflows — document authoring, form filling, exam
typesetting — install
[`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation)
alongside it. It runs in the same environment without the MCP SDK.

## What it does

- **Read & extract** — text/HTML/rich Markdown export (formatting, nested tables, footnotes preserved), XPath object search
- **Edit** — paragraphs, tables, images, headers/footers, memos, footnotes; line spacing, margins, page numbers
- **Form filling** — label/path-based cell filling, byte-preserving structural edits (rows, columns, autofit, shrink-to-fit)
- **Create & batch** — paragraphs, tables, images, TOCs and cross-references; explicit-sanitizer mail merge and text diff
- **Tracked changes & TOC** — redline authoring, native table of contents and cross-references
- **Verify & safety** — package-structure validation CLI, open-safety gate, a receipt on every write (`MutationReport`) — the bundled XSDs are permissive structural schemas, not full OWPML validation

More: [usage guide](docs/usage.md) · [API reference](https://airmang.github.io/python-hwpx/) · [examples](docs/examples.md)

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

## Measured, not claimed

Every output is measured against real Hancom Office and published as-is
(frozen corpus, N=497):

- **Hancom opens 476/476 all-pass** — real Hancom opens every file we produce
- **Byte preservation of untouched regions 497/497** · personal-info 0-leak
- **Render-verified 416/476** + honesty bucket of 43 — cases where Hancom itself refuses PDF export are counted, not hidden
- Low numbers are published as-is — full figures and caveats: [measured corpus metrics](https://airmang.github.io/python-hwpx/corpus-metrics.html)

What works and what doesn't is graded per capability in the
[support matrix](docs/support-matrix.md). Development status is Alpha — the API
may change.

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

Measured: in a plain ChatGPT conversation, uploading an `.hwpx` and asking for
python-hwpx produced a successful PyPI install, and the edited document came
back. Python execution and network access vary by plan and settings, so this is
not a guaranteed path on every account. Where the runtime has no network,
uploading the wheel alongside the document gives the same journey via an offline
install.

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

- `add_shape()` / `add_control()` are low-level escape hatches and do not generate
  every sub-element Hancom requires. Saving one as-is produces a file Hancom
  cannot open, and the only signal is a warning at call time — neither the save
  nor package validation blocks it. For shapes use `add_line()` /
  `add_rectangle()` / `add_ellipse()`.
- Pictures: simple picture objects can be generated; complex ones (groups,
  effects) cannot.
- Encrypted HWPX files are not supported.

## Contributing

[help wanted](https://github.com/airmang/python-hwpx/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) ·
[roadmap](https://github.com/airmang/python-hwpx/milestones) ·
[Discussions](https://github.com/airmang/python-hwpx/discussions) ·
[internals field guide](docs/internals/) ·
[CONTRIBUTING](CONTRIBUTING.md)

New to HWPX internals? Start with the [internals field guide](docs/internals/) —
layout caches, TOC fields, OPC repacking and other behaviors verified against
real Hancom.

## Acknowledgements

This project is indebted to the following open standards and projects.

- **[OWPML — Open Word-Processor Markup Language (KS X 6101)](https://www.kssn.net/search/stddetail.do?itemNo=K001010119985)** — the Korean industrial standard HWPX is built on
- **[hancom-io/hwpx-owpml-model](https://github.com/hancom-io/hwpx-owpml-model)** — OWPML element-structure reference model · **[neolord0/hwpxlib](https://github.com/neolord0/hwpxlib)** — oracle sample corpus
- **[edwardkim/rhwp](https://github.com/edwardkim/rhwp)** — inspiration for idempotency and verification gates
- **the Korean government office suite** — official-document workflow ideas

## License · Maintainer

Apache-2.0 ([LICENSE](LICENSE) · [NOTICE](NOTICE)) — **Kohkyuhyun** [@airmang](https://github.com/airmang) · [kokyuhyun@hotmail.com](mailto:kokyuhyun@hotmail.com)
