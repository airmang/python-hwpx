# ComputerUse Visual Review Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repeatable visual-review evidence loop for generated HWPX operating-plan outputs so `visual_review_required` is resolved to `observed_pass`, `needs_review`, or `blocked` with timestamped handoff evidence.

**Architecture:** Keep executable workflow ownership in `hwpx-skill` because the loop depends on local viewer and ComputerUse availability, not core HWPX package logic. The runner writes a stable JSON evidence contract, supports viewer-missing fallback for CI, and appends iteration history across regeneration attempts. `hwpx-mcp-server` and `python-hwpx` docs point to the same evidence contract so agents do not claim submission readiness from file-only quality alone.

**Tech Stack:** Python 3.10+, stdlib JSON/argparse/subprocess/pathlib, optional `python-hwpx.inspect_operating_plan_quality`, hwpx-skill quickcheck smoke, Markdown docs.

---

## Stage Context

Wily Stage: `S-005` / `ComputerUse 시각 검증 반복 루프 자동화`

Claimed work session: `WS-595dc689196c`

Current planned phases:

1. `PH-7f6c5438ea82` - 시각 검증 증거 계약 정리
2. `PH-3bfd8c21ab34` - ComputerUse 반복 루프 문서화와 스크립트화
3. `PH-1cde5c77b4c5` - fallback smoke와 handoff 검증

Important acceptance points:

- A runner/workflow must record target `.hwpx`, observation result, screenshot path or viewer-missing fallback.
- `visual_review_required` must resolve to one of `observed_pass`, `needs_review`, or `blocked` with timestamp and tool path.
- Regeneration loops must append iteration history and residual layout risk.
- MCP/skill docs must require visual evidence before claiming final submission readiness.
- CI or machines without Hancom must still validate fallback evidence shape.

## File Structure

- Create: `hwpx-skill/scripts/visual_review.py`
  - Owns the JSON evidence contract and local fallback behavior.
  - Does not require ComputerUse or Hancom to be installed.
  - Optionally launches a local viewer when explicitly requested.
- Modify: `hwpx-skill/scripts/quickcheck.py`
  - Adds `--visual-review` smoke that produces and validates fallback evidence.
- Create: `hwpx-skill/examples/09_visual_review_loop.md`
  - Shows the ComputerUse/manual viewer loop, screenshot handoff, and regeneration iteration.
- Modify: `hwpx-skill/SKILL.md`
  - Adds visual-review gate requirements to operating-plan and template form-fit workflows.
- Modify: `hwpx-skill/README.md`
  - Documents the new command and smoke check.
- Modify: `hwpx-skill/references/api.md`
  - Documents `hwpx.visual-review.v1` evidence fields.
- Modify: `hwpx-mcp-server/README.md`
  - Clarifies that MCP `visual_review_required=true` requires external evidence before submission-ready claims.
- Modify: `hwpx-mcp-server/docs/use-cases.md`
  - Adds the handoff workflow after operating-plan/template form-fit generation.
- Modify: `python-hwpx/docs/examples.md`
  - Points file-only quality readers to the visual-review evidence loop.
- Modify: `python-hwpx/docs/usage.md`
  - Clarifies that `inspect_operating_plan_quality(path).status == "ready"` is not a visual pass.

## Task 1: Add The Visual Review Evidence Runner

**Files:**
- Create: `hwpx-skill/scripts/visual_review.py`

- [ ] **Step 1: Write the runner with a stable evidence schema**

Create `hwpx-skill/scripts/visual_review.py` with this content:

