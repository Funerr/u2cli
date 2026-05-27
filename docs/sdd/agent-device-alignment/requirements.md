# Agent Device Alignment Requirements

- **Spec ID**：`agent-device-alignment`
- **Status**：`Review`
- **Owner**：`u2cli maintainers`
- **Last Updated**：`2026-05-26`
- **Source**：`PRD-agent-device-alignment.md`

## Context

`u2cli` 已具备以 `uiautomator2` 为执行内核的 Android Agent CLI，包括核心子命令树、JSON 契约、错误码、per-serial 串行锁与 snapshot 能力。

在多 Agent 接入中，`agent-device` 风格 CLI 对 Agent 更友好：扁平顶层命令、`@eN` 短引用、snapshot 缓存、session 自动 hydrate、结构化诊断和高频组合命令。本 spec 定义 u2cli 对齐这些体验的需求。

## Goals

- `REQ-ADA-001`：降低 Agent 单步调用 token 和命令复杂度。
- `REQ-ADA-002`：提供 snapshot ref 系统，使 `@eN` 可跨命令消费。
- `REQ-ADA-003`：提供本地 session hydrate，减少重复传 `--serial`。
- `REQ-ADA-004`：提供顶层 agent 风格命令，并与现有子命令树并存。
- `REQ-ADA-005`：扩展 selector 位置参数语法。
- `REQ-ADA-006`：为 `wait/find/is/alert` 提供结构化诊断字段。
- `REQ-ADA-007`：提供 `batch` 串行组合命令。
- `REQ-ADA-008`：补齐 P1 设备管理和交互能力。
- `REQ-ADA-009`：不破坏 `u2cli-core` 中已有 JSON 契约和旧命令行为。

## Non-Goals

- 不支持 HarmonyOS、iOS、云设备。
- 不引入 `record/replay/test` 资产体系。
- 不引入 React Native、DevTools、Metro。
- 不暴露任意 shell 或 Python eval。
- 不实现 PNG 像素 diff、screenshot overlay-refs、network 线索解析。
- 不替换 `uiautomator2` 执行语义。
- 不实现多 Agent 多设备并发 session。

## Requirements

### `REQ-ADA-001`：降低 Agent 调用成本

**Statement**：在不破坏现有 JSON 契约的前提下，新增更短、更扁平的命令入口，使常见 Agent 操作不需要重复构造长 selector 或多层子命令。

**Acceptance**：

- `TEST-ADA-001`：`back/home/open/close/snapshot/click/fill/get/wait/batch` 等 P0 命令可在顶层调用。
- `TEST-ADA-002`：旧命令仍可按原方式调用。

### `REQ-ADA-002`：Snapshot ref 系统

**Statement**：`snapshot -i` 或 compact snapshot 返回节点时必须附加 `ref: "e<N>"`，并将完整 `refMap` 写入本地 session，使后续 `click @eN`、`fill @eN`、`get text @eN` 可消费最近 snapshot。

**Acceptance**：

- `TEST-ADA-003`：snapshot 输出节点包含稳定格式 `ref`。
- `TEST-ADA-004`：`refMap` 写入 session，不完整写入 stdout。
- `TEST-ADA-005`：`click @eN` 和 `fill @eN` 优先走 bounds center fast path。
- `TEST-ADA-006`：不存在的 ref 返回 `SNAPSHOT_REF_NOT_FOUND`。
- `TEST-ADA-007`：无可执行 selector 或 bounds 的 ref 返回 `SNAPSHOT_REF_INVALID`。

### `REQ-ADA-003`：Session hydrate

**Statement**：CLI 启动时如果未显式传入 `--serial`，应从本地 session 注入最近有效 serial；成功命令在 serial 已知时更新 session。

**Acceptance**：

- `TEST-ADA-008`：`connect --serial X` 后，后续命令无需显式 `--serial`。
- `TEST-ADA-009`：显式 `--serial` 始终覆盖 session。
- `TEST-ADA-010`：session 中设备不可用时返回或标记 `SESSION_STALE`。

### `REQ-ADA-004`：顶层 agent 命令

**Statement**：新增顶层命令，并与现有 `device/app/screen/element/input/toast/watcher/session/pi` 子命令树并存。顶层命令复用核心执行语义。

**Acceptance**：

