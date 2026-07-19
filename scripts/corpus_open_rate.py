# SPDX-License-Identifier: Apache-2.0
"""Aggregate a frozen generated corpus into an honest, stratified open-rate report.

This is the M9 open-rate driver (specs/007-open-rate, phase P1/P3). It loads a
frozen manifest of GENERATED ``.hwpx`` files, drives the real-Hancom open check
over them (``WindowsComOracle.open_check_many``), and computes the published
numbers: per-stratum nested honesty tiers, the emit/open/combined denominators,
raw + effective N, the rule-of-three lower bound, and the negative-control
must-fail table. It writes ``docs/openrate/report.json``.

Design constraints (constitution III/V/VI/IX):

* No silent True. Files Hancom could not judge (off-Windows / oracle down) are
  ``unverified`` — never counted as opened, never counted as failed.
* render_checked is the THIRD tier and is NOT fabricated here. Unless a render
  verdict is supplied per file, that tier reports ``unverified`` for the stratum.
* The denominator is the PRE-GATE population: ``open_rate = opened / produced``
  AND ``emit_rate = produced / requested`` are both published, plus the combined
  ``emit_x_open``. A composer-withheld item (produced=false) is an end-to-end
  failure, not an absent row.
* Negative controls MUST report opened==false. If ANY reports opened==true the
  whole report is marked ``harness_valid: false`` with a loud error — fail-closed
  (the suppressed-modal default action turned out to be auto-repair, FR-005).
* 100% is never printed: a rule-of-three 95% lower bound accompanies every rate.
* ``generatedAt`` is left ``null`` — root stamps it; this script never calls
  ``datetime.now`` (deterministic, golden-friendly).

Frozen-manifest schema (produced by the P2 generator; tolerated absent via
``--manifest`` / ``--fake-backend``)::

    {
      "schemaVersion": 1,
      "seed": 1234,
      "requested": 100,                # population requested from the generator
      "strata": [                      # one bucket descriptor each (optional)
        {"bucket": "authored", "requested": 40},
        ...
      ],
      "items": [
        {
          "bucket": "mail-merge",      # stratum / bucket label (required)
          "output_path": ".../row_001.hwpx",  # produced file (null if withheld)
          "produced": true,            # composer emitted bytes (FR-003)
          "input_path": ".../roster.xlsx",     # source for effective-N grouping
          "template": "cert_v1",       # template id; preferred effective-N key
          "seed": 1234,
          "sha256": "...",
          "render_verdict": true | false | null   # optional P3 seed-sample tier
        },
        ...
      ]
    }

Negatives are NOT in the manifest; they are passed via ``--negatives`` (paths
under tests/fixtures/reader_robustness/ + the stale-lineseg inputs).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Iterable

# Make ``import hwpx`` work when run straight from a checkout (scripts/ sibling
# of src/), without requiring an install. Harmless if hwpx is already importable.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# An open-check callable maps a list of paths -> list of verdict dicts with at
# least {path, opened, parsed, text_length, error, retried, status}. The real
# one is WindowsComOracle.open_check_many; the fake one is for tests.
OpenChecker = Callable[[list[str]], list[dict[str, Any]]]

# Strata whose PDF export Hancom refuses (tracked-change docs): their render tier
# is ``render_unavailable_redline`` (never render_failed) and their parsed tier is
# supplied by the InitScan/GetText probe, not GetTextFile (frozen P0 metric, box
# spike 2026-07-19: SaveAs("PDF") returns saved=false, GetTextFile textLength=0).
REDLINE_STRATA = frozenset({"redline", "redline-wide"})

# Ids that are redline-class by DOCUMENT PROPERTY (tracked-change) even though
# their stratum is not redline — the shipped M4 redline demo. Box P2 (2026-07-19):
# opened=true but SaveAs('PDF') refused, the third independent proof of the export
# block (receipt.md). Render tier = render_unavailable_redline, not render_failed.
_M9_REDLINE_CONTENT_IDS = frozenset({"shipped-demo-M4-redline-redline"})

# The box-mirror layout roots every shipped file under ``m9-full/``; the combined
# manifest's ``box_rel`` is exactly the suffix after this marker. The v2 verdict
# join keys on that suffix (case-folded) so duplicate basenames (many shipped
# ``document.hwpx``) each resolve to their own verdict.
_BOX_ROOT_MARKER = "m9-full/"


# --------------------------------------------------------------------------- #
# Pure aggregation helpers (no Hancom, no I/O) — these are what the unit test
# pins. Everything below operates on already-collected verdicts.
# --------------------------------------------------------------------------- #

def rule_of_three_lower_bound(failures: int, n: int) -> float | None:
    """95% lower bound on the success rate for *failures* in *n* trials.

    For ``failures == 0`` this is the rule of three: ``1 - 3/n`` (the classic
    95% CI lower bound when no failure is observed in n trials). For
    ``failures > 0`` we use the same conservative 3-event spread shifted by the
    point estimate: ``max(0, observed_rate - 3/n)``. Either way the headline can
    never print 100% (it prints this bound). ``None`` when ``n == 0``.
    """

    if n <= 0:
        return None
    if failures <= 0:
        return max(0.0, 1.0 - 3.0 / n)
    observed = (n - failures) / n
    return max(0.0, observed - 3.0 / n)


def rule_of_three_text(failures: int, n: int) -> str:
    """Human-readable interval string, e.g. ``"0/100 -> >= 97.0% (95% CI, rule of three)"``."""

    lb = rule_of_three_lower_bound(failures, n)
    if lb is None:
        return f"{failures}/{n} -> N/A (no trials)"
    return f"{failures}/{n} -> >= {lb * 100:.1f}% (95% CI, rule of three: 1 - 3/N)"


def _effective_key(item: dict[str, Any]) -> tuple[str, str]:
    """Effective-N grouping key for one item: (bucket, template-or-input-or-path).

    Near-identical mail-merge clones off one template/roster collapse to a single
    effective unit. Preference: template > input_path > output_path (so a
    20-row merge off one template counts as ~1 effective, not 20).
    """

    bucket = str(item.get("bucket", "?"))
    key = item.get("template") or item.get("input_path") or item.get("output_path") or "?"
    return (bucket, str(key))


def aggregate(
    items: list[dict[str, Any]],
    verdicts_by_path: dict[str, dict[str, Any]],
    *,
    requested_total: int | None = None,
    strata_requested: dict[str, int] | None = None,
    render_by_id: dict[str, dict[str, Any]] | None = None,
    redline_parsed_by_id: dict[str, bool] | None = None,
    redline_content_ids: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Compute the per-stratum tiers + denominators from manifest items + verdicts.

    ``items`` are the manifest entries (with ``bucket``, ``produced``,
    ``output_path``, optional ``render_verdict``); ``verdicts_by_path`` maps an
    output_path to its open-check verdict dict. A produced item with no verdict
    is ``unverified``; a withheld item (produced=false) is an end-to-end failure
    and is counted in ``produced`` denominators as a non-open.

    v2 combined-corpus supply (all optional — absent => v1 behaviour unchanged):

    * ``render_by_id`` — box render receipts keyed by manifest ``id``. When given,
      the render tier is receipt-driven (``saved && pdfBytes>0`` => render_checked,
      gated on parsed; a row that failed => render_failed; no row => unverified) and
      redline-class docs become ``render_unavailable_redline``. When ``None`` the v1
      per-item ``render_verdict`` path is used verbatim.
    * ``redline_parsed_by_id`` — InitScan/GetText parsed verdict keyed by ``id``.
      For ``REDLINE_STRATA`` records the parsed tier reads this (GetTextFile returns
      0 for tracked-change docs — the FLOOR artifact); every other stratum keeps the
      frozen ``textLength>0`` definition.
    * ``redline_content_ids`` — ids that are redline-class by DOCUMENT PROPERTY even
      though their stratum is not redline (e.g. the shipped M4 demo).
    """

    strata_requested = strata_requested or {}
    redline_parsed_by_id = redline_parsed_by_id or {}
    redline_content_ids = redline_content_ids or frozenset()
    buckets: "OrderedDict[str, dict[str, Any]]" = OrderedDict()

    def _bucket(name: str) -> dict[str, Any]:
        if name not in buckets:
            buckets[name] = {
                "bucket": name,
                "requested": strata_requested.get(name, 0),
                "produced": 0,            # composer emitted bytes
                "withheld": 0,            # produced=false (end-to-end failure)
                "opens_clean": 0,         # tier 1: opened & no error & not retried
                "parsed": 0,              # tier 2: opens_clean & textLength>0
                "render_checked": 0,      # tier 3: parsed & render_verdict==true
                "render_unverified": 0,   # render verdict not supplied
                "render_failed": 0,       # render_verdict==false
                "render_unavailable_redline": 0,  # tracked-change doc: SaveAs PDF refused
                "open_failed": 0,         # opened==false (incl. withheld)
                "unverified": 0,          # oracle could not judge (opened None)
                "retried_clean": 0,       # opened but non-clean (retried or auto-repaired)
                "effective_keys": set(),
                "failures": [],           # list of {path, reason}
            }
        return buckets[name]

    for item in items:
        name = str(item.get("bucket", "?"))
        bucket = _bucket(name)
        bucket["effective_keys"].add(_effective_key(item))
        produced = bool(item.get("produced", item.get("output_path") is not None))
        out_path = item.get("output_path")

        if not produced:
            # Composer withheld the bytes: end-to-end failure (FR-003). It lowers
            # emit_rate (it was not produced) and is listed as a failure, but it is
            # NOT added to the open_rate denominator — that would double-count it
            # (emit_x_open already captures it via emit_rate).
            bucket["withheld"] += 1
            bucket["failures"].append(
                {"path": out_path, "reason": "composer_withheld (open-safety pre-gate)"}
            )
            continue

        bucket["produced"] += 1
        verdict = verdicts_by_path.get(out_path) if out_path is not None else None
        opened = verdict.get("opened") if verdict else None
        retried = bool(verdict.get("retried")) if verdict else False
        repaired = bool(verdict.get("repaired")) if verdict else False
        text_length = verdict.get("text_length") if verdict else None
        error = verdict.get("error") if verdict else None
        stratum = str(item.get("stratum") or item.get("bucket") or "?")
        item_id = item.get("id")

        # Resolve the open state and whether the file reached the parsed tier
        # WITHOUT early-continuing, so the render tier is assigned exactly once
        # (below) for every produced item — including non-clean opens, which the
        # redline-render rule must still be able to reach.
        parsed = False
        if opened is None:
            # Honest unverified: oracle could not judge. Not opened, not failed.
            bucket["unverified"] += 1
        elif not opened:
            bucket["open_failed"] += 1
            bucket["failures"].append(
                {"path": out_path, "reason": error or "opened=false"}
            )
        elif retried or repaired:
            # A file that only opened on the retry pass (FR-002d) OR that Hancom
            # silently auto-repaired (dirty after a fresh Open — the per-file
            # repair canary, S2) is NON-clean: it counts toward open_rate (it
            # loaded) but is excluded from the opens_clean headline and from the
            # nested parsed/render tiers.
            bucket["retried_clean"] += 1
            reason = (
                "opened only on retry (non-clean)" if retried
                else "opened but auto-repaired (dirty on load; non-clean)"
            )
            bucket["failures"].append({"path": out_path, "reason": reason})
        else:
            bucket["opens_clean"] += 1
            # Redline-aware parsed: tracked-change strata carry no GetTextFile
            # text (Hancom returns 0 — the FLOOR artifact), so their parsed tier
            # is the InitScan/GetText probe; every other stratum keeps textLength.
            if stratum in REDLINE_STRATA and redline_parsed_by_id:
                parsed = bool(redline_parsed_by_id.get(item_id))
            else:
                parsed = (text_length or 0) > 0
            if parsed:
                bucket["parsed"] += 1

        # Render tier: exactly one bucket per produced item. render_checked is
        # gated on parsed (nesting render_checked ⊆ parsed ⊆ opens_clean); the
        # redline exclusion is a document property, not an outcome.
        bucket[
            _classify_render(
                item,
                parsed=parsed,
                render_by_id=render_by_id,
                redline_content_ids=redline_content_ids,
            )
        ] += 1

    # Materialise effective_keys -> counts and drop the set (not JSON-serialisable).
    strata: list[dict[str, Any]] = []
    for bucket in buckets.values():
        bucket["effective_n"] = len(bucket["effective_keys"])
        del bucket["effective_keys"]
        # opened = opens_clean + retried_clean (every produced file that loaded).
        opened_n = bucket["opens_clean"] + bucket["retried_clean"]
        # JUDGED = produced files real Hancom actually ruled on (opened true OR
        # false). Unverified (oracle could not judge) is EXCLUDED from the rate
        # denominator: counting it as a failure would be a silent-false (the dual
        # of constitution V's no-silent-true). It is reported separately, and
        # `coverage` exposes how much of the produced set was judged so excluded
        # files can never silently shrink the denominator unseen.
        judged_n = opened_n + bucket["open_failed"]
        bucket["opened"] = opened_n
        bucket["judged"] = judged_n
        bucket["open_denominator"] = judged_n
        bucket["open_rate"] = _rate(opened_n, judged_n)
        bucket["coverage"] = _rate(judged_n, bucket["produced"])
        req = bucket["requested"] or (bucket["produced"] + bucket["withheld"])
        bucket["emit_rate"] = _rate(bucket["produced"], req)
        bucket["emit_x_open"] = (
            None
            if bucket["emit_rate"] is None or bucket["open_rate"] is None
            else round(bucket["emit_rate"] * bucket["open_rate"], 4)
        )
        # rule-of-three over the JUDGED denominator (failures = open_failed only).
        open_failures = judged_n - opened_n
        bucket["open_rate_lower_bound"] = rule_of_three_lower_bound(open_failures, judged_n)
        bucket["open_rate_interval"] = rule_of_three_text(open_failures, judged_n)
        # HEADLINE (box finding 2026-07-01): Hancom Open() returns true for blank/
        # garbage, so 'opened' is a weak signal. The published rate is PARSED
        # (opened AND real content loaded, textLength>0) / judged.
        bucket["parsed_rate"] = _rate(bucket["parsed"], judged_n)
        parsed_failures = judged_n - bucket["parsed"]
        bucket["parsed_rate_lower_bound"] = rule_of_three_lower_bound(parsed_failures, judged_n)
        bucket["parsed_rate_interval"] = rule_of_three_text(parsed_failures, judged_n)
        # effective_n is reported ALONGSIDE the raw rate (spec asks for both raw and
        # effective N), not folded into a re-weighted rate.
        strata.append(bucket)

    # Corpus totals.
    totals = _sum_strata(strata)
    totals["open_denominator"] = totals["judged"]
    totals_open_failures = totals["judged"] - totals["opened"]
    totals["open_rate"] = _rate(totals["opened"], totals["judged"])
    totals["coverage"] = _rate(totals["judged"], totals["produced"])
    totals["open_rate_lower_bound"] = rule_of_three_lower_bound(
        totals_open_failures, totals["judged"]
    )
    totals["open_rate_interval"] = rule_of_three_text(
        totals_open_failures, totals["judged"]
    )
    # HEADLINE: parsed (opened AND real content) / judged.
    totals["parsed_rate"] = _rate(totals["parsed"], totals["judged"])
    totals_parsed_failures = totals["judged"] - totals["parsed"]
    totals["parsed_rate_lower_bound"] = rule_of_three_lower_bound(
        totals_parsed_failures, totals["judged"]
    )
    totals["parsed_rate_interval"] = rule_of_three_text(
        totals_parsed_failures, totals["judged"]
    )
    req = requested_total if requested_total is not None else sum(
        (b["requested"] or (b["produced"] + b["withheld"])) for b in strata
    )
    totals["requested"] = req
    totals["emit_rate"] = _rate(totals["produced"], req)
    totals["emit_x_open"] = (
        None
        if totals["emit_rate"] is None or totals["open_rate"] is None
        else round(totals["emit_rate"] * totals["open_rate"], 4)
    )

    return {"strata": strata, "totals": totals}


