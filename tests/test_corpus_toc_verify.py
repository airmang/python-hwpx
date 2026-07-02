# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the P3 TOC structural corpus driver
(specs/010-corpus-publication, scripts/corpus_toc_verify.py).

NO live Hancom anywhere (S-060 discipline: live render is opt-in only, never
in the default suite). The renumber-sample leg is exercised with a FAKE oracle
object plus synthetic word boxes (the test_toc_fidelity.py precedent) — the
fake's ``refresh_document`` / ``render_pdf`` calls double as a session-
separation probe.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from hwpx.document import HwpxDocument
from hwpx.tools import toc_author as ta
from hwpx.tools import toc_fidelity as tf

# Load scripts/corpus_toc_verify.py as a module (scripts/ is not a package).
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
_spec = importlib.util.spec_from_file_location(
    "corpus_toc_verify", _SCRIPTS / "corpus_toc_verify.py"
)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
sys.modules["corpus_toc_verify"] = mod
_spec.loader.exec_module(mod)


# ---------------------------------------------------------------------------------
# tiny fixtures: docs WITH a native TOC (shipped API) and WITHOUT
# ---------------------------------------------------------------------------------
def _toc_doc(path: Path, count: int = 3) -> Path:
    """Small doc with a native TABLEOFCONTENTS (test_toc_author fixture shape)."""
    doc = HwpxDocument.new()
    headings = []
    for i in range(1, count + 1):
        h = doc.add_paragraph(f"개요 {i}번 제목")
        headings.append(h)
        doc.add_paragraph(f"{i}번 제목의 본문입니다. " * 20)
    ta.add_native_toc(doc, headings=headings)
    doc.save_to_path(path)
    doc.close()
    return path


def _plain_doc(path: Path) -> Path:
    doc = HwpxDocument.new()
    doc.add_paragraph("차례 없는 일반 문서입니다.")
    doc.save_to_path(path)
    doc.close()
    return path


def _manifest(path: Path, records: list[dict]) -> Path:
    payload = {"schemaVersion": "hwpx.openrate.frozen-manifest.v2", "records": records}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _record(
    rec_id: str,
    doc_path: Path | None,
    *,
    produced: bool = True,
    stratum: str = "authored-toc",
    entry_count: int | None = None,
) -> dict:
    rec: dict = {
        "id": rec_id,
        "stratum": stratum,
        "bucket": stratum,
        "seed": f"{stratum}:{rec_id}",
        "produced": produced,
        "output_path": str(doc_path) if doc_path else None,
    }
    if entry_count is not None:
        rec["toc_entry_count"] = entry_count
    return rec


# ---------------------------------------------------------------------------------
# structural leg (mode 1, oracle-free)
# ---------------------------------------------------------------------------------
def test_structural_pass_on_native_toc_doc(tmp_path: Path) -> None:
    doc = _toc_doc(tmp_path / "toc.hwpx")
    manifest = _manifest(
        tmp_path / "manifest.json", [_record("authoredtoc-00", doc, entry_count=3)]
    )

    report, code = mod.run(manifest, tmp_path)

    assert code == mod.EXIT_OK
    totals = report["totals"]
    assert totals["records"] == 1 and totals["judged"] == 1
    assert totals["structural"]["pass"] == 1 and totals["structural"]["all_pass"]
    # rule-of-three interval accompanies the rate; 100% is never a bare headline
    assert totals["structural"]["rate"] == 1.0
    assert "rule of three" in totals["structural"]["rate_interval"]
    assert totals["structural"]["rate_lower_bound"] is not None
    row = report["per_file"][0]
    assert row["status"] == "judged" and row["structural_pass"] is True
    assert row["checks"]["field_present"] is True
    assert row["checks"]["entries_sane"] is True
    assert row["checks"]["targets_resolve"] is True
    assert row["checks"]["manifest_entry_count_match"] is True
    assert row["entryCount"] == 3
    # dirty flag recorded verbatim (authored default is "1"), never gated
    assert row["tocDirty"] == "1"
    assert report["failures"] == []
    # no renumber sample requested -> null block, oracle never consulted
    assert report["renumberSample"] is None
    assert report["generatedAt"] is None


def test_non_toc_doc_fails_structurally_but_run_publishes(tmp_path: Path) -> None:
    doc = _plain_doc(tmp_path / "plain.hwpx")
    manifest = _manifest(tmp_path / "manifest.json", [_record("authoredtoc-00", doc)])

    report, code = mod.run(manifest, tmp_path)

    # honesty rule: a low rate is publishable truth — exit stays 0
    assert code == mod.EXIT_OK
    row = report["per_file"][0]
    assert row["status"] == "judged" and row["structural_pass"] is False
    assert row["checks"]["field_present"] is False
    assert row["tocDirty"] is None
    totals = report["totals"]
    assert totals["structural"]["pass"] == 0 and totals["structural"]["fail"] == 1
    assert totals["structural"]["all_pass"] is False
    assert totals["structural"]["check_failure_histogram"]["field_present"] == 1
    assert len(report["failures"]) == 1
    assert "field_present" in report["failures"][0]["reason"]


