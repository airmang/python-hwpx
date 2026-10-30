# EqEdit font-command boundaries

EqEdit font commands apply at the beginning of an alphabetic word even without
a space: `rmA` means `rm A`, `itx` means `it x`, and `boldx` means `bold x`.
Commands can follow one another without spaces (`rmitA`). A prefix inside an
ordinary word (`armA`) remains part of that word. Quotes keep the entire run
literal. The LaTeX writer therefore quotes ordinary identifiers such as `rmA`
and `itself`; a reader must distinguish those identifiers from actual commands.

The observed spellings are `rm`/`Rm`/`RM`, `it`/`It`/`IT` and
`bold`/`Bold`/`BOLD`. Arbitrary mixed case (`rM`, `iT`, `bOlD`) is literal.
The converter and size estimator share the same tokenization and spelling set.

## Observer and limits

On2026-10-30, Hancom Office HWP for macOS12.30.0 build6446 opened, displayed
and saved three synthetic documents containing151 equations. The primary
matrix compares attached/spaced pairs at baseUnit1000 and1100, including
uppercase/lowercase letters, Greek symbols, Korean, digits, groups and scripts.
The boundary matrix checks repeated switches, internal prefixes and quoted
controls; the case matrix covers all24 case spellings of the three commands.
The committed fixtures preserve every saved section byte. Metadata/preview
redaction and exact hashes are described in the fixture README and
`tests/data/equation_font_boundary_provenance.json`.

For example, at baseUnit1100 Hancom saved both `rmA` and `rm A` with
width742, height1125 and baseline85; the former estimator assigned2431 to
`rmA`. The correction makes their estimated boxes equal. Estimated glyph
metrics remain approximate; it does not fit every stored box exactly or
establish behavior on every Hancom platform. No PDF export was used.

General keyword-prefix tokenization beyond font commands remains separate:
Hancom displays `boldness` and `bold ness` as a bold not-equal symbol followed
by `ss` because of `ne`; the general `ne` prefix rule is not added here.
Quoted-text font semantics outside the affected identifiers are unchanged.