def _classify_render(
    item: dict[str, Any],
    *,
    parsed: bool,
    render_by_id: dict[str, dict[str, Any]] | None,
    redline_content_ids: frozenset[str],
) -> str:
    """Return the render-tier bucket key for one produced item (exactly one).

    v1 (``render_by_id is None``): the per-item ``render_verdict`` rides on the
    item and is meaningful only for a parsed doc — non-parsed => render_unverified,
    else True => render_checked / False => render_failed / None => render_unverified.

    v2 (``render_by_id`` supplied — the box render batch): a redline-class doc
    (stratum in ``REDLINE_STRATA`` or id in ``redline_content_ids``) is
    ``render_unavailable_redline`` (SaveAs PDF refused — a document property, never
    a failure). Otherwise the receipt decides: ``saved && pdfBytes>0`` =>
    render_checked *if parsed* (nesting; a blank doc that still emits a PDF is not a
    content render, so it degrades to render_unverified), a row that did not save =>
    render_failed, no row => render_unverified.
    """

    if render_by_id is None:
        if not parsed:
            return "render_unverified"
        rv = item.get("render_verdict", None)
        if rv is None:
            return "render_unverified"
        return "render_checked" if bool(rv) else "render_failed"

    stratum = str(item.get("stratum") or item.get("bucket") or "?")
    item_id = item.get("id")
    if stratum in REDLINE_STRATA or (item_id is not None and item_id in redline_content_ids):
        return "render_unavailable_redline"
    row = render_by_id.get(item_id) if item_id is not None else None
    if row is None:
        return "render_unverified"
    saved_ok = bool(row.get("saved")) and (row.get("pdfBytes", row.get("pdf_bytes")) or 0) > 0
    if saved_ok:
        return "render_checked" if parsed else "render_unverified"
    return "render_failed"