def test_only_authored_toc_stratum_records_are_selected(tmp_path: Path) -> None:
    toc = _toc_doc(tmp_path / "toc.hwpx")
    other = _plain_doc(tmp_path / "other.hwpx")
    manifest = _manifest(
        tmp_path / "manifest.json",
        [
            _record("pii-00", other, stratum="pii-merge"),
            _record("authoredtoc-00", toc),
            _record("runformat-00", other, stratum="reading-runformat"),
        ],
    )

    report, code = mod.run(manifest, tmp_path)

    assert code == mod.EXIT_OK
    assert report["totals"]["records"] == 1
    assert [r["id"] for r in report["per_file"]] == ["authoredtoc-00"]


def test_aggregation_and_rule_of_three_math(tmp_path: Path) -> None:
    docs = [
        _toc_doc(tmp_path / "a.hwpx"),
        _toc_doc(tmp_path / "b.hwpx"),
        _plain_doc(tmp_path / "c.hwpx"),  # judged but fails structurally
    ]
    manifest = _manifest(
        tmp_path / "manifest.json",
        [_record(f"authoredtoc-0{i}", d) for i, d in enumerate(docs)],
    )

    report, code = mod.run(manifest, tmp_path)

    assert code == mod.EXIT_OK
    s = report["totals"]["structural"]
    assert (s["pass"], s["fail"]) == (2, 1)
    assert s["rate"] == round(2 / 3, 4)
    # single definition of the published bound: delegate agrees with the report
    assert s["rate_lower_bound"] == mod.rule_of_three_lower_bound(1, 3)
    assert s["rate_interval"] == mod.rule_of_three_text(1, 3)


def test_exit_3_when_zero_records_match(tmp_path: Path) -> None:
    other = _plain_doc(tmp_path / "other.hwpx")
    manifest = _manifest(
        tmp_path / "manifest.json", [_record("pii-00", other, stratum="pii-merge")]
    )

    report, code = mod.run(manifest, tmp_path)

    assert code == mod.EXIT_NO_RECORDS
    assert report["totals"]["records"] == 0


def test_withheld_and_missing_files_are_listed_not_judged(tmp_path: Path) -> None:
    toc = _toc_doc(tmp_path / "toc.hwpx")
    manifest = _manifest(
        tmp_path / "manifest.json",
        [
            _record("authoredtoc-00", toc),
            _record("authoredtoc-01", None, produced=False),
            _record("authoredtoc-02", tmp_path / "ghost.hwpx"),
        ],
    )

    report, code = mod.run(manifest, tmp_path)

    assert code == mod.EXIT_OK
    totals = report["totals"]
    assert totals["records"] == 3 and totals["judged"] == 1
    assert totals["withheld"] == 1 and totals["missing_file"] == 1
    assert totals["produced"] == 2
    assert totals["coverage"] == 0.5
    statuses = {r["id"]: r["status"] for r in report["per_file"]}
    assert statuses["authoredtoc-01"] == "withheld"
    assert statuses["authoredtoc-02"] == "missing_file"
    failure_ids = {f["id"] for f in report["failures"]}
    assert failure_ids == {"authoredtoc-01", "authoredtoc-02"}


def test_manifest_entry_count_mismatch_fails_the_doc(tmp_path: Path) -> None:
    doc = _toc_doc(tmp_path / "toc.hwpx", count=3)
    manifest = _manifest(
        tmp_path / "manifest.json", [_record("authoredtoc-00", doc, entry_count=99)]
    )

    report, _code = mod.run(manifest, tmp_path)

    row = report["per_file"][0]
    assert row["structural_pass"] is False
    assert row["checks"]["manifest_entry_count_match"] is False
    hist = report["totals"]["structural"]["check_failure_histogram"]
    assert hist == {"manifest_entry_count_match": 1}


# ---------------------------------------------------------------------------------
# renumber-sample leg (mode 2) — FAKE oracle only, synthetic word boxes
# ---------------------------------------------------------------------------------
def _fake_boxes(pages: dict[int, list[str]]):
    """Word boxes where each string in a page's list is its own LINE
    (test_toc_fidelity precedent)."""
    from hwpx.form_fit.wordbox import WordBox

    boxes = []
    for page, lines in pages.items():
        for line_no, line in enumerate(lines):
            for word_no, word in enumerate(line.split()):
                boxes.append(
                    WordBox(
                        x0=word_no, y0=line_no, x1=word_no + 1, y1=line_no + 1,
                        text=word, page=page, block=0, line=line_no, word_no=word_no,
                    )
                )
    return boxes


