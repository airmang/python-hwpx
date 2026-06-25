# reader-robustness fixtures — intentionally non-standard HWPX

These `.hwpx` files are **sample data vendored for testing** under the project's
clean-room policy (Constitution VIII: "Sample data may be vendored with NOTICE
attribution; ideas may be absorbed. Oracles and references are consulted, not
cloned."). No source **code** is copied — only public document files are vendored
as regression inputs.

Downloaded 2026-06-25 from public GitHub repositories. Each remains under its
upstream license; see the source repo. If any rights holder objects, the file
will be removed.

| Local file | Source repo | Upstream path |
|---|---|---|
| `irb_form_blank.hwpx` | [nathankim0/easy-hwp](https://github.com/nathankim0/easy-hwp) | `IRB서식_샘플.hwpx` |
| `irb_form_filled.hwpx` | [nathankim0/easy-hwp](https://github.com/nathankim0/easy-hwp) | `IRB서식_완성.hwpx` |

## Why these live here, not in `m2_corpus/`

Unlike the M2 oracle corpus (whose entry bar is "opens clean in real Hancom"),
these are **hand-authored minimal IRB forms that real Hancom rejects as
손상(corrupt)** — they ship no `Contents/header.xml` (the part holding the char/
para/style definitions `section0.xml` references) and carry XML `<!-- comment -->`
/ processing-instruction nodes as direct children of `<hs:sec>`. Our tolerant
reader must still open them and surface the real paragraphs; a strict loader need
not. **The Hancom rejection is the point** — these guard that the reader/validator
do not crash on real-world non-standard input. They are therefore **not** oracle
inputs and must not be "repaired" to open in Hancom (that would destroy their
purpose).

Used by:

- `tests/test_comment_node_robustness.py` — reader tolerates comment/PI nodes.
- `tests/test_validator_comment_nodes.py` — `validate_document` does not crash on
  comment-bearing sections.
