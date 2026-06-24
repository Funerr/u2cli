## Context

u2cli is currently a compatibility entry point over the `androidtestclii` package. `screen dump --compact` already has a lightweight XML projection and the top-level agent commands already consume session-backed `@eN` refs, but the screen dump contract is not yet strong enough for MobileTestAgent:

- compact output is not a structured MobileTestAgent-facing snapshot contract;
- raw dump/ref map artifacts are not returned as durable paths from `u2cli_screen_dump(compact=true)`;
- compact refs are mostly session cache entries, not snapshot-scoped artifacts owned by u2cli;
- legacy element tools still primarily accept selectors rather than structured ref targets;
- denoising is minimal and does not fold wrappers, invisible nodes, offscreen nodes, or duplicate siblings in a principled way.

This change upgrades the u2cli layer into the owner of raw capture, compact presentation, denoising, and actionable refs. MobileTestAgent should consume compact nodes plus artifact paths and leave task-specific relevance, memory, reporting, and healer strategy outside u2cli.

## Goals / Non-Goals

**Goals:**

- Return a structured compact snapshot from `u2cli_screen_dump(compact=true)` with `snapshotId`, raw/compact/ref map artifact paths, and full-field compact nodes.
- Persist raw UI dump/raw snapshot, compact snapshot JSON, and ref map JSON for compact captures.
- Assign canonical `@eN` refs in u2cli and map them back to raw node locators.
- Provide platform-generic denoising that reduces context while preserving visible, interactable, and explanatory semantic nodes.
- Let element click, set-text/input, and wait tools consume `target: {"ref":"@e3","snapshotId":"..."}` while keeping existing selector inputs.
- Return structured ref resolution errors that are useful to retry, re-snapshot, report, or heal.
- Preserve old behavior for `compact=false` and keep existing selector-based APIs compatible.

**Non-Goals:**

- No task-step intent relevance filtering.
- No MemoryPack, keyPath, caseId, report adoption, or healer recovery strategy decisions.
- No platform-specific business semantics.
- No replacement of the existing snapshot backends.
- No requirement that refs remain valid across unrelated future screens; refs are snapshot-scoped.

## Decisions

### 1. Artifact-first compact snapshot pipeline

Compact capture will be split into four stages:

1. Capture raw XML/snapshot metadata using the existing snapshot backends.
2. Write raw artifact first, then parse it into a normalized internal node tree.
3. Build compact nodes and ref map from the normalized tree.
4. Write compact JSON and ref map JSON, then return only compact presentation fields and artifact paths.

Default artifact layout should be deterministic and local, for example:

```text
artifacts/snapshots/<snapshotId>/raw.xml
artifacts/snapshots/<snapshotId>/compact.json
artifacts/snapshots/<snapshotId>/ref-map.json
```

`snapshotId` should be unique and traceable to the capture, such as an ISO timestamp plus a short content hash. The response should include `rawArtifactPath`, `compactArtifactPath`, and `refMapPath`; the top-level `artifacts` list may also include typed entries for these files.

Alternative considered: continue returning in-memory projected nodes and only caching refs in the session. That keeps the implementation smaller, but it gives healer/report/debug flows no durable raw artifact boundary and makes refs ambiguous once the session changes.

### 2. Normalize raw nodes before denoising

Create a small internal raw-node model from XML attributes:

- raw tree path, raw ordinal, parent path, and XML attributes;
- normalized `text`, `contentDesc`, `resourceId`, `className`, and `packageName`;
- parsed `bounds`, `center`, and screen intersection;
- booleans for visible, enabled, clickable, long-clickable, focusable, scrollable, selected, checked, checkable, editable, and password where available;
- derived `role` and `actions`.

Visibility should be conservative: `visible-to-user="false"`, zero-area bounds, and fully offscreen bounds are invisible; when explicit visibility is absent, a nonzero screen-intersecting node is treated as potentially visible. Interactable nodes are kept even with sparse text, as long as their bounds/action flags make them useful.

Alternative considered: denoise directly from XML during traversal. That is faster to write, but it makes parent label preservation, duplicate sibling folding, and ref-map raw locator generation harder to reason about and test.

### 3. Denoising is generic, not task-semantic

The compact builder should keep:

- visible nodes with text, content description, resource id, role, or useful state;
- enabled or disabled interactable nodes that explain what can be tapped, typed into, waited for, or scrolled;
- nearby visible labels/headings/semantic text needed to understand an interactable node.

The builder should remove or fold:

- invisible, zero-size, or fully offscreen nodes;
- pure wrapper containers such as textless/actionless `FrameLayout`, `LinearLayout`, and `ViewGroup` descendants;
- duplicate sibling groups with the same normalized signature, while preserving count and a representative node;
- empty strings, noisy whitespace, invalid bounds, and inconsistent action flags.

Duplicate sibling signatures should be based on role, normalized text/content description/resource id, class, state/action flags, and compact child signatures. Folded representatives should expose a `count` or `foldedCount` field without hiding required node fields.

