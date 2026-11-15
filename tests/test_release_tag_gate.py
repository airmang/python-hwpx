# SPDX-License-Identifier: Apache-2.0
"""릴리스 태그 형식은 발행 앞에서 걸러야 한다.

6.12까지 release.yml은 ``v*``와 ``[0-9]*`` 태그를 모두 받았는데, PyPI 발행 **뒤에**
도는 ``scripts/verify_release_hashes.py``는 ``v``와 최종판 버전(``v7.0.0``)만
받는다. ``7.0.0``이나 ``v7.0.0rc1`` 태그는 PyPI에 올라간 다음에야 실패했다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
SCRIPT = ROOT / "scripts" / "verify_release_hashes.py"
TAG_GATE = 'python scripts/verify_release_hashes.py --tag "${TAG_NAME}" --tag-only'


def _verifier():
    spec = importlib.util.spec_from_file_location("verify_release_hashes_gate", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _release_steps() -> list[dict]:
    parsed = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    return parsed["jobs"]["release"]["steps"]


def test_release_trigger_takes_only_v_tags() -> None:
    parsed = yaml.safe_load(RELEASE.read_text(encoding="utf-8"))
    trigger = parsed["on"] if "on" in parsed else parsed[True]
    assert trigger == {"push": {"tags": ["v*"]}}


def test_tag_format_is_checked_before_build_and_publish() -> None:
    steps = _release_steps()
    names = [step.get("name") for step in steps]
    gate_index = next(
        index for index, step in enumerate(steps) if TAG_GATE in str(step.get("run", ""))
    )
    build_index = names.index("Build distributions (migrated from scripts/build-and-publish.sh)")
    publish_index = next(
        index
        for index, step in enumerate(steps)
        if str(step.get("uses", "")).startswith("pypa/gh-action-pypi-publish@")
    )
    assert gate_index < build_index < publish_index


@pytest.mark.parametrize("tag", ["7.0.0", "v7.0.0rc1", "v7.0.0.dev1", "release-7.0.0"])
def test_tag_only_mode_refuses_tags_the_post_publish_check_refuses(tag: str) -> None:
    verifier = _verifier()
    with pytest.raises(ValueError):
        verifier.main(["--tag", tag, "--tag-only"])


def test_tag_only_mode_accepts_a_final_v_tag_without_manifest(
    capsys: pytest.CaptureFixture[str],
) -> None:
    verifier = _verifier()
    assert verifier.main(["--tag", "v7.0.0", "--tag-only"]) == 0
    assert "7.0.0" in capsys.readouterr().out


def test_full_mode_still_requires_manifest_and_asset_dir() -> None:
    verifier = _verifier()
    with pytest.raises(SystemExit):
        verifier.main(["--tag", "v7.0.0"])