```python
#!/usr/bin/env python3
"""Record HWPX visual-review evidence for submission handoff.

The script is intentionally useful without Hancom or ComputerUse.  In CI it can
write a blocked fallback record that proves the evidence shape is valid.  In a
local GUI session, launch or open the target with a viewer, inspect it with
ComputerUse or a human reviewer, then rerun this command with observations and
an optional screenshot path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "hwpx.visual-review.v1"
ALLOWED_STATUSES = {"observed_pass", "needs_review", "blocked"}
ROOT = Path(__file__).resolve().parents[1]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quality_report(path: Path) -> dict[str, Any]:
    try:
        from hwpx import inspect_operating_plan_quality
    except Exception as exc:
        return {
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
            "visual_review_required": True,
        }
    try:
        report = inspect_operating_plan_quality(path)
    except Exception as exc:
        return {
            "available": False,
            "error": f"{type(exc).__name__}: {exc}",
            "visual_review_required": True,
        }
    return {
        "available": True,
        "report_version": report.get("report_version"),
        "status": report.get("status"),
        "score": report.get("score"),
        "pass": report.get("pass"),
        "gaps": report.get("gaps", []),
        "repair_hints": report.get("repair_hints", []),
        "visual_review_required": bool(report.get("visual_review_required", True)),
    }


def _viewer_command(mode: str) -> tuple[list[str] | None, str | None]:
    if mode == "none":
        return None, "viewer disabled by --viewer none"
    if mode.startswith("command:"):
        command = mode.removeprefix("command:").strip()
        if not command:
            return None, "empty command viewer"
        return command.split(), None
    env_command = os.environ.get("HWPX_VIEWER_COMMAND", "").strip()
    if env_command:
        return env_command.split(), None
    if platform.system() == "Darwin" and shutil.which("open"):
        return ["open"], None
        return None, "no viewer command found; set HWPX_VIEWER_COMMAND or use --viewer command:open"


def _launch_viewer(command: list[str] | None, target: Path, enabled: bool) -> tuple[bool, str | None]:
    if not enabled:
        return False, "viewer launch skipped; rerun with --launch-viewer to open the document"
    if not command:
        return False, "viewer command unavailable"
    try:
        subprocess.run([*command, str(target)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, None


def _load_previous(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"unsupported evidence schema: {data.get('schemaVersion')}")
    return data


def _target_block(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "size_bytes": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "sha256": _sha256(path),
    }


def _screenshot_path(value: str | None) -> str | None:
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"screenshot path does not exist: {path}")
    return str(path)


def build_evidence(args: argparse.Namespace) -> dict[str, Any]:
    target = Path(args.hwpx).expanduser().resolve()
    if not target.exists():
        raise FileNotFoundError(f"target HWPX does not exist: {target}")
    if target.suffix.lower() != ".hwpx":
        raise ValueError(f"target must be a .hwpx file: {target}")

    command, viewer_reason = _viewer_command(args.viewer)
    launched, launch_reason = _launch_viewer(command, target, args.launch_viewer)
    quality = _quality_report(target)
    fallback_reason = viewer_reason or launch_reason
    status = args.status
    if status is None:
        status = "blocked" if command is None else "needs_review"
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"status must be one of {sorted(ALLOWED_STATUSES)}")
    if status == "observed_pass" and quality.get("visual_review_required", True) and not (
        args.screenshot or args.observation
    ):
        raise ValueError("observed_pass requires --screenshot or at least one --observation")

    evidence_path = Path(args.evidence).expanduser().resolve()
    previous = _load_previous(evidence_path)
    previous_iterations = list((previous or {}).get("iterations", []))
    previous_current = (previous or {}).get("current")
    if previous_current:
        previous_iterations.append(previous_current)

    current = {
        "iteration": len(previous_iterations) + 1,
        "status": status,
        "timestamp": _utc_now(),
        "tool_path": str(Path(__file__).resolve()),
        "review_method": args.method,
        "screenshot_path": _screenshot_path(args.screenshot),
        "observations": list(args.observation or []),
        "layout_risks": list(args.layout_risk or []),
        "notes": args.notes or "",
        "regenerated_from": args.regenerated_from or "",
    }
    if fallback_reason:
        current["fallback_reason"] = fallback_reason

    return {
        "schemaVersion": SCHEMA_VERSION,
        "target": _target_block(target),
        "quality": quality,
        "viewer": {
            "mode": args.viewer,
            "available": command is not None,
            "command": " ".join(command) if command else "",
            "launched": launched,
        },
        "current": current,
        "iterations": previous_iterations,
        "summary": {
            "resolved_visual_review_required": status,
            "ready_for_submission_claim": status == "observed_pass",
            "residual_layout_risk_count": len(current["layout_risks"]),
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record HWPX visual review evidence")
    parser.add_argument("hwpx", help="target .hwpx file")
    parser.add_argument(
        "--evidence",
        default=str(ROOT / "examples" / "out" / "visual_review_evidence.json"),
        help="JSON evidence path",
    )
    parser.add_argument(
        "--viewer",
        default="auto",
        help="auto, none, or command:open",
    )
    parser.add_argument("--launch-viewer", action="store_true", help="open the HWPX with the selected viewer")
    parser.add_argument("--status", choices=sorted(ALLOWED_STATUSES), help="visual review result")
    parser.add_argument(
        "--method",
        default="computer-use-or-human-viewer",
        help="review method label stored in evidence",
    )
    parser.add_argument("--screenshot", help="path to screenshot captured during visual review")
    parser.add_argument("--observation", action="append", help="observed layout fact; repeatable")
    parser.add_argument("--layout-risk", action="append", help="remaining visual/layout risk; repeatable")
    parser.add_argument("--notes", default="", help="short reviewer note")
    parser.add_argument("--regenerated-from", default="", help="previous evidence path or source run id")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        evidence = build_evidence(args)
    except Exception as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        return 2
    evidence_path = Path(args.evidence).expanduser().resolve()
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[OK] visual review evidence written: {evidence_path}")
    print(f"[OK] status={evidence['current']['status']}")
    print(f"[OK] ready_for_submission_claim={evidence['summary']['ready_for_submission_claim']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the new script without a target and verify argparse works**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
python3 scripts/visual_review.py --help
```