Alternative considered: allow MobileTestAgent to ask for intent-filtered compact output. That belongs above u2cli; putting it here would couple device observation to test planning and memory.

### 4. Refs are snapshot-scoped and artifact-backed

Canonical refs in compact output should include the `@` prefix, for example `@e0`, `@e1`, and so on. The resolver should accept legacy `eN` input where practical, but new compact nodes should expose `ref: "@eN"`.

`refMapPath` should point to a JSON object shaped around the snapshot:

```json
{
  "snapshotId": "2026-06-24T12-34-56.789Z-ab12cd34",
  "rawArtifactPath": "artifacts/snapshots/.../raw.xml",
  "compactArtifactPath": "artifacts/snapshots/.../compact.json",
  "refs": {
    "@e0": {
      "ref": "@e0",
      "stableKey": "button:com.example:id/login:...",
      "rawNodePath": [0, 1, 3],
      "rawOrdinal": 7,
      "selector": {"text": "Login", "resourceId": "com.example:id/login"},
      "bounds": {"left": 40, "top": 1200, "right": 720, "bottom": 1320},
      "center": {"x": 380, "y": 1260}
    }
  }
}
```

`stableKey` should be deterministic for the same raw node attributes and path. It is not a promise that a ref can be replayed forever; it is a comparison key for memory, report, and healer layers.

Alternative considered: rely only on selectors inside the ref map. Selectors are useful fallbacks, but some nodes are only safely actionable via bounds or raw location, and reports need to know which raw node was summarized.

### 5. Element targets support selectors and snapshot refs

Introduce a shared target resolution layer that accepts:

- existing structured selector targets;
- canonical ref targets with `snapshotId`, such as `{"ref":"@e3","snapshotId":"..."}`;
- compatibility string refs where current CLI surfaces already accept `@e3`.

Resolution should load the requested ref map by `snapshotId`; if absent, it may fall back to the latest session snapshot only for compatibility surfaces. Click uses bounds center first when available, then selector fallback. Set text taps/focuses the ref target and sends text through the existing input path. Wait re-evaluates via selector when present and otherwise reports that the ref is not waitable.

Structured ref failures should preserve the standard result envelope and include, in the error details, `code`, `message`, `snapshotId`, `ref`, `candidateRefs`, and `rawArtifactPath`.

Alternative considered: add separate `click-ref`, `set-text-ref`, and `wait-ref` tools. A unified target model keeps MobileTestAgent simple and keeps selectors backwards compatible.

### 6. Compatibility is additive

`compact=false` must keep the old screen dump behavior. Existing selector-based element APIs continue to work. Existing top-level `snapshot/click/fill/get` session-ref flows should keep accepting `@eN`; they can be backed by the new artifact ref map and latest-session pointer.

For compact output, full-field node names are canonical (`contentDesc`, `resourceId`, `className`, `parentRef`, etc.). Short legacy aliases such as `desc`, `rid`, or unprefixed `eN` may be retained temporarily if needed, but MobileTestAgent should rely on the new structured fields.

## Risks / Trade-offs

- [Risk] Ref numbers change when denoising changes. -> Keep refs explicitly snapshot-scoped and provide `stableKey` for cross-snapshot comparison.
- [Risk] Denoising can accidentally remove a useful label. -> Preserve visible labels/headings near interactable nodes and use golden tests for label/context cases.
- [Risk] Duplicate folding can hide repeated actionable list rows. -> Fold only sibling groups with matching signatures and preserve `count`, representative refs, and necessary children.
- [Risk] Artifact files can grow over time. -> Keep this change to writing explicit artifacts; cleanup/retention policy can be handled separately if needed.
- [Risk] Ref artifact lookup may fail after files are moved. -> Return structured errors with snapshot id, ref, candidate refs, and raw artifact path, and allow callers to re-snapshot.

## Migration Plan

1. Add fixtures and tests that describe the new compact snapshot contract.
2. Implement artifact path helpers and write raw/compact/ref map artifacts for compact captures.
3. Replace or extend `compact_projection` with the normalized denoising pipeline.
4. Update session latest-snapshot storage to reference the new snapshot id/ref map while preserving current session-ref flows.
5. Update element target parsing/resolution and Pi schema for ref-aware targets.
6. Update README/docs after tests pass.

Rollback is straightforward because `compact=false` remains unchanged and selector-based element APIs remain intact. If compact snapshot behavior needs to be reverted, callers can temporarily use existing selectors or the prior top-level snapshot session-ref flow while the artifact-backed compact path is fixed.

## Open Questions

- Should the default artifact root remain `artifacts/snapshots/`, or should it use an OS-specific cache/config directory for long-running agent sessions?
- Should compact output keep short aliases (`cls`, `rid`, `desc`) for one release, or move immediately to full-field names only?
- Should `snapshotId` be accepted on CLI commands as `--snapshot-id`, only through Pi tool target JSON, or both?