def _pages_for(hwpx_path: str, page_of: dict[str, int] | None = None) -> dict[int, list[str]]:
    """Synthetic render of a refreshed doc: TOC entry lines on fitz page 0,
    each heading as its own line on page_of[title] (default: its cached page)."""
    model = tf.parse_toc_model(str(hwpx_path))
    pages: dict[int, list[str]] = {0: ["< 제목 차례 >"]}
    for entry in model.entries:
        pages[0].append(f"{entry.title} ..... {entry.cached_page}")
    for entry in model.entries:
        # entry.title carries the emitted numbering prefix ("2. 개요 …"), so
        # page_of keys match by substring
        target = next(
            (pg for key, pg in (page_of or {}).items() if key in entry.title),
            entry.cached_page or 1,
        )
        pages.setdefault(target - 1, []).append(entry.title)
    return pages


class FakeOracle:
    """No GUI, no Hancom: refresh is a no-op save-marker, render writes a stub
    'pdf' whose word boxes are served by a monkeypatched extract_word_boxes.
    Records every call so tests can assert session separation and that the
    frozen corpus file itself is never touched."""

    def __init__(self, *, refresh_ok: bool = True):
        self.refresh_ok = refresh_ok
        self.events: list[tuple[str, str]] = []
        self.pdf_to_hwpx: dict[str, str] = {}

    def available(self) -> bool:
        return True

    def refresh_document(self, path: str) -> bool:
        self.events.append(("refresh", str(path)))
        return self.refresh_ok

    def render_pdf(self, path: str, out_pdf: str | None = None) -> str | None:
        self.events.append(("render", str(path)))
        out = out_pdf or str(path) + ".pdf"
        Path(out).write_bytes(b"%PDF-1.4 fake")
        self.pdf_to_hwpx[str(out)] = str(path)
        return out


class _UnavailableOracle:
    def available(self) -> bool:
        return False

    def refresh_document(self, path: str) -> bool:  # pragma: no cover - guard
        raise AssertionError("refresh must never run when the oracle is unavailable")

    def render_pdf(self, path: str, out_pdf: str | None = None):  # pragma: no cover
        raise AssertionError("render must never run when the oracle is unavailable")


def _patch_boxes(monkeypatch, oracle: FakeOracle, page_of: dict[str, int] | None = None):
    monkeypatch.setattr(
        "hwpx.form_fit.wordbox.extract_word_boxes",
        lambda pdf, **kw: _fake_boxes(_pages_for(oracle.pdf_to_hwpx[str(pdf)], page_of)),
    )


def test_renumber_sample_verified_with_fake_oracle(tmp_path: Path, monkeypatch) -> None:
    docs = [_toc_doc(tmp_path / f"toc-{i}.hwpx") for i in range(2)]
    manifest = _manifest(
        tmp_path / "manifest.json",
        [_record(f"authoredtoc-0{i}", d) for i, d in enumerate(docs)],
    )
    oracle = FakeOracle()
    _patch_boxes(monkeypatch, oracle)
    workdir = tmp_path / "renumber-work"
    frozen_before = [d.read_bytes() for d in docs]

    report, code = mod.run(
        manifest, tmp_path, renumber_sample=2, oracle=oracle, renumber_workdir=workdir
    )

    assert code == mod.EXIT_OK
    sample = report["renumberSample"]
    assert sample["sampled"] == 2 and sample["renderChecked"] == 2
    assert sample["verified"] == 2 and sample["stale"] == 0 and sample["unverified"] == 0
    assert sample["verifiedRatio"] == 1.0
    assert "rule of three" in sample["verifiedInterval"]
    assert all(r["verdict"] == "verified" and r["tocRatio"] == 1.0 for r in sample["perDoc"])
    # session separation: exactly one refresh THEN one render per doc, as
    # separate calls (M7 crash contract)
    per_path: dict[str, list[str]] = {}
    for kind, p in oracle.events:
        per_path.setdefault(p, []).append(kind)
    assert all(kinds == ["refresh", "render"] for kinds in per_path.values())
    assert len(per_path) == 2
    # the oracle only ever saw the WORK copies; the frozen corpus is untouched
    assert all(str(workdir) in p for _kind, p in oracle.events)
    assert [d.read_bytes() for d in docs] == frozen_before


