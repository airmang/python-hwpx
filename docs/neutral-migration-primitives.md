# Neutral primitives for application policy

These additions let applications own document-plan interpretation, heading
guessing and caption selection while core keeps document reading and safe
format edits. They do not remove or warn on any existing6.x entry point.
(7.0 moved the reference consistency lint and the Markdown exporter, with its
heading detector, to python-hwpx-automation; the other primitives stay.)

## Paragraph texts

```python
from hwpx.tools.doc_diff import paragraph_texts

paragraphs = paragraph_texts(document_or_path)
```

The module-level reader accepts an open document, path, text, paragraph sequence
or mapping with `paragraphs`/`text`. The `paragraphs` key takes precedence.
Whitespace and error semantics match the existing generic diff source reader.
The reader rejects application plans containing only `sections`; applications
must normalize their own plan schema. Existing diff/reference entry points
still accept their legacy plan inputs without new warnings.

## Heading detector — moved with the Markdown export (7.0)

The rich Markdown exporter and its `heading_detector=` callback moved to
`python-hwpx-automation` in 7.0 (`hwpx_automation.markdown.to_markdown(doc,
rich=True, heading_detector=...)`; document ingest in `hwpx_automation.ingest`).
The callback keeps its contract there: it receives formatted paragraph/cell
Markdown and returns a Markdown heading or `None`.

## Caller-selected trailing text

```python
from hwpx.table_patch import strip_trailing_table_text

result = strip_trailing_table_text(
    source, predicate=lambda text: text == "Remove this label",
    output_path=destination,
)
```

The predicate receives stripped XML-decoded text after the last direct table in
its paragraph, before that paragraph's actual line cache. Only paragraph-family
text/run elements are eligible. Foreign elements, controls, paragraph/table
boundaries, missing/lookalike caches and unwrapped non-whitespace text are
preserved. Namespace aliases and supported namespace versions retain their
original bytes. A secure parsed tree is bound to the original byte spans once;
the selector never serializes the section or repeatedly scans beyond a wrapper.

The result is the existing `CellFillResult`; untouched ZIP members stay byte
identical. Predicate exceptions propagate before publishing an output. The old
`strip_trailing_table_captions` entry point keeps its exact6.x selection/splice
behavior as a frozen compatibility policy; it shares package patch/finalization
machinery but does not adopt the new selector's stricter rules.

These are generic core capabilities. They do not implement application policy
or complete the multi-major compatibility schedule tracked in issue565.
