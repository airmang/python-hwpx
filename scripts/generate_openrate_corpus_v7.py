# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v7 — the 6.3 cycle's authorable read-write gaps, additive over v6.

Why v7 exists
=============

Cycle 6.3 closed three audit-identified gaps (감사 갭 #8 문자 서식 잔여, #11
필드 파라미터, #14 compose/container). Of those three, only **two** produced
a new *authoring* surface — the third (compose/container) was a read-only
train (감사 지시: "compose(6)·container(8) 읽기 우선, 저작 보류"): it
promoted ``hp:compose``/nested ``hp:container`` children from generic
passthrough to typed models on the *read* path, but added no ``add_*``/
``ensure_*`` that could put either into a document that did not already
have one. openrate corpora measure "does what we now let a caller *write*
survive a real Hancom open/render" — there is nothing new to author for
compose/container this cycle, so **v7 has no ``authored-compose`` stratum**.
Re-running v1-v6's own strata here would not test anything new either (see
each predecessor's own scopeNote for what it already covers).

Two strata (all deterministic — fixed seeds, bank rotation, no wall clock)
=============================================================================

* ``authored-charformat``  15  ``doc.styles.ensure_run`` — ``script``
                                 ("sup"/"sub", rotated: the *real*
                                 ``hh:supscript``/``hh:subscript`` flag
                                 element paired with the existing relSz/
                                 offset approximation, not a replacement of
                                 it — cycle-6.3 train 10's central finding)
                                 · ``outline`` (rotated across the full
                                 7-value ``hc:LineType1`` vocabulary,
                                 NONE included) · ``emboss``/``engrave``
                                 (rotated across emboss-only/engrave-only/
                                 neither — three independent banks, not
                                 locked together, so records genuinely
                                 differ record to record)
* ``authored-fieldparams`` 15  ``doc.refs.add_hyperlink`` (the existing,
                                 already render-verified field-creation
                                 path) + a ``hp:parameters`` payload built
                                 from the new general-purpose
                                 ``hwpx.oxml.body.ParameterList``/
                                 ``Parameter`` model (cycle-6.3 train 11).
                                 Every record keeps the 5-param
                                 ``HWPHYPERLINK_*`` payload
                                 ``toc_author.py`` already proved safe
                                 (Prop/Command/Category/TargetType/
                                 DocOpenType) as an unmodified safety
                                 baseline, then *appends* one extra
                                 ``booleanParam``/``integerParam``/
                                 ``stringParam`` trio wrapped in a rotating
                                 named ``listParam`` — real Hancom's own
                                 tolerance for unrecognized-but-well-formed
                                 parameter names is exactly what this
                                 measures. ~1/3 of records (``idx % 3 == 0``)
                                 nest a *second* ``listParam`` inside the
                                 first, exercising the recursive case the
                                 flat ``FieldParameter`` model never could.
                                 ``comboBox`` is explicitly **out of
                                 scope**: train 11 gave it a typed *read*
                                 accessor (``FormComboBoxControl.list_items``)
                                 but no ``add_combo_box``/``ensure_*``
                                 authoring entry point exists yet — nothing
                                 new to put in an openrate corpus for it.

That is 30 records total, not the "3 surfaces x 15 = 45" the cycle brief
first sketched — compose/container's authoring absence removes a whole
stratum rather than leaving a partial one. Padding either remaining stratum
past 15 to hit 45 would inflate the rotation banks past what is actually
meaningful (the vocabulary sizes here — 2-value script, 7-value outline,
3-value emboss/engrave combo — are small; a bank of 22-23 would mostly
repeat) purely to hit a round number, which is worse than an honest 30.

Generation ONLY — no Hancom oracle here. Every produced file gets the static
``validate_editor_open_safety`` pre-filter (necessary, not sufficient); the
real verdict comes from the macOS GUI oracle (osascript-driven — the
distinct 6.2-era finding: the oracle is *this* Mac, not the 192.168.50.161
Windows box, which is a separate second observer). ``render_jobs_v7.json``
lists a PDF export job per produced file, same shape as v4/v5/v6.

Field names are the render pipeline's contract (see v4/v5/v6's own
comments) — a bare array of ``{sourceId,stratum,src,pdf}``, not wrapped in
a ``{"jobs": [...]}`` object.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly, not
``importlib.metadata`` — same staleness rationale v4-v6 already established.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v7.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

PYTHON_HWPX = Path(__file__).resolve().parent.parent
# Explicit — this worktree's src/ must win over whatever editable install the
# running venv happens to carry (v5's own comment records the exact failure
# mode this guards against).
sys.path.insert(0, str(PYTHON_HWPX / "src"))
sys.path.insert(0, str(PYTHON_HWPX / "scripts"))

from generate_openrate_corpus import (  # noqa: E402
    SUBJECT_BANK,
    cycle,
    record,
)
from generate_openrate_corpus_v3 import (  # noqa: E402
    BOX_NEGATIVE_CONTROLS,
    OUT_DIR_V3,
    _base_document,
)
from generate_openrate_corpus_v4 import (  # noqa: E402
    OUT_DIR_V4,
    _deterministic_object_ids,
    _frozen_reference,
    _git_commit,
    _read_pyproject_version,
)
from generate_openrate_corpus_v5 import OUT_DIR_V5  # noqa: E402
from generate_openrate_corpus_v6 import OUT_DIR_V6  # noqa: E402

from hwpx.oxml.body import Parameter, ParameterList, parameter_list_to_xml  # noqa: E402
from hwpx.oxml.namespaces import HP  # noqa: E402

# Same discipline v4-v6 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) — restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V7 = PYTHON_HWPX / "work" / "openrate-corpus-v7"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v7"
BOX_ROOT = "C:\\openrate\\v7"
BOX_ROOT_PDF = "C:\\openrate\\v7-pdf"


# ================================================================================
# new-stratum banks (rotation only — no wall clock, no randomness)
# ================================================================================
SCRIPT_BANK = ("sup", "sub")
#: OWPML hc:LineType1 (Header XML schema.xml:906) — hh:outline's full vocabulary.
OUTLINE_BANK = ("NONE", "SOLID", "DOT", "THICK", "DASH", "DASH_DOT", "DASH_DOT_DOT")
#: (emboss, engrave) — three independent states, not a fourth "both" combo:
#: 양각/음각 are opposite visual effects in the Hangul character-format
#: dialog and no real-corpus or schema evidence supports combining them.
EMBOSS_ENGRAVE_BANK: tuple[tuple[bool | None, bool | None], ...] = (
    (True, None), (None, True), (None, None),
)

#: rotating name for the *extra* listParam every authored-fieldparams record
#: appends onto the proven 5-param HYPERLINK baseline (see module docstring).
FIELDPARAM_LISTPARAM_NAME_BANK = ("CustomOptions", "ExtraFlags", "RenderHints", "LinkMeta")
FIELDPARAM_BOOL_BANK = (True, False)
FIELDPARAM_INT_BANK = (0, 1, 7, 42, 100)
FIELDPARAM_STR_BANK = ("alpha", "beta", "gamma", "delta")


def _tool_versions() -> dict[str, str | None]:
    """python-hwpx's own version, pyproject-first (see module docstring)."""

    versions: dict[str, str | None] = {}
    versions["python-hwpx"] = _read_pyproject_version(PYTHON_HWPX / "pyproject.toml")
    if versions["python-hwpx"] is None:
        import hwpx

        versions["python-hwpx"] = str(hwpx.__version__)
    return versions


# ================================================================================
# strata
# ================================================================================
def gen_charformat(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v7-charformat-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "문자 서식 잔여 표본")
            script = SCRIPT_BANK[idx % len(SCRIPT_BANK)]
            outline = OUTLINE_BANK[idx % len(OUTLINE_BANK)]
            emboss, engrave = EMBOSS_ENGRAVE_BANK[idx % len(EMBOSS_ENGRAVE_BANK)]
            style_id = document.styles.ensure_run(
                script=script, outline=outline, emboss=emboss, engrave=engrave,
            )
            document.add_paragraph(
                f"문자서식 표본 {idx} ({script}/{outline}): {cycle(SUBJECT_BANK, idx)}",
                char_pr_id_ref=style_id,
            )
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-charformat", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-charformat", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def _fieldparams_extra_listparam(idx: int) -> Parameter:
    """The new-capability payload every record appends to the proven
    5-param HYPERLINK baseline — see module docstring for why this shape."""

    inner_bool = Parameter(
        name="Enabled", kind="boolean", value=FIELDPARAM_BOOL_BANK[idx % len(FIELDPARAM_BOOL_BANK)],
    )
    inner_int = Parameter(
        name="Priority", kind="integer", value=FIELDPARAM_INT_BANK[idx % len(FIELDPARAM_INT_BANK)],
    )
    inner_str = Parameter(
        name="Label", kind="string", value=FIELDPARAM_STR_BANK[idx % len(FIELDPARAM_STR_BANK)],
    )
    custom_list = Parameter(
        name=FIELDPARAM_LISTPARAM_NAME_BANK[idx % len(FIELDPARAM_LISTPARAM_NAME_BANK)],
        kind="list",
        items=[inner_bool, inner_int, inner_str],
    )
    if idx % 3 == 0:
        # ~1/3 of records nest a second listParam inside the first — the
        # recursive case a flat FieldParameter tuple could never represent.
        custom_list = Parameter(
            name=custom_list.name, kind="list",
            items=[custom_list, Parameter(name="Flag", kind="boolean", value=True)],
        )
    return custom_list


def gen_fieldparams(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v7-fieldparams-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "필드 파라미터 표본")
            target_id = f"anchor-{idx}"
            inline = document.refs.add_hyperlink(f"#{target_id}", f"파라미터 링크 {idx}")
            field_begin = inline.element.find(f"{HP}fieldBegin")
            if field_begin is None:  # pragma: no cover - defensive, would mean add_hyperlink's own shape changed
                raise RuntimeError("add_hyperlink did not produce a fieldBegin child")
            baseline = ParameterList(
                tag=f"{HP}parameters",
                name="",
                params=[
                    Parameter(name="Prop", kind="integer", value=0),
                    Parameter(name="Command", kind="string", value=f"?#{target_id};0;1;0;"),
                    Parameter(name="Category", kind="string", value="HWPHYPERLINK_TYPE_HWP"),
                    Parameter(name="TargetType", kind="string", value="HWPHYPERLINK_TARGET_OUTLINE"),
                    Parameter(name="DocOpenType", kind="string", value="HWPHYPERLINK_JUMP_CURRENTTAB"),
                ],
            )
            baseline.params.append(_fieldparams_extra_listparam(idx))
            field_begin.append(parameter_list_to_xml(baseline))
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-fieldparams", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-fieldparams", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-charformat", gen_charformat),
    ("authored-fieldparams", gen_fieldparams),
)


