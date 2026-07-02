# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the M9 open-rate aggregator (specs/007-open-rate, phase P1).

These prove the apparatus WITHOUT Hancom, using a fake open-check backend:

* tier nesting math (opens_clean >= parsed; render_checked only when supplied),
* emit / open / emit_x_open denominator rules incl. withheld = end-to-end fail,
* effective-N clone collapse (mail-merge rows off one template -> ~1 effective),
* rule-of-three lower bound (k=0 -> 1 - 3/N; never 100%),
* negative-control fail-closed invalidation (one opened=true flips harness_valid),
* honest unverified (opened=None never counted as opened nor failed),
* off-Windows degrade of WindowsComOracle.open_check_many (all unverified).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import zipfile
from pathlib import Path

import pytest

# Load scripts/corpus_open_rate.py as a module (scripts/ is not a package).
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "corpus_open_rate", _SCRIPTS / "corpus_open_rate.py"
)
assert _spec and _spec.loader
cor = importlib.util.module_from_spec(_spec)
sys.modules["corpus_open_rate"] = cor
_spec.loader.exec_module(cor)


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# The generator's MCP-surface import is lazy (v1-only), so the module imports
# cleanly in the python-hwpx venv for the v2 pure functions under test.
gen = _load_script("generate_openrate_corpus")
bfl = _load_script("openrate_box_filelist")


def _v(path, *, opened, text_length=None, error=None, retried=False, repaired=False):
    parsed = None if opened is None else bool(opened and (text_length or 0) > 0)
    return {
        "path": path,
        "opened": opened,
        "parsed": parsed,
        "text_length": text_length,
        "error": error,
        "retried": retried,
        "repaired": repaired,
        "status": "ok" if opened else ("unverified" if opened is None else "open_failed"),
    }


def _neg(path, tier="must_refuse", kind="synthetic"):
    return {"path": path, "tier": tier, "kind": kind, "name": path.rsplit("/", 1)[-1]}


def _item(bucket, path, *, produced=True, template=None, input_path=None, render=None):
    return {
        "bucket": bucket,
        "output_path": path,
        "produced": produced,
        "template": template,
        "input_path": input_path,
        "render_verdict": render,
    }


# --------------------------------------------------------------------------- #
# rule of three
# --------------------------------------------------------------------------- #

def test_rule_of_three_zero_failures():
    # 0/100 -> >= 1 - 3/100 = 0.97, never 1.0.
    lb = cor.rule_of_three_lower_bound(0, 100)
    assert lb == pytest.approx(0.97)
    assert lb < 1.0
    assert "97.0%" in cor.rule_of_three_text(0, 100)


def test_rule_of_three_with_failures_and_empty():
    # 1/50: observed 0.98, minus 3/50=0.06 -> 0.92.
    assert cor.rule_of_three_lower_bound(1, 50) == pytest.approx(0.92)
    # N=0 -> None (no trials), text says N/A.
    assert cor.rule_of_three_lower_bound(0, 0) is None
    assert "N/A" in cor.rule_of_three_text(0, 0)


def test_never_prints_100_percent():
    # Even a perfect run reports the lower bound, not 100%.
    txt = cor.rule_of_three_text(0, 30)
    assert "100" not in txt
    assert ">=" in txt


# --------------------------------------------------------------------------- #
# tier nesting math
# --------------------------------------------------------------------------- #

def test_tier_nesting_opens_clean_ge_parsed_ge_render():
    items = [
        _item("authored", "/a/clean1.hwpx", render=True),
        _item("authored", "/a/clean2.hwpx"),          # render verdict not supplied
        _item("authored", "/a/empty.hwpx"),           # opened but textLength 0 -> not parsed
    ]
    verdicts = {
        "/a/clean1.hwpx": _v("/a/clean1.hwpx", opened=True, text_length=200),
        "/a/clean2.hwpx": _v("/a/clean2.hwpx", opened=True, text_length=200),
        "/a/empty.hwpx": _v("/a/empty.hwpx", opened=True, text_length=0),
    }
    agg = cor.aggregate(items, verdicts, strata_requested={"authored": 3})
    b = agg["strata"][0]
    assert b["opens_clean"] == 3            # all three opened clean
    assert b["parsed"] == 2                 # empty one has no text
    assert b["render_checked"] == 1         # only clean1 had render_verdict=true
    assert b["render_unverified"] == 2      # clean2 + empty had no render verdict
    # Nesting invariant: opens_clean >= parsed >= render_checked.
    assert b["opens_clean"] >= b["parsed"] >= b["render_checked"]


