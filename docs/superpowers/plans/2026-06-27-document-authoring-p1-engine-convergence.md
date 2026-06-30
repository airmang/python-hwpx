# M3 Document Authoring — P1: Engine Convergence + 결문 IR — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the public authoring path (`create_document_from_plan`) produce **profile-based, Hancom-opens-clean** documents by routing `document_type` (공문/보고서/가정통신문) to the verified `design.compose` profile path, and carry 결문 메타(발신명의·생산등록번호·시행일·공개구분) in the IR.

**Architecture (Approach A, owner-approved):** Add a thin **router + bridge** inside `hwpx.authoring.create_document_from_plan`. When the plan's `document_type` resolves to a committed design profile (`available_profiles()`), bridge the plan dict → `design.DocumentPlan` and call `design.compose_bytes(...)`, then `HwpxDocument.open(BytesIO(bytes))` and return it — **preserving the existing `-> HwpxDocument` contract** so the MCP `_create_document_from_plan_impl` (server.py:1396, `doc = build_document_from_plan(...)` → `_save_generated_document`) needs no change. Unknown/no-profile types keep the current from-scratch builder path (regression-safe).

**Tech Stack:** python-hwpx (`hwpx.authoring`, `hwpx.design.{compose_bytes,DocumentPlan,Block,available_profiles}`, `hwpx.document.HwpxDocument`), `uv run --extra dev [--extra visual] python -m pytest`.

## Global Constraints