Expected:

```text
usage: visual_review.py [-h]
```

The help output must include `--status`, `--viewer`, `--launch-viewer`, `--screenshot`, `--observation`, and `--layout-risk`.

- [ ] **Step 3: Commit the runner**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
git add scripts/visual_review.py
git commit -m "feat: add hwpx visual review evidence runner"
```

Expected: commit succeeds, preserving unrelated dirty files outside this task.

## Task 2: Add CI-Safe Fallback Smoke

**Files:**
- Modify: `hwpx-skill/scripts/quickcheck.py`

- [ ] **Step 1: Add imports and CLI flag**

In `hwpx-skill/scripts/quickcheck.py`, add `import json` near the existing imports:

```python
import argparse
import json
import subprocess
import sys
from pathlib import Path
```

Add this argument after `--template-formfit`:

```python
    parser.add_argument(
        "--visual-review",
        action="store_true",
        help="also validate the visual-review fallback evidence shape",
    )
```

- [ ] **Step 2: Add the visual-review command**

In the command construction block, add this after the `if args.template_formfit:` block:

```python
    if args.visual_review:
        if not args.operating_plan:
            commands.append((
                "operating-plan",
                [sys.executable, str(EXAMPLES_DIR / "07_create_operating_plan.py")],
            ))
        commands.append((
            "visual-review-fallback",
            [
                sys.executable,
                str(SCRIPTS_DIR / "visual_review.py"),
                str(EXAMPLES_DIR / "out" / "07_operating_plan.hwpx"),
                "--evidence",
                str(EXAMPLES_DIR / "out" / "09_visual_review_fallback.json"),
                "--viewer",
                "none",
                "--status",
                "blocked",
                "--notes",
                "CI fallback smoke: document viewer is intentionally disabled.",
                "--layout-risk",
                "Rendered page breaks and table fit require opened-document review.",
            ],
        ))