def test_parsed_rate_is_the_headline():
    # parsed_rate = parsed/judged is the published headline (opened alone is weak:
    # Hancom opens garbage blank). Here 2 load real content, 1 opens blank, 1 fails.
    items = [
        _item("authored", "/a/content1.hwpx"),
        _item("authored", "/a/content2.hwpx"),
        _item("authored", "/a/blank.hwpx"),      # opened but textLength 0 (blank)
        _item("authored", "/a/failed.hwpx"),      # opened=false
    ]
    verdicts = {
        "/a/content1.hwpx": _v("/a/content1.hwpx", opened=True, text_length=200),
        "/a/content2.hwpx": _v("/a/content2.hwpx", opened=True, text_length=200),
        "/a/blank.hwpx": _v("/a/blank.hwpx", opened=True, text_length=0),
        "/a/failed.hwpx": _v("/a/failed.hwpx", opened=False, error="corrupt"),
    }
    b = cor.aggregate(items, verdicts, strata_requested={"authored": 4})["strata"][0]
    assert b["judged"] == 4
    assert b["opened"] == 3                      # 3 opened (incl. the blank)
    assert b["open_rate"] == pytest.approx(0.75)  # 3/4 — the WEAK signal
    assert b["parsed"] == 2                      # only 2 loaded real content
    assert b["parsed_rate"] == pytest.approx(0.5)  # 2/4 — the HEADLINE
    assert "100" not in b["parsed_rate_interval"] or ">=" in b["parsed_rate_interval"]


def test_render_checked_never_fabricated():
    # No render verdict anywhere -> render_checked tier is 0, all render_unverified.
    items = [_item("exam", "/e/x1.hwpx"), _item("exam", "/e/x2.hwpx")]
    verdicts = {
        "/e/x1.hwpx": _v("/e/x1.hwpx", opened=True, text_length=10),
        "/e/x2.hwpx": _v("/e/x2.hwpx", opened=True, text_length=10),
    }
    b = cor.aggregate(items, verdicts, strata_requested={"exam": 2})["strata"][0]
    assert b["render_checked"] == 0
    assert b["render_unverified"] == 2


# --------------------------------------------------------------------------- #
# denominators: emit / open / emit_x_open + withheld
# --------------------------------------------------------------------------- #

def test_emit_open_combined_with_withheld():
    items = [
        _item("authored", "/a/ok1.hwpx"),
        _item("authored", "/a/ok2.hwpx"),
        _item("authored", "/a/withheld.hwpx", produced=False),  # composer withheld
    ]
    verdicts = {
        "/a/ok1.hwpx": _v("/a/ok1.hwpx", opened=True, text_length=5),
        "/a/ok2.hwpx": _v("/a/ok2.hwpx", opened=True, text_length=5),
    }
    b = cor.aggregate(items, verdicts, strata_requested={"authored": 3})["strata"][0]
    # requested=3, produced=2 -> emit_rate = 2/3
    assert b["produced"] == 2
    assert b["withheld"] == 1
    assert b["emit_rate"] == pytest.approx(2 / 3, abs=1e-4)
    # withheld is NOT in the open denominator (it lowers emit_rate, not open_rate,
    # so it is never double-counted). Both produced files opened -> open_rate = 1.0.
    assert b["judged"] == 2
    assert b["open_denominator"] == 2
    assert b["opened"] == 2
    assert b["open_rate"] == pytest.approx(1.0, abs=1e-4)
    assert b["coverage"] == pytest.approx(1.0, abs=1e-4)
    # emit_x_open = (2/3)*1.0 = 2/3 captures the withheld end-to-end loss.
    assert b["emit_x_open"] == pytest.approx(2 / 3, abs=1e-3)
    # withheld surfaces in the failure list with a clear reason.
    reasons = [f["reason"] for f in b["failures"]]
    assert any("withheld" in r for r in reasons)


def test_unverified_is_neither_opened_nor_failed():
    items = [
        _item("form-fit", "/f/ok.hwpx"),
        _item("form-fit", "/f/unk.hwpx"),
    ]
    verdicts = {
        "/f/ok.hwpx": _v("/f/ok.hwpx", opened=True, text_length=9),
        "/f/unk.hwpx": _v("/f/unk.hwpx", opened=None, error="oracle down"),
    }
    b = cor.aggregate(items, verdicts, strata_requested={"form-fit": 2})["strata"][0]
    assert b["unverified"] == 1
    assert b["opened"] == 1          # the unverified file is NOT counted opened
    assert b["open_failed"] == 0     # ...and NOT counted as a failure either
    # Unverified is EXCLUDED from the rate denominator (no silent-false): judged=1,
    # open_rate=1.0. coverage=0.5 makes the excluded file VISIBLE so it can never
    # silently shrink the denominator unseen.
    assert b["judged"] == 1
    assert b["open_denominator"] == 1
    assert b["open_rate"] == pytest.approx(1.0, abs=1e-4)
    assert b["coverage"] == pytest.approx(0.5, abs=1e-4)


def test_retry_opened_is_not_clean():
    items = [_item("authored", "/a/r.hwpx")]
    verdicts = {"/a/r.hwpx": _v("/a/r.hwpx", opened=True, text_length=50, retried=True)}
    b = cor.aggregate(items, verdicts, strata_requested={"authored": 1})["strata"][0]
    assert b["opens_clean"] == 0          # retried -> excluded from clean headline
    assert b["retried_clean"] == 1
    assert b["opened"] == 1                # but it DID open -> counts for open_rate
    assert b["open_rate"] == pytest.approx(1.0, abs=1e-4)


