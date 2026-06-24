## 1. Contract Tests and Fixtures

- [x] 1.1 Add raw UI dump fixtures covering visible controls, labels/headings, invisible nodes, zero-size nodes, offscreen nodes, pure containers, and repeated sibling structures.
- [x] 1.2 Add compact snapshot golden tests for required node fields, canonical `@eN` refs, `stableKey`, normalized bounds/center, roles, actions, and stable ordering.
- [x] 1.3 Add denoising tests proving invisible, zero-size, offscreen, pure-container, and duplicate sibling nodes are pruned or folded while visible/interactable nodes and required labels remain.
- [x] 1.4 Add screen dump tests verifying compact captures return `snapshotId`, `compactArtifactPath`, `rawArtifactPath`, `refMapPath`, and do not inline full raw UI XML.
- [x] 1.5 Add ref target tests proving click, set-text/input, and wait resolve `target: {"ref":"@eN","snapshotId":"..."}` and selector targets remain compatible.

## 2. Snapshot Artifact Model

- [x] 2.1 Add snapshot id and artifact path helpers for raw, compact, and ref map files under a deterministic local artifact root.
- [x] 2.2 Add atomic JSON/text artifact writing helpers and typed artifact metadata for screen dump results.
- [x] 2.3 Implement normalized raw-node parsing from UI XML with raw tree path, raw ordinal, parent path, normalized semantic fields, bounds, center, visibility, state flags, role, and actions.
- [x] 2.4 Update compact screen dump pipeline to persist raw dump first, then compact JSON and ref map JSON, before returning the agent-facing compact response.

## 3. Compact Denoising and Presentation

- [x] 3.1 Implement generic keep/drop rules for visible nodes, interactable nodes, semantic text, labels, headings, invisible nodes, zero-size nodes, and offscreen nodes.
- [x] 3.2 Implement wrapper/container pruning for textless actionless layout nodes while preserving child context and correct `parentRef` relationships.
- [x] 3.3 Implement duplicate sibling folding by normalized signature with count and representative data.
- [x] 3.4 Emit full-field compact nodes with `ref`, `text`, `contentDesc`, `resourceId`, `className`, `packageName`, `role`, `bounds`, `center`, state flags, `actions`, `parentRef`, and `stableKey`.
- [x] 3.5 Preserve `compact=false` behavior and retain compatibility aliases or parsing support needed by existing snapshot/ref callers.

## 4. Ref Map Ownership and Resolution

- [x] 4.1 Write ref map artifacts keyed by `snapshotId` and canonical `@eN` refs, including raw node locator, stable key, compact node metadata, selector fallback, bounds, center, and artifact paths.
- [x] 4.2 Update session latest-snapshot storage to point at the latest artifact-backed snapshot/ref map while preserving existing top-level `@eN` flows.
- [x] 4.3 Add a shared element target resolver that accepts existing selectors, canonical ref objects with `snapshotId`, and compatibility string refs where supported.
- [x] 4.4 Return structured stale/missing/invalid ref errors with `code`, `message`, `snapshotId`, `ref`, `candidateRefs`, and `rawArtifactPath`.

## 5. Element Tools and Schemas

- [x] 5.1 Extend `u2cli_element_click` and CLI element click paths to execute ref targets via bounds center or selector fallback.
- [x] 5.2 Extend `u2cli_element_set_text` / input paths to focus ref targets and enter text using existing mutation semantics.
- [x] 5.3 Extend `u2cli_element_wait` to resolve ref targets and wait using available selector or equivalent locator data.
- [x] 5.4 Update Pi tool schema/data and TypeScript extension surfaces so `u2cli_screen_dump`, `u2cli_element_click`, `u2cli_element_set_text`, and `u2cli_element_wait` expose the new compact/ref target contract.

## 6. Documentation and Verification

- [x] 6.1 Update README or project docs with compact snapshot output, artifact paths, ref map shape, ref target examples, and non-goal boundaries.
- [x] 6.2 Run focused compact/ref tests and the existing pytest suite for screen dump, element actions, selector parsing, Pi schema smoke, and compatibility behavior.
- [x] 6.3 Validate OpenSpec artifacts with `openspec validate add-compact-snapshot-refs` and ensure the change remains apply-ready.
