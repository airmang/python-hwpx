# SPDX-License-Identifier: Apache-2.0
"""Rebuild ``docs/_extra/element-census.json`` from an accessible real-file corpus.

This is the generator the 2026-08-04 completeness audit found missing
(``docs/2026-08-04-completeness-audit-verdict.md`` §3-C1): the previous
census (166 "real" files, 84 "unknown") was produced by a one-off script that
was never committed, so nobody after that session could reproduce it, extend
it, or even list what the 166 files were.

**Population redefinition (explicit, not silent).** The original 166/84 split
traced back to two sources: the vendored ``tests/fixtures/hwpxlib_corpus``
(47 files, still here, still reproducible) and ~119 "private real files" that
were never checked into any repo this workspace can reach. Those are gone —
this generator does not try to guess what they were. Instead it defines the
census population as whatever ``--corpus`` roots are passed on the command
line, recursively globbed for ``*.hwpx``, plus the always-included vendored
hwpxlib corpus. The script that produced *this* repo's checked-in
``docs/_extra/element-census.json`` snapshot was run once with an additional
``--corpus`` pointing at the maintainer's private real-world Hancom documents
(school administrative paperwork, review reports, etc.) — genuinely
Hancom-authored files, not anything this pipeline generated. That directory
is **not** committed and its path is deliberately not recorded anywhere in
this file or its output (privacy) — only the aggregate file count and a
prose description of what kind of documents they are. Anyone without access
to that directory can still regenerate the *hwpxlib-only* slice
deterministically; the full snapshot is reproducible only by the maintainer.
That asymmetry is the honest state of the world, not something to paper
over — see ``docs/coverage-ledger.md``'s "수리 기록" section for the numbers.

**Scope: all parts, all namespaces, unknowns explained.** Unlike the
predecessor (hp:/hh:/hc: only — spec 056's method note), this scans every
XML-ish part inside each package (``*.xml``, ``*.hpf``, ``*.rdf`` — anything
that is not a known binary part) and tallies **every** namespace it finds:

* The 7 OWPML XSD families (hp/hh/hc/hs/hm/hhs) plus the ``app``/``version``
  families that ``hwpx.oxml.namespaces`` already registers but that the OWPML
  XSDs under ``DevDoc/OWPML SCHEMA/`` do not cover (``ha:*`` in
  ``settings.xml``, ``hv:HCFVersion`` in ``version.xml``) — these become
  first-class element rows in the ledger, same as hp/hh/hc.
* Everything else (OPF packaging: ``opf:``/``dc:``/``rdf:``; ODF config in
  ``settings.xml``: ``config:``; embedded OOXML DrawingML charts under
  ``Chart/``; Hancom's own ``ooxmlchart:``/``hwpunitchar:`` extensions) is
  **foreign to the OWPML element schema this ledger measures** — it is
  recorded in ``foreignNamespaces`` (URI → file count) so it stays *visible*
  instead of silently vanishing the way it did before, but it does not
  become per-element ledger rows, because there is no OWPML schema surface
  for coverage_ledger.py to compare it against.

Files that fail to open as a zip, or whose zip has no XML part this script
can parse at all, land in ``unknownFiles`` with a reason string — never a
silent drop from the denominator.

**Unnamespaced elements.** A handful of real Hancom-authored roots carry no
namespace prefix at all even though their OWPML XSD family is namespaced —
e.g. ``Contents/masterpageN.xml`` roots are emitted as bare ``<masterPage>``,
not ``<hm:masterPage>``. Attributing that silently to ``hm:masterPage``
would be exactly the kind of unlabelled merge ``coverage_ledger.py``'s
methodology notes already refuse to do for ``hc:pt0`` vs ``hp:pt0`` drift, so
these are recorded separately in ``unnamespacedElements`` (bare tag → file
count) rather than folded into ``real_element_filecounts``.

**Attribute axis (minimal).** For every observed element this also records
the *set* of attribute names seen across the corpus (not full value
frequency — spec 056 promised element+attribute frequency and only ever
shipped element frequency; this closes the "attribute axis is entirely
unmeasured" gap at the cheapest honest level: presence, not distribution).

Usage::

    python scripts/build_element_census.py                       # hwpxlib only
    python scripts/build_element_census.py --corpus ~/some/dir    # + extra root
    python scripts/build_element_census.py --check                # drift check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hwpx.oxml.namespaces import HWPML_COMPAT_ROOT_NAMESPACES, namespace_family  # noqa: E402

DEFAULT_OUTPUT = ROOT / "docs" / "_extra" / "element-census.json"
DEFAULT_REAL_CORPUS = ROOT / "tests" / "fixtures" / "hwpxlib_corpus"
DEFAULT_OURS_CORPUS = ROOT / "examples"

#: Same fallback the ledger generator uses: the ``version`` family has no XSD
#: family entry in ``hwpx.oxml.namespaces.NAMESPACE_URIS`` (a real registry
#: gap), so it is not resolvable via ``namespace_family()``.
_FALLBACK_URI_TO_PREFIX = {
    "http://www.hancom.co.kr/hwpml/2011/version": "hv",
    "http://www.hancom.co.kr/hwpml/2016/version": "hv",
    "http://www.owpml.org/owpml/2024/version": "hv",
}

#: Parts worth attempting to parse as XML. Everything else (BinData/*,
#: Preview/*, Scripts/*.js, mimetype, ...) is binary or non-XML and is
#: skipped without counting as a parse failure.
_XML_PART_SUFFIXES = (".xml", ".hpf", ".rdf")

SCHEMA_VERSION = "python-hwpx.element-census/v2"


def _family_to_prefix() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for prefix, uri in HWPML_COMPAT_ROOT_NAMESPACES.items():
        family = namespace_family(uri)
        if family is not None:
            mapping.setdefault(family, prefix)
    return mapping


def _resolve_prefix(uri: str, family_to_prefix: dict[str, str]) -> str | None:
    family = namespace_family(uri)
    if family is not None:
        return family_to_prefix.get(family)
    return _FALLBACK_URI_TO_PREFIX.get(uri)


class _FileScanResult:
    __slots__ = (
        "elements",
        "attributes_by_element",
        "foreign_namespaces",
        "unnamespaced_elements",
        "parsed_any_part",
    )

    def __init__(self) -> None:
        self.elements: set[tuple[str, str]] = set()
        self.attributes_by_element: dict[tuple[str, str], set[str]] = {}
        self.foreign_namespaces: set[str] = set()
        # Elements written with no namespace prefix at all -- e.g. real
        # Hancom output emits masterpage roots as bare ``<masterPage>``, not
        # ``<hm:masterPage>``, even though the OWPML 2024 XSD declares
        # master-page as a namespaced family. That is a genuine vocabulary
        # deviation (same species as hc:pt0 vs hp:pt0 -- see
        # coverage_ledger.py's methodology notes), not something to silently
        # attribute to a namespace the document never declared.
        self.unnamespaced_elements: set[str] = set()
        self.parsed_any_part = False


def _scan_file(path: Path, family_to_prefix: dict[str, str]) -> _FileScanResult | str:
    """Scan one ``.hwpx`` package. Returns a result, or a failure reason string."""

    result = _FileScanResult()
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        return f"not a valid zip: {type(exc).__name__}"

    with archive:
        xml_members = [
            info
            for info in archive.infolist()
            if info.filename.lower().endswith(_XML_PART_SUFFIXES)
        ]
        if not xml_members:
            return "zip has no .xml/.hpf/.rdf part"

        for info in xml_members:
            try:
                raw = archive.read(info.filename)
                tree = etree.fromstring(raw)
            except (etree.XMLSyntaxError, KeyError, OSError):
                continue
            result.parsed_any_part = True
            for node in tree.iter():
                tag = node.tag
                if not isinstance(tag, str):
                    continue  # comment/PI nodes expose a callable tag
                if not tag.startswith("{"):
                    result.unnamespaced_elements.add(tag)
                    continue
                uri, _, local = tag[1:].partition("}")
                prefix = _resolve_prefix(uri, family_to_prefix)
                if prefix is None:
                    result.foreign_namespaces.add(uri)
                    continue
                key = (prefix, local)
                result.elements.add(key)
                attrs = result.attributes_by_element.setdefault(key, set())
                for attr_name in node.attrib:
                    # Attribute names can themselves be namespaced
                    # (xml:space etc.) -- keep only the local part.
                    if isinstance(attr_name, str) and attr_name.startswith("{"):
                        attr_name = attr_name.split("}", 1)[1]
                    attrs.add(attr_name)

    if not result.parsed_any_part:
        return "all XML parts failed to parse"
    return result


def _iter_hwpx_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(p for p in root.rglob("*.hwpx") if p.is_file())


def _dedupe_by_content(paths: list[Path]) -> tuple[list[Path], int]:
    """Drop byte-identical duplicates (backup copies etc.) -- keep the first
    occurrence in sorted-path order for determinism."""

    seen: dict[str, Path] = {}
    duplicates = 0
    for path in paths:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in seen:
            duplicates += 1
            continue
        seen[digest] = path
    return sorted(seen.values()), duplicates


def _scan_corpus(
    roots: list[Path], family_to_prefix: dict[str, str]
) -> tuple[
    dict[tuple[str, str], int],
    dict[tuple[str, str], set[str]],
    dict[str, int],
    dict[str, int],
    dict[str, int],
    int,
    int,
]:
    """Returns (element_filecounts, attrs_by_element, foreign_ns_filecounts,
    unnamespaced_filecounts, unknown_reasons, real_file_count, duplicate_count)."""

    all_paths: list[Path] = []
    for root in roots:
        all_paths.extend(_iter_hwpx_files(root))
    all_paths = sorted(set(all_paths))
    deduped, duplicates = _dedupe_by_content(all_paths)

    element_filecounts: dict[tuple[str, str], int] = {}
    attrs_by_element: dict[tuple[str, str], set[str]] = {}
    foreign_ns_filecounts: dict[str, int] = {}
    unnamespaced_filecounts: dict[str, int] = {}
    unknown_reasons: dict[str, int] = {}
    real_count = 0

    for path in deduped:
        outcome = _scan_file(path, family_to_prefix)
        if isinstance(outcome, str):
            unknown_reasons[outcome] = unknown_reasons.get(outcome, 0) + 1
            continue
        real_count += 1
        for key in outcome.elements:
            element_filecounts[key] = element_filecounts.get(key, 0) + 1
            attrs_by_element.setdefault(key, set()).update(
                outcome.attributes_by_element.get(key, set())
            )
        for uri in outcome.foreign_namespaces:
            foreign_ns_filecounts[uri] = foreign_ns_filecounts.get(uri, 0) + 1
        for tag in outcome.unnamespaced_elements:
            unnamespaced_filecounts[tag] = unnamespaced_filecounts.get(tag, 0) + 1

    return (
        element_filecounts,
        attrs_by_element,
        foreign_ns_filecounts,
        unnamespaced_filecounts,
        unknown_reasons,
        real_count,
        duplicates,
    )


def build_census(real_roots: list[Path], ours_roots: list[Path]) -> dict[str, object]:
    family_to_prefix = _family_to_prefix()

    (
        real_elements,
        real_attrs,
        real_foreign,
        real_unnamespaced,
        real_unknown,
        real_count,
        real_duplicates,
    ) = _scan_corpus(real_roots, family_to_prefix)
    (
        ours_elements,
        _ours_attrs,
        _ours_foreign,
        _ours_unnamespaced,
        _ours_unknown,
        ours_count,
        _ours_duplicates,
    ) = _scan_corpus(ours_roots, family_to_prefix)

    unknown_total = sum(real_unknown.values())

    def _key(k: tuple[str, str]) -> str:
        return f"{k[0]}:{k[1]}"

    return {
        "schemaVersion": SCHEMA_VERSION,
        "generator": "scripts/build_element_census.py",
        "populationNote": (
            "real = every *.hwpx under the committed roots this generator was "
            "invoked with, deduplicated by content hash. This repo's committed "
            "snapshot was produced with the vendored tests/fixtures/hwpxlib_corpus "
            "(47 files, reproducible by anyone) plus the maintainer's private "
            "real-world Hancom-authored documents (school administrative and "
            "review paperwork -- not this pipeline's output) as a second "
            "--corpus root. That second root is not committed and its path is "
            "not recorded here (privacy); only the aggregate counts are. The "
            "legacy 166/84 split this census previously reported traced to a "
            "population that was never committed anywhere reachable from this "
            "workspace -- it could not be reproduced or extended, so this "
            "generator does not carry it forward. See "
            "docs/2026-08-04-completeness-audit-verdict.md §3-C1 and "
            "docs/coverage-ledger.md's repair notes."
        ),
        "files": {
            "real": real_count,
            "unknown": unknown_total,
            "ours": ours_count,
        },
        "unknownFiles": {
            "count": unknown_total,
            "reasons": dict(sorted(real_unknown.items())),
        },
        "duplicatesDropped": {
            "real": real_duplicates,
        },
        "real_element_filecounts": dict(
            sorted((_key(k), v) for k, v in real_elements.items())
        ),
        "ours_element_filecounts": dict(
            sorted((_key(k), v) for k, v in ours_elements.items())
        ),
        "real_attribute_names_by_element": {
            _key(k): sorted(v) for k, v in sorted(real_attrs.items(), key=lambda kv: _key(kv[0]))
        },
        "foreignNamespaces": dict(sorted(real_foreign.items())),
        "unnamespacedElements": dict(sorted(real_unnamespaced.items())),
    }


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--corpus",
        action="append",
        type=Path,
        default=[],
        help="additional real-file corpus root (recursively globbed for *.hwpx); "
        "repeatable. Always includes tests/fixtures/hwpxlib_corpus.",
    )
    parser.add_argument(
        "--ours",
        action="append",
        type=Path,
        default=[],
        help="additional 'our own output' corpus root; repeatable. "
        "Always includes examples/.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="drift check only (nonzero exit on drift)")
    args = parser.parse_args()

    real_roots = [DEFAULT_REAL_CORPUS, *args.corpus]
    ours_roots = [DEFAULT_OURS_CORPUS, *args.ours]

    census = build_census(real_roots, ours_roots)
    text = json.dumps(census, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != text:
            print(f"element census drift (run scripts/build_element_census.py): {_display_path(args.output)}", file=sys.stderr)
            return 1
        print("element census in sync")
        return 0

    args.output.write_text(text, encoding="utf-8")
    files_summary = census["files"]
    assert isinstance(files_summary, dict)
    print(
        f"[OK] {_display_path(args.output)} (real={files_summary['real']}, "
        f"unknown={files_summary['unknown']}, ours={files_summary['ours']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
