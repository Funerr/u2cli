## ADDED Requirements

### Requirement: Compact screen dump returns a structured snapshot

`u2cli_screen_dump(compact=true)` and `screen dump --compact` MUST return an agent-facing compact snapshot object that includes `snapshotId`, `compactArtifactPath`, `rawArtifactPath`, `refMapPath`, and `nodes`. Each `nodes[]` entry MUST include at least `ref`, `text`, `contentDesc`, `resourceId`, `className`, `packageName`, `role`, `bounds`, `center`, `visible`, `enabled`, `clickable`, `focusable`, `scrollable`, `selected`, `checked`, `actions`, `parentRef`, and `stableKey`. The agent-facing compact response MUST NOT inline the full raw UI dump or raw UI XML text.

#### Scenario: Compact dump returns contract fields

- **WHEN** `u2cli_screen_dump` is called with `compact=true`
- **THEN** the result includes `snapshotId`, `compactArtifactPath`, `rawArtifactPath`, `refMapPath`, and a `nodes` array whose entries include all required compact node fields

#### Scenario: Raw dump is not returned inline

- **WHEN** a compact screen dump captures a raw UI hierarchy larger than the compact summary
- **THEN** the agent-facing result references `rawArtifactPath` and does not include the full raw hierarchy text inline

#### Scenario: Non-compact behavior remains compatible

- **WHEN** `u2cli_screen_dump` or `screen dump` is called with `compact=false`
- **THEN** the existing non-compact behavior and selector-compatible API surface remain available

### Requirement: Compact captures persist raw compact and ref map artifacts

For every successful compact capture, u2cli MUST persist the raw dump or raw snapshot, the compact snapshot JSON, and the ref map JSON. `compactArtifactPath`, `rawArtifactPath`, and `refMapPath` MUST point to files that exist after the command returns. The ref map artifact MUST include `snapshotId`, `rawArtifactPath`, `compactArtifactPath`, and a mapping from each compact `ref` to a raw node locator.

#### Scenario: Compact capture writes all artifacts

- **WHEN** a compact screen dump succeeds
- **THEN** the raw artifact, compact artifact, and ref map artifact exist on disk and their paths are returned in the result

#### Scenario: Ref map links refs to raw nodes

- **WHEN** a compact snapshot contains a node with `ref="@e3"`
- **THEN** the ref map artifact contains an entry for `@e3` with the same `snapshotId` and a raw node locator such as a raw tree path or raw ordinal

### Requirement: Compact snapshot denoising is generic and stable

u2cli MUST apply platform-generic UI dump denoising before returning compact nodes. The denoiser MUST keep visible or interactable nodes, preserve necessary visible labels, headings, and nearby explanatory text for interactable nodes, and remove invisible, zero-size, fully offscreen, and no-semantics wrapper/container nodes. The denoiser MUST fold duplicate sibling nodes by normalized signature while preserving count, representative information, and necessary children. It MUST normalize whitespace, empty text, bounds, role, and action flags. Compact node order MUST be stable and follow screen reading order or UI tree traversal order consistently.

#### Scenario: Invisible and empty container nodes are removed

- **WHEN** the raw UI dump contains invisible nodes, zero-size nodes, offscreen nodes, and textless actionless wrapper containers
- **THEN** those nodes are absent from the compact `nodes` output unless they are needed to preserve required context for a kept child

#### Scenario: Interactable nodes and context labels are preserved

- **WHEN** a visible interactable control has a nearby visible label or heading that explains it
- **THEN** the compact output includes the control and enough label or heading context to identify the interaction

#### Scenario: Duplicate siblings are folded

- **WHEN** sibling nodes have the same normalized signature and repeat as structural duplicates
- **THEN** the compact output represents them with a folded representative and a count rather than repeating all duplicates verbatim

#### Scenario: Compact ordering is deterministic

- **WHEN** the same raw dump is compacted multiple times with the same options
- **THEN** the compact `nodes` order and generated refs are identical

### Requirement: Refs are owned by u2cli and snapshot scoped

u2cli MUST generate and maintain canonical `@eN` refs for compact snapshot nodes. Each ref MUST be scoped to a `snapshotId` and MUST map back to the corresponding raw node locator through `refMapPath`. Each compact node and ref map entry MUST include a `stableKey` suitable for comparing equivalent nodes across snapshots, without making refs globally permanent.

#### Scenario: Compact node refs use canonical format

- **WHEN** compact nodes are returned
- **THEN** every actionable or semantic compact node has a `ref` formatted as `@eN`

#### Scenario: Ref map can resolve raw node locator

- **WHEN** a caller reads `refMapPath` for a returned `snapshotId`
- **THEN** each ref entry maps to the raw node locator, compact node metadata, `stableKey`, and available selector or bounds fallback data

### Requirement: Element tools accept ref targets

`u2cli_element_click`, `u2cli_element_set_text`, and `u2cli_element_wait` MUST accept `target: {"ref": "@e3", "snapshotId": "..."}` in addition to existing selector targets. Ref target resolution MUST use the u2cli-owned ref map for the given `snapshotId`. Existing selector targets MUST remain compatible.

#### Scenario: Click resolves a ref target

- **WHEN** `u2cli_element_click` receives `target: {"ref": "@e3", "snapshotId": "S"}`
- **THEN** it resolves `@e3` through snapshot `S` and performs the click using bounds center or selector fallback

#### Scenario: Set text resolves a ref target

- **WHEN** `u2cli_element_set_text` receives `target: {"ref": "@e3", "snapshotId": "S"}` and text to enter
- **THEN** it resolves `@e3`, focuses the target, and sets or inputs the requested text using the existing mutation semantics

#### Scenario: Wait resolves a ref target

- **WHEN** `u2cli_element_wait` receives `target: {"ref": "@e3", "snapshotId": "S"}`
- **THEN** it resolves `@e3` through snapshot `S` and waits using available selector or equivalent ref locator data

#### Scenario: Selector targets remain supported

- **WHEN** an element tool receives an existing selector target instead of a ref target
- **THEN** it behaves compatibly with the pre-change selector path

### Requirement: Ref resolution failures are structured

If a ref is expired, missing, or cannot be resolved to an actionable locator, u2cli MUST return a structured error. The error MUST include `code`, `message`, `snapshotId`, `ref`, `candidateRefs`, and `rawArtifactPath` when those values are available.

#### Scenario: Missing ref returns candidates

- **WHEN** an element tool receives `target: {"ref": "@e99", "snapshotId": "S"}` and snapshot `S` exists but does not contain `@e99`
- **THEN** the command fails with a structured ref error that includes `snapshotId="S"`, `ref="@e99"`, candidate refs from that snapshot, and `rawArtifactPath`

#### Scenario: Missing snapshot reports stale ref

- **WHEN** an element tool receives a ref target whose `snapshotId` cannot be found
- **THEN** the command fails with a structured ref error that includes the requested `snapshotId`, requested `ref`, and guidance through the error message to capture a fresh compact snapshot

### Requirement: u2cli does not perform task semantic pruning

u2cli MUST NOT filter compact nodes based on test step intent, MemoryPack, keyPath, caseId, report adoption rules, or healer recovery strategy. Those decisions MUST remain in MobileTestAgent or the higher-level Agent workflow.

#### Scenario: Same raw dump produces same compact output across intents

- **WHEN** the same raw UI dump is compacted for different higher-level test intents or case metadata
- **THEN** u2cli produces the same generic compact snapshot, refs, and artifact paths except for capture-time metadata