- **Spec:** `specs/004-document-authoring/spec.md` (FR-001 routing, FR-002 공문 골격, FR-003 결문 메타, FR-007 보고서 제목위계). This plan = **P1**.
- **Branch:** `feat/s057-document-authoring` (never main).
- **Contract preserved:** `authoring.create_document_from_plan(plan, *, preset=None) -> HwpxDocument` signature + return type UNCHANGED. Router is internal.
- **Profiles (P0-verified, coverage 1.0, opens-clean):** `official_notice`, `report`, `home_notice` (+ `application_form`). `design.compose(..., production=True)` enforces style-coverage ≥ threshold.
- **No silent true / fail-closed:** if a profile route's `compose_bytes` result is `not ok`, do NOT silently fall back to from-scratch — raise/return the structured compose errors (Constitution V/VI). From-scratch is only for types with NO profile.
- **결문 (P0 finding):** 발신명의·생산등록번호·시행일·공개구분 render as design `body` blocks and survive Hancom (p0-gyeolmun-footnote-verdict.json). Model them as structured IR fields lowered to body blocks in 결문 order.
- **각주 = OUT of P1** (P2: add_footnote+compose doesn't render — separate investigation).
- TDD per task; commit per task.

---

### Task 1: document_type → design profile resolver

**Files:**
- Modify: `python-hwpx/src/hwpx/authoring.py` (add `_resolve_design_profile`)
- Test: `python-hwpx/tests/test_authoring_profile_routing.py` (new)

**Interfaces:**
- Produces: `_resolve_design_profile(plan: Mapping) -> str | None` — returns a profile id present in `design.available_profiles()`, or None.

- [ ] **Step 1: Confirm the v1 plan schema's document_type carrier**

Run: `cd python-hwpx && uv run python -c "from hwpx.authoring import normalize_document_plan as n; p=n({'title':'t','documentType':'공문','blocks':[]}); print(type(p).__name__, getattr(p,'document_type',None), getattr(p,'metadata',None))"`
Expected: prints the normalized plan; note whether `document_type` is a field or lives in `metadata`/raw key. (Schema uses camelCase `documentType` / Korean `문서 유형` per authoring.py:57.) Use the confirmed key in Step 3.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_authoring_profile_routing.py
from hwpx.authoring import _resolve_design_profile

def test_resolves_known_korean_types():
    assert _resolve_design_profile({"documentType": "공문"}) == "official_notice"
    assert _resolve_design_profile({"documentType": "보고서"}) == "report"
    assert _resolve_design_profile({"documentType": "가정통신문"}) == "home_notice"

def test_resolves_profile_id_directly():
    assert _resolve_design_profile({"documentType": "official_notice"}) == "official_notice"

def test_unknown_returns_none():
    assert _resolve_design_profile({"documentType": "메모"}) is None
    assert _resolve_design_profile({}) is None
```

Run: `cd python-hwpx && uv run --extra dev python -m pytest tests/test_authoring_profile_routing.py -q`
Expected: FAIL (`_resolve_design_profile` not defined).

- [ ] **Step 3: Implement the resolver**

In `authoring.py`, add a mapping of Korean labels + profile ids → profile id, gated by `design.available_profiles()`:
```python
from hwpx import design as _design

_DOCTYPE_TO_PROFILE = {
    "공문": "official_notice", "공문서": "official_notice", "official_notice": "official_notice",
    "보고서": "report", "report": "report", "government_report": "report",
    "가정통신문": "home_notice", "home_notice": "home_notice",
}

def _resolve_design_profile(plan):
    raw = plan.get("documentType") or plan.get("document_type") or plan.get("문서 유형") if isinstance(plan, Mapping) else None
    if not raw:
        return None
    pid = _DOCTYPE_TO_PROFILE.get(str(raw).strip())
    return pid if (pid and pid in _design.available_profiles()) else None
```

- [ ] **Step 4: Run tests to pass**

Run: `cd python-hwpx && uv run --extra dev python -m pytest tests/test_authoring_profile_routing.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/hwpx/authoring.py tests/test_authoring_profile_routing.py
git commit -m "feat(m3-p1): document_type -> design profile resolver"
```

---

### Task 2: plan dict → design.DocumentPlan bridge

**Files:**
- Modify: `python-hwpx/src/hwpx/authoring.py` (add `_bridge_to_design_plan`)
- Test: `tests/test_authoring_profile_routing.py` (extend)

**Interfaces:**
- Consumes: Task 1 resolver; `design.DocumentPlan`, `design.plan.Block`.
- Produces: `_bridge_to_design_plan(plan: Mapping, profile_id: str) -> design.DocumentPlan` — title + blocks mapped to design roles (heading levels → `heading`/`subheading`, paragraphs → `body`, tables → `type="table"`).

- [ ] **Step 1: Confirm the plan block structure**

Run: `cd python-hwpx && uv run python -c "from hwpx.authoring import get_document_plan_schema as s; import json; print(json.dumps(s(), ensure_ascii=False)[:1200])"` (or read `validate_document_plan` source). Confirm how blocks/sections + heading level are represented (e.g. `{'type':'heading','level':1,'text':...}` vs `{'type':'paragraph'}`). Use the confirmed shape in Step 3.

- [ ] **Step 2: Write the failing test**

```python
from hwpx.authoring import _bridge_to_design_plan
from hwpx.design.plan import DocumentPlan as DP

def test_bridge_maps_title_and_blocks():
    plan = {"documentType": "공문", "title": "협조 요청",
            "blocks": [{"type": "heading", "level": 1, "text": "1. 관련"},
                       {"type": "paragraph", "text": "가. 본문"}]}
    dp = _bridge_to_design_plan(plan, "official_notice")
    assert isinstance(dp, DP) and dp.profile == "official_notice" and dp.title == "협조 요청"
    roles = [(b.type, b.role) for b in dp.blocks]
    assert ("paragraph", "heading") in roles and ("paragraph", "body") in roles
```

Run it → FAIL.

- [ ] **Step 3: Implement the bridge**

Map each plan block to a design `Block` (heading level 1→`heading`, ≥2→`subheading`; paragraph→`body`; table→`type="table"`, columns/rows passthrough). Title → `DocumentPlan.title` (design promotes it to a title block via `iter_blocks`). Skip block types with no design role (record nothing — compose's production gate will surface coverage gaps).

- [ ] **Step 4: Run → PASS. Step 5: Commit** (`feat(m3-p1): plan -> design.DocumentPlan bridge`)

---

### Task 3: 결문 메타 IR (발신명의·생산등록번호·시행일·공개구분)

**Files:** Modify `authoring.py` (extend bridge); Test extend.

**Interfaces:** bridge reads `plan["gyeolmun"]` (or `결문`) = `{issuer, productionNumber, enforcementDate, disclosure}` and appends them as trailing design `body` blocks in 결문 order (P0-proven to render + survive).

- [ ] **Step 1: Failing test**

```python
def test_bridge_appends_gyeolmun_blocks():
    plan = {"documentType": "공문", "title": "t", "blocks": [{"type":"paragraph","text":"본문  끝."}],
            "gyeolmun": {"issuer": "○○교육지원청교육장", "productionNumber": "교육과-123",
                          "enforcementDate": "2026. 6. 27.", "disclosure": "공개"}}
    dp = _bridge_to_design_plan(plan, "official_notice")
    texts = " ".join(b.text for b in dp.blocks)
    assert "○○교육지원청교육장" in texts and "교육과-123" in texts and "2026. 6. 27." in texts and "공개" in texts
```

- [ ] **Step 2: Implement** — append body blocks for each present 결문 field (label + value), in order issuer→productionNumber→enforcementDate→disclosure, after content blocks. **Step 3: PASS. Step 4: Commit** (`feat(m3-p1): 결문 메타 IR lowered to 결문 blocks`).

---

### Task 4: Route create_document_from_plan to compose_bytes (contract-preserving)

**Files:** Modify `authoring.py:877` `create_document_from_plan`; Test extend (+ a real compose+open).

**Interfaces:** Consumes Tasks 1–3 + `design.compose_bytes(plan, production=True) -> (bytes, ComposeResult)`, `HwpxDocument.open(BytesIO)`.

- [ ] **Step 1: Failing test (routed doc opens + uses profile)**

```python
import io
from hwpx.authoring import create_document_from_plan
from hwpx.document import HwpxDocument

def test_gongmun_routes_to_profile_and_opens():
    plan = {"documentType":"공문","title":"협조 요청",
            "blocks":[{"type":"heading","level":1,"text":"1. 관련"},
                      {"type":"paragraph","text":"가. 협조하여 주시기 바랍니다.  끝."}],
            "gyeolmun":{"issuer":"○○교육지원청교육장","enforcementDate":"2026. 6. 27.","disclosure":"공개"}}
    doc = create_document_from_plan(plan)
    assert isinstance(doc, HwpxDocument)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "협조" in text  # body present
    doc.close()

def test_unknown_type_uses_from_scratch_path():
    # regression: no profile -> existing builder path still returns a doc
    doc = create_document_from_plan({"title":"메모","blocks":[{"type":"paragraph","text":"x"}]})
    assert isinstance(doc, HwpxDocument); doc.close()
```

Run → FAIL (first test: 공문 currently goes through from-scratch, not profile).

- [ ] **Step 2: Implement the route** — at the top of `create_document_from_plan`, after obtaining the raw mapping:
```python
if isinstance(plan, Mapping):
    pid = _resolve_design_profile(plan)
    if pid is not None:
        import io
        dp = _bridge_to_design_plan(plan, pid)
        data, result = _design.compose_bytes(dp, production=True)
        if not result.ok:
            raise ValueError(f"profile compose failed for {pid!r}: {result.errors}")
        return HwpxDocument.open(io.BytesIO(data))
# ... existing normalize + from-scratch path unchanged
```

- [ ] **Step 3: Run → PASS (both). Step 4: full suite** `uv run --extra dev python -m pytest -q` (expect green; investigate any authoring regressions). **Step 5: Commit** (`feat(m3-p1): route document_type to design.compose, contract-preserving`).

---

### Task 5: 보고서 heading hierarchy (≤3) through the routed path (FR-007)

**Files:** Test only (verify), adjust bridge if levels mis-map.

- [ ] **Step 1: Test** a `보고서` plan with 3 heading levels → routed doc; assert distinct styles applied for level1 vs level2/3 (heading vs subheading roles present in the composed doc). Run → fix bridge level mapping if needed → PASS → Commit (`test(m3-p1): report 3-level heading hierarchy via profile`).

---

### Task 6: Oracle smoke — routed 공문·보고서·가정통신문 open clean (gated)

**Files:** `tests/test_authoring_profile_routing_oracle.py` (new, gated by `HWPX_MAC_ORACLE_SMOKE=1` like `tests/test_design_builder.py:284`).

- [ ] **Step 1:** For each of 공문/보고서/가정통신문, build via `create_document_from_plan`, save, render via `MacHancomOracle.render_pdf`, assert PDF opens in fitz with text. Skip unless `HWPX_MAC_ORACLE_SMOKE=1`.
- [ ] **Step 2:** Run locally: `HWPX_MAC_ORACLE_SMOKE=1 uv run --extra dev --extra visual python -m pytest tests/test_authoring_profile_routing_oracle.py -q` (dangerouslyDisableSandbox). Expect opens-clean for all three. **Step 3: Commit** (`test(m3-p1): oracle smoke for routed authoring (gated)`).

---

## Self-Review

- **Spec coverage:** FR-001 → T1+T4; FR-002 (공문 골격) → T4 (profile skeleton); FR-003 (결문 메타) → T3; FR-007 (제목위계) → T5; oracle opens-clean → T6. home_notice routing covered by T1/T4 (profile exists). FR-004 lint hard-gate = **P2**; FR-006 각주 = **P2**; FR-008 oracle-in-quality-gate = **P3**; FR-010/011 MCP+guard = **P4**.
- **Placeholder scan:** Steps 1 of T1/T2 are real schema-confirmation commands (not placeholders); all code steps show code.
- **Type consistency:** `_resolve_design_profile(plan)->str|None`, `_bridge_to_design_plan(plan, pid)->design.DocumentPlan`, route uses `compose_bytes(dp, production=True)->(bytes,result)` + `HwpxDocument.open(BytesIO)`; contract `create_document_from_plan(...)->HwpxDocument` preserved.

## Execution note
Subagent/workflow-driven from root; oracle smoke (T6) serial + `dangerouslyDisableSandbox`. On P1 completion: `complete_phase` PH-2b37a2dd3417, then author P2 plan (공문 구조 hard-gate using seoul_sihaengmun anchor + 각주 investigation).
