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
New documents are produced in a form real Hancom Office accepts, and every output
is measured against real Hancom and published as-is —
[measured corpus metrics](https://airmang.github.io/python-hwpx/corpus-metrics.html).

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
- **Create** — composable builder, official-document lint and approval blocks, photo sheets, nameplates, org charts, mail merge, old-vs-new comparison tables
- **Tracked changes & TOC** — redline authoring, native table of contents and cross-references
- **Verify & safety** — XSD/package validation CLIs, open-safety gate, a receipt on every write (`MutationReport`)

More: [usage guide](docs/usage.md) · [API reference](https://airmang.github.io/python-hwpx/) · [examples](docs/examples.md)

## Why you can trust it

- [Safe Write Contract](docs/safe-write-contract.md) — the preservation grade is decided before writing, and a measured receipt of actual changes is returned (fail-closed)
- [Support matrix](docs/support-matrix.md) — real support grades per capability; what doesn't work is graded too
- [Measured corpus metrics](https://airmang.github.io/python-hwpx/corpus-metrics.html) — exhaustive real-Hancom measurements with caveats; low numbers are published as-is

Development status is Alpha — the API may change.

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

## Acknowledgements

[OWPML (KS X 6101)](https://www.kssn.net/search/stddetail.do?itemNo=K001010119985) — underlying standard ·
[hancom-io/hwpx-owpml-model](https://github.com/hancom-io/hwpx-owpml-model) — structure reference ·
[neolord0/hwpxlib](https://github.com/neolord0/hwpxlib) — oracle samples ·
[edwardkim/rhwp](https://github.com/edwardkim/rhwp) — verification-gate inspiration ·
the Korean government office suite — workflow ideas

## License · Maintainer

Apache-2.0 ([LICENSE](LICENSE) · [NOTICE](NOTICE)) — **Kohkyuhyun** [@airmang](https://github.com/airmang) · [kokyuhyun@hotmail.com](mailto:kokyuhyun@hotmail.com)