def test_auto_repaired_open_is_not_clean():
    # A file Hancom silently auto-repaired (dirty on load) opened, but is NON-clean
    # (the per-file repair canary, S2): counts for open_rate, excluded from opens_clean.
    items = [_item("authored", "/a/rep.hwpx", render=True)]
    verdicts = {"/a/rep.hwpx": _v("/a/rep.hwpx", opened=True, text_length=50, repaired=True)}
    b = cor.aggregate(items, verdicts, strata_requested={"authored": 1})["strata"][0]
    assert b["opens_clean"] == 0
    assert b["retried_clean"] == 1        # non-clean opened bucket
    assert b["opened"] == 1
    assert b["parsed"] == 0               # not parsed (non-clean)
    assert b["render_checked"] == 0       # render verdict NOT counted for a repaired file
    reasons = [f["reason"] for f in b["failures"]]
    assert any("repair" in r for r in reasons)


def test_render_checked_never_exceeds_parsed_with_retry_and_repair():
    # Nesting invariant must hold even when non-clean opens carry render verdicts:
    # render_checked <= parsed <= opens_clean, always.
    items = [
        _item("authored", "/a/clean.hwpx", render=True),       # parsed + render
        _item("authored", "/a/retry.hwpx", render=True),       # non-clean (retry) + render
        _item("authored", "/a/repaired.hwpx", render=True),    # non-clean (repair) + render
        _item("authored", "/a/empty.hwpx", render=True),       # opened clean but no text
    ]
    verdicts = {
        "/a/clean.hwpx": _v("/a/clean.hwpx", opened=True, text_length=99),
        "/a/retry.hwpx": _v("/a/retry.hwpx", opened=True, text_length=99, retried=True),
        "/a/repaired.hwpx": _v("/a/repaired.hwpx", opened=True, text_length=99, repaired=True),
        "/a/empty.hwpx": _v("/a/empty.hwpx", opened=True, text_length=0),
    }
    b = cor.aggregate(items, verdicts, strata_requested={"authored": 4})["strata"][0]
    assert b["opens_clean"] == 2          # clean + empty
    assert b["parsed"] == 1               # only clean has text
    assert b["render_checked"] == 1       # ONLY the parsed clean file, not retry/repair/empty
    assert b["opens_clean"] >= b["parsed"] >= b["render_checked"]


# --------------------------------------------------------------------------- #
# effective-N collapse
# --------------------------------------------------------------------------- #

def test_effective_n_collapses_mail_merge_clones():
    # 20 mail-merge rows off ONE template -> effective_n == 1, raw produced == 20.
    items = [
        _item("mail-merge", f"/m/row_{i:03d}.hwpx", template="cert_v1")
        for i in range(20)
    ]
    verdicts = {
        it["output_path"]: _v(it["output_path"], opened=True, text_length=33)
        for it in items
    }
    b = cor.aggregate(items, verdicts, strata_requested={"mail-merge": 20})["strata"][0]
    assert b["produced"] == 20
    assert b["effective_n"] == 1          # collapsed to one template group
    # Two templates -> two effective units.
    items2 = items + [
        _item("mail-merge", "/m/other_1.hwpx", template="cert_v2"),
        _item("mail-merge", "/m/other_2.hwpx", template="cert_v2"),
    ]
    verdicts2 = dict(verdicts)
    for it in items2[-2:]:
        verdicts2[it["output_path"]] = _v(it["output_path"], opened=True, text_length=1)
    b2 = cor.aggregate(items2, verdicts2, strata_requested={"mail-merge": 22})["strata"][0]
    assert b2["effective_n"] == 2
    assert b2["produced"] == 22


# --------------------------------------------------------------------------- #
# negative controls — fail closed
# --------------------------------------------------------------------------- #

def test_negative_controls_must_fail():
    negatives = [_neg("/neg/not_zip.hwpx"), _neg("/neg/truncated.hwpx")]
    nv = {
        "/neg/not_zip.hwpx": _v("/neg/not_zip.hwpx", opened=False, error="corrupt"),
        "/neg/truncated.hwpx": _v("/neg/truncated.hwpx", opened=False, error="corrupt"),
    }
    result = cor.evaluate_negatives(negatives, nv)
    assert result["harness_valid"] is True
    assert all(row["pass"] for row in result["negatives"])
    assert result["errors"] == []
    assert result["warnings"] == []


def test_must_refuse_leak_invalidates_harness():
    negatives = [_neg("/neg/good_fail.hwpx"), _neg("/neg/CANARY.hwpx", tier="must_refuse")]
    nv = {
        "/neg/good_fail.hwpx": _v("/neg/good_fail.hwpx", opened=False, error="corrupt"),
        "/neg/CANARY.hwpx": _v("/neg/CANARY.hwpx", opened=True, text_length=10),  # opened!
    }
    result = cor.evaluate_negatives(negatives, nv)
    assert result["harness_valid"] is False
    assert "/neg/CANARY.hwpx" in result["hard_leaked"]
    assert any("HARNESS_INVALID" in e for e in result["errors"])


