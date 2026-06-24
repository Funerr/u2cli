# Agent Device Alignment Tasks

- **Spec ID**：`agent-device-alignment`
- **Status**：`Implemented`
- **Owner**：`androidtestclii maintainers`
- **Last Updated**：`2026-05-28`
- **Source Design**：`./design.md`

## Status Note

本文件的勾选状态表示 SDD 验收状态，而不是代码仓库中是否已经存在相关实现。若实现已先行落地，也应在完成验证和文档回填后再勾选对应任务。

## Task List

- [x] `TASK-ADA-001`：实现 session store 和 hydrate
  - Covers：`REQ-ADA-003`
  - Design：`DES-ADA-003`
  - Verification：`TEST-ADA-008`、`TEST-ADA-009`、`TEST-ADA-010`

- [x] `TASK-ADA-002`：为 compact snapshot 增加 ref 并写入 refMap
  - Covers：`REQ-ADA-002`
  - Design：`DES-ADA-002`
  - Verification：`TEST-ADA-003`、`TEST-ADA-004`

- [x] `TASK-ADA-003`：实现 `@eN` ref 消费路径
  - Covers：`REQ-ADA-002`
  - Design：`DES-ADA-002`
  - Verification：`TEST-ADA-005`、`TEST-ADA-006`、`TEST-ADA-007`

- [x] `TASK-ADA-004`：实现 target parser
  - Covers：`REQ-ADA-005`
  - Design：`DES-ADA-005`
  - Verification：`TEST-ADA-014`、`TEST-ADA-015`、`TEST-ADA-016`、`TEST-ADA-017`、`TEST-ADA-018`

- [x] `TASK-ADA-005`：注册 P0 顶层 agent 命令
  - Covers：`REQ-ADA-001`、`REQ-ADA-004`
  - Design：`DES-ADA-001`、`DES-ADA-004`
  - Verification：`TEST-ADA-001`、`TEST-ADA-002`、`TEST-ADA-011`、`TEST-ADA-012`、`TEST-ADA-013`

- [x] `TASK-ADA-006`：补齐 `wait/find/is` 结构化诊断
  - Covers：`REQ-ADA-006`
  - Design：`DES-ADA-006`
  - Verification：`TEST-ADA-019`、`TEST-ADA-020`、`TEST-ADA-021`

- [x] `TASK-ADA-007`：实现 `batch` 命令
  - Covers：`REQ-ADA-007`
  - Design：`DES-ADA-007`
  - Verification：`TEST-ADA-022`、`TEST-ADA-023`、`TEST-ADA-024`

- [x] `TASK-ADA-008`：新增 ref、session、batch、alert 错误码
  - Covers：`REQ-ADA-002`、`REQ-ADA-003`、`REQ-ADA-007`、`REQ-ADA-008`、`REQ-ADA-009`
  - Design：`DES-ADA-002`、`DES-ADA-003`、`DES-ADA-007`、`DES-ADA-008`、`DES-ADA-009`
  - Verification：`TEST-ADA-006`、`TEST-ADA-007`、`TEST-ADA-010`、`TEST-ADA-023`、`TEST-ADA-033`

- [x] `TASK-ADA-009`：实现 P1 alert 能力
  - Covers：`REQ-ADA-008`
  - Design：`DES-ADA-008`
  - Verification：`TEST-ADA-025`

- [x] `TASK-ADA-010`：实现 P1 scroll 和 click 修饰器
  - Covers：`REQ-ADA-008`
  - Design：`DES-ADA-008`
  - Verification：`TEST-ADA-026`、`TEST-ADA-027`

- [x] `TASK-ADA-011`：增强 appstate、apps、reinstall、keyboard、connect 能力
  - Covers：`REQ-ADA-008`
  - Design：`DES-ADA-008`
  - Verification：`TEST-ADA-028`、`TEST-ADA-029`、`TEST-ADA-030`

- [x] `TASK-ADA-012`：同步 README 和 Pi schema
  - Covers：`REQ-ADA-009`
  - Design：`DES-ADA-009`
  - Verification：`TEST-ADA-031`、`TEST-ADA-032`、`TEST-ADA-033`

## Traceability Matrix

| Requirement | Design | Task | Verification |
|---|---|---|---|
| `REQ-ADA-001` | `DES-ADA-001` | `TASK-ADA-005` | `TEST-ADA-001`, `TEST-ADA-002` |
| `REQ-ADA-002` | `DES-ADA-002` | `TASK-ADA-002`, `TASK-ADA-003`, `TASK-ADA-008` | `TEST-ADA-003`, `TEST-ADA-004`, `TEST-ADA-005`, `TEST-ADA-006`, `TEST-ADA-007` |
| `REQ-ADA-003` | `DES-ADA-003` | `TASK-ADA-001`, `TASK-ADA-008` | `TEST-ADA-008`, `TEST-ADA-009`, `TEST-ADA-010` |
| `REQ-ADA-004` | `DES-ADA-004` | `TASK-ADA-005` | `TEST-ADA-011`, `TEST-ADA-012`, `TEST-ADA-013` |
| `REQ-ADA-005` | `DES-ADA-005` | `TASK-ADA-004` | `TEST-ADA-014`, `TEST-ADA-015`, `TEST-ADA-016`, `TEST-ADA-017`, `TEST-ADA-018` |
| `REQ-ADA-006` | `DES-ADA-006` | `TASK-ADA-006` | `TEST-ADA-019`, `TEST-ADA-020`, `TEST-ADA-021` |
| `REQ-ADA-007` | `DES-ADA-007` | `TASK-ADA-007`, `TASK-ADA-008` | `TEST-ADA-022`, `TEST-ADA-023`, `TEST-ADA-024` |
| `REQ-ADA-008` | `DES-ADA-008` | `TASK-ADA-008`, `TASK-ADA-009`, `TASK-ADA-010`, `TASK-ADA-011` | `TEST-ADA-025`, `TEST-ADA-026`, `TEST-ADA-027`, `TEST-ADA-028`, `TEST-ADA-029`, `TEST-ADA-030` |
| `REQ-ADA-009` | `DES-ADA-009` | `TASK-ADA-008`, `TASK-ADA-012` | `TEST-ADA-031`, `TEST-ADA-032`, `TEST-ADA-033` |

## Completion Rules

- P0 可独立交付：`TASK-ADA-001` 至 `TASK-ADA-008` 完成并通过验收后，P0 可标记 implemented。
- P1 不得阻塞 P0，但 P1 任务开始前必须确认对应测试策略。
- 任何新增顶层命令必须更新 Pi schema 和 README。
- 任何新增错误码必须同步 `androidtestclii-core` 兼容说明或本 spec 的 compatibility。