def main() -> int:
    if OUT_DIR_V7.exists() and any(OUT_DIR_V7.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V7} already exists — v7 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V7 / bucket
            bucket_dir.mkdir(parents=True, exist_ok=True)
            all_records += generator(bucket_dir)

    all_records.sort(key=lambda item: (item["bucket"], item["id"]))

    counts: dict[str, dict[str, Any]] = {}
    for entry in all_records:
        slot = counts.setdefault(
            entry["bucket"],
            {"requested": 0, "produced": 0, "withheld_ids": [], "static_unsafe_ids": []},
        )
        slot["requested"] += 1
        if entry["produced"]:
            slot["produced"] += 1
            if entry["static_open_safety_ok"] is False:
                slot["static_unsafe_ids"].append(entry["id"])
        else:
            slot["withheld_ids"].append(entry["id"])

    manifest = {
        "schemaVersion": MANIFEST_SCHEMA,
        "scopeNote": (
            "v7 is ADDITIVE over v6: 2 new strata exercising the ONLY two "
            "authorable surfaces the 6.3 cycle opened — character-format "
            "residuals (doc.styles.ensure_run(script=/outline=/emboss=/"
            "engrave=)) and general-purpose field parameters "
            "(hwpx.oxml.body.ParameterList/Parameter, appended onto "
            "doc.refs.add_hyperlink's proven fieldBegin/parameters shape). "
            "compose/container (the cycle's third gap) was a READ-ONLY "
            "train — hp:compose and nested hp:container children gained "
            "typed models on the parse side, but no add_*/ensure_* "
            "authoring entry point exists for either, so there is "
            "deliberately NO authored-compose stratum here; nothing new to "
            "author means nothing new for an openrate corpus to measure. "
            "comboBox similarly gained only a typed READ accessor "
            "(FormComboBoxControl.list_items) — no add_combo_box exists — "
            "so it is likewise absent from authored-fieldparams. This is "
            "30 records total (15+15), not v6's 60 (4 strata) or a padded "
            "45 — see module docstring for why padding was rejected. It is "
            "not a v6 re-run and does not re-touch v6's 4 strata; it does "
            "not replace v1-v6, which remain published with their own "
            "measurement stack and date."
        ),
        "generatedAt": None,  # root stamps it; determinism
        "toolVersions": _tool_versions(),
        "generatingCommit": {
            "python-hwpx": _git_commit(PYTHON_HWPX),
        },
        "boxRoot": BOX_ROOT,
        "boxRootPdf": BOX_ROOT_PDF,
        "negativeControlsByReference": list(BOX_NEGATIVE_CONTROLS),
        "frozenPredecessors": {
            "v3": _frozen_reference(OUT_DIR_V3 / "manifest.json"),
            "v4": _frozen_reference(OUT_DIR_V4 / "manifest.json"),
            "v5": _frozen_reference(OUT_DIR_V5 / "manifest.json"),
            "v6": _frozen_reference(OUT_DIR_V6 / "manifest.json"),
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V7 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V7 / "box_run_v7.filelist"
    lines = [
        f"{BOX_ROOT}\\{entry['bucket']}\\{entry['id']}.hwpx"
        for entry in all_records
        if entry["produced"]
    ]
    lines += list(BOX_NEGATIVE_CONTROLS)
    filelist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Field names are the render pipeline's contract (see module docstring —
    # v5's already-corrected shape, copied verbatim: a bare array of
    # {sourceId,stratum,src,pdf}, not {id,bucket,input,output} wrapped in a
    # {"jobs": [...]} object.
    render_jobs = [
        {
            "sourceId": entry["id"],
            "stratum": entry["bucket"],
            "src": f"{BOX_ROOT}\\{entry['bucket']}\\{entry['id']}.hwpx",
            "pdf": f"{BOX_ROOT_PDF}\\{entry['bucket']}\\{entry['id']}.pdf",
        }
        for entry in all_records
        if entry["produced"]
    ]
    render_jobs_path = OUT_DIR_V7 / "render_jobs_v7.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v7 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
    for bucket in sorted(counts):
        slot = counts[bucket]
        flags = ""
        if slot["withheld_ids"]:
            flags += f"  withheld={len(slot['withheld_ids'])}"
        if slot["static_unsafe_ids"]:
            flags += f"  STATIC-UNSAFE={slot['static_unsafe_ids']}"
        print(f"  {bucket:24s} {slot['produced']:3d}/{slot['requested']:3d}{flags}")
    print(f"manifest    : {manifest_path}")
    print(f"filelist    : {filelist_path}")
    print(f"render jobs : {render_jobs_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