def test_expected_refuse_leak_warns_but_does_not_invalidate():
    # A soft (expected_refuse) control that Hancom opens is flagged loudly but the
    # run is NOT invalidated -- these controls are honestly labelled unreliable.
    negatives = [
        _neg("/neg/not_zip.hwpx", tier="must_refuse"),
        _neg("/neg/missing_mimetype.hwpx", tier="expected_refuse"),
    ]
    nv = {
        "/neg/not_zip.hwpx": _v("/neg/not_zip.hwpx", opened=False),
        "/neg/missing_mimetype.hwpx": _v("/neg/missing_mimetype.hwpx", opened=True, text_length=8),
    }
    result = cor.evaluate_negatives(negatives, nv)
    assert result["harness_valid"] is True             # soft leak != invalid
    assert result["hard_leaked"] == []
    assert "/neg/missing_mimetype.hwpx" in result["soft_leaked"]
    assert any("SOFT_NEGATIVE_LEAK" in w for w in result["warnings"])
    assert result["errors"] == []


def test_bare_string_negative_defaults_to_must_refuse():
    # A bare path (no tier metadata) is treated strictly.
    result = cor.evaluate_negatives(
        ["/neg/x.hwpx"], {"/neg/x.hwpx": _v("/neg/x.hwpx", opened=True, text_length=1)}
    )
    assert result["harness_valid"] is False
    assert "/neg/x.hwpx" in result["hard_leaked"]


def test_opened_blank_negative_is_NOT_a_leak():
    # Box finding 2026-07-01: Hancom Open() returns true for container-garbage,
    # loading a BLANK doc (textLength=0). That is expected leniency, NOT a leak —
    # it never reaches the PARSED headline. Only real content from a corrupt file
    # (parsed) is a leak. This mirrors the actual .161 spike result.
    negatives = [
        _neg("/neg/not_zip.hwpx", tier="must_refuse"),
        _neg("/neg/empty.hwpx", tier="must_refuse"),
        _neg("/neg/truncated.hwpx", tier="must_refuse"),
        _neg("/neg/missing_mimetype.hwpx", tier="expected_refuse"),
    ]
    nv = {
        "/neg/not_zip.hwpx": _v("/neg/not_zip.hwpx", opened=True, text_length=0),      # blank
        "/neg/empty.hwpx": _v("/neg/empty.hwpx", opened=True, text_length=0),          # blank
        "/neg/truncated.hwpx": _v("/neg/truncated.hwpx", opened=True, text_length=0),  # blank
        "/neg/missing_mimetype.hwpx": _v("/neg/missing_mimetype.hwpx", opened=True, text_length=0),
    }
    result = cor.evaluate_negatives(negatives, nv)
    assert result["harness_valid"] is True         # opened-blank != leak
    assert result["hard_leaked"] == []
    assert result["soft_leaked"] == []
    assert all(row["pass"] for row in result["negatives"])   # all pass (not parsed)


def test_negative_parses_content_IS_a_leak():
    # If a "corrupt" negative yields real content (parsed), that IS a leak —
    # Hancom fabricated/repaired content, or the file wasn't actually corrupt.
    negatives = [_neg("/neg/canary.hwpx", tier="must_refuse")]
    nv = {"/neg/canary.hwpx": _v("/neg/canary.hwpx", opened=True, text_length=500)}
    result = cor.evaluate_negatives(negatives, nv)
    assert result["harness_valid"] is False
    assert "/neg/canary.hwpx" in result["hard_leaked"]
    assert any("PARSED" in e for e in result["errors"])


def test_negative_unverified_does_not_invalidate_but_is_flagged():
    negatives = [_neg("/neg/unk.hwpx")]
    nv = {"/neg/unk.hwpx": _v("/neg/unk.hwpx", opened=None, error="off-box")}
    result = cor.evaluate_negatives(negatives, nv)
    assert result["harness_valid"] is True          # unverified != leak
    assert "/neg/unk.hwpx" in result["unverified"]


# --------------------------------------------------------------------------- #
# full report assembly + end-to-end via run() with the fake backend
# --------------------------------------------------------------------------- #

def test_build_report_shape_and_no_clock():
    items = [_item("authored", "/a/ok.hwpx", render=True)]
    verdicts = {"/a/ok.hwpx": _v("/a/ok.hwpx", opened=True, text_length=10)}
    report = cor.build_report(
        items, verdicts,
        negatives=["/neg/x.hwpx"],
        negative_verdicts_by_path={"/neg/x.hwpx": _v("/neg/x.hwpx", opened=False)},
        requested_total=1,
        strata_requested={"authored": 1},
        tool_versions={"python-hwpx": "test"},
    )
    assert report["generatedAt"] is None             # root stamps; never now()
    assert report["harness_valid"] is True
    assert report["totals"]["open_rate"] is not None
    assert "100" not in report["totals"]["open_rate_interval"]
    assert report["tool_versions"] == {"python-hwpx": "test"}
    assert report["schemaVersion"] == 1


