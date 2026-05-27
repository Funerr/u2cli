# Agent Device Catchup Tasks

- **Spec ID**：`agent-device-catchup`
- **Status**：`Draft`
- **Owner**：`u2cli maintainers`
- **Last Updated**：`2026-05-27`
- **Source Design**：`./design.md`

## Task List

### P0：先补可信诊断

- [ ] `TASK-ADC-001`：建立 capability registry 和命令到能力层映射
  - Covers：`REQ-ADC-001`
  - Design：`DES-ADC-001`
  - Verification：`TEST-ADC-001`

- [ ] `TASK-ADC-002`：为现有核心命令结果补充 `data.metadata.capabilityLayer`
  - Covers：`REQ-ADC-001`
  - Design：`DES-ADC-001`
  - Verification：`TEST-ADC-002`

- [ ] `TASK-ADC-003`：补充 fallback/degraded/failureStage/recoveryHint 字段模型
  - Covers：`REQ-ADC-001`、`REQ-ADC-003`
  - Design：`DES-ADC-001`
  - Verification：`TEST-ADC-003`

- [ ] `TASK-ADC-004`：新增 `runtime status`、`runtime clear`、`session status`、`session list`
  - Covers：`REQ-ADC-002`
  - Design：`DES-ADC-001`
  - Verification：`TEST-ADC-004`

### P1：补齐 snapshot 和视觉诊断

- [ ] `TASK-ADC-005`：新增 `snapshot capture --full` 命令和 full snapshot 数据契约
  - Covers：`REQ-ADC-004`
  - Design：`DES-ADC-002`
  - Verification：`TEST-ADC-005`

- [ ] `TASK-ADC-006`：为 compact/default snapshot 明确 `canProveAbsence=false`
  - Covers：`REQ-ADC-004`
  - Design：`DES-ADC-002`
  - Verification：`TEST-ADC-006`

- [ ] `TASK-ADC-007`：实现 `diff screenshot`，输出 diffRatio、changedPixels、passed 和 overlay artifact
  - Covers：`REQ-ADC-005`
  - Design：`DES-ADC-002`
  - Verification：`TEST-ADC-007`

- [ ] `TASK-ADC-008`：实现 `diff snapshot` 节点签名对比
  - Covers：`REQ-ADC-005`
  - Design：`DES-ADC-002`
  - Verification：`TEST-ADC-008`

- [ ] `TASK-ADC-009`：实现 `screenshot --overlay-refs`
  - Covers：`REQ-ADC-005`
  - Design：`DES-ADC-002`
  - Verification：`TEST-ADC-009`

### P1：补齐日志、Trace、Perf、Network

- [ ] `TASK-ADC-010`：实现 `logs start/stop/clear/mark/path/doctor`
  - Covers：`REQ-ADC-006`
  - Design：`DES-ADC-003`
  - Verification：`TEST-ADC-010`

- [ ] `TASK-ADC-011`：实现 marker 后日志过滤和 logs artifact
  - Covers：`REQ-ADC-006`
  - Design：`DES-ADC-003`
  - Verification：`TEST-ADC-011`

- [ ] `TASK-ADC-012`：实现 `trace start/stop` 和 trace artifact
  - Covers：`REQ-ADC-007`
  - Design：`DES-ADC-003`
  - Verification：`TEST-ADC-012`

- [ ] `TASK-ADC-013`：实现 `perf collect` procfs 快照
  - Covers：`REQ-ADC-008`
  - Design：`DES-ADC-003`
  - Verification：`TEST-ADC-013`

- [ ] `TASK-ADC-014`：实现顶层 `network` summary，从 logcat/log artifact 提取网络线索
  - Covers：`REQ-ADC-009`
  - Design：`DES-ADC-003`
  - Verification：`TEST-ADC-014`

### P1：补齐系统控制和 App 事件

- [ ] `TASK-ADC-015`：实现 `settings animations/wifi/airplane/permission` 写入和读回验证
  - Covers：`REQ-ADC-010`
  - Design：`DES-ADC-004`
  - Verification：`TEST-ADC-015`