```

- [ ] **Step 3: Validate the evidence JSON after commands run**

After the existing `if args.template_formfit:` success print block, add:

```python
    if args.visual_review:
        evidence_path = EXAMPLES_DIR / "out" / "09_visual_review_fallback.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert evidence["schemaVersion"] == "hwpx.visual-review.v1"
        assert evidence["current"]["status"] == "blocked"
        assert evidence["summary"]["resolved_visual_review_required"] == "blocked"
        assert evidence["summary"]["ready_for_submission_claim"] is False
        assert evidence["viewer"]["available"] is False
        assert evidence["current"]["tool_path"].endswith("visual_review.py")
        print("[OK] visual-review fallback evidence workflow passed")
```

- [ ] **Step 4: Run the smoke and verify fallback works without a viewer**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
python3 scripts/quickcheck.py --visual-review
```

Expected:

```text
[OK] visual review evidence written:
[OK] status=blocked
[OK] ready_for_submission_claim=False
[OK] visual-review fallback evidence workflow passed
```

- [ ] **Step 5: Commit the quickcheck smoke**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
git add scripts/quickcheck.py
git commit -m "test: add visual review fallback smoke"
```

Expected: commit succeeds.

## Task 3: Document The ComputerUse Iteration Workflow In hwpx-skill

**Files:**
- Create: `hwpx-skill/examples/09_visual_review_loop.md`
- Modify: `hwpx-skill/SKILL.md`
- Modify: `hwpx-skill/README.md`
- Modify: `hwpx-skill/references/api.md`

- [ ] **Step 1: Add the example workflow**

Create `hwpx-skill/examples/09_visual_review_loop.md`:

```markdown
# Visual Review Loop

Use this workflow when `inspect_operating_plan_quality(path).visual_review_required == true` or a template form-fit result returns `visual_review_required=true`.

## CI or viewer-missing fallback

```bash
python3 scripts/visual_review.py examples/out/07_operating_plan.hwpx \
  --evidence examples/out/09_visual_review_fallback.json \
  --viewer none \
  --status blocked \
  --notes "No HWPX viewer is available in this environment." \
  --layout-risk "Rendered page breaks and table fit require opened-document review."
```

The fallback evidence is valid handoff evidence, but it is not a submission-ready visual pass.

## Local ComputerUse or human viewer pass

1. Generate or regenerate the target HWPX.
2. Run the file-only quality check and confirm `status == "ready"`.
3. Open the HWPX with a local viewer. With a default macOS viewer:

```bash
python3 scripts/visual_review.py examples/out/07_operating_plan.hwpx \
  --evidence examples/out/09_visual_review.json \
  --launch-viewer \
  --status needs_review \
  --notes "Opened for visual review."
```

4. Use ComputerUse or a human reviewer to inspect:
   - first page title, metadata, and margins
   - required section order
   - schedule table fit
   - budget/resource table fit
   - final confirmation or closing material
   - obvious clipped text, missing glyphs, broken table borders, and page overflow
5. Capture a screenshot when possible.
6. Record the result:

```bash
python3 scripts/visual_review.py examples/out/07_operating_plan.hwpx \
  --evidence examples/out/09_visual_review.json \
  --status observed_pass \
  --screenshot examples/out/09_visual_review_page1.png \
  --observation "Title, front matter, and required sections are visible." \
  --observation "Schedule and budget tables fit inside the page width." \
  --notes "Opened in local viewer and inspected with ComputerUse."
```

## Regeneration iteration

If the viewer shows layout risk, record it and regenerate:

```bash
python3 scripts/visual_review.py examples/out/07_operating_plan.hwpx \
  --evidence examples/out/09_visual_review.json \
  --status needs_review \
  --layout-risk "Budget table wraps across pages and needs column width adjustment." \
  --notes "Regenerate with narrower item labels and fewer columns."
```

