## Why

MobileTestAgent needs a low-noise, actionable screen observation contract from u2cli. Today agents can receive compact-ish dump data and some session refs, but the raw UI hierarchy remains too large for agent context, refs are not owned by a durable screen dump artifact contract, and legacy element tools cannot consume snapshot refs as first-class targets.

## What Changes

- Upgrade `u2cli_screen_dump(compact=true)` / `screen dump --compact` from a simple projected dump into a structured compact snapshot presentation.
- Persist raw dump, compact snapshot, and ref map artifacts for every compact capture while keeping raw UI XML out of the agent-facing response.
- Add stable `snapshotId` and `@eN` refs owned by u2cli, with `refMapPath` mapping snapshot refs back to raw node locators.
- Add platform-generic UI dump denoising: visibility/interactability filtering, semantic label preservation, wrapper pruning, duplicate sibling folding, normalized text/bounds/roles/actions, and stable ordering.
- Allow element interaction tools to target refs with `target: {"ref":"@e3","snapshotId":"..."}` while preserving existing selector targets.
- Return structured stale/unresolvable ref errors with candidate refs and raw artifact path.
- Keep task-intent, memory, report, healer strategy, and business semantic pruning out of u2cli.
- Preserve old behavior when `compact=false`.

## Capabilities

### New Capabilities

- `compact-snapshot-refs`: Structured compact screen snapshots, raw/compact/ref map artifacts, u2cli-owned actionable refs, and ref-aware element tool targets.

### Modified Capabilities

- None.

## Impact

- Code: `src/androidtestclii/screen/dump.py`, snapshot/ref helpers, session/ref store, element target parsing/action/query paths, CLI command adapters, Pi tool schema generation/data, and compatibility aliases under `src/u2cli`.
- APIs: `u2cli_screen_dump(compact=true)` gains `snapshotId`, `compactArtifactPath`, `rawArtifactPath`, `refMapPath`, and structured `nodes`; element tools accept ref targets in addition to existing selectors.
- Artifacts: compact screen dumps write raw XML/snapshot, compact JSON, and ref map JSON under deterministic artifact paths.
- Tests: add raw UI dump fixtures, compact snapshot golden coverage, denoising/folding tests, ref-resolution tests for click/input/wait, artifact persistence checks, and regression tests ensuring raw XML is not returned inline.
- Dependencies: no new runtime dependency is expected; implementation should use existing Python stdlib XML/JSON/path utilities unless a stronger local project pattern already exists.
