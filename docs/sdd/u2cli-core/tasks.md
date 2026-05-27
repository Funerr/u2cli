# Android CLI Core Tasks

- **Spec ID**：`u2cli-core`
- **Status**：`Implemented`
- **Owner**：`u2cli maintainers`
- **Last Updated**：`2026-05-27`
- **Source Design**：`./design.md`

## Task List

- [x] `TASK-CORE-001`：建立 CLI 骨架和统一 JSON 结果模型
  - Covers：`REQ-CORE-001`
  - Design：`DES-CORE-001`
  - Verification：`TEST-CORE-001`、`TEST-CORE-002`

- [x] `TASK-CORE-002`：实现核心命令族
  - Covers：`REQ-CORE-002`
  - Design：`DES-CORE-002`
  - Verification：`TEST-CORE-003`、`TEST-CORE-004`

- [x] `TASK-CORE-003`：实现 selector 模型和歧义策略
  - Covers：`REQ-CORE-003`
  - Design：`DES-CORE-003`
  - Verification：`TEST-CORE-005`、`TEST-CORE-006`、`TEST-CORE-007`

- [x] `TASK-CORE-004`：实现 per-serial 文件锁和 timeout 包装
  - Covers：`REQ-CORE-004`
  - Design：`DES-CORE-004`
  - Verification：`TEST-CORE-008`、`TEST-CORE-009`

- [x] `TASK-CORE-005`：实现错误码、异常映射和退出码
  - Covers：`REQ-CORE-005`
  - Design：`DES-CORE-005`
  - Verification：`TEST-CORE-010`、`TEST-CORE-011`

- [x] `TASK-CORE-006`：实现截图、录屏和文件 artifact 返回
  - Covers：`REQ-CORE-006`
  - Design：`DES-CORE-006`
  - Verification：`TEST-CORE-012`、`TEST-CORE-013`

- [x] `TASK-CORE-007`：实现 Pi schema 导出和 extension 同步路径
  - Covers：`REQ-CORE-007`
  - Design：`DES-CORE-007`
  - Verification：`TEST-CORE-014`、`TEST-CORE-015`

## Traceability Matrix

| Requirement | Design | Task | Verification |
|---|---|---|---|
| `REQ-CORE-001` | `DES-CORE-001` | `TASK-CORE-001` | `TEST-CORE-001`, `TEST-CORE-002` |
| `REQ-CORE-002` | `DES-CORE-002` | `TASK-CORE-002` | `TEST-CORE-003`, `TEST-CORE-004` |
| `REQ-CORE-003` | `DES-CORE-003` | `TASK-CORE-003` | `TEST-CORE-005`, `TEST-CORE-006`, `TEST-CORE-007` |
| `REQ-CORE-004` | `DES-CORE-004` | `TASK-CORE-004` | `TEST-CORE-008`, `TEST-CORE-009` |
| `REQ-CORE-005` | `DES-CORE-005` | `TASK-CORE-005` | `TEST-CORE-010`, `TEST-CORE-011` |
| `REQ-CORE-006` | `DES-CORE-006` | `TASK-CORE-006` | `TEST-CORE-012`, `TEST-CORE-013` |
| `REQ-CORE-007` | `DES-CORE-007` | `TASK-CORE-007` | `TEST-CORE-014`, `TEST-CORE-015` |

## Completion Rules

- 对核心命令的行为变更必须更新 `requirements.md` 和本任务矩阵。
- 对错误码、JSON 字段、退出码的变更必须显式说明兼容策略。
- 新增命令必须同步 README、Pi schema 和相应测试。