After regenerating the HWPX, rerun the same command with `--regenerated-from examples/out/09_visual_review.json`. The script appends the previous `current` record to `iterations[]`, so handoff evidence shows the full observe-regenerate-review loop.

## Required handoff fields

The JSON must include:

- `schemaVersion == "hwpx.visual-review.v1"`
- `target.path`, `target.sha256`, and `target.size_bytes`
- `quality.visual_review_required`
- `current.status` as `observed_pass`, `needs_review`, or `blocked`
- `current.timestamp`
- `current.tool_path`
- `current.screenshot_path` or `current.fallback_reason`
- `iterations[]` when a document is regenerated
- `summary.ready_for_submission_claim`
```

- [ ] **Step 2: Update `SKILL.md` quick decision and operating-plan gates**

In `hwpx-skill/SKILL.md`, change the operating-plan handoff bullets so the final gate reads:

```markdown
   - file-only `inspect_operating_plan_quality(path).report_version == "operating-plan-quality-v1"`
   - file-only `inspect_operating_plan_quality(path).status == "ready"`
   - visual review evidence `schemaVersion == "hwpx.visual-review.v1"`
   - visual review evidence `current.status == "observed_pass"` before claiming the document is submission-ready
   - if a viewer is unavailable, run `python3 scripts/visual_review.py examples/out/07_operating_plan.hwpx --viewer none --status blocked` and hand off the blocker instead of claiming visual pass
```

In the template form-fit workflow, replace the final `visual_review_required=true` sentence with:

```markdown
6. `visual_review_required=true`이면 `scripts/visual_review.py` 또는 ComputerUse/열린 문서 검토로 `hwpx.visual-review.v1` evidence를 만든다. `current.status="observed_pass"`가 아니면 최종 제출 가능하다고 주장하지 않는다.
```

Add the new bundled resource bullet near the other examples:

```markdown
- [`examples/09_visual_review_loop.md`](examples/09_visual_review_loop.md)
  `visual_review_required=true`를 열린 문서 관찰, 스크린샷, fallback blocker, iteration history로 해소하는 handoff workflow.
```

- [ ] **Step 3: Update `README.md` commands and workflow text**

In `hwpx-skill/README.md`, add this command near the existing quickcheck commands:

```markdown
python3 scripts/quickcheck.py --visual-review
```

Add this paragraph after the operating-plan/template-formfit sections:

```markdown
`visual_review_required=true`는 file-only 구조 검증이 통과했더라도 열린 문서 기준의 시각 검토가 남았다는 뜻입니다. 제출 가능하다고 말하기 전에는 `python3 scripts/visual_review.py examples/out/07_operating_plan.hwpx --status observed_pass --screenshot examples/out/09_visual_review_page1.png`로 `hwpx.visual-review.v1` evidence를 남기세요. 뷰어가 없는 CI나 원격 환경에서는 `--viewer none --status blocked`로 fallback evidence를 남기고, 제출 가능 상태가 아니라는 blocker를 handoff합니다.
```

Add `examples/09_visual_review_loop.md` to the examples list with this description:

```markdown
- `examples/09_visual_review_loop.md`: ComputerUse/문서 뷰어 기반 시각 검증 loop와 fallback evidence 예제
```

- [ ] **Step 4: Document the evidence contract in `references/api.md`**

Append this section after the operating-plan/template form-fit API sections:

```markdown
### Visual review evidence

`inspect_operating_plan_quality()` and template form-fit reports can return `visual_review_required=True`. That value is not a failure, but it means package/XML/text checks cannot prove rendered layout quality. Use `scripts/visual_review.py` to record opened-document evidence.

```bash
python3 scripts/visual_review.py output.hwpx \
  --evidence visual_review.json \
  --status observed_pass \
  --screenshot page1.png \
  --observation "Required sections and tables are visible without clipping."
```

Evidence schema:

