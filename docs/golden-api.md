# Golden API — core-only common tasks

The Golden API is the executable adoption contract for `python-hwpx`. It is not
another public facade. It records the ordinary tasks that must remain possible
with a direct `python-hwpx` install and without MCP, a skill, a genre profile,
or agent orchestration.

The machine-readable scenario list is
`tests/data/golden_api_contract.json`; `tests/test_golden_api.py` executes every
scenario.

```python
from hwpx import HwpxDocument

with HwpxDocument.new() as document:
    document.add_paragraph("Hello HWPX")
    table = document.add_table(2, 2)
    table.cell(0, 0).text = "Name"
    table.cell(0, 1).text = "Value"
    document.save_to_path("example.hwpx")
```

## Contract scenarios

| Area | Scenarios |
|---|---|
| Lifecycle | new document, open bytes, context manager |
| Text | add paragraph, iterate runs, replace text, create run style |
| Formatting | paragraph format, list format |
| Tables | add table, merge cells, map tables, find a cell by label |
| Sections/layout | add/remove section, page setup, header/footer, page number |
| Navigation | bookmark, hyperlink |
| Reading | export text, export Markdown |
| Safety/persistence | validate, save/reopen path, save/reopen stream, preserve all unmodified package parts |

The contract has 25 scenarios. A scenario may change only with a
reviewed public API decision. Application workflows such as evaluation-plan
fill, genre authoring, PII policy, or agent blueprint replay belong to
`python-hwpx-automation` tests instead.
