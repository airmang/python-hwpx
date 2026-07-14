"""Deterministic synthetic Korean-school dossiers with no source value reuse."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from .registry import SHA256_PATTERN, assert_redacted_payload

SYNTHETIC_DOSSIER_SCHEMA = "hwpx.synthetic-dossier/v1"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def synthetic_dossier(seed: str, index: int) -> dict[str, Any]:
    """Create a reproducible dossier whose values are visibly synthetic."""
    if not seed or not isinstance(index, int) or index < 0:
        raise ValueError("synthetic dossier requires a seed and non-negative index")
    digest = hashlib.sha256(f"{seed}\n{index}".encode("utf-8")).hexdigest()
    number = int(digest[:8], 16)
    fields = {
        "기관": f"합성-새봄학교-{number % 97 + 1:02d}",
        "담당자": f"합성-연습담당-{number % 997 + 1:03d}",
        "대상": f"합성-학생집단-{number % 41 + 1:02d}",
        "일자": f"합성-일자-2099-{number % 12 + 1:02d}-{number % 27 + 1:02d}",
        "학년반": f"합성-학급-{number % 3 + 1}-{number % 8 + 1}",
        "금액": f"합성-금액-{(number % 900 + 100) * 1000}원",
        "목적": f"합성-문서편집연습-{digest[8:16].upper()}",
        "문서번호": f"합성-연습-{digest[16:24].upper()}",
    }
    dossier: dict[str, Any] = {
        "schema": SYNTHETIC_DOSSIER_SCHEMA,
        "synthetic": True,
        "dossierId": f"DOS-{digest[:20].upper()}",
        "seedSha256": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
        "fields": fields,
    }
    dossier["dossierSha256"] = hashlib.sha256(_canonical(dossier)).hexdigest()
    return validate_synthetic_dossier(dossier)


def validate_synthetic_dossier(
    value: Mapping[str, Any],
    *,
    forbidden_values: Sequence[str] = (),
) -> dict[str, Any]:
    raw = dict(value)
    assert_redacted_payload(raw, sensitive_values=forbidden_values)
    if raw.get("schema") != SYNTHETIC_DOSSIER_SCHEMA or raw.get("synthetic") is not True:
        raise ValueError("unsupported or non-synthetic dossier")
    if not str(raw.get("dossierId", "")).startswith("DOS-"):
        raise ValueError("synthetic dossierId is required")
    fields = raw.get("fields")
    if not isinstance(fields, Mapping) or not fields:
        raise ValueError("synthetic dossier fields are required")
    if any(not isinstance(item, str) or not item.startswith("합성-") for item in fields.values()):
        raise ValueError("every dossier field must be visibly synthetic")
    supplied = str(raw.get("dossierSha256", ""))
    if not SHA256_PATTERN.fullmatch(supplied):
        raise ValueError("synthetic dossier hash is required")
    payload = dict(raw)
    payload.pop("dossierSha256", None)
    expected = hashlib.sha256(_canonical(payload)).hexdigest()
    if supplied != expected:
        raise ValueError("synthetic dossier hash mismatch")
    return raw


__all__ = [
    "SYNTHETIC_DOSSIER_SCHEMA",
    "synthetic_dossier",
    "validate_synthetic_dossier",
]
