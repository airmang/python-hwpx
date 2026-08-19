# SPDX-License-Identifier: Apache-2.0
"""Release ordering must protect the already-published 5.x application."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest
import yaml

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 lane
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_legacy_release_cap.py"
RELEASE_HASH_SCRIPT = ROOT / "scripts" / "verify_release_hashes.py"
LEGACY_STEP = "Require public 5.1.1 legacy cap before core 5"
LEGACY_COMMAND = (
    'python scripts/verify_legacy_release_cap.py '
    '--venv "${RUNNER_TEMP}/hwpx-phase0-legacy"'
)
BUILD_STEP = "Build distributions (migrated from scripts/build-and-publish.sh)"
SBOM_STEP = "Generate release SBOM"
PYPI_ACTION = "pypa/gh-action-pypi-publish@"
GITHUB_ACTION = "softprops/action-gh-release@"
CHECKOUT_ACTION = (
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
)
EXPECTED_TRIGGER = {
    "push": {
        "tags": [
            "v*",
            "[0-9]*",
        ],
    },
}
EXPECTED_PREPUBLICATION_CHECKOUTS = {
    "legacy-cap": ((CHECKOUT_ACTION, None),),
    "prepublish": ((CHECKOUT_ACTION, None),),
}
REMOTE_HASH_STEP = "Verify PyPI and GitHub release hashes"
REMOTE_HASH_COMMAND = (
    "python scripts/verify_release_hashes.py "
    "--manifest release-artifacts/SHA256SUMS "
    '--asset-dir "${RUNNER_TEMP}/python-hwpx-release-assets" '
    '--tag "${GITHUB_REF_NAME}"'
)
EXPECTED_BUILD_RUN = """\
set -euo pipefail
export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
test -n "${SOURCE_DATE_EPOCH}"
python -m pip install "build==1.5.0" "twine==6.2.0"
rm -rf dist build
python -m build
twine check dist/*
mkdir -p release-artifacts
python - <<'PY'
import hashlib
from pathlib import Path

artifacts = sorted(path for path in Path("dist").iterdir() if path.is_file())
if not artifacts:
    raise SystemExit("dist/ has no release artifacts")
lines = [
    f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
    for path in artifacts
]
Path("release-artifacts/SHA256SUMS").write_text(
    "\\n".join(lines) + "\\n",
    encoding="utf-8",
)
PY
python scripts/check_public_hygiene.py
"""
EXPECTED_SBOM_RUN = """\
python -m venv .sbom-runtime
.sbom-runtime/bin/python -m pip install dist/*.whl
python -m venv .sbom-tool
.sbom-tool/bin/python -m pip install "cyclonedx-bom==7.3.0"
mkdir -p release-artifacts
.sbom-tool/bin/cyclonedx-py environment .sbom-runtime/bin/python \\
  --pyproject pyproject.toml \\
  --mc-type library \\
  --output-reproducible \\
  --output-format JSON \\
  --output-file "release-artifacts/python-hwpx-${GITHUB_REF_NAME}.cdx.json"
"""
EXPECTED_RELEASE_STEPS = (
    (
        "Checkout repository",
        "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
        False,
        None,
        None,
        None,
        None,
    ),
    (
        "Set up Python",
        "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
        False,
        {"python-version": "3.12"},
        None,
        None,
        None,
    ),
    (
        "Validate tag/version consistency",
        None,
        True,
        None,
        None,
        "bash",
        None,
    ),
    (
        "Extract latest changelog section for release notes",
        None,
        True,
        None,
        None,
        None,
        None,
    ),
    (BUILD_STEP, None, True, None, None, None, None),
    (SBOM_STEP, None, True, None, None, None, None),
    (
        "Publish package to PyPI",
        "pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33",
        False,
        None,
        None,
        None,
        None,
    ),
    (
        "Create GitHub Release",
        "softprops/action-gh-release@3d0d9888cb7fd7b750713d6e236d1fcb99157228",
        False,
        {
            "body_path": "release_notes.md",
            "draft": False,
            "files": "dist/*\nrelease-artifacts/*\n",
            "prerelease": False,
        },
        None,
        None,
        None,
    ),
    (
        REMOTE_HASH_STEP,
        None,
        True,
        None,
        {"GH_TOKEN": "${{ github.token }}"},
        None,
        None,
    ),
)
EXPECTED_PREBUILD_RUN_SHA256 = {
    "Validate tag/version consistency": (
        "093ec109015dff5f5d6163a548e810c42bff5ecc2dd9308208cc747ca86f292c"
    ),
    "Extract latest changelog section for release notes": (
        "0e2f1d7765304dc2377a9dbffd8cb29bf69852817f9e393ac5b4044d33a9d18a"
    ),
}
EXPECTED_PREPUBLISH_RUNS = {
    "Install release test dependencies": 'python -m pip install -e ".[test,typecheck]"',
    "Check public repository hygiene": "python scripts/check_public_hygiene.py",
    "Run Ruff gates": """\
ruff check --select E9,F .
ruff check --select E4,E7,E9,F \\
  src/hwpx/document.py \\
  src/hwpx/oxml/{_document_impl,_document_primitives,document,document_parts,header_part,memo,numbering,objects,paragraph,run,section,section_format,section_story,simple_parts,table}.py \\
  src/hwpx/tools/package_validator.py \\
  tests/template_automation/generate_fixtures.py \\
  tests/{test_oxml_modularization,test_paragraph_section_management,test_section_headers}.py
""",
    "Run typing checks": """\
python scripts/check_typing_generics_scope.py
mypy
pyright
""",
    "Run tests with coverage ratchet": (
        "pytest -q --cov=hwpx --cov-report=term-missing --cov-fail-under=80"
    ),
}
FAIL_OPEN_RUN = re.compile(
    r"(?:^|[;&|])\s*(?:exit|return)\s+0+\b"
    r"|\|\|\s*(?:true|:)(?:\s|;|$)"
    r"|(?:^|\s)set\s+\+e(?:\s|;|$)"
    r"|(?:^|\s)trap\b[^\n]*\bERR\b",
    re.MULTILINE,
)


def _verifier_module():
    spec = importlib.util.spec_from_file_location(
        "verify_legacy_release_cap",
        VERIFY_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _release_hash_module():
    spec = importlib.util.spec_from_file_location(
        "verify_release_hashes",
        RELEASE_HASH_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _require_exact_named_runs(
    failures: list[str],
    *,
    job_name: str,
    job: dict[str, Any],
    expected: dict[str, str],
) -> None:
    for step_name, expected_run in expected.items():
        matches = [
            step
            for step in job.get("steps", [])
            if step.get("name") == step_name
        ]
        if len(matches) != 1 or matches[0].get("run") != expected_run:
            failures.append(f"{job_name} step must be exact: {step_name}")


def _trigger(parsed: dict[object, Any]) -> object:
    """Return the literal ``on`` block despite PyYAML's YAML-1.1 bool key."""

    return parsed["on"] if "on" in parsed else parsed.get(True)


def _workflow_safety_failures(workflow: str) -> list[str]:
    failures: list[str] = []
    try:
        parsed = yaml.safe_load(workflow)
        jobs: dict[str, dict[str, Any]] = parsed["jobs"]
        legacy = jobs["legacy-cap"]
        prepublish = jobs["prepublish"]
        release = jobs["release"]
    except (KeyError, TypeError, yaml.YAMLError) as exc:
        return [f"invalid release job structure: {exc}"]

    if set(jobs) != {"legacy-cap", "prepublish", "release"}:
        failures.append("release workflow must contain only the three expected jobs")
    if _trigger(parsed) != EXPECTED_TRIGGER:
        failures.append("release trigger must be exactly tag-push-only")
    if parsed.get("defaults"):
        failures.append("release workflow must not override the default run shell")
    if prepublish.get("needs") != "legacy-cap":
        failures.append("prepublish must need legacy-cap")
    if release.get("needs") != "prepublish":
        failures.append("release must need prepublish")
    for job_name, job in (
        ("legacy-cap", legacy),
        ("prepublish", prepublish),
        ("release", release),
    ):
        if job.get("defaults"):
            failures.append(f"{job_name} must not override the default run shell")
        if "if" in job:
            failures.append(f"{job_name} must not override dependency status")
        if job.get("continue-on-error", False):
            failures.append(f"{job_name} must not continue on error")
        for step in job.get("steps", []):
            shell = step.get("shell")
            if shell not in (None, "bash"):
                failures.append(
                    f"{job_name} step has an unsafe custom shell: "
                    f"{step.get('name', step.get('uses', '<unnamed>'))}"
                )
            if "if" in step:
                failures.append(
                    f"{job_name} step must not have a condition: "
                    f"{step.get('name', step.get('uses', '<unnamed>'))}"
                )
            if step.get("continue-on-error", False):
                failures.append(
                    f"{job_name} step must not continue on error: "
                    f"{step.get('name', step.get('uses', '<unnamed>'))}"
                )
            run = step.get("run")
            if isinstance(run, str) and FAIL_OPEN_RUN.search(run):
                failures.append(
                    f"{job_name} step contains a fail-open shell construct: "
                    f"{step.get('name', '<unnamed>')}"
                )

    for job_name, expected in EXPECTED_PREPUBLICATION_CHECKOUTS.items():
        observed = tuple(
            (step.get("uses"), step.get("with"))
            for step in jobs[job_name].get("steps", [])
            if str(step.get("uses", "")).startswith("actions/checkout@")
        )
        if observed != expected:
            failures.append(
                f"{job_name} checkout inputs must match the frozen release source"
            )

    matching_steps = [
        step
        for step in legacy.get("steps", [])
        if step.get("name") == LEGACY_STEP
    ]
    if len(matching_steps) != 1:
        failures.append("legacy-cap must have exactly one named verifier step")
    elif matching_steps[0].get("run") != LEGACY_COMMAND:
        failures.append("legacy-cap verifier command must be exact")

    _require_exact_named_runs(
        failures,
        job_name="prepublish",
        job=prepublish,
        expected=EXPECTED_PREPUBLISH_RUNS,
    )
    for job_name, job in jobs.items():
        if job_name == "release":
            continue
        if any(
            str(step.get("uses", "")).startswith(
                (PYPI_ACTION, GITHUB_ACTION)
            )
            for step in job.get("steps", [])
        ):
            failures.append("publisher actions must exist only in release")

    steps = release.get("steps", [])
    release_step_identities = tuple(
        (
            step.get("name"),
            step.get("uses"),
            "run" in step,
            step.get("with"),
            step.get("env"),
            step.get("shell"),
            step.get("working-directory"),
        )
        for step in steps
    )
    if release_step_identities != EXPECTED_RELEASE_STEPS:
        failures.append("release steps must match the exact order and actions")
    for step_name, expected_digest in EXPECTED_PREBUILD_RUN_SHA256.items():
        matches = [step for step in steps if step.get("name") == step_name]
        run = matches[0].get("run") if len(matches) == 1 else None
        observed_digest = (
            hashlib.sha256(run.encode()).hexdigest()
            if isinstance(run, str)
            else None
        )
        if observed_digest != expected_digest:
            failures.append(f"release run must be frozen: {step_name}")
    build_steps = [step for step in steps if step.get("name") == BUILD_STEP]
    if len(build_steps) != 1:
        failures.append("release must have exactly one distribution build step")
        return failures
    build = build_steps[0].get("run")
    if build != EXPECTED_BUILD_RUN:
        failures.append("build step must match the frozen single-build procedure")
    sbom_steps = [step for step in steps if step.get("name") == SBOM_STEP]
    if len(sbom_steps) != 1 or sbom_steps[0].get("run") != EXPECTED_SBOM_RUN:
        failures.append("SBOM step must match the frozen post-build procedure")
    build_index = steps.index(build_steps[0])
    pypi = [
        (index, step)
        for index, step in enumerate(steps)
        if str(step.get("uses", "")).startswith(PYPI_ACTION)
    ]
    github = [
        (index, step)
        for index, step in enumerate(steps)
        if str(step.get("uses", "")).startswith(GITHUB_ACTION)
    ]
    if len(pypi) != 1 or pypi[0][0] <= build_index:
        failures.append("PyPI publish must consume the one checked build")
    elif pypi[0][1].get("with", {}).get("packages-dir", "dist/") != "dist/":
        failures.append("PyPI publish must use dist/")
    if len(github) != 1 or github[0][0] <= build_index:
        failures.append("GitHub release must consume the one checked build")
    elif not {"dist/*", "release-artifacts/*"} <= {
        line.strip()
        for line in github[0][1].get("with", {}).get("files", "").splitlines()
    }:
        failures.append("GitHub release must upload dist and provenance manifest")
    remote_steps = [
        (index, step)
        for index, step in enumerate(steps)
        if step.get("name") == REMOTE_HASH_STEP
    ]
    if (
        len(remote_steps) != 1
        or len(pypi) != 1
        or len(github) != 1
        or remote_steps[0][0] <= max(pypi[0][0], github[0][0])
    ):
        failures.append("remote hash verification must follow both publications")
    elif remote_steps[0][1].get("run") != REMOTE_HASH_COMMAND:
        failures.append("remote hash verifier command must be exact")
    return failures


def test_public_legacy_cap_is_a_required_fail_closed_job() -> None:
    workflow = RELEASE.read_text(encoding="utf-8")
    assert _workflow_safety_failures(workflow) == []


@pytest.mark.parametrize(
    ("mutate", "expected"),
    (
        (
            lambda text: text.replace("needs: legacy-cap", "needs: []", 1),
            "prepublish must need legacy-cap",
        ),
        (
            lambda text: text.replace("needs: prepublish", "needs: []", 1),
            "release must need prepublish",
        ),
        (
            lambda text: text.replace(
                "  release:\n    needs:",
                "  release:\n    if: always()\n    needs:",
                1,
            ),
            "release must not override dependency status",
        ),
        (
            lambda text: text.replace(
                "      - name: Require public 5.1.1 legacy cap before core 5",
                "      - name: Require public 5.1.1 legacy cap before core 5\n"
                "        if: false",
                1,
            ),
            "legacy-cap step must not have a condition",
        ),
        (
            lambda text: text.replace(
                "      - name: Require public 5.1.1 legacy cap before core 5",
                "      - name: Require public 5.1.1 legacy cap before core 5\n"
                "        continue-on-error: true",
                1,
            ),
            "legacy-cap step must not continue on error",
        ),
        (
            lambda text: text.replace(
                f"run: {LEGACY_COMMAND}",
                f"run: {LEGACY_COMMAND} || true",
                1,
            ),
            "legacy-cap verifier command must be exact",
        ),
        (
            lambda text: text.replace(
                f"run: {LEGACY_COMMAND}",
                f"run: exit    0; {LEGACY_COMMAND}",
                1,
            ),
            "legacy-cap verifier command must be exact",
        ),
        (
            lambda text: text.replace(
                f"run: {LEGACY_COMMAND}",
                f"run: if false; then {LEGACY_COMMAND}; fi",
                1,
            ),
            "legacy-cap verifier command must be exact",
        ),
        (
            lambda text: text.replace(
                "jobs:\n",
                "defaults:\n"
                "  run:\n"
                "    shell: bash -c 'bash \"$1\" || true' -- {0}\n"
                "jobs:\n",
                1,
            ),
            "release workflow must not override the default run shell",
        ),
        (
            lambda text: text.replace(
                "  legacy-cap:\n    runs-on:",
                "  legacy-cap:\n"
                "    defaults:\n"
                "      run:\n"
                "        shell: bash -c 'bash \"$1\" || true' -- {0}\n"
                "    runs-on:",
                1,
            ),
            "legacy-cap must not override the default run shell",
        ),
        (
            lambda text: text.replace(
                "      - name: Require public 5.1.1 legacy cap before core 5\n",
                "      - name: Require public 5.1.1 legacy cap before core 5\n"
                "        shell: bash -c 'bash \"$1\" || true' -- {0}\n",
                1,
            ),
            "legacy-cap step has an unsafe custom shell",
        ),
        (
            lambda text: text.replace(
                "run: pytest -q --cov=hwpx --cov-report=term-missing "
                "--cov-fail-under=80",
                "run: |\n"
                "          pytest -q --cov=hwpx --cov-report=term-missing "
                "--cov-fail-under=80 || :",
                1,
            ),
            "prepublish step contains a fail-open shell construct",
        ),
        (
            lambda text: text.replace(
                "      - name: Verify PyPI and GitHub release hashes\n",
                "      - name: Verify PyPI and GitHub release hashes\n"
                "        shell: bash -c 'bash \"$1\" || true' -- {0}\n",
                1,
            ),
            "release step has an unsafe custom shell",
        ),
        (
            lambda text: (
                text
                + "\n  rogue-publish:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - uses: pypa/gh-action-pypi-publish@"
                "ba38be9e461d3875417946c167d0b5f3d385a247\n"
            ),
            "release workflow must contain only the three expected jobs",
        ),
        (
            lambda text: text.replace(
                "      - name: Check public repository hygiene",
                "      - uses: pypa/gh-action-pypi-publish@"
                "ba38be9e461d3875417946c167d0b5f3d385a247\n"
                "      - name: Check public repository hygiene",
                1,
            ),
            "publisher actions must exist only in release",
        ),
        (
            lambda text: text.replace(
                "      - name: Generate release SBOM",
                "      - name: Replace checked artifacts\n"
                "        run: python scripts/rewrite_dist_and_manifest.py\n\n"
                "      - name: Generate release SBOM",
                1,
            ),
            "release steps must match the exact order and actions",
        ),
        (
            lambda text: text.replace(
                '          --output-file "release-artifacts/'
                'python-hwpx-${GITHUB_REF_NAME}.cdx.json"',
                '          --output-file "release-artifacts/'
                'python-hwpx-${GITHUB_REF_NAME}.cdx.json"\n'
                "          python scripts/rewrite_dist_and_manifest.py",
                1,
            ),
            "SBOM step must match the frozen post-build procedure",
        ),
        (
            lambda text: re.sub(
                r"\n      - name: Validate tag/version consistency\n.*?"
                r"(?=\n      - name: Extract latest changelog section)",
                "",
                text,
                count=1,
                flags=re.DOTALL,
            ),
            "release steps must match the exact order and actions",
        ),
        (
            lambda text: re.sub(
                r"(      - name: Validate tag/version consistency\n"
                r"        shell: bash\n)"
                r"        run: \|.*?"
                r"(?=\n      - name: Extract latest changelog section)",
                r"\1        run: true\n",
                text,
                count=1,
                flags=re.DOTALL,
            ),
            "release run must be frozen: Validate tag/version consistency",
        ),
        (
            lambda text: text.replace(
                "          draft: false",
                "          draft: true",
                1,
            ),
            "release steps must match the exact order and actions",
        ),
        (
            lambda text: re.sub(
                r'on:\n  push:\n    tags:\n      - "v\*"\n      - "\[0-9\]\*"\n',
                'on:\n  push:\n    branches: ["**"]\n',
                text,
                count=1,
            ),
            "release trigger must be exactly tag-push-only",
        ),
        (
            lambda text: text.replace(
                "  push:\n    tags:",
                '  push:\n    branches: ["**"]\n    tags:',
                1,
            ),
            "release trigger must be exactly tag-push-only",
        ),
        (
            lambda text: text.replace(
                "\npermissions:",
                "\n  workflow_dispatch:\n\npermissions:",
                1,
            ),
            "release trigger must be exactly tag-push-only",
        ),
        (
            lambda text: text.replace('      - "v*"', '      - "*"', 1),
            "release trigger must be exactly tag-push-only",
        ),
        (
            lambda text: text.replace(
                "  prepublish:\n"
                "    needs: legacy-cap\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                f"      - uses: {CHECKOUT_ACTION} # v7.0.1\n",
                "  prepublish:\n"
                "    needs: legacy-cap\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                f"      - uses: {CHECKOUT_ACTION} # v7.0.1\n"
                "        with:\n"
                "          ref: main\n",
                1,
            ),
            "prepublish checkout inputs must match the frozen release source",
        ),
    ),
    ids=(
        "remove-legacy-needs",
        "remove-prepublish-needs",
        "release-always",
        "conditional-verifier",
        "continue-on-error",
        "ignore-verifier-failure",
        "early-success-exit",
        "unreachable-verifier",
        "workflow-default-shell-wrapper",
        "job-default-shell-wrapper",
        "legacy-step-shell-wrapper",
        "prepublish-colon-fallback",
        "remote-step-shell-wrapper",
        "extra-publish-job",
        "prepublish-publisher",
        "extra-post-build-rewrite",
        "sbom-appended-rewrite",
        "remove-tag-gate",
        "replace-tag-gate",
        "draft-github-release",
        "branch-only-trigger",
        "branch-and-tag-trigger",
        "workflow-dispatch-trigger",
        "widen-tag-glob",
        "prepublish-checkout-main",
    ),
)
def test_release_workflow_mutations_are_rejected(
    mutate,
    expected: str,
) -> None:
    workflow = RELEASE.read_text(encoding="utf-8")

    failures = _workflow_safety_failures(mutate(workflow))

    assert any(expected in failure for failure in failures)


def _safe_requirements() -> list[str]:
    return [
        "python-hwpx>=4.2.0,<5",
        'python-hwpx[visual]<5,>=4.2.0; extra == "oracle"',
        'python-hwpx[visual]>=4.2.0,<5; extra == "vision"',
    ]


def test_exact_legacy_metadata_contract_accepts_only_safe_public_pair() -> None:
    verifier = _verifier_module()

    assert (
        verifier.validate_legacy_cap(
            core_version="4.2.0",
            legacy_version="5.1.1",
            requirements=_safe_requirements(),
        )
        == []
    )


@pytest.mark.parametrize(
    ("core_version", "legacy_version", "requirements", "expected"),
    (
        ("5.0.0", "5.1.1", _safe_requirements(), "python-hwpx version"),
        ("4.2.0", "5.1.0", _safe_requirements(), "hwpx-mcp-server version"),
        (
            "4.2.0",
            "5.1.1",
            [
                "python-hwpx>=4.2.0,<50",
                'python-hwpx[visual]>=4.2.0,<50; extra == "oracle"',
                'python-hwpx[visual]>=4.2.0,<50; extra == "vision"',
            ],
            "unsafe python-hwpx specifiers",
        ),
        (
            "4.2.0",
            "5.1.1",
            _safe_requirements()[:2],
            "expected 3 python-hwpx requirements",
        ),
    ),
    ids=("core5", "legacy510", "upper50", "missing-extra"),
)
def test_legacy_metadata_mutations_fail_closed(
    core_version: str,
    legacy_version: str,
    requirements: list[str],
    expected: str,
) -> None:
    verifier = _verifier_module()

    failures = verifier.validate_legacy_cap(
        core_version=core_version,
        legacy_version=legacy_version,
        requirements=requirements,
    )

    assert any(expected in failure for failure in failures)


def test_legacy_runner_executes_every_command_with_check_true(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    verifier = _verifier_module()
    calls: list[tuple[tuple[str, ...], bool]] = []

    def record(command, *, check: bool):
        calls.append((tuple(command), check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(verifier.subprocess, "run", record)
    verifier.install_and_verify(tmp_path / "legacy-venv")

    assert len(calls) == 7
    assert all(check is True for _, check in calls)
    assert calls[0][0][-2:] == (
        str(tmp_path / "legacy-venv-wheelhouse"),
        str(ROOT),
    )
    assert calls[1][0][-2:] == (
        "python-hwpx==4.2.0",
        "hwpx-mcp-server==5.1.1",
    )
    install = calls[3][0]
    assert "--no-index" in install
    assert "--find-links" in install
    assert "python-hwpx==4.2.0" not in install
    assert install[-1] == "hwpx-mcp-server==5.1.1"
    assert calls[4][0][-3:] == ("-m", "pip", "check")
    assert calls[5][0][-1] == "--inspect-installed"
    assert calls[6][0][-1] == "--help"


def test_legacy_runner_main_dispatches_install_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    verifier = _verifier_module()
    calls: list[Path] = []

    monkeypatch.setattr(
        verifier,
        "install_and_verify",
        lambda venv: calls.append(venv),
    )

    venv = tmp_path / "legacy-venv"
    assert verifier.main(["--venv", str(venv)]) == 0
    assert calls == [venv]


def test_legacy_runner_main_propagates_inspection_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _verifier_module()
    monkeypatch.setattr(verifier, "inspect_installed_pair", lambda: 37)

    assert verifier.main(["--inspect-installed"]) == 37


@pytest.mark.parametrize("failed_command", range(7))
def test_legacy_runner_propagates_every_subprocess_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failed_command: int,
) -> None:
    verifier = _verifier_module()
    call_index = 0

    def fail_one(command, *, check: bool):
        nonlocal call_index
        current = call_index
        call_index += 1
        if current == failed_command:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(verifier.subprocess, "run", fail_one)

    with pytest.raises(subprocess.CalledProcessError):
        verifier.install_and_verify(tmp_path / "legacy-venv")


def _manifest_bytes(payloads: dict[str, bytes]) -> bytes:
    return (
        "\n".join(
            f"{hashlib.sha256(data).hexdigest()}  {name}"
            for name, data in payloads.items()
        )
        + "\n"
    ).encode()


def test_core_release_build_inputs_and_remote_provenance_are_frozen() -> None:
    pyproject = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert pyproject["build-system"]["requires"] == [
        "setuptools==84.0.0",
        "wheel==0.48.0",
    ]
    assert _workflow_safety_failures(RELEASE.read_text(encoding="utf-8")) == []


def test_release_hash_verifier_checks_manifest_and_downloaded_assets(
    tmp_path: Path,
) -> None:
    verifier = _release_hash_module()
    payloads = {
        "python_hwpx-5.0.0-py3-none-any.whl": b"wheel",
        "python_hwpx-5.0.0.tar.gz": b"sdist",
    }
    manifest = tmp_path / "SHA256SUMS"
    manifest.write_bytes(_manifest_bytes(payloads))
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    (asset_dir / "SHA256SUMS").write_bytes(manifest.read_bytes())
    for name, data in payloads.items():
        (asset_dir / name).write_bytes(data)

    expected = verifier.read_manifest(manifest)
    verifier.verify_github_assets(
        expected,
        manifest=manifest,
        asset_dir=asset_dir,
    )

    (asset_dir / next(iter(payloads))).write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="GitHub hash differs"):
        verifier.verify_github_assets(
            expected,
            manifest=manifest,
            asset_dir=asset_dir,
        )


@pytest.mark.parametrize(
    "manifest_text",
    (
        "not-a-hash  package.whl\n",
        f"{'0' * 64}  nested/package.whl\n{'1' * 64}  package.tar.gz\n",
        f"{'0' * 64}  one.whl\n{'1' * 64}  two.whl\n",
    ),
    ids=("malformed", "path", "missing-sdist"),
)
def test_release_hash_verifier_rejects_ambiguous_manifests(
    tmp_path: Path,
    manifest_text: str,
) -> None:
    verifier = _release_hash_module()
    manifest = tmp_path / "SHA256SUMS"
    manifest.write_text(manifest_text, encoding="utf-8")

    with pytest.raises(ValueError):
        verifier.read_manifest(manifest)


class _PyPIResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


def test_release_hash_verifier_rejects_pypi_digest_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _release_hash_module()
    expected = {
        "python_hwpx-5.0.0-py3-none-any.whl": "0" * 64,
        "python_hwpx-5.0.0.tar.gz": "1" * 64,
    }
    payload = {
        "urls": [
            {
                "filename": filename,
                "digests": {"sha256": "f" * 64},
            }
            for filename in expected
        ]
    }
    monkeypatch.setattr(
        verifier.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _PyPIResponse(),
    )
    monkeypatch.setattr(verifier.json, "load", lambda _response: payload)

    with pytest.raises(RuntimeError, match="PyPI hashes differ"):
        verifier.verify_pypi(
            expected, version="5.0.0", attempts=1, retry_seconds=0
        )


def test_release_hash_verifier_exhausts_pypi_lookup_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _release_hash_module()
    attempts: list[str] = []

    def fail_lookup(*_args, **_kwargs):
        attempts.append("lookup")
        raise URLError("offline")

    monkeypatch.setattr(verifier.urllib.request, "urlopen", fail_lookup)
    monkeypatch.setattr(verifier.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="PyPI hash lookup failed"):
        verifier.verify_pypi(
            {"package.whl": "0" * 64, "package.tar.gz": "1" * 64},
            version="5.0.0",
            attempts=3,
            retry_seconds=0,
        )
    assert attempts == ["lookup", "lookup", "lookup"]


def test_release_hash_verifier_polls_the_tag_derived_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The v5.0.1 regression: a frozen version constant polled a JSON URL
    that could never exist, so the verify step stayed red forever."""

    verifier = _release_hash_module()
    polled: list[str] = []

    def capture_lookup(url, **_kwargs):
        polled.append(str(url))
        raise URLError("offline")

    monkeypatch.setattr(verifier.urllib.request, "urlopen", capture_lookup)

    with pytest.raises(RuntimeError, match="PyPI hash lookup failed"):
        verifier.verify_pypi(
            {"package.whl": "0" * 64, "package.tar.gz": "1" * 64},
            version="9.9.9",
            attempts=1,
            retry_seconds=0,
        )
    assert polled == ["https://pypi.org/pypi/python-hwpx/9.9.9/json"]


def test_release_tag_version_derivation_fails_closed() -> None:
    verifier = _release_hash_module()
    assert verifier.version_from_tag("v5.0.1") == "5.0.1"
    for bad_tag in ("5.0.1", "v5.0.1rc1", "v", "release-5.0.1", "v5.0.1 "):
        with pytest.raises(ValueError):
            verifier.version_from_tag(bad_tag)


def test_release_hash_verifier_main_rejects_foreign_manifest_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    verifier = _release_hash_module()
    expected = {
        "python_hwpx-4.2.0-py3-none-any.whl": "0" * 64,
        "python_hwpx-4.2.0.tar.gz": "1" * 64,
    }
    monkeypatch.setattr(verifier, "read_manifest", lambda path: expected)

    with pytest.raises(ValueError, match="does not carry the tagged version"):
        verifier.main(
            [
                "--manifest",
                str(tmp_path / "SHA256SUMS"),
                "--asset-dir",
                str(tmp_path / "assets"),
                "--tag",
                "v5.0.1",
            ]
        )


def test_release_hash_verifier_main_wires_every_remote_check(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    verifier = _release_hash_module()
    manifest = tmp_path / "SHA256SUMS"
    asset_dir = tmp_path / "assets"
    expected = {
        "python_hwpx-5.0.0-py3-none-any.whl": "0" * 64,
        "python_hwpx-5.0.0.tar.gz": "1" * 64,
    }
    calls: list[object] = []
    monkeypatch.setattr(verifier, "read_manifest", lambda path: expected)
    monkeypatch.setattr(
        verifier,
        "verify_pypi",
        lambda observed, **kwargs: calls.append(("pypi", observed, kwargs)),
    )
    monkeypatch.setattr(
        verifier,
        "verify_github_release",
        lambda observed, **kwargs: calls.append(
            ("github", observed, kwargs)
        ),
    )

    assert (
        verifier.main(
            [
                "--manifest",
                str(manifest),
                "--asset-dir",
                str(asset_dir),
                "--tag",
                "v5.0.0",
            ]
        )
        == 0
    )
    assert calls == [
        ("pypi", expected, {"version": "5.0.0"}),
        (
            "github",
            expected,
            {
                "manifest": manifest,
                "asset_dir": asset_dir,
                "tag": "v5.0.0",
            },
        ),
    ]


def test_github_release_readback_retries_with_fresh_directories(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    verifier = _release_hash_module()
    payloads = {
        "python_hwpx-5.0.0-py3-none-any.whl": b"wheel",
        "python_hwpx-5.0.0.tar.gz": b"sdist",
    }
    manifest = tmp_path / "SHA256SUMS"
    manifest.write_bytes(_manifest_bytes(payloads))
    expected = verifier.read_manifest(manifest)
    attempts: list[Path] = []
    states: list[str] = []

    def verify_state(tag: str) -> None:
        states.append(tag)

    def download(tag: str, directory: Path) -> None:
        assert tag == "v5.0.0"
        attempts.append(directory)
        if len(attempts) == 1:
            raise verifier.subprocess.CalledProcessError(1, ["gh"])
        (directory / "SHA256SUMS").write_bytes(manifest.read_bytes())
        for name, data in payloads.items():
            (directory / name).write_bytes(data)

    monkeypatch.setattr(verifier, "verify_github_release_state", verify_state)
    monkeypatch.setattr(verifier, "download_github_assets", download)
    monkeypatch.setattr(verifier.time, "sleep", lambda _seconds: None)
    asset_dir = tmp_path / "assets"

    verifier.verify_github_release(
        expected,
        manifest=manifest,
        asset_dir=asset_dir,
        tag="v5.0.0",
        attempts=2,
        retry_seconds=0,
    )

    assert len(attempts) == 2
    assert states == ["v5.0.0", "v5.0.0"]
    assert attempts[0] != attempts[1]
    assert asset_dir.is_dir()


@pytest.mark.parametrize(
    "stdout",
    (
        '{"tagName":"v5.0.0","isDraft":true,"isPrerelease":false}',
        '{"tagName":"v5.0.0","isDraft":false,"isPrerelease":true}',
        '{"tagName":"wrong","isDraft":false,"isPrerelease":false}',
    ),
    ids=("draft", "prerelease", "wrong-tag"),
)
def test_github_release_state_rejects_nonfinal_truth(
    monkeypatch: pytest.MonkeyPatch,
    stdout: str,
) -> None:
    verifier = _release_hash_module()

    def view(command, **kwargs):
        assert command[-2:] == ["--json", "tagName,isDraft,isPrerelease"]
        assert kwargs == {
            "check": True,
            "capture_output": True,
            "text": True,
        }
        return subprocess.CompletedProcess(command, 0, stdout=stdout)

    monkeypatch.setattr(verifier.subprocess, "run", view)

    with pytest.raises(RuntimeError, match="GitHub release state differs"):
        verifier.verify_github_release_state("v5.0.0")