def test_run_end_to_end_with_fake_backend_flips_on_leak():
    items = [
        _item("authored", "/frozen/authored/a.hwpx"),
        _item("mail-merge", "/frozen/mm/row_001.hwpx", template="cert_v1"),
        _item("mail-merge", "/frozen/mm/row_002.hwpx", template="cert_v1"),
        _item("authored", "/frozen/authored/withheld__withheld.hwpx", produced=False),
    ]
    # Clean negatives -> valid harness.
    good = cor.run(
        items,
        open_checker=cor._fake_open_checker,
        negatives=["/neg/a__fail.hwpx", "/neg/b__fail.hwpx"],
        requested_total=4,
    )
    assert good["harness_valid"] is True
    mm = next(b for b in good["strata"] if b["bucket"] == "mail-merge")
    assert mm["effective_n"] == 1                     # two rows, one template
    auth = next(b for b in good["strata"] if b["bucket"] == "authored")
    assert auth["withheld"] == 1

    # A leaking negative (basename has __leak -> fake reports opened=true).
    bad = cor.run(
        items,
        open_checker=cor._fake_open_checker,
        negatives=["/neg/a__fail.hwpx", "/neg/b__leak.hwpx"],
        requested_total=4,
    )
    assert bad["harness_valid"] is False
    assert any("HARNESS_INVALID" in e for e in bad["errors"])


# --------------------------------------------------------------------------- #
# off-Windows degrade of the oracle primitive
# --------------------------------------------------------------------------- #

def test_open_check_many_degrades_off_windows():
    from hwpx.visual.oracle import WindowsComOracle

    oracle = WindowsComOracle()
    # On this Mac available() is False, so every entry must be unverified --
    # opened=None, NEVER False, NEVER True (constitution V).
    entries = oracle.open_check_many(["/x/a.hwpx", "/x/b.hwpx"])
    assert len(entries) == 2
    for e in entries:
        assert e["opened"] is None
        assert e["status"] == "unverified"
        assert e["parsed"] is None
    # Empty input -> empty list (no crash).
    assert oracle.open_check_many([]) == []


# --------------------------------------------------------------------------- #
# jsonl_open_checker — the ACTUAL box-run ingest path (FR-001; was untested)
# --------------------------------------------------------------------------- #

def test_jsonl_open_checker_basename_join_backslash_meta_and_repaired(tmp_path):
    # The box emits Windows backslash paths + a leading {_meta} probe line; the
    # aggregator joins verdicts to posix corpus paths by basename.
    jsonl = tmp_path / "verdicts.jsonl"
    jsonl.write_text(
        "\n".join([
            '{"_meta":"repair-mode-probe","requestedMode":131072}',
            '{"sourcePath":"C:\\\\openrate\\\\corpus\\\\authored\\\\a.hwpx","opened":true,"textLength":42,"retried":false}',
            '{"sourcePath":"C:\\\\openrate\\\\corpus\\\\authored\\\\b.hwpx","opened":false,"error":"corrupt"}',
            '{"sourcePath":"C:\\\\openrate\\\\corpus\\\\authored\\\\c.hwpx","opened":true,"textLength":10,"repaired":true}',
        ]) + "\n",
        encoding="utf-8",
    )
    checker = cor.jsonl_open_checker(str(jsonl))
    out = checker([
        "/workspace/openrate-corpus/authored/a.hwpx",
        "/workspace/openrate-corpus/authored/b.hwpx",
        "/workspace/openrate-corpus/authored/c.hwpx",
        "/workspace/openrate-corpus/authored/missing.hwpx",  # no verdict -> unverified
    ])
    by_base = {p["path"].rsplit("/", 1)[-1]: p for p in out}
    assert by_base["a.hwpx"]["opened"] is True and by_base["a.hwpx"]["text_length"] == 42
    assert by_base["b.hwpx"]["opened"] is False
    assert by_base["c.hwpx"]["opened"] is True and by_base["c.hwpx"]["repaired"] is True
    # A produced file with no box verdict degrades to unverified (never opened/failed).
    assert by_base["missing.hwpx"]["opened"] is None
    assert by_base["missing.hwpx"]["status"] == "unverified"


# --------------------------------------------------------------------------- #
# main() CLI fail-closed guards (M3 negatives, S3 coverage floor)
# --------------------------------------------------------------------------- #

def _write_json(path, obj):
    import json
    path.write_text(json.dumps(obj), encoding="utf-8")


def _tiny_manifest(tmp_path):
    m = tmp_path / "manifest.json"
    _write_json(m, {
        "schemaVersion": 1, "requested_total": 1,
        "counts_per_bucket": {"authored": {"requested": 1}},
        "records": [{"bucket": "authored",
                     "output_path": str(tmp_path / "authored" / "a.hwpx"),
                     "produced": True}],
    })
    return m


def _negs_manifest(tmp_path):
    n = tmp_path / "negatives.json"
    _write_json(n, {"schemaVersion": "hwpx.openrate.negatives.v2", "negatives": [
        {"path": str(tmp_path / "_negatives" / "not_zip.hwpx"),
         "tier": "must_refuse", "kind": "synthetic:not_zip", "name": "not_zip.hwpx"},
    ]})
    return n


def test_main_missing_negatives_manifest_is_fail_closed(tmp_path):
    # --negatives-manifest set but pointing at a missing file must NOT silently
    # disarm the guard: it errors (parser.error -> SystemExit), like --manifest.
    m = _tiny_manifest(tmp_path)
    verdicts = tmp_path / "v.jsonl"
    verdicts.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit):
        cor.main([
            "--manifest", str(m),
            "--negatives-manifest", str(tmp_path / "DOES_NOT_EXIST.json"),
            "--verdicts-jsonl", str(verdicts),
            "--out", str(tmp_path / "report.json"),
        ])