```json
{
  "schemaVersion": "hwpx.visual-review.v1",
  "target": {
    "path": "/absolute/path/output.hwpx",
    "sha256": "64 hex characters",
    "size_bytes": 12345
  },
  "quality": {
    "report_version": "operating-plan-quality-v1",
    "status": "ready",
    "visual_review_required": true
  },
  "current": {
    "status": "observed_pass",
    "timestamp": "2026-05-30T12:00:00Z",
    "tool_path": "/path/to/scripts/visual_review.py",
    "screenshot_path": "/path/to/page1.png",
    "observations": ["Required sections and tables are visible without clipping."],
    "layout_risks": []
  },
  "iterations": [],
  "summary": {
    "resolved_visual_review_required": "observed_pass",
    "ready_for_submission_claim": true,
    "residual_layout_risk_count": 0
  }
}
```

Allowed `current.status` values:

- `observed_pass`: opened-document review found no blocking visual issue.
- `needs_review`: a viewer opened or a reviewer inspected the file, but remaining layout risk requires regeneration or human decision.
- `blocked`: no viewer, no screenshot, missing file, or another blocker prevents visual review.

Only `observed_pass` supports a final submission-ready claim. `blocked` and `needs_review` are valid evidence for handoff, but they preserve the visual-review gate.
```

- [ ] **Step 5: Run skill docs/smoke verification**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
python3 scripts/quickcheck.py --visual-review
python3 scripts/quickcheck.py --operating-plan --template-formfit
```

Expected:

```text
[OK] visual-review fallback evidence workflow passed
[OK] operating-plan document-plan workflow passed
[OK] template form-fit workflow passed
```

- [ ] **Step 6: Commit skill docs**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
git add SKILL.md README.md references/api.md examples/09_visual_review_loop.md
git commit -m "docs: document hwpx visual review loop"
```

Expected: commit succeeds.

## Task 4: Align MCP And python-hwpx Documentation

**Files:**
- Modify: `hwpx-mcp-server/README.md`
- Modify: `hwpx-mcp-server/docs/use-cases.md`
- Modify: `python-hwpx/docs/examples.md`
- Modify: `python-hwpx/docs/usage.md`

- [ ] **Step 1: Update MCP README tool guidance**

In `hwpx-mcp-server/README.md`, replace the current single-sentence explanation of `visual_review_required=true` with:

```markdown
`visual_review_required=true`는 렌더러 기반 시각 검수 없이 구조 검증만 통과했다는 뜻이다. 운영계획서나 template form-fit 산출물을 제출 가능하다고 말하려면 `hwpx-skill/scripts/visual_review.py` 또는 ComputerUse/열린 문서 검토로 `hwpx.visual-review.v1` evidence를 남기고 `current.status="observed_pass"`를 확인해야 한다. 뷰어가 없는 환경은 `current.status="blocked"` handoff evidence로 남긴다.
```

In the operating-plan workflow section, add this step after file-only quality inspection:

```markdown
6. `visual_review_required=true`이면 `visual_review.py` evidence를 생성한다. `observed_pass`가 아니면 `handoff_status="ready"`여도 최종 제출 가능 상태로 표현하지 않는다.
```

- [ ] **Step 2: Update MCP use-cases handoff docs**

In `hwpx-mcp-server/docs/use-cases.md`, add this subsection near the operating-plan/template form-fit use cases:

```markdown
### Visual review handoff evidence

MCP tools can prove package validity, schema validity, file-only operating-plan quality, and template source preservation. They do not prove rendered visual layout. When a result includes `visual_review_required=true`, attach `hwpx.visual-review.v1` evidence before final submission handoff:

```bash
python3 ../hwpx-skill/scripts/visual_review.py work/output.hwpx \
  --evidence work/output.visual-review.json \
  --status observed_pass \
  --screenshot work/output-page1.png \
  --observation "Front matter, section headings, schedule table, and budget table are visible."
```

Viewer-missing fallback:

```bash
python3 ../hwpx-skill/scripts/visual_review.py work/output.hwpx \
  --evidence work/output.visual-review.json \
  --viewer none \
  --status blocked \
  --notes "No HWPX viewer is available on this machine."
```

`observed_pass` is the only status that permits a submission-ready visual claim. `needs_review` and `blocked` keep the handoff honest and should be recorded as residual risk.
```

- [ ] **Step 3: Update python-hwpx examples docs**

In `python-hwpx/docs/examples.md`, add this paragraph after the operating-plan quality example:

```markdown
`inspect_operating_plan_quality(path).status == "ready"` is file-only evidence. If the report returns `visual_review_required=True`, final submission handoff still needs opened-document evidence. In this three-repo stack, use `../hwpx-skill/scripts/visual_review.py` to record `hwpx.visual-review.v1` evidence with `current.status="observed_pass"`, or record `current.status="blocked"` when no viewer is available.
```

- [ ] **Step 4: Update python-hwpx usage docs**

In `python-hwpx/docs/usage.md`, add this paragraph after the template form-fit visual-review note:

```markdown
For repeatable handoff evidence, pair file-only quality with the `hwpx-skill` visual review runner:

```bash
python3 ../hwpx-skill/scripts/visual_review.py output.hwpx \
  --evidence output.visual-review.json \
  --status observed_pass \
  --screenshot output-page1.png
```

Use `--viewer none --status blocked` in CI or headless environments. A blocked visual review is valid evidence, but it does not clear the final submission gate.
```

- [ ] **Step 5: Run lightweight documentation checks**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-mcp-server
python -m pytest tests/test_quality_generation_pipeline.py::test_mcp_inspect_operating_plan_quality_supports_file_only_path -q
cd /Users/wilycastle/Code/projects/hwpx/python-hwpx
uv run pytest tests/test_document_plan.py::test_operating_plan_file_only_quality_passes_complete_submission_candidate tests/test_template_formfit.py::test_template_formfit_output_has_file_only_operating_plan_quality -q
```

Expected:

```text
1 passed
2 passed
```

- [ ] **Step 6: Commit docs alignment**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-mcp-server
git add README.md docs/use-cases.md
git commit -m "docs: require visual review evidence for hwpx handoff"
cd /Users/wilycastle/Code/projects/hwpx/python-hwpx
git add docs/examples.md docs/usage.md
git commit -m "docs: clarify hwpx visual review gate"
```

Expected: both commits succeed.

## Task 5: Final Verification And Wily Evidence

**Files:**
- No source changes beyond Tasks 1-4.

- [ ] **Step 1: Run final stack checks**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
python3 scripts/quickcheck.py --visual-review --operating-plan --template-formfit
cd /Users/wilycastle/Code/projects/hwpx/hwpx-mcp-server
python -m pytest tests/test_quality_generation_pipeline.py::test_mcp_inspect_operating_plan_quality_supports_file_only_path -q
cd /Users/wilycastle/Code/projects/hwpx/python-hwpx
uv run pytest tests/test_document_plan.py::test_operating_plan_file_only_quality_passes_complete_submission_candidate tests/test_template_formfit.py::test_template_formfit_output_has_file_only_operating_plan_quality -q
```

Expected:

```text
[OK] visual-review fallback evidence workflow passed
1 passed
2 passed
```

- [ ] **Step 2: Inspect the generated fallback evidence**