- [ ] `TASK-ADC-016`：实现 `push` broadcast/deep link 封装和结果解析
  - Covers：`REQ-ADC-011`
  - Design：`DES-ADC-004`
  - Verification：`TEST-ADC-016`

- [ ] `TASK-ADC-017`：实现 `trigger-app-event` intent 封装和 `am start` 输出解析
  - Covers：`REQ-ADC-011`
  - Design：`DES-ADC-004`
  - Verification：`TEST-ADC-017`

- [ ] `TASK-ADC-018`：实现 `boot`、`ensure-simulator` 和 session stale 校验增强
  - Covers：`REQ-ADC-012`
  - Design：`DES-ADC-004`
  - Verification：`TEST-ADC-018`

### P2：补齐 replay/test

- [ ] `TASK-ADC-019`：定义 `.ad` replay 脚本格式和 parser
  - Covers：`REQ-ADC-013`
  - Design：`DES-ADC-005`
  - Verification：`TEST-ADC-019`

- [ ] `TASK-ADC-020`：实现 `replay` 串行执行、context/env、变量和引号参数
  - Covers：`REQ-ADC-013`
  - Design：`DES-ADC-005`
  - Verification：`TEST-ADC-020`

- [ ] `TASK-ADC-021`：实现 replay selector/ref healing 和 `--replay-update`
  - Covers：`REQ-ADC-014`
  - Design：`DES-ADC-005`
  - Verification：`TEST-ADC-021`

- [ ] `TASK-ADC-022`：实现 `test` 批量 replay、失败汇总和 JUnit artifact
  - Covers：`REQ-ADC-015`
  - Design：`DES-ADC-005`
  - Verification：`TEST-ADC-022`

- [ ] `TASK-ADC-023`：实现 `# expect-screenshot` 视觉断言
  - Covers：`REQ-ADC-016`
  - Design：`DES-ADC-005`
  - Verification：`TEST-ADC-023`

### P2：补齐高级手势和录制

- [ ] `TASK-ADC-024`：实现 `gesture pan/fling/replay` 单指 fast path
  - Covers：`REQ-ADC-017`
  - Design：`DES-ADC-006`
  - Verification：`TEST-ADC-024`

- [ ] `TASK-ADC-025`：实现 `screen multi-touch/pinch/expand` structured unavailable 和 fallback 建议
  - Covers：`REQ-ADC-017`
  - Design：`DES-ADC-006`
  - Verification：`TEST-ADC-025`

- [ ] `TASK-ADC-026`：实现 `gesture record` 占位或录制能力，至少返回 replay JSON 模板
  - Covers：`REQ-ADC-018`
  - Design：`DES-ADC-006`
  - Verification：`TEST-ADC-026`

- [ ] `TASK-ADC-027`：实现顶层 `record start/stop` session 化后台录屏
  - Covers：`REQ-ADC-019`
  - Design：`DES-ADC-006`
  - Verification：`TEST-ADC-027`

### P3：明确平台和生态边界

- [ ] `TASK-ADC-028`：为 HarmonyOS 相关入口返回稳定 unsupported 或制定独立平台 spec
  - Covers：`REQ-ADC-020`
  - Design：`DES-ADC-007`
  - Verification：`TEST-ADC-028`

- [ ] `TASK-ADC-029`：为 React Native、React DevTools、云设备、daemon 等入口返回稳定 unsupported
  - Covers：`REQ-ADC-021`
  - Design：`DES-ADC-007`
  - Verification：`TEST-ADC-029`

- [ ] `TASK-ADC-030`：同步 README、Pi schema 和 SDD 追踪矩阵
  - Covers：`REQ-ADC-001` 至 `REQ-ADC-021`
  - Design：`DES-ADC-001` 至 `DES-ADC-007`
  - Verification：`TEST-ADC-030`

## Traceability Matrix