def test_main_real_run_requires_negatives(tmp_path):
    m = _tiny_manifest(tmp_path)
    verdicts = tmp_path / "v.jsonl"
    verdicts.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit):
        cor.main([
            "--manifest", str(m),
            "--verdicts-jsonl", str(verdicts),
            "--out", str(tmp_path / "report.json"),
        ])


def test_main_coverage_floor_blocks_exit0_when_nothing_judged(tmp_path):
    # Real run whose verdicts JSONL matches the negative (opened=false) but NOT the
    # produced file -> judged=0 -> must return 3, not a benign exit 0.
    m = _tiny_manifest(tmp_path)
    n = _negs_manifest(tmp_path)
    verdicts = tmp_path / "v.jsonl"
    verdicts.write_text(
        '{"sourcePath":"not_zip.hwpx","opened":false,"error":"corrupt"}\n', encoding="utf-8"
    )
    args = [
        "--manifest", str(m), "--negatives-manifest", str(n),
        "--verdicts-jsonl", str(verdicts), "--out", str(tmp_path / "report.json"),
    ]
    assert cor.main(args) == 3                       # coverage floor
    assert cor.main(args + ["--allow-degraded"]) == 0  # intentional dry run is allowed


# =========================================================================== #
# corpus v2 (specs/010 FR-002) — pure-function units of the generator.
# NO real generation here: small synthetic inputs only.
# =========================================================================== #

def _fake_v1_manifest():
    """Miniature frozen-v1 manifest exercising the v2 collision-skip logic."""
    return {
        "schemaVersion": "hwpx.openrate.frozen-manifest.v1",
        "requested_total": 4,
        "produced_total": 4,
        "records": [
            {"id": "formfit-m2_a-short", "bucket": "form-fit",
             "seed": "formfit:m2:a:short", "produced": True,
             "output_path": "/v1/form-fit/formfit-m2_a-short.hwpx"},
            {"id": "authored-bogoseo-00", "bucket": "authored",
             "seed": "authored:bogoseo:00", "produced": True,
             "output_path": "/v1/authored/authored-bogoseo-00.hwpx"},
            {"id": "authored-bogoseo-01", "bucket": "authored",
             "seed": "authored:bogoseo:01", "produced": True,
             "output_path": "/v1/authored/authored-bogoseo-01.hwpx"},
            {"id": "redline-00-authored-bogoseo-00", "bucket": "redline",
             "seed": "redline:authored-bogoseo-00", "produced": True,
             "output_path": "/v1/redline/redline-00-authored-bogoseo-00.hwpx",
             "input_path": "/v1/authored/authored-bogoseo-00.hwpx"},
        ],
    }


# --------------------------------------------------------------------------- #
# pii roster: deterministic, pattern-valid, and masked by the SHIPPED default
# --------------------------------------------------------------------------- #

def test_pii_roster_is_deterministic_and_pattern_valid():
    r1 = gen.synthetic_pii_roster(35)
    r2 = gen.synthetic_pii_roster(35)
    assert r1 == r2                                   # no randomness, index-derived
    assert len(r1) == 35
    # unique probe values per row (each output greps for ITS OWN raw values)
    for key in ("rrn", "phone", "email", "card"):
        assert len({row[key] for row in r1}) == 35, key
    for row in r1:
        assert re.fullmatch(r"\d{6}-[1-4]\d{6}", row["rrn"])
        mm, dd = int(row["rrn"][2:4]), int(row["rrn"][4:6])
        assert 1 <= mm <= 12 and 1 <= dd <= 28        # range-safe fake dates
        assert re.fullmatch(r"010-\d{4}-\d{4}", row["phone"])
        assert re.fullmatch(r"[a-z0-9]+@example\.com", row["email"])
        assert re.fullmatch(r"\d{4}-\d{4}-\d{4}-\d{4}", row["card"])
        assert gen.luhn_ok(row["card"])               # card must survive Luhn gate


def test_pii_roster_values_are_masked_by_shipped_default_policy():
    # The corpus property under test: the SHIPPED engine default masks every
    # machine-PII field, so raw probe values never reach the merged outputs.
    from hwpx.tools.pii import mask_pii

    row = gen.synthetic_pii_roster(3)[2]
    for key in ("rrn", "phone", "email", "card"):
        masked = mask_pii(row[key])
        assert masked != row[key], key
        assert row[key] not in masked, key            # raw value fully absent


def test_luhn_check_digit_roundtrip():
    payload = "411122003300100"
    card = payload + gen.luhn_check_digit(payload)
    assert len(card) == 16
    assert gen.luhn_ok(card)
    # flipping any digit breaks it (sanity that the checker is not vacuous)
    broken = ("9" if card[0] != "9" else "1") + card[1:]
    assert not gen.luhn_ok(broken)


# --------------------------------------------------------------------------- #
# form-fit-wide: v1-combo extraction + collision skip
# --------------------------------------------------------------------------- #

def test_v1_formfit_combos_parses_colon_tags():
    combos = gen.v1_formfit_combos(_fake_v1_manifest())
    assert combos == {("m2:a", "short")}