def _rate(num: int, den: int | None) -> float | None:
    if not den or den <= 0:
        return None
    return round(num / den, 4)


def _sum_strata(strata: list[dict[str, Any]]) -> dict[str, Any]:
    keys = (
        "requested", "produced", "withheld", "opens_clean", "parsed",
        "render_checked", "render_unverified", "render_failed",
        "render_unavailable_redline", "open_failed",
        "unverified", "retried_clean", "effective_n", "opened", "judged",
        "open_denominator",
    )
    out: dict[str, Any] = {k: 0 for k in keys}
    for bucket in strata:
        for k in keys:
            out[k] += int(bucket.get(k, 0) or 0)
    return out


def evaluate_negatives(
    negatives: list[dict[str, Any] | str],
    verdicts_by_path: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Build the negative-control table and the fail-closed harness verdict.

    Each negative is a record ``{path, tier, kind, name}`` (a bare string path is
    accepted and defaults to the strict ``must_refuse`` tier).

    LEAK CRITERION = the negative reached the PARSED tier (opened==true AND
    textLength>0). Box finding (2026-07-01): Hancom's COM Open() returns true for
    container-garbage (not-a-zip/empty/truncated), loading a BLANK doc with
    textLength=0 — so ``opened`` alone is NOT a leak (that is expected leniency and
    it never reaches the PARSED headline). A negative only threatens the number if
    it produces real content from a corrupt file (Hancom fabricated/repaired it, or
    the file was not actually corrupt). Tiers (FR-005):

    * ``must_refuse`` leak (parsed) — esp. the corrupt_section auto-repair canary
      producing content -> ``harness_valid=false``, do not publish the number.
    * ``expected_refuse`` leak (parsed) -> SOFT warning, does NOT invalidate.

    opened==None (unverified) is recorded but never invalidates (off-box dry runs).
    """

    rows: list[dict[str, Any]] = []
    hard_leaked: list[str] = []
    soft_leaked: list[str] = []
    unverified: list[str] = []
    for neg in negatives:
        if isinstance(neg, str):
            path, tier, kind, name = neg, "must_refuse", "unspecified", os.path.basename(neg)
        else:
            path = str(neg.get("path"))
            tier = str(neg.get("tier", "must_refuse"))
            kind = str(neg.get("kind", "unspecified"))
            name = str(neg.get("name", os.path.basename(path)))
        verdict = verdicts_by_path.get(path)
        opened = verdict.get("opened") if verdict else None
        text_length = verdict.get("text_length") if verdict else None
        error = verdict.get("error") if verdict else "no verdict"
        # A leak is a PARSED negative (opened AND real content), not a blank open.
        parsed = bool(opened) and (text_length or 0) > 0
        rows.append(
            {
                "path": path,
                "name": name,
                "kind": kind,
                "tier": tier,
                "opened": opened,
                "text_length": text_length,
                "parsed": parsed,
                "error": error,
                "expected": "not parsed (opened=false, or opened-blank with textLength=0)",
                "pass": not parsed,
            }
        )
        if parsed:
            (hard_leaked if tier == "must_refuse" else soft_leaked).append(path)
        elif opened is None:
            unverified.append(path)

    harness_valid = len(hard_leaked) == 0
    errors: list[str] = []
    warnings: list[str] = []
    if hard_leaked:
        errors.append(
            "HARNESS_INVALID: must_refuse negative control(s) reached the PARSED tier "
            "(opened AND loaded real content from a corrupt file) -- Hancom fabricated/repaired "
            "content, or the file was not actually corrupt. The parsed-rate number is "
            "untrustworthy, do not publish. FILES: " + ", ".join(hard_leaked)
        )
    if soft_leaked:
        warnings.append(
            "SOFT_NEGATIVE_LEAK: expected_refuse control(s) reached the PARSED tier -- Hancom is "
            "more tolerant than expected; these are not reliable controls on this build (run is "
            "NOT invalidated). FILES: " + ", ".join(soft_leaked)
        )
    return {
        "harness_valid": harness_valid,
        "negatives": rows,
        "hard_leaked": hard_leaked,
        "soft_leaked": soft_leaked,
        "unverified": unverified,
        "errors": errors,
        "warnings": warnings,
    }


def _provenance_tag(item: dict[str, Any], tags: dict[str, list[str]]) -> str | None:
    """Return the first tag whose box_rel prefix matches this item, else None.

    Tagging is by FILE IDENTITY (box_rel prefix), never by outcome — a probe that
    happens to open cleanly is still an internal fixture (no survivorship bias).
    """

    box_rel = item.get("box_rel") or ""
    for tag, prefixes in tags.items():
        if any(box_rel.startswith(p) for p in prefixes):
            return tag
    return None


def build_report(
    items: list[dict[str, Any]],
    verdicts_by_path: dict[str, dict[str, Any]],
    *,
    negatives: list[dict[str, Any] | str] | None = None,
    negative_verdicts_by_path: dict[str, dict[str, Any]] | None = None,
    requested_total: int | None = None,
    strata_requested: dict[str, int] | None = None,
    tool_versions: dict[str, Any] | None = None,
    render_by_id: dict[str, dict[str, Any]] | None = None,
    redline_parsed_by_id: dict[str, bool] | None = None,
    redline_content_ids: frozenset[str] | None = None,
    parsed_source_by_stratum: dict[str, str] | None = None,
    provenance_tags: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Assemble the full ``report.json`` dict (pure; no I/O, no clock)."""

    agg = aggregate(
        items,
        verdicts_by_path,
        requested_total=requested_total,
        strata_requested=strata_requested,
        render_by_id=render_by_id,
        redline_parsed_by_id=redline_parsed_by_id,
        redline_content_ids=redline_content_ids,
    )
    neg = evaluate_negatives(negatives or [], negative_verdicts_by_path or {})

    failures: list[dict[str, Any]] = []
    for bucket in agg["strata"]:
        for f in bucket["failures"]:
            failures.append({"bucket": bucket["bucket"], **f})

    # Provenance rollup (specs/010 P3): the FULL-corpus numbers above are published
    # unchanged; alongside them we publish a "product" rollup (records NOT tagged as
    # internal fixtures) and each tag's own rollup, using the identical denominator
    # discipline (same aggregate over the subset). Neither replaces the other.
    provenance: dict[str, Any] | None = None
    if provenance_tags:
        def _rollup(subset: list[dict[str, Any]]) -> dict[str, Any]:
            return aggregate(
                subset,
                verdicts_by_path,
                render_by_id=render_by_id,
                redline_parsed_by_id=redline_parsed_by_id,
                redline_content_ids=redline_content_ids,
            )["totals"]

        tagged: dict[str, list[dict[str, Any]]] = {t: [] for t in provenance_tags}
        product_items: list[dict[str, Any]] = []
        for item in items:
            tag = _provenance_tag(item, provenance_tags)
            (tagged[tag] if tag is not None else product_items).append(item)
        provenance = {
            "definition": provenance_tags,
            "note": "Headline = the 'product' rollup (records NOT matching any "
            "internal-fixture box_rel prefix). The FULL-corpus totals are published "
            "unchanged alongside; tagging is by file identity, not outcome.",
            "product": _rollup(product_items),
            "product_count": len(product_items),
            "tags": {t: _rollup(sub) for t, sub in tagged.items()},
            "tag_counts": {t: len(sub) for t, sub in tagged.items()},
        }

    report = {
        "schemaVersion": 1,
        "generatedAt": None,  # root stamps; never datetime.now (constitution V)
        "feature": "007-open-rate",
        "metric": {
            "headline": "hancom-load-rate = parsed / judged (real Hancom COM Open() AND real "
            "content loaded, textLength>0)",
            "headlineNote": "Box finding 2026-07-01: Hancom COM Open() returns true even for "
            "blank/garbage files (opened-blank, textLength=0), so 'opened' alone is NOT the "
            "headline. The published rate is PARSED = opened AND textLength>0. 'open_rate' "
            "(opened/judged) is reported alongside as a weaker secondary signal.",
            "tiers": ["opened (weak: incl. blank opens)", "parsed (HEADLINE)", "render_checked"],
            "denominatorRule": "parsed_rate = parsed/judged; open_rate = opened/judged; "
            "emit_rate = produced/requested; emit_x_open = emit_rate * open_rate; withheld "
            "counts as end-to-end failure",
            "intervalRule": "rule of three: k=0 -> >= 1 - 3/N (95% CI); 100% is never printed",
            "renderCheckedNote": "render_checked = parsed AND box SaveAs('PDF') saved with "
            "pdfBytes>0 (nesting render_checked ⊆ parsed ⊆ opens_clean). A doc that opens "
            "blank (textLength=0) but still emits a PDF is render_unverified, not render_checked. "
            "render_unavailable_redline = tracked-change docs whose PDF export Hancom refuses "
            "(document property, never render_failed). render_failed = a render row that did not "
            "save; render_unverified = no render row / off-box.",
            "parsedSourceByStratum": parsed_source_by_stratum or {},
            "parsedSourceNote": "Non-redline strata: parsed = GetTextFile('TEXT') textLength>0. "
            "REDLINE_STRATA (redline, redline-wide): parsed = InitScan/GetText byref mask-0 "
            "textLength>0 (GetTextFile returns 0 for tracked-change docs — the FLOOR artifact).",
        },
        "harness_valid": neg["harness_valid"],
        "errors": neg["errors"],
        "warnings": neg["warnings"],
        "strata": agg["strata"],
        "totals": agg["totals"],
        "provenance": provenance,
        "failures": failures,
        "negatives": {
            "table": neg["negatives"],
            "hard_leaked": neg["hard_leaked"],
            "soft_leaked": neg["soft_leaked"],
            "unverified": neg["unverified"],
        },
        "tool_versions": tool_versions or {},
    }
    return report


# --------------------------------------------------------------------------- #
# I/O + drivers (manifest loading, oracle wiring, CLI)
# --------------------------------------------------------------------------- #

def load_manifest(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _verdicts_by_path(verdicts: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for v in verdicts:
        p = v.get("path")
        if p is not None:
            out[p] = v
    return out


def _box_rel_suffix(src: str) -> str | None:
    """The path suffix after the box-mirror root (``m9-full/``), lower-cased.

    ``C:\\openrate\\m9-full\\shipped\\demo\\x\\document.hwpx`` -> ``shipped/demo/x/
    document.hwpx``. Returns ``None`` when the marker is absent (so basename-join
    verdicts and _meta lines don't collide into a spurious key).
    """

    norm = str(src).replace("\\", "/").lower()
    idx = norm.find(_BOX_ROOT_MARKER)
    if idx < 0:
        return None
    return norm[idx + len(_BOX_ROOT_MARKER):]


def jsonl_open_checker(
    jsonl_path: str,
    path_to_boxrel: dict[str, str] | None = None,
) -> OpenChecker:
    """Open-checker backed by a PS1-produced JSONL (a Windows box run).

    The box writes one record per file ``{sourcePath, opened, textLength, error,
    retried}``. Two join strategies, tried in order per queried path:

    * v2 combined corpus (``path_to_boxrel`` given): the shipped stratum has many
      duplicate basenames (``document.hwpx`` etc.), so a basename join is unsafe.
      Each local ``output_path`` maps to its ``box_rel``; verdicts are keyed by the
      normalised path suffix after ``m9-full/`` (== box_rel, case-folded) so every
      file resolves its EXACT verdict. Falls back to the basename join below when a
      queried path has no box_rel (e.g. negatives, which live outside the manifest).
    * v1 (``path_to_boxrel`` absent, or path not in it): the P2 generator gives every
      output a unique id-based filename, so a BASENAME join is unambiguous.

    Non-file records (e.g. ``{"_meta":...}``) have no key and are skipped. A file
    with no matching record degrades to ``unverified`` (never silently opened/failed).
    """

    path_to_boxrel = path_to_boxrel or {}
    by_base: dict[str, dict[str, Any]] = {}
    by_suffix: dict[str, dict[str, Any]] = {}
    # utf-8-sig: Windows PowerShell 5.1 `Add-Content -Encoding UTF8` prepends a BOM
    # to the first line. Without stripping it, json.loads on line 1 raises and the
    # record is silently dropped — which, absent a leading _meta probe line, would
    # drop the FIRST file's verdict and silently weaken the population/negative gate.
    with open(jsonl_path, encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            src = rec.get("sourcePath") or rec.get("path") or ""
            # The box emits Windows paths (C:\..\x.hwpx); this aggregator runs on
            # posix where os.path.basename does NOT split on backslash. Normalise
            # separators first so the basename join works cross-platform.
            base = os.path.basename(str(src).replace("\\", "/"))
            if base:
                by_base[base] = rec
            suffix = _box_rel_suffix(src)
            if suffix is not None:
                by_suffix[suffix] = rec

    def _resolve(p: str) -> dict[str, Any] | None:
        box_rel = path_to_boxrel.get(p)
        if box_rel:
            return by_suffix.get(box_rel.lower())
        return by_base.get(os.path.basename(str(p).replace("\\", "/")))

    def checker(paths: list[str]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for p in paths:
            rec = _resolve(p)
            if rec is None:
                out.append(_v(p, opened=None, error="no verdict in JSONL for this file"))
                continue
            opened_raw = rec.get("opened")
            opened = bool(opened_raw) if opened_raw is not None else None
            tl = rec.get("textLength", rec.get("text_length"))
            out.append(
                _v(
                    p,
                    opened=opened,
                    text_length=tl,
                    error=rec.get("error"),
                    retried=bool(rec.get("retried")),
                    repaired=bool(rec.get("repaired")),
                    page_count=rec.get("pageCount", rec.get("page_count")),
                )
            )
        return out

    return checker


def render_receipts_from_jsonl(jsonl_path: str) -> dict[str, dict[str, Any]]:
    """Load box render receipts keyed by ``sourceId`` (== manifest id, unique).

    Rows are ``{sourceId, stratum, opened, saved, pdfBytes, ...}``; the leading
    ``{_meta:...}`` batch header (no sourceId) is skipped.
    """

    out: dict[str, dict[str, Any]] = {}
    with open(jsonl_path, encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = rec.get("sourceId")
            if sid:
                out[str(sid)] = rec
    return out


def redline_parsed_from_jsonl(jsonl_path: str) -> dict[str, bool]:
    """Load the redline InitScan/GetText parsed verdict keyed by manifest ``id``.

    The redline probe file keys on ``sourceId`` = ``<id>.hwpx``; the frozen parsed
    definition is the InitScan/GetText **byref, mask-0** probe with textLength>0
    (GetTextFile returns 0 for tracked-change docs — the FLOOR artifact).
    """

    out: dict[str, bool] = {}
    with open(jsonl_path, encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = rec.get("sourceId")
            if not sid:
                continue
            key = sid[:-5] if str(sid).endswith(".hwpx") else str(sid)
            parsed = False
            for probe in rec.get("probes", []):
                if (
                    probe.get("method") == "InitScan/GetText"
                    and probe.get("callShape") == "byref"
                    and probe.get("option") == 0
                ):
                    parsed = bool(probe.get("ok")) and (probe.get("textLength") or 0) > 0
                    break
            out[key] = parsed
    return out


def real_open_checker(powershell: str | None = None, timeout: float = 300.0) -> OpenChecker:
    """Return the real Hancom open checker (degrades to all-unverified off-box)."""

    from hwpx.visual.oracle import WindowsComOracle

    oracle = WindowsComOracle(powershell=powershell, timeout=timeout)
    return oracle.open_check_many


def _collect_tool_versions() -> dict[str, Any]:
    versions: dict[str, Any] = {}
    try:
        from importlib.metadata import version

        versions["python-hwpx"] = version("python-hwpx")
    except Exception:
        versions["python-hwpx"] = None
    versions["python"] = sys.version.split()[0]
    # Hancom build is box-supplied; root/box stamps it. Left as a documented slot.
    versions["hancom_build"] = None
    return versions


def run(
    items: list[dict[str, Any]],
    *,
    open_checker: OpenChecker,
    negatives: list[dict[str, Any] | str] | None = None,
    requested_total: int | None = None,
    strata_requested: dict[str, int] | None = None,
    tool_versions: dict[str, Any] | None = None,
    render_by_id: dict[str, dict[str, Any]] | None = None,
    redline_parsed_by_id: dict[str, bool] | None = None,
    redline_content_ids: frozenset[str] | None = None,
    parsed_source_by_stratum: dict[str, str] | None = None,
    provenance_tags: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Drive the open check over produced items + negatives and build the report."""

    negatives = negatives or []
    neg_paths = [(n["path"] if isinstance(n, dict) else n) for n in negatives]
    produced_paths = [
        it["output_path"]
        for it in items
        if it.get("output_path") is not None
        and bool(it.get("produced", it.get("output_path") is not None))
    ]
    verdicts = open_checker(produced_paths) if produced_paths else []
    neg_verdicts = open_checker(neg_paths) if neg_paths else []

    return build_report(
        items,
        _verdicts_by_path(verdicts),
        negatives=negatives,
        negative_verdicts_by_path=_verdicts_by_path(neg_verdicts),
        requested_total=requested_total,
        strata_requested=strata_requested,
        tool_versions=tool_versions or _collect_tool_versions(),
        render_by_id=render_by_id,
        redline_parsed_by_id=redline_parsed_by_id,
        redline_content_ids=redline_content_ids,
        parsed_source_by_stratum=parsed_source_by_stratum,
        provenance_tags=provenance_tags,
    )


def _fake_open_checker(paths: list[str]) -> list[dict[str, Any]]:
    """Deterministic FAKE backend for --fake-backend smoke runs (no Hancom).

    A path is "opened clean" unless its basename encodes a marker:
      *__withheld*  -> handled upstream (produced=false), never reaches here
      *__fail*      -> opened=false
      *__retry*     -> opened=true but retried=true (non-clean)
      *__unverified*-> opened=None (oracle could not judge)
      *__empty*     -> opened=true but text_length 0 (not parsed)
      *__leak*      -> opened=true (used to show a negative-control leak)
    """

    out: list[dict[str, Any]] = []
    for p in paths:
        base = os.path.basename(p)
        if "__fail" in base:
            out.append(_v(p, opened=False, error="fake: corrupt"))
        elif "__retry" in base:
            out.append(_v(p, opened=True, text_length=120, retried=True))
        elif "__unverified" in base:
            out.append(_v(p, opened=None, error="fake: oracle down"))
        elif "__empty" in base:
            out.append(_v(p, opened=True, text_length=0))
        elif "__leak" in base:
            out.append(_v(p, opened=True, text_length=300))
        else:
            out.append(_v(p, opened=True, text_length=240))
    return out


def _v(
    path: str,
    *,
    opened: bool | None,
    text_length: int | None = None,
    error: str | None = None,
    retried: bool = False,
    repaired: bool = False,
    page_count: int | None = None,
) -> dict[str, Any]:
    parsed = None if opened is None else bool(opened and (text_length or 0) > 0)
    status = "ok" if opened else ("unverified" if opened is None else "open_failed")
    return {
        "path": path,
        "opened": opened,
        "parsed": parsed,
        "text_length": text_length,
        "page_count": page_count,
        "error": error,
        "retried": retried,
        "repaired": repaired,
        "status": status,
    }


def _sample_manifest() -> dict[str, Any]:
    """A tiny illustrative manifest used by --fake-backend when none is given."""

    def item(bucket, name, template=None, produced=True, render=None):
        return {
            "bucket": bucket,
            "output_path": None if not produced else f"/frozen/{bucket}/{name}.hwpx",
            "produced": produced,
            "template": template,
            "input_path": None,
            "render_verdict": render,
        }

    items = [
        item("authored", "gongmun_01", render=True),
        item("authored", "gongmun_02"),
        item("authored", "report_01__empty"),
        item("authored", "letter_01__withheld", produced=False),
        item("mail-merge", "row_001", template="cert_v1"),
        item("mail-merge", "row_002", template="cert_v1"),
        item("mail-merge", "row_003", template="cert_v1"),
        item("mail-merge", "row_004__retry", template="cert_v1"),
        item("form-fit", "form_01"),
        item("form-fit", "form_02__fail"),
        item("exam", "exam_01__unverified"),
        item("redline", "redline_01"),
    ]
    strata = [
        {"bucket": "authored", "requested": 4},
        {"bucket": "mail-merge", "requested": 4},
        {"bucket": "form-fit", "requested": 2},
        {"bucket": "exam", "requested": 1},
        {"bucket": "redline", "requested": 1},
    ]
    return {"schemaVersion": 1, "seed": 1234, "requested": 12, "strata": strata, "items": items}


def _items_from_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    # Accept both the P1 reference schema (``items``) and the P2 frozen-manifest
    # schema (``records``, schemaVersion hwpx.openrate.frozen-manifest.v1).
    return list(manifest.get("items") or manifest.get("records") or [])


def _strata_requested(manifest: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in manifest.get("strata", []):
        out[str(s.get("bucket"))] = int(s.get("requested", 0))
    if not out:
        # P2 schema: counts_per_bucket maps bucket -> {requested, produced, ...}
        # (or, defensively, bucket -> int).
        cpb = manifest.get("counts_per_bucket") or {}
        for bucket, info in cpb.items():
            if isinstance(info, dict):
                out[str(bucket)] = int(info.get("requested", 0))
            else:
                out[str(bucket)] = int(info or 0)
    if not out:
        # Combined-manifest schema: counts_per_stratum maps "<corpus>:<stratum>" ->
        # {requested, produced}. Records group by bucket == stratum, so strip the
        # corpus prefix to recover the per-bucket requested count.
        cps = manifest.get("counts_per_stratum") or {}
        for key, info in cps.items():
            stratum = str(key).split(":", 1)[-1]
            requested = int(info.get("requested", 0)) if isinstance(info, dict) else int(info or 0)
            out[stratum] = out.get(stratum, 0) + requested
    return out


def _requested_total(manifest: dict[str, Any]) -> int | None:
    val = manifest.get("requested")
    if val is None:
        val = manifest.get("requested_total")
    return int(val) if val is not None else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="corpus_open_rate",
        description="Aggregate a frozen generated corpus into a stratified Hancom open-rate report.",
    )
    parser.add_argument(
        "--manifest",
        default="work/openrate-corpus/manifest.json",
        help="frozen corpus manifest (default: work/openrate-corpus/manifest.json)",
    )
    parser.add_argument(
        "--negatives",
        nargs="*",
        default=[],
        help="negative-control paths (must report opened=false)",
    )
    parser.add_argument(
        "--negatives-manifest",
        default=None,
        help="negatives.json (from build_openrate_negatives.py); reads .negatives[].path "
        "— preferred over --negatives for reproducible box runs",
    )
    parser.add_argument(
        "--verdicts-jsonl",
        default=None,
        help="ingest per-file open verdicts from a PS1-produced JSONL (the box run), "
        "matched by basename — use this when hancom_open_rate.ps1 ran on the Windows "
        "box and only the JSONL was copied back (no live oracle / no Python on the box)",
    )
    parser.add_argument(
        "--render-verdicts-jsonl",
        default=None,
        help="box render receipts JSONL (joined by sourceId == manifest id). Enables the "
        "receipt-driven render tier + render_unavailable_redline for tracked-change docs",
    )
    parser.add_argument(
        "--redline-verdicts-jsonl",
        default=None,
        help="box InitScan/GetText probe JSONL for the redline strata (parsed override — "
        "GetTextFile returns 0 for tracked-change docs, the FLOOR artifact)",
    )
    parser.add_argument(
        "--provenance-tags",
        default=None,
        help='JSON file mapping tag -> [box_rel prefixes]; the report gains a provenance '
        'rollup (per-tag totals + a "product" rollup of untagged records)',
    )
    parser.add_argument(
        "--out",
        default="docs/openrate/report.json",
        help="output report.json path (default: docs/openrate/report.json)",
    )
    parser.add_argument(
        "--fake-backend",
        action="store_true",
        help="use the deterministic FAKE open checker (no Hancom) + a sample manifest if none exists",
    )
    parser.add_argument(
        "--allow-degraded",
        action="store_true",
        help="permit a real run that judged 0 files (oracle degraded to all-unverified) to exit 0 "
        "— use ONLY for an intentional off-box (Mac) dry run of the aggregation pipeline",
    )
    parser.add_argument("--powershell", default=None, help="powershell executable for the real oracle")
    parser.add_argument("--timeout", type=float, default=300.0, help="per-batch oracle timeout seconds")
    args = parser.parse_args(argv)

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

    if args.fake_backend:
        if os.path.exists(args.manifest):
            manifest = load_manifest(args.manifest)
        else:
            manifest = _sample_manifest()
        checker: OpenChecker = _fake_open_checker
        tool_versions = {"python-hwpx": None, "python": sys.version.split()[0],
                         "hancom_build": "FAKE-BACKEND"}
    else:
        if not os.path.exists(args.manifest):
            parser.error(
                f"manifest not found: {args.manifest} (run the P2 generator first, "
                "pass --manifest, or use --fake-backend)"
            )
        manifest = load_manifest(args.manifest)
        if args.verdicts_jsonl:
            if not os.path.exists(args.verdicts_jsonl):
                parser.error(f"verdicts JSONL not found: {args.verdicts_jsonl}")
            # Combined-corpus join: each local output_path -> its box_rel so the
            # verdict lookup keys on the exact box-mirror suffix (duplicate shipped
            # basenames each resolve to their own verdict). v1 manifests carry no
            # box_rel -> this map is empty -> basename join, unchanged.
            path_to_boxrel = {
                str(r["output_path"]): str(r["box_rel"])
                for r in _items_from_manifest(manifest)
                if r.get("output_path") and r.get("box_rel")
            }
            checker = jsonl_open_checker(args.verdicts_jsonl, path_to_boxrel=path_to_boxrel)
        else:
            checker = real_open_checker(powershell=args.powershell, timeout=args.timeout)
        tool_versions = None

    # Negative controls (FR-005). --negatives-manifest is fail-CLOSED: a path that
    # is SET but missing is an error (a typo / missed rsync / wrong CWD must not
    # silently disarm the auto-repair guard), mirroring --manifest/--verdicts-jsonl.
    negatives: list[dict[str, Any] | str] = [
        {"path": p, "tier": "must_refuse", "kind": "cli", "name": os.path.basename(p)}
        for p in args.negatives
    ]
    if args.negatives_manifest:
        if not os.path.exists(args.negatives_manifest):
            parser.error(f"negatives manifest not found: {args.negatives_manifest}")
        nm = load_manifest(args.negatives_manifest)
        for r in nm.get("negatives", []):
            if r.get("path"):
                negatives.append({
                    "path": str(r["path"]),
                    "tier": str(r.get("tier", "must_refuse")),
                    "kind": str(r.get("kind", "unspecified")),
                    "name": str(r.get("name", os.path.basename(str(r["path"])))),
                })

    # A real (non-fake) run MUST evaluate negative controls; publishing an
    # open-rate with zero controls checked is the silently-disarmed-guard failure.
    if not args.fake_backend and not negatives:
        parser.error(
            "real run requires negative controls: pass --negatives-manifest (preferred) "
            "or --negatives (or use --fake-backend for a smoke run)"
        )

    # v2 render / redline / provenance supply. Each is fail-CLOSED: set-but-missing
    # is an error (a wrong path must not silently drop a whole axis).
    render_by_id: dict[str, dict[str, Any]] | None = None
    if args.render_verdicts_jsonl:
        if not os.path.exists(args.render_verdicts_jsonl):
            parser.error(f"render verdicts JSONL not found: {args.render_verdicts_jsonl}")
        render_by_id = render_receipts_from_jsonl(args.render_verdicts_jsonl)
    redline_parsed_by_id: dict[str, bool] | None = None
    if args.redline_verdicts_jsonl:
        if not os.path.exists(args.redline_verdicts_jsonl):
            parser.error(f"redline verdicts JSONL not found: {args.redline_verdicts_jsonl}")
        redline_parsed_by_id = redline_parsed_from_jsonl(args.redline_verdicts_jsonl)
    provenance_tags: dict[str, list[str]] | None = None
    if args.provenance_tags:
        if not os.path.exists(args.provenance_tags):
            parser.error(f"provenance tags file not found: {args.provenance_tags}")
        provenance_tags = load_manifest(args.provenance_tags)

    # Per-stratum parsed provenance (which probe fed the parsed tier), for the report.
    strata_seen = {str(r.get("stratum") or r.get("bucket") or "?") for r in _items_from_manifest(manifest)}
    parsed_source_by_stratum = {
        s: (
            "InitScan/GetText (byref, mask 0), textLength>0"
            if s in REDLINE_STRATA and redline_parsed_by_id
            else "GetTextFile('TEXT'), textLength>0"
        )
        for s in sorted(strata_seen)
    }

    report = run(
        _items_from_manifest(manifest),
        open_checker=checker,
        negatives=negatives,
        requested_total=_requested_total(manifest),
        strata_requested=_strata_requested(manifest),
        tool_versions=tool_versions,
        render_by_id=render_by_id,
        redline_parsed_by_id=redline_parsed_by_id,
        redline_content_ids=_M9_REDLINE_CONTENT_IDS,
        parsed_source_by_stratum=parsed_source_by_stratum,
        provenance_tags=provenance_tags,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Fail-closed exits, most severe first.
    # (2) Harness invalid: a must_refuse negative control leaked opened=true.
    if not report["harness_valid"]:
        sys.stderr.write("\n".join(report["errors"]) + "\n")
        return 2
    # Soft negative leaks (expected_refuse): warn loudly, do not fail.
    for w in report.get("warnings", []):
        sys.stderr.write(w + "\n")
    # (3) Coverage floor (S3): a real run that judged NOTHING (oracle down or the
    # basename join silently broke) must not masquerade as a benign exit-0 publish.
    judged = int(report["totals"].get("judged", 0) or 0)
    if not args.fake_backend and not args.allow_degraded and judged == 0:
        sys.stderr.write(
            f"COVERAGE_FLOOR: real run judged 0 of {report['totals'].get('produced', 0)} produced "
            "files (open_rate is null). The oracle degraded to all-unverified or the basename join "
            f"failed. Wrote {out_path} for inspection but refusing exit 0. Pass --allow-degraded for "
            "an intentional off-box dry run.\n"
        )
        return 3
    prov = report.get("provenance")
    if prov:
        p = prov["product"]
        print(
            f"wrote {out_path} (harness_valid={report['harness_valid']}, judged={judged})\n"
            f"  PRODUCT [HEADLINE]: n={prov['product_count']} opened={p['opened']}/{p['judged']} "
            f"parsed={p['parsed']}/{p['judged']} (rate={p.get('parsed_rate')}) "
            f"render_checked={p['render_checked']} render_unavailable_redline={p['render_unavailable_redline']}\n"
            f"  FULL: opened={report['totals']['opened']}/{report['totals']['judged']} "
            f"parsed_rate={report['totals'].get('parsed_rate')}"
        )
    else:
        print(
            f"wrote {out_path} (harness_valid={report['harness_valid']}, judged={judged}, "
            f"parsed_rate={report['totals'].get('parsed_rate')} [HEADLINE], "
            f"open_rate={report['totals'].get('open_rate')})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