| Requirement | Design | Task | Verification |
|---|---|---|---|
| `REQ-ADC-001` | `DES-ADC-001` | `TASK-ADC-001`, `TASK-ADC-002`, `TASK-ADC-003` | `TEST-ADC-001`, `TEST-ADC-002`, `TEST-ADC-003` |
| `REQ-ADC-002` | `DES-ADC-001` | `TASK-ADC-004` | `TEST-ADC-004` |
| `REQ-ADC-003` | `DES-ADC-001` | `TASK-ADC-003` | `TEST-ADC-003` |
| `REQ-ADC-004` | `DES-ADC-002` | `TASK-ADC-005`, `TASK-ADC-006` | `TEST-ADC-005`, `TEST-ADC-006` |
| `REQ-ADC-005` | `DES-ADC-002` | `TASK-ADC-007`, `TASK-ADC-008`, `TASK-ADC-009` | `TEST-ADC-007`, `TEST-ADC-008`, `TEST-ADC-009` |
| `REQ-ADC-006` | `DES-ADC-003` | `TASK-ADC-010`, `TASK-ADC-011` | `TEST-ADC-010`, `TEST-ADC-011` |
| `REQ-ADC-007` | `DES-ADC-003` | `TASK-ADC-012` | `TEST-ADC-012` |
| `REQ-ADC-008` | `DES-ADC-003` | `TASK-ADC-013` | `TEST-ADC-013` |
| `REQ-ADC-009` | `DES-ADC-003` | `TASK-ADC-014` | `TEST-ADC-014` |
| `REQ-ADC-010` | `DES-ADC-004` | `TASK-ADC-015` | `TEST-ADC-015` |
| `REQ-ADC-011` | `DES-ADC-004` | `TASK-ADC-016`, `TASK-ADC-017` | `TEST-ADC-016`, `TEST-ADC-017` |
| `REQ-ADC-012` | `DES-ADC-004` | `TASK-ADC-018` | `TEST-ADC-018` |
| `REQ-ADC-013` | `DES-ADC-005` | `TASK-ADC-019`, `TASK-ADC-020` | `TEST-ADC-019`, `TEST-ADC-020` |
| `REQ-ADC-014` | `DES-ADC-005` | `TASK-ADC-021` | `TEST-ADC-021` |
| `REQ-ADC-015` | `DES-ADC-005` | `TASK-ADC-022` | `TEST-ADC-022` |
| `REQ-ADC-016` | `DES-ADC-005` | `TASK-ADC-023` | `TEST-ADC-023` |
| `REQ-ADC-017` | `DES-ADC-006` | `TASK-ADC-024`, `TASK-ADC-025` | `TEST-ADC-024`, `TEST-ADC-025` |
| `REQ-ADC-018` | `DES-ADC-006` | `TASK-ADC-026` | `TEST-ADC-026` |
| `REQ-ADC-019` | `DES-ADC-006` | `TASK-ADC-027` | `TEST-ADC-027` |
| `REQ-ADC-020` | `DES-ADC-007` | `TASK-ADC-028` | `TEST-ADC-028` |
| `REQ-ADC-021` | `DES-ADC-007` | `TASK-ADC-029` | `TEST-ADC-029` |

## Suggested Execution Order

1. `TASK-ADC-001` 至 `TASK-ADC-004`：先补可观测性，否则后续能力难以验证。
2. `TASK-ADC-005` 至 `TASK-ADC-009`：补 snapshot 可信语义和视觉诊断。
3. `TASK-ADC-010` 至 `TASK-ADC-018`：补日志、trace、perf、settings、push 等高频诊断能力。
4. `TASK-ADC-019` 至 `TASK-ADC-027`：补 replay/test/gesture/record。
5. `TASK-ADC-028` 至 `TASK-ADC-030`：补 unsupported 边界和文档/schema 同步。

## Completion Rules

- 新增顶层命令必须同步 README 和 Pi schema。
- 新增错误码必须同步 `u2cli-core` 或本 spec compatibility。
- 未能真实实现的能力必须返回 structured unsupported，不得静默成功。
- full snapshot 不完整时必须返回 `complete=false`，不得证明目标不存在。