def test_plan_form_fit_wide_skips_v1_combos_and_is_deterministic():
    combos = {("m2:a", "short")}
    inputs = [("m2:a", Path("/in/a.hwpx")), ("corpus:b", Path("/in/b.hwpx"))]
    planned = gen.plan_form_fit_wide(inputs, combos)
    keys = [(tag, length) for tag, _p, length in planned]
    assert ("m2:a", "short") not in keys              # v1 combo skipped, not duplicated
    assert ("m2:a", "medium") in keys and ("m2:a", "overflow") in keys
    # untouched input keeps the full 3-length sweep, in sweep order
    assert [k for k in keys if k[0] == "corpus:b"] == [
        ("corpus:b", "short"), ("corpus:b", "medium"), ("corpus:b", "overflow")
    ]
    assert len(planned) == 5                          # 2*3 - 1 v1 collision
    assert planned == gen.plan_form_fit_wide(inputs, combos)


# --------------------------------------------------------------------------- #
# redline-wide: round-robin ops + v1 coverage skip
# --------------------------------------------------------------------------- #

def test_v1_redline_covered_attributes_insert_and_replace():
    covered = gen.v1_redline_covered(_fake_v1_manifest())
    # the frozen v1 generator applied insert always + replace conditionally
    assert covered == {
        ("authored-bogoseo-00", "insert"), ("authored-bogoseo-00", "replace"),
    }


def test_plan_redline_wide_round_robin_and_skip():
    stems = [f"authored-bogoseo-{i:02d}" for i in range(6)]
    covered = gen.v1_redline_covered(_fake_v1_manifest())
    planned = gen.plan_redline_wide(stems, covered)
    ops = dict(planned)
    # i=0 -> insert on bogoseo-00 = v1-covered -> SKIPPED not duplicated
    assert "authored-bogoseo-00" not in ops
    assert ops["authored-bogoseo-01"] == "delete"     # round-robin holds positions
    assert ops["authored-bogoseo-02"] == "replace"
    assert ops["authored-bogoseo-03"] == "insert"
    assert ops["authored-bogoseo-04"] == "delete"
    assert ops["authored-bogoseo-05"] == "replace"
    assert len(planned) == 5
    assert planned == gen.plan_redline_wide(stems, covered)


def test_v1_authored_sources_sorted_produced_only():
    manifest = _fake_v1_manifest()
    manifest["records"].append(
        {"id": "authored-withheld", "bucket": "authored", "produced": False,
         "seed": "authored:x", "output_path": None}
    )
    sources = gen.v1_authored_sources(manifest)
    assert [s for s, _p in sources] == ["authored-bogoseo-00", "authored-bogoseo-01"]


# --------------------------------------------------------------------------- #
# manifest merge: v1 by reference + box_rel layout
# --------------------------------------------------------------------------- #

def test_merge_manifests_box_rel_and_counts(tmp_path):
    v1_root = tmp_path / "openrate-corpus"
    v2_root = tmp_path / "openrate-corpus-v2"
    shipped_root = tmp_path / "repo"
    v1 = {
        "schemaVersion": "hwpx.openrate.frozen-manifest.v1",
        "produced_total": 1,
        "records": [{"id": "a", "bucket": "authored", "produced": True,
                     "output_path": str(v1_root / "authored" / "a.hwpx")}],
    }
    v2 = {
        "schemaVersion": "hwpx.openrate.frozen-manifest.v2",
        "records": [
            {"id": "b", "bucket": "pii-merge", "stratum": "pii-merge",
             "produced": True,
             "output_path": str(v2_root / "pii-merge" / "merged" / "b.hwpx")},
            {"id": "c", "bucket": "shipped-artifacts", "stratum": "shipped-artifacts",
             "produced": True,
             "output_path": str(shipped_root / "demo" / "M4-redline" / "c.hwpx")},
            {"id": "d", "bucket": "redline-wide", "stratum": "redline-wide",
             "produced": False, "output_path": None},
        ],
    }
    combined = gen.merge_manifests(
        v1, v2, v1_root=v1_root, v2_root=v2_root, shipped_root=shipped_root
    )
    by_id = {r["id"]: r for r in combined["records"]}
    assert by_id["a"]["corpus"] == "v1"
    assert by_id["a"]["box_rel"] == "v1/authored/a.hwpx"
    assert by_id["a"]["stratum"] == "authored"        # backfilled from bucket
    assert by_id["b"]["corpus"] == "v2"
    assert by_id["b"]["box_rel"] == "v2/pii-merge/merged/b.hwpx"
    assert by_id["c"]["box_rel"] == "shipped/demo/M4-redline/c.hwpx"
    assert by_id["d"]["box_rel"] is None              # withheld -> never listed
    assert combined["schemaVersion"] == "hwpx.openrate.combined-manifest.v1"
    assert combined["requested_total"] == 4
    assert combined["produced_total"] == 3
    assert combined["generatedAt"] is None            # root stamps; never now()
    assert combined["counts_per_stratum"]["v1:authored"] == {"requested": 1, "produced": 1}
    # inputs are NOT mutated (v1 stays frozen even in memory)
    assert "corpus" not in v1["records"][0]
    assert "box_rel" not in v2["records"][0]


# --------------------------------------------------------------------------- #
# shipped-artifacts inventory on a tmp fixture tree
# --------------------------------------------------------------------------- #

