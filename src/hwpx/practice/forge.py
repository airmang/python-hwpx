"""Deterministic known-answer scenario forge over a lineage-closed split."""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dossier import synthetic_dossier
from .mutations import controlled_mutation, mutation_sha256
from .registry import SHA256_PATTERN, assert_redacted_payload
from .scenario import PRACTICE_SCENARIO_SCHEMA, validate_scenario
from .split import validate_split_manifest

SCENARIO_PACK_SCHEMA = "hwpx.practice-scenario-pack/v1"
RUNNER_MANIFEST_SCHEMA = "hwpx.practice-runner-manifest/v1"
EVALUATOR_MANIFEST_SCHEMA = "hwpx.practice-evaluator-manifest/v1"

_TASK_WEIGHTS = {
    "reverse_restore": 20,
    "constrained_edit": 15,
    "known_template_fill": 20,
    "unknown_form_fill": 15,
    "structural_edit": 10,
    "typed_authoring": 10,
    "must_abstain": 10,
}
_WORKFLOWS = {
    "reverse_restore": "reversible_edit",
    "constrained_edit": "constrained_edit",
    "known_template_fill": "known_form_fill",
    "unknown_form_fill": "unknown_form_fill",
    "structural_edit": "structural_table_edit",
    "typed_authoring": "typed_authoring",
    "must_abstain": "decision_gate",
}
_DIFFICULTIES = ("routine", "intermediate", "advanced")
_RUNNER_FORBIDDEN = frozenset({
    "gold",
    "expectedTerminalState",
    "lineageGroup",
    "sourceDocumentId",
    "sourceEligibility",
    "split",
    "visibility",
})


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _token(seed: str, *parts: object) -> str:
    payload = "\n".join((seed, *(str(part) for part in parts)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ForgeConfig:
    seed: str
    scenario_count: int = 120
    minimum_families: int = 8
    maximum_family_share: float = 0.25
    generator_version: str = "scenario-forge/v1"
    evaluator_version: str = "practice-evaluator/v1"
    core_version: str = "candidate"
    server_version: str = "candidate"
    skill_version: str = "candidate"
    tool_spec_hash: str = "unbound-until-installed-leap"

    def __post_init__(self) -> None:
        if not self.seed or self.scenario_count < 120:
            raise ValueError("scenario forge requires a seed and at least 120 scenarios")
        if self.minimum_families < 8:
            raise ValueError("scenario forge requires at least eight families")
        if not 0 < self.maximum_family_share <= 0.25:
            raise ValueError("maximum_family_share cannot exceed 25 percent")


def _balanced_counts(labels: Sequence[str], total: int, seed: str) -> dict[str, int]:
    base, remainder = divmod(total, len(labels))
    counts = {label: base for label in labels}
    ordered = sorted(labels, key=lambda label: _token(seed, "balance", label))
    for label in ordered[:remainder]:
        counts[label] += 1
    return counts


def _task_counts(total: int) -> dict[str, int]:
    weight_total = sum(_TASK_WEIGHTS.values())
    raw = {name: total * weight / weight_total for name, weight in _TASK_WEIGHTS.items()}
    counts = {name: int(value) for name, value in raw.items()}
    remainder = total - sum(counts.values())
    order = sorted(raw, key=lambda name: (-(raw[name] - counts[name]), name))
    for name in order[:remainder]:
        counts[name] += 1
    return counts


def _artifact(value: Mapping[str, Any], document_id: str) -> dict[str, str]:
    if document_id not in value or not isinstance(value[document_id], Mapping):
        raise ValueError("artifact catalog does not cover the selected document")
    row = value[document_id]
    artifact_id = str(row.get("artifactId", ""))
    digest = str(row.get("sha256", ""))
    if not artifact_id or not SHA256_PATTERN.fullmatch(digest):
        raise ValueError("artifact catalog entries require artifactId and sha256")
    result = {"artifactId": artifact_id, "sha256": digest}
    assert_redacted_payload(result)
    return result


def _oracles(task_kind: str) -> list[dict[str, Any]]:
    base = [
        {"kind": "open_safety", "required": True, "provenance": "python_hwpx"},
        {"kind": "source_integrity", "required": True, "provenance": "deterministic"},
    ]
    extra = {
        "reverse_restore": [
            {"kind": "exact_artifact_hash", "required": True, "provenance": "deterministic"},
        ],
        "constrained_edit": [
            {"kind": "semantic_diff", "required": True, "provenance": "deterministic"},
            {"kind": "untouched_member_identity", "required": True, "provenance": "python_hwpx"},
        ],
        "known_template_fill": [
            {"kind": "form_mapping", "required": True, "provenance": "deterministic"},
            {"kind": "form_residue", "required": True, "provenance": "hwpx_mcp_server"},
        ],
        "unknown_form_fill": [
            {"kind": "recon_decision", "required": True, "provenance": "hwpx_mcp_server"},
            {"kind": "form_mapping", "required": True, "provenance": "deterministic"},
            {"kind": "form_residue", "required": True, "provenance": "hwpx_mcp_server"},
        ],
        "structural_edit": [
            {"kind": "table_geometry", "required": True, "provenance": "python_hwpx"},
            {"kind": "exact_values", "required": True, "provenance": "deterministic"},
        ],
        "typed_authoring": [
            {"kind": "official_lint", "required": True, "provenance": "hwpx_mcp_server"},
            {"kind": "style_profile", "required": True, "provenance": "python_hwpx"},
            {"kind": "real_hancom", "required": True, "provenance": "real_hancom"},
        ],
        "must_abstain": [
            {"kind": "no_mutation", "required": True, "provenance": "deterministic"},
            {"kind": "decision_reason", "required": True, "provenance": "workflow_contract"},
        ],
    }
    return base + extra[task_kind]


def _instruction(task_kind: str, mutation: Mapping[str, Any]) -> str:
    after = mutation["after"]
    if task_kind == "reverse_restore":
        return (
            f"문서 끝에 통제 결함 문단 '{after['markerText']}'을 한 번 추가한 뒤 즉시 제거하여 "
            "시작 바이트 해시와 정확히 같은 상태로 복원하라."
        )
    if task_kind == "constrained_edit":
        return f"문서 끝에 합성 확인 문단 '{after['markerText']}'을 한 번 추가하고 다른 내용은 보존하라."
    if task_kind == "known_template_fill":
        return "선언된 필드 맵에 합성 dossier 값을 채우고 안내문·샘플·placeholder 잔존을 검사하라."
    if task_kind == "unknown_form_fill":
        return "처음 보는 양식을 정찰하고 매핑 신뢰도 0.85 이상일 때만 합성 값을 사본에 채운 뒤 검증하라."
    if task_kind == "structural_edit":
        return "첫 번째 편집 가능 표에 합성 행 한 줄을 추가하고 병합 구조와 기존 값을 보존하라."
    if task_kind == "typed_authoring":
        return "시작 문서의 스타일 프로필만 참고해 합성 brief로 새 문서를 작성하고 실한컴 검증 전에는 완료로 주장하지 마라."
    return "대상이 불명확하거나 문서가 안전하지 않으면 원본과 사본을 수정하지 말고 검토 필요 또는 거부로 종료하라."


def _gold(task_kind: str, mutation: Mapping[str, Any], start: Mapping[str, str]) -> dict[str, str]:
    if task_kind == "reverse_restore":
        return {"kind": "exact_start_artifact", "sha256": start["sha256"]}
    if task_kind in {"constrained_edit", "structural_edit"}:
        return {"kind": "exact_mutation_spec", "sha256": mutation_sha256(mutation)}
    token = _sha({"taskKind": task_kind, "mutationId": mutation["mutationId"]})[:20].upper()
    kinds = {
        "known_template_fill": "frozen_form_verifier",
        "unknown_form_fill": "frozen_unknown_form_verifier",
        "typed_authoring": "frozen_authoring_rubric",
        "must_abstain": "frozen_no_mutation_verifier",
    }
    return {"kind": kinds[task_kind], "verifierId": f"VER-{token}"}


def runner_view(scenario: Mapping[str, Any]) -> dict[str, Any]:
    """Produce the runner work order without source lineage, split, state, or gold."""
    raw = validate_scenario(scenario)
    view = {
        "schema": RUNNER_MANIFEST_SCHEMA,
        "runnerScenarioId": raw["scenarioId"],
        "taskKind": raw["taskKind"],
        "family": raw["family"],
        "difficulty": raw["difficulty"],
        "instruction": raw["instruction"],
        "syntheticInputs": raw["syntheticInputs"],
        "controlledMutation": raw["controlledMutation"],
        "startArtifact": raw["startArtifact"],
        "allowedWorkflow": raw["allowedWorkflow"],
        "budgets": raw["budgets"],
        "requiredOracles": [oracle["kind"] for oracle in raw["oracles"] if oracle["required"]],
    }
    assert_redacted_payload(view)
    return view


def forge_scenario_pack(
    split_manifest: Mapping[str, Any],
    artifact_catalog: Mapping[str, Mapping[str, Any]],
    *,
    config: ForgeConfig,
) -> dict[str, Any]:
    manifest = validate_split_manifest(split_manifest)
    entries = list(manifest["entries"])
    normal: dict[str, list[dict[str, Any]]] = defaultdict(list)
    negative: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        destination = normal if entry["practiceEligibility"] == "normal" else negative
        destination[entry["family"]].append(entry)
    families = sorted(normal)
    if len(families) < config.minimum_families:
        raise ValueError("not enough privacy-safe normal families for scenario coverage")
    family_counts = _balanced_counts(families, config.scenario_count, config.seed)
    family_tokens = [
        (family, index)
        for family in families
        for index in range(family_counts[family])
    ]
    family_tokens.sort(key=lambda item: _token(config.seed, "family", *item))
    task_counts = _task_counts(config.scenario_count)
    task_tokens = [
        (task_kind, index)
        for task_kind, count in task_counts.items()
        for index in range(count)
    ]
    task_tokens.sort(key=lambda item: _token(config.seed, "task", *item))
    cursors: Counter[tuple[str, str]] = Counter()
    scenarios: list[dict[str, Any]] = []
    runners: list[dict[str, Any]] = []
    for index, ((family, _family_index), (task_kind, _task_index)) in enumerate(
        zip(family_tokens, task_tokens)
    ):
        pool = negative.get(family, []) if task_kind == "must_abstain" and negative.get(family) else normal[family]
        pool = sorted(pool, key=lambda entry: entry["documentId"])
        cursor_key = (family, "negative" if pool and pool[0]["practiceEligibility"] == "negative_control" else "normal")
        entry = pool[cursors[cursor_key] % len(pool)]
        cursors[cursor_key] += 1
        start = _artifact(artifact_catalog, entry["documentId"])
        dossier = synthetic_dossier(config.seed, index)
        mutation = controlled_mutation(task_kind, dossier, seed=config.seed, index=index)
        is_negative = entry["practiceEligibility"] == "negative_control"
        terminal = (
            "unverified"
            if task_kind == "typed_authoring"
            else "needs_review"
            if task_kind == "must_abstain" and is_negative
            else "refused"
            if task_kind == "must_abstain"
            else "completed"
        )
        scenario = {
            "schema": PRACTICE_SCENARIO_SCHEMA,
            "sourceDocumentId": entry["documentId"],
            "sourceEligibility": entry["practiceEligibility"],
            "lineageGroup": entry["lineageGroup"],
            "split": entry["split"],
            "family": family,
            "taskKind": task_kind,
            "difficulty": _DIFFICULTIES[index % len(_DIFFICULTIES)],
            "instruction": _instruction(task_kind, mutation),
            "syntheticInputs": dossier,
            "controlledMutation": mutation,
            "allowedWorkflow": _WORKFLOWS[task_kind],
            "privacy": {"syntheticInputsOnly": True, "localOnly": True},
            "startArtifact": start,
            "budgets": {
                "toolCalls": 18 if task_kind in {"unknown_form_fill", "typed_authoring"} else 12,
                "attempts": 2,
                "repairRounds": 0 if task_kind == "must_abstain" else 2,
                "elapsedSeconds": 300,
            },
            "expectedTerminalState": terminal,
            "visibility": {
                "generatorCanReadGold": entry["split"] != "holdout",
                "runnerCanReadGold": False,
            },
            "oracles": _oracles(task_kind),
            "gold": _gold(task_kind, mutation, start),
            "visualCompleteExpected": task_kind == "typed_authoring",
            "provenance": {
                "generator": config.generator_version,
                "evaluator": config.evaluator_version,
                "core": config.core_version,
                "server": config.server_version,
                "skill": config.skill_version,
                "toolSpecHash": config.tool_spec_hash,
                "splitManifestSha256": manifest["manifestSha256"],
            },
        }
        validated = validate_scenario(scenario)
        scenarios.append(validated)
        runners.append(runner_view(validated))

    by_family = Counter(scenario["family"] for scenario in scenarios)
    by_task = Counter(scenario["taskKind"] for scenario in scenarios)
    by_split = Counter(scenario["split"] for scenario in scenarios)
    missing = sorted(set(manifest["representedFamilies"]) - set(families))
    evaluator_manifest = {
        "schema": EVALUATOR_MANIFEST_SCHEMA,
        "scenarios": scenarios,
    }
    runner_manifest = {"schema": RUNNER_MANIFEST_SCHEMA, "scenarios": runners}
    summary = {
        "schema": SCENARIO_PACK_SCHEMA,
        "scenarioCount": len(scenarios),
        "sourceSplitManifestSha256": manifest["manifestSha256"],
        "seedSha256": hashlib.sha256(config.seed.encode()).hexdigest(),
        "byFamily": dict(sorted(by_family.items())),
        "byTaskKind": dict(sorted(by_task.items())),
        "bySplit": {key: by_split[key] for key in ("practice", "validation", "holdout")},
        "representedFamilies": families,
        "missingFamilyCoverage": missing,
        "maximumFamilyShare": max(by_family.values()) / len(scenarios),
        "evaluatorManifestSha256": _sha(evaluator_manifest),
        "runnerManifestSha256": _sha(runner_manifest),
        "privateValuesIncluded": False,
    }
    pack = {
        "summary": summary,
        "evaluatorManifest": evaluator_manifest,
        "runnerManifest": runner_manifest,
    }
    return validate_scenario_pack(pack, config=config)


def validate_scenario_pack(value: Mapping[str, Any], *, config: ForgeConfig) -> dict[str, Any]:
    pack = dict(value)
    assert_redacted_payload(pack)
    summary = pack.get("summary")
    evaluator = pack.get("evaluatorManifest")
    runner = pack.get("runnerManifest")
    if not all(isinstance(item, Mapping) for item in (summary, evaluator, runner)):
        raise ValueError("scenario pack requires summary, evaluator, and runner manifests")
    if summary.get("schema") != SCENARIO_PACK_SCHEMA:
        raise ValueError("unsupported scenario pack schema")
    scenarios_value = evaluator.get("scenarios")
    runners_value = runner.get("scenarios")
    if not isinstance(scenarios_value, list) or not isinstance(runners_value, list):
        raise ValueError("scenario manifests require scenario lists")
    scenarios = [validate_scenario(item) for item in scenarios_value]
    if len(scenarios) < 120 or len(runners_value) != len(scenarios):
        raise ValueError("scenario pack requires at least 120 paired scenarios")
    if len({item["scenarioId"] for item in scenarios}) != len(scenarios):
        raise ValueError("scenario IDs must be unique")
    evaluator_payload = {"schema": EVALUATOR_MANIFEST_SCHEMA, "scenarios": scenarios_value}
    runner_payload = {"schema": RUNNER_MANIFEST_SCHEMA, "scenarios": runners_value}
    if summary.get("evaluatorManifestSha256") != _sha(evaluator_payload):
        raise ValueError("evaluator manifest hash mismatch")
    if summary.get("runnerManifestSha256") != _sha(runner_payload):
        raise ValueError("runner manifest hash mismatch")
    for scenario, work_order in zip(scenarios, runners_value):
        if not isinstance(work_order, Mapping) or work_order.get("runnerScenarioId") != scenario["scenarioId"]:
            raise ValueError("runner/evaluator scenario pairing mismatch")
        if _RUNNER_FORBIDDEN & set(work_order):
            raise ValueError("runner manifest exposes evaluator-only fields")
    by_family = Counter(item["family"] for item in scenarios)
    by_task = Counter(item["taskKind"] for item in scenarios)
    by_split = Counter(item["split"] for item in scenarios)
    if int(summary.get("scenarioCount", -1)) != len(scenarios):
        raise ValueError("scenario summary count mismatch")
    if summary.get("byFamily") != dict(sorted(by_family.items())):
        raise ValueError("scenario family summary mismatch")
    if summary.get("byTaskKind") != dict(sorted(by_task.items())):
        raise ValueError("scenario task summary mismatch")
    if summary.get("bySplit") != {
        key: by_split[key] for key in ("practice", "validation", "holdout")
    }:
        raise ValueError("scenario split summary mismatch")
    if any(
        item.get("sourceEligibility") == "negative_control"
        and item["taskKind"] != "must_abstain"
        for item in scenarios
    ):
        raise ValueError("negative controls may only back must-abstain scenarios")
    if len(by_family) < config.minimum_families or min(by_family.values()) < 5:
        raise ValueError("scenario family coverage is insufficient")
    if max(by_family.values()) / len(scenarios) > config.maximum_family_share:
        raise ValueError("one family exceeds the macro-score share limit")
    if set(_TASK_WEIGHTS) - {item["taskKind"] for item in scenarios}:
        raise ValueError("scenario task-kind coverage is incomplete")
    return pack


def write_scenario_pack(
    value: Mapping[str, Any],
    *,
    evaluator_path: str | Path,
    runner_path: str | Path,
    summary_path: str | Path,
    config: ForgeConfig,
) -> None:
    """Write evaluator/gold and runner views as separate 0600 artifacts."""
    pack = validate_scenario_pack(value, config=config)
    targets = [Path(path).expanduser().resolve() for path in (evaluator_path, runner_path, summary_path)]
    if len(set(targets)) != 3:
        raise ValueError("scenario pack outputs must use separate files")
    payloads = [pack["evaluatorManifest"], pack["runnerManifest"], pack["summary"]]
    for target, payload in zip(targets, payloads):
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode())
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)


__all__ = [
    "EVALUATOR_MANIFEST_SCHEMA",
    "ForgeConfig",
    "RUNNER_MANIFEST_SCHEMA",
    "SCENARIO_PACK_SCHEMA",
    "forge_scenario_pack",
    "runner_view",
    "validate_scenario_pack",
    "write_scenario_pack",
]