- `TEST-ADA-011`：P0 顶层命令成功路径可用。
- `TEST-ADA-012`：P0 顶层命令失败路径返回标准 JSON。
- `TEST-ADA-013`：顶层命令的 `command` 字段使用扁平命名，如 `click`、`fill`、`snapshot`、`batch`。

P0 顶层命令范围：

```text
apps, appstate, open, close, back, home, app-switcher, rotate,
screenshot, snapshot, click, press, longpress, swipe, scroll,
fill, type, focus, get, find, is, wait, clipboard, batch,
connect, disconnect, connection status
```

### `REQ-ADA-005`：Selector 位置参数

**Statement**：新增位置参数 selector 语法，并与现有长选项 selector 并存。

**Acceptance**：

- `TEST-ADA-014`：`text=登录` 等价于 `Selector(text="登录")`。
- `TEST-ADA-015`：`id=login` 和 `testid=login` 映射到 `resourceId`。
- `TEST-ADA-016`：`desc=...` 映射到 `description`。
- `TEST-ADA-017`：`@eN` 从 session `refMap` 解析。
- `TEST-ADA-018`：带空格文本支持引号包裹。

### `REQ-ADA-006`：结构化诊断字段

**Statement**：`wait/find/is/alert` 命令应统一返回 `selector`、`state`、`timeoutMs`、`attempts`、`durationMs`、`matchedCount`、`selectedIndex` 等诊断字段。

**Acceptance**：

- `TEST-ADA-019`：`wait text 首页 3000` 返回 `attempts/durationMs/matchedCount`。
- `TEST-ADA-020`：`find --first` 多命中时返回 `selectedIndex=0`。
- `TEST-ADA-021`：未指定 `--first/--last/index` 且多命中时返回 `ELEMENT_AMBIGUOUS`。

### `REQ-ADA-007`：Batch 命令

**Statement**：`batch --steps '<json>'` 串行执行多步命令；失败时保留已执行步骤和失败 step 的结构化错误。

**Acceptance**：

- `TEST-ADA-022`：step2 失败时，stdout 顶层 `success=false`，且保留 step1 数据。
- `TEST-ADA-023`：失败 step 包含标准错误结构。
- `TEST-ADA-024`：`--out` 写完整结果为 artifact，stdout 仍是合法 JSON。

### `REQ-ADA-008`：P1 能力补齐

**Statement**：在 P0 完成后补齐常用设备管理和交互能力，包括 alert、scroll 增强、点击修饰器、appstate/apps 字段增强、reinstall、install-from-source、keyboard、connect/disconnect/connection status。

**Acceptance**：

- `TEST-ADA-025`：`alert accept` 可命中中英文确认按钮。
- `TEST-ADA-026`：`scroll down/top/bottom/--pixels` 可用。
- `TEST-ADA-027`：`click @eN --double-tap/--hold-ms/--count/--interval-ms/--jitter-px` 表现稳定。
- `TEST-ADA-028`：`appstate`、`apps --kind all` 返回增强字段。
- `TEST-ADA-029`：`keyboard status/hide/show` 返回结构化状态。
- `TEST-ADA-030`：远程 `connect/disconnect/connection status` 可用。

### `REQ-ADA-009`：兼容核心契约

**Statement**：新增能力不得破坏 `u2cli-core` 中定义的 stdout JSON、stderr、退出码、错误码、artifact 和旧命令兼容性。

**Acceptance**：

- `TEST-ADA-031`：旧命令 `u2cli element click --text 登录 --json` 行为不变。
- `TEST-ADA-032`：所有新增命令 stdout 仍是单个 JSON 对象。
- `TEST-ADA-033`：新增错误码只扩展集合，不改变旧错误码语义。

## Compatibility

- stdout JSON：沿用 `u2cli-core` 顶层字段。
- stderr 日志：沿用核心日志约定。
- 退出码：沿用核心退出码。
- 错误码：新增 `SNAPSHOT_REF_NOT_FOUND`、`SNAPSHOT_REF_INVALID`、`SESSION_STALE`、`ALERT_NOT_FOUND`、`BATCH_STEP_FAILED`。
- Pi schema：新增顶层命令后必须更新 Pi schema。
- 旧命令兼容：现有子命令树保持不变。

## Open Questions

- `connect --address` 与 `connect --serial` 是否拆分为两个子模式。
- `@eN` 过期策略是否需要 TTL，当前只要求 capturedAt 诊断。
- P1 的 `install-from-source` 是否允许 URL 下载，若允许需补充安全策略。