def test_inventory_shipped_artifacts_tmp_tree(tmp_path):
    root = tmp_path / "repo"
    demo_dir = root / "demo" / "M4-redline" / "out"
    demo_dir.mkdir(parents=True)
    good = demo_dir / "sample.hwpx"
    with zipfile.ZipFile(good, "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
    bad = demo_dir / "notzip.hwpx"
    bad.write_bytes(b"this is not a zip container")

    records, excluded = gen.inventory_shipped_artifacts(
        [("demo", root / "demo")], base_root=root, check_open_safety=False
    )
    assert [Path(p).name for p in excluded] == ["notzip.hwpx"]  # defensive exclude
    assert len(records) == 1
    rec = records[0]
    assert rec["output_path"] == str(good)
    assert rec["bucket"] == "shipped-artifacts" == rec["stratum"]
    assert rec["produced"] is True
    assert rec["output_sha256"] == hashlib.sha256(good.read_bytes()).hexdigest()
    assert rec["size_bytes"] == good.stat().st_size
    assert rec["provenance"] == "demo/M4-redline/out"
    assert rec["milestone"] == "M4-redline"
    assert rec["hostile_input"] is False              # tagging hook present, unused
    assert rec["static_open_safety_ok"] is None       # honest: check was skipped
    # determinism: a second scan yields the identical inventory
    again, _ = gen.inventory_shipped_artifacts(
        [("demo", root / "demo")], base_root=root, check_open_safety=False
    )
    assert again == records


def test_inventory_shipped_artifacts_static_open_safety_is_honest(tmp_path):
    # A bare zip is NOT a valid hwpx: with the check on, the pre-filter must say
    # False (never silently true).
    root = tmp_path / "repo"
    d = root / "demo" / "M1"
    d.mkdir(parents=True)
    with zipfile.ZipFile(d / "barezip.hwpx", "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
    records, _ = gen.inventory_shipped_artifacts(
        [("demo", root / "demo")], base_root=root, check_open_safety=True
    )
    assert records[0]["static_open_safety_ok"] is False


# --------------------------------------------------------------------------- #
# box filelist --combined: box_rel layout + v1/ negatives prefix + fail-closed
# --------------------------------------------------------------------------- #

def _write_combined_fixture(tmp_path, *, drop_box_rel=False):
    records = [
        {"id": "a", "bucket": "authored", "corpus": "v1", "produced": True,
         "output_path": "/x/openrate-corpus/authored/a.hwpx",
         "box_rel": "v1/authored/a.hwpx"},
        {"id": "b", "bucket": "pii-merge", "corpus": "v2", "produced": True,
         "output_path": "/x/openrate-corpus-v2/pii-merge/merged/b.hwpx",
         "box_rel": "v2/pii-merge/merged/b.hwpx"},
        {"id": "c", "bucket": "shipped-artifacts", "corpus": "v2", "produced": True,
         "output_path": "/x/repo/demo/M4-redline/c.hwpx",
         "box_rel": "shipped/demo/M4-redline/c.hwpx"},
    ]
    if drop_box_rel:
        del records[1]["box_rel"]
    manifest = tmp_path / "combined_manifest.json"
    manifest.write_text(json.dumps({
        "schemaVersion": "hwpx.openrate.combined-manifest.v1",
        "produced_total": 3,
        "records": records,
    }), encoding="utf-8")
    negatives = tmp_path / "negatives.json"
    negatives.write_text(json.dumps({
        "schemaVersion": "hwpx.openrate.negatives.v2",
        "negatives": [
            {"path": "/x/openrate-corpus/_negatives/not_zip.hwpx",
             "tier": "must_refuse", "kind": "synthetic:not_zip", "name": "not_zip.hwpx"},
        ],
    }), encoding="utf-8")
    return manifest, negatives


def test_box_filelist_combined_mode_uses_box_rel(tmp_path):
    manifest, negatives = _write_combined_fixture(tmp_path)
    out = tmp_path / "box_run.filelist"
    rc = bfl.main([
        "--manifest", str(manifest), "--negatives-manifest", str(negatives),
        "--combined", "--out", str(out), "--box-root", "C:\\openrate\\corpus",
    ])
    assert rc == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    # negatives FIRST (spike gate), inside the mirrored v1 tree
    assert lines[0] == "C:\\openrate\\corpus\\v1\\not_zip.hwpx"
    assert "C:\\openrate\\corpus\\v1\\authored\\a.hwpx" in lines
    assert "C:\\openrate\\corpus\\v2\\pii-merge\\merged\\b.hwpx" in lines
    assert "C:\\openrate\\corpus\\shipped\\demo\\M4-redline\\c.hwpx" in lines
    assert len(lines) == 4                            # 1 negative + 3 produced


def test_box_filelist_combined_missing_box_rel_fails_closed(tmp_path):
    manifest, negatives = _write_combined_fixture(tmp_path, drop_box_rel=True)
    out = tmp_path / "box_run.filelist"
    rc = bfl.main([
        "--manifest", str(manifest), "--negatives-manifest", str(negatives),
        "--combined", "--out", str(out), "--box-root", "C:\\openrate\\corpus",
    ])
    assert rc == 1                                    # never silently drop a member
