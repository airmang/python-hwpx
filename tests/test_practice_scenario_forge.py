from __future__ import annotations

import copy

import pytest

from hwpx.practice import (
    apply_mutation,
    controlled_mutation,
    reverse_mutation,
    synthetic_dossier,
    validate_controlled_mutation,
    validate_synthetic_dossier,
)


def test_synthetic_dossier_is_deterministic_and_visibly_synthetic() -> None:
    first = synthetic_dossier("forge-seed", 7)
    second = synthetic_dossier("forge-seed", 7)

    assert first == second
    assert first["synthetic"] is True
    assert all(value.startswith("합성-") for value in first["fields"].values())
    assert validate_synthetic_dossier(first, forbidden_values=["실제학생", "실제학교"]) == first


def test_synthetic_dossier_rejects_private_value_reuse() -> None:
    dossier = synthetic_dossier("forge-seed", 1)
    dossier["fields"]["담당자"] = "실제학생"
    with pytest.raises(ValueError, match="known sensitive value"):
        validate_synthetic_dossier(dossier, forbidden_values=["실제학생"])


@pytest.mark.parametrize(
    "task_kind",
    [
        "reverse_restore",
        "constrained_edit",
        "known_template_fill",
        "unknown_form_fill",
        "structural_edit",
        "must_abstain",
    ],
)
def test_controlled_mutations_reverse_exactly(task_kind: str) -> None:
    dossier = synthetic_dossier("forge-seed", 2)
    mutation = controlled_mutation(task_kind, dossier, seed="forge-seed", index=2)
    model = {"paragraphs": [], "fields": {}, "rows": []}

    changed = apply_mutation(model, mutation)
    restored = reverse_mutation(changed, mutation)

    assert restored == model
    assert validate_controlled_mutation(mutation) == mutation


def test_non_reversible_authoring_fails_closed() -> None:
    dossier = synthetic_dossier("forge-seed", 3)
    mutation = controlled_mutation("typed_authoring", dossier, seed="forge-seed", index=3)
    changed = apply_mutation({}, mutation)
    assert "authored" in changed
    with pytest.raises(ValueError, match="not reversible"):
        reverse_mutation(changed, mutation)


def test_mutation_id_detects_tampering() -> None:
    mutation = controlled_mutation(
        "constrained_edit", synthetic_dossier("forge-seed", 4), seed="forge-seed", index=4
    )
    tampered = copy.deepcopy(mutation)
    tampered["after"]["markerText"] = "합성-변조"
    with pytest.raises(ValueError, match="ID mismatch"):
        validate_controlled_mutation(tampered)
