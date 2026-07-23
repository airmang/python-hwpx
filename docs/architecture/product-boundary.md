# python-hwpx product boundary

`python-hwpx` is the primary product: an independently useful HWPX document
library comparable in role to `python-docx`.

## Core owns

- the document object model and public facade;
- OPC package and OXML part ownership;
- generic reading, traversal, editing, formatting, and table primitives;
- serialization, byte/story preservation, validation, rollback, and recovery;
- renderer-neutral quality contracts such as `RenderBackend`, `EditMask`, and
  `VisualReport`.

## Companion layers own

`hwpx-mcp-server` owns office workflows, genre/profile/policy decisions, agent
plans, Hancom discovery, and renderer binding. `hwpx-skill` owns task judgment,
routing, and prompt guidance.

Core must not import either companion package. A new core module that was not
present at the 4.2.0 baseline requires an explicit entry in
[`module-ownership.json`](./module-ownership.json); falling through the generic
core rule is not enough.

## Mixed-module decisions

- `quality` and `table_patch` stay core.
- `visual` is split: neutral contracts are core; Hancom/backend binding is MCP.
- document diff keeps a generic diff model in core; task-plan composition moves.
- mail merge keeps generic HWPX binding in core; sanitization/policy is injected.
- tracked-change format primitives stay core; oracle verification moves.
- benchmark and conformance campaign runners are repository QA, not product API.

The released application packages are grandfathered debt. Their file and LOC
totals may shrink but cannot grow. Breaking removal requires a published 4.x
migration path and a separate owner-approved 5.0 gate.