Run:

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
python3 -m json.tool examples/out/09_visual_review_fallback.json
```

Expected keys in the output:

```text
"schemaVersion": "hwpx.visual-review.v1"
"status": "blocked"
"ready_for_submission_claim": false
"tool_path":
"fallback_reason":
```

- [ ] **Step 3: Record Wily phase completion evidence**

Use Wily lifecycle tools:

```text
complete_phase(stage_id="S-005", phase_id="PH-7f6c5438ea82", verification="Visual review evidence contract documented in hwpx-skill references and example.")
complete_phase(stage_id="S-005", phase_id="PH-3bfd8c21ab34", verification="scripts/visual_review.py records viewer, screenshot/fallback, status, and iteration history.")
complete_phase(stage_id="S-005", phase_id="PH-1cde5c77b4c5", verification="python3 scripts/quickcheck.py --visual-review passed with viewer-missing fallback evidence.")
```

- [ ] **Step 4: Add a Wily stage note**

Use Wily lifecycle tools:

```text
add_stage_note(
  stage_id="S-005",
  body="Implemented HWPX visual review loop. Added hwpx.visual-review.v1 runner, fallback smoke, skill docs, MCP handoff docs, and python-hwpx usage notes. observed_pass is required before submission-ready visual claims; blocked/needs_review preserve residual risk.",
  evidence={
    "commands": [
      "hwpx-skill: python3 scripts/quickcheck.py --visual-review --operating-plan --template-formfit",
      "hwpx-mcp-server: python -m pytest tests/test_quality_generation_pipeline.py::test_mcp_inspect_operating_plan_quality_supports_file_only_path -q",
      "python-hwpx: uv run pytest tests/test_document_plan.py::test_operating_plan_file_only_quality_passes_complete_submission_candidate tests/test_template_formfit.py::test_template_formfit_output_has_file_only_operating_plan_quality -q"
    ],
    "evidence_files": [
      "hwpx-skill/examples/out/09_visual_review_fallback.json"
    ]
  }
)
```

- [ ] **Step 5: Complete the Stage when implementation is done**

Use Wily lifecycle tools in this order:

```text
observer_run_once(config_path=null)
list_checkouts(repo_slug="hwpx-skill")
list_checkouts(repo_slug="hwpx-mcp-server")
list_checkouts(repo_slug="python-hwpx")
get_lifecycle_payload_schema(tool_name="complete_stage")
complete_stage(payload={stage_id, git_snapshots, evidence})
```

Build `git_snapshots` from the exact `list_checkouts` output for all three claimed checkouts:

- `hwpx-skill` / `CO-hwpx-skill-main`: include the returned `branch`, `head_sha`, `dirty`, parsed `dirty_files_json`, parsed `unpushed_commits_json`, implementation commit ids in `commits_since_claim`, and `changed_files_since_claim` containing `scripts/visual_review.py`, `scripts/quickcheck.py`, `examples/09_visual_review_loop.md`, `SKILL.md`, `README.md`, and `references/api.md`.
- `hwpx-mcp-server` / `CO-hwpx-mcp-server-main`: include the returned checkout fields and `changed_files_since_claim` containing `README.md` and `docs/use-cases.md`.
- `python-hwpx` / `CO-python-hwpx-main`: include the returned checkout fields and `changed_files_since_claim` containing `docs/examples.md`, `docs/usage.md`, and this plan file.

Use this evidence list in the completion payload:

```json
[
  "hwpx-skill: python3 scripts/quickcheck.py --visual-review --operating-plan --template-formfit passed",
  "hwpx-mcp-server: targeted file-only quality pytest passed",
  "python-hwpx: targeted operating-plan and template-formfit pytest passed"
]
```

Do not call `complete_stage` until the verification commands have actually passed and the observer output is fresh.

## Self-Review

- Spec coverage: The runner records target file, viewer state, screenshot/fallback, status, timestamp, tool path, iteration history, and residual layout risks. Docs require `observed_pass` before submission-ready visual claims. Fallback smoke covers CI/viewer-missing environments.
- Placeholder scan: The plan contains no implementation placeholders for code or docs. Runtime Stage completion values are collected from fresh Wily observer output at completion time.
- Type consistency: The evidence schema uses `schemaVersion`, `current.status`, `summary.resolved_visual_review_required`, `summary.ready_for_submission_claim`, `iterations[]`, and `viewer.available` consistently across runner, quickcheck, examples, and docs.
