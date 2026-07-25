# Migrating to python-hwpx 5.0

`python-hwpx` 5.0 is the HWPX object model, OPC/OXML, and the format-native
primitives built on them. The application workflows that grew inside the library
— agent editing, document authoring, form-fill, eval-plan, exam typesetting,
institutional lint, and Hancom rendering — now live in `hwpx-mcp-server`, which
has owned their canonical implementation since the 4.x line.

Nothing here is discontinued. Every removed import has a named replacement, and
`python-hwpx` 4.x keeps all of it for anyone who needs time.

## If you use the MCP server or the skill

Nothing to do. The tool names, schemas, and results are unchanged; only the
implementation's address moved, and it moved before this release.

## If you import `hwpx` directly

Install the companion package and change the import path:

```bash
pip install hwpx-mcp-server
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
| `hwpx.exam.compose_exam_into_form` | `hwpx_mcp_server.office.exam.compose.compose_exam_into_form`, or the MCP `compose_exam` tool |
| `hwpx.exam.measure` | `hwpx_mcp_server.office.exam.measure`, or the MCP `verify_question_splits` tool |
| `hwpx.exam.parser` | `hwpx_mcp_server.office.exam.parser` |
| `hwpx.exam.ir` | `hwpx_mcp_server.office.exam.ir` |
| `hwpx.exam.profile` | `hwpx_mcp_server.office.exam.profile` |

The `examples/compose_exam.py` script is removed with it; the skill's exam
workflow covers the same ground through the MCP tools.

*Why it moved:* laying out exam questions to fit a specific form is a document
genre, not a property of the HWPX format. The primitives it stands on — tables,
paragraphs, page geometry, package preservation — are all still core, which is
why the MCP owner builds on them rather than carrying its own copy.