def test_renumber_sample_detects_stale_and_publishes_low_ratio(
    tmp_path: Path, monkeypatch
) -> None:
    doc = _toc_doc(tmp_path / "toc.hwpx")
    manifest = _manifest(tmp_path / "manifest.json", [_record("authoredtoc-00", doc)])
    oracle = FakeOracle()
    # render the second heading on page 2 while its cache still says 1 -> stale
    _patch_boxes(monkeypatch, oracle, page_of={"개요 2번 제목": 2})

    report, code = mod.run(
        manifest, tmp_path, renumber_sample=1, oracle=oracle,
        renumber_workdir=tmp_path / "w",
    )

    # render-checked measurement happened; the low number is published (exit 0)
    assert code == mod.EXIT_OK
    sample = report["renumberSample"]
    assert sample["stale"] == 1 and sample["verified"] == 0
    assert sample["verifiedRatio"] == 0.0
    assert sample["perDoc"][0]["verdict"] == "stale"
    assert sample["perDoc"][0]["tocRatio"] < 1.0


def test_renumber_sample_unavailable_oracle_never_passes(tmp_path: Path) -> None:
    doc = _toc_doc(tmp_path / "toc.hwpx")
    manifest = _manifest(tmp_path / "manifest.json", [_record("authoredtoc-00", doc)])

    for oracle in (_UnavailableOracle(), None):
        report, code = mod.run(
            manifest, tmp_path, renumber_sample=1, oracle=oracle,
            renumber_workdir=tmp_path / "w",
        )
        assert code == mod.EXIT_SAMPLE_UNVERIFIED
        sample = report["renumberSample"]
        assert sample["verified"] == 0 and sample["unverified"] == 1
        assert sample["renderChecked"] == 0
        row = sample["perDoc"][0]
        assert row["verdict"] == "unverified"
        assert "unavailable" in row["reason"]
        assert sample["oracle"]["available"] is False


def test_renumber_refresh_failure_degrades_and_skips_render(tmp_path: Path) -> None:
    doc = _toc_doc(tmp_path / "toc.hwpx")
    manifest = _manifest(tmp_path / "manifest.json", [_record("authoredtoc-00", doc)])
    oracle = FakeOracle(refresh_ok=False)

    report, code = mod.run(
        manifest, tmp_path, renumber_sample=1, oracle=oracle,
        renumber_workdir=tmp_path / "w",
    )

    assert code == mod.EXIT_SAMPLE_UNVERIFIED
    row = report["renumberSample"]["perDoc"][0]
    assert row["refreshed"] is False and row["verdict"] == "unverified"
    # render must NOT run after a failed refresh (no second session)
    assert [kind for kind, _p in oracle.events] == ["refresh"]


def test_renumber_sample_picks_first_n_in_manifest_order(
    tmp_path: Path, monkeypatch
) -> None:
    docs = [_toc_doc(tmp_path / f"toc-{i}.hwpx") for i in range(3)]
    records = [_record(f"authoredtoc-0{i}", d) for i, d in enumerate(docs)]
    # a withheld record ahead of the produced ones is skipped, not sampled
    records.insert(0, _record("authoredtoc-w", None, produced=False))
    manifest = _manifest(tmp_path / "manifest.json", records)
    oracle = FakeOracle()
    _patch_boxes(monkeypatch, oracle)

    report, _code = mod.run(
        manifest, tmp_path, renumber_sample=2, oracle=oracle,
        renumber_workdir=tmp_path / "w",
    )

    sample = report["renumberSample"]
    assert [r["id"] for r in sample["perDoc"]] == ["authoredtoc-00", "authoredtoc-01"]
    assert sample["skipped"] == [
        {"id": "authoredtoc-w", "reason": "withheld (produced=false)"}
    ]


# ---------------------------------------------------------------------------------
# CLI (no oracle path: --renumber-sample defaults to 0)
# ---------------------------------------------------------------------------------
def test_cli_writes_report_and_exit_codes(tmp_path: Path, capsys) -> None:
    doc = _toc_doc(tmp_path / "toc.hwpx")
    good = _manifest(tmp_path / "good.json", [_record("authoredtoc-00", doc)])
    empty = _manifest(tmp_path / "empty.json", [])
    out = tmp_path / "report.json"

    assert mod.main(["--manifest", str(good), "--corpus-root", str(tmp_path),
                     "--out", str(out)]) == mod.EXIT_OK
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["report"] == mod.REPORT_SCHEMA
    assert written["generatedAt"] is None
    assert written["renumberSample"] is None
    assert "structural_pass 1/1" in capsys.readouterr().out

    assert mod.main(["--manifest", str(empty), "--corpus-root", str(tmp_path),
                     "--out", str(out)]) == mod.EXIT_NO_RECORDS
    assert mod.main(["--manifest", str(tmp_path / "nope.json"),
                     "--out", str(out)]) == mod.EXIT_NO_RECORDS
