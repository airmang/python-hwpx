<p align="center">
  <h1 align="center">python-hwpx</h1>
  <p align="center">
    <strong>A pure-Python library to read, edit, and create HWPX — no Hancom Office required</strong>
  </p>
  <p align="center">
    <a href="https://pypi.org/project/python-hwpx/"><img src="https://img.shields.io/pypi/v/python-hwpx?color=blue&label=PyPI" alt="PyPI"></a>
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
Windows, macOS, Linux, and CI.

| | Repo | Role |
|---|---|---|
| 📦 | **`python-hwpx`** | Pure-Python HWPX core (this repo) |
| 🔌 | [`hwpx-mcp-server`](https://github.com/airmang/hwpx-mcp-server) | Drive HWPX from MCP clients (Claude Desktop, etc.) |
| 🎯 | [`hwpx-plugin`](https://github.com/airmang/hwpx-plugins) | Plugin / skill bundle for agents |

## Getting started

```bash
pip install python-hwpx      # Python 3.10+
```

```python
from hwpx import HwpxDocument

doc = HwpxDocument.open("report.hwpx")
doc.add_paragraph("A paragraph added by automation.")
doc.save_to_path("report-edited.hwpx")
```

## What it does

- **Read & extract** — text/HTML/rich Markdown export (formatting, nested tables, footnotes preserved), XPath object search
- **Edit** — paragraphs, tables, images, headers/footers, memos, footnotes; line spacing, margins, page numbers
- **Form filling** — label/path-based cell filling, byte-preserving structural edits (rows, columns, autofit, shrink-to-fit)
- **Create** — composable builder, official-document lint and approval blocks, photo sheets, nameplates, org charts, mail merge, comparison tables
- **Tracked changes & TOC** — redline authoring, native table of contents and cross-references
- **Verify & safety** — XSD/package validation CLIs, open-safety gate, a receipt on every write (`MutationReport`)

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

## Comparison

| | python-hwpx | pyhwpx | pyhwp |
|---|---|---|---|
| **Target format** | `.hwpx` (OWPML/OPC) | `.hwpx` | `.hwp` (v5 binary) |
| **Hancom install** | Not required | Required (Windows COM) | Not required |
| **Cross-platform** | ✅ Linux / macOS / Windows / CI | ❌ Windows only | ✅ |
| **Edit/create API** | ✅ | ✅ (COM) | ❌ mostly read |
| **AI agent integration (MCP)** | ✅ | ❌ | ❌ |

> HWP (v5 binary) files are not supported. Convert to HWPX in Hancom Office first.

## Known limitations

- `add_shape()` / `add_control()` do not generate every sub-element Hancom requires.
- Fully automatic generation of `<hp:pic>` picture objects is not provided.
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
