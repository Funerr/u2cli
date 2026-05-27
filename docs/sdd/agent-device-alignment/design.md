# Agent Device Alignment Design

- **Spec ID**：`agent-device-alignment`
- **Status**：`Review`
- **Owner**：`u2cli maintainers`
- **Last Updated**：`2026-05-27`
- **Source Requirements**：`./requirements.md`

## Design Summary

本 spec 在现有 `u2cli-core` 子命令树之上新增 agent 风格入口层。推荐入口名为 `android-cli`，`u2cli` 作为兼容入口保留。顶层命令尽量复用现有 handler、selector、锁、timeout、错误模型和 JSON 渲染，不复制 Android 执行语义。新增能力集中在 session store、snapshot ref、target parser、顶层命令适配、诊断字段和 batch 编排。

## Requirement Mapping

| Requirement | Design Section |
|---|---|
| `REQ-ADA-001` | `DES-ADA-001` |
| `REQ-ADA-002` | `DES-ADA-002` |
| `REQ-ADA-003` | `DES-ADA-003` |
| `REQ-ADA-004` | `DES-ADA-004` |
| `REQ-ADA-005` | `DES-ADA-005` |
| `REQ-ADA-006` | `DES-ADA-006` |
| `REQ-ADA-007` | `DES-ADA-007` |
| `REQ-ADA-008` | `DES-ADA-008` |
| `REQ-ADA-009` | `DES-ADA-009` |

## `DES-ADA-001`：Agent 风格入口层

**Covers**：`REQ-ADA-001`

新增入口层只负责把短命令和位置参数转换为现有核心语义。示例：

```text
android-cli back             -> input press --key back
android-cli open <package>   -> app start / app launch
android-cli snapshot -i      -> screen dump --compact + ref
android-cli click @e3        -> ref target -> bounds tap or selector click
```

设计原则：

- 旧子命令和 `u2cli` 兼容入口保持原样。
- 顶层命令返回同一 JSON result 模型。
- 顶层命令的 `command` 字段使用扁平命名。

## `DES-ADA-002`：Snapshot ref 和 refMap

**Covers**：`REQ-ADA-002`

compact snapshot 输出节点增加 `ref: "e<N>"`。完整 refMap 写入 session，不直接进入 stdout。

`refMap` schema：

```json
{
  "@e3": {
    "selector": {"text": "登录", "resourceId": "com.example:id/login"},
    "bounds": {"left": 40, "top": 1200, "right": 720, "bottom": 1320},
    "text": "登录",
    "className": "Button",
    "resourceId": "com.example:id/login"
  }
}
```

消费规则：

- `click @eN`、`press @eN`、`longpress @eN` 优先用 bounds center。
- `fill @eN <text>` 先 tap bounds center，再走文本输入。
- `get text @eN` 可直接返回 cached text。
- ref 缺失返回 `SNAPSHOT_REF_NOT_FOUND`。
- ref 无 bounds 且无 selector 返回 `SNAPSHOT_REF_INVALID`。

## `DES-ADA-003`：Session store 和 hydrate

**Covers**：`REQ-ADA-003`

session 存储位置：

- macOS：`~/Library/Application Support/u2cli/session.json`。
- 其他环境：`${HOME}/.config/u2cli/session.json`。

字段：

```json
{
  "serial": "emulator-5554",
  "timeoutMs": 5000,
  "lastSnapshot": {
    "capturedAt": "2026-05-26T00:00:00Z",
    "refMap": {}
  },
  "updatedAt": "2026-05-26T00:00:00Z"
}
```

写入触发：

- `connect --serial X`。
- 任意成功命令在 serial 已知时更新 session。
- snapshot 成功时更新 `lastSnapshot`。

读取触发：

- CLI 启动时未显式传 `--serial`，从 session 注入。
- 显式 `--serial` 优先。

并发写入使用 filelock 和 atomic rename。

## `DES-ADA-004`：顶层命令注册

**Covers**：`REQ-ADA-004`

新增 `u2cli/agent/cli.py` 或等价模块注册顶层命令：

```text
apps, appstate, open, close, back, home, app-switcher, rotate,
screenshot, snapshot, click, press, longpress, swipe, scroll,
fill, type, focus, get, find, is, wait, clipboard, keyboard,
batch, connect, disconnect, connection status
```

顶层命令复用 `element/input/screen/app/device/session` 现有 handler 或 service 函数。

## `DES-ADA-005`：Target parser

**Covers**：`REQ-ADA-005`

新增 `selector.from_target(value: str)` 或等价解析函数。

支持语法：

```text
text=登录
id=login
testid=login
class=Button
description=...
desc=...
@e3
'text="带空格 文本"'
```

解析结果要么是 selector，要么是 ref target。后续命令根据 target 类型选择 bounds fast path、cached read 或设备查询。

## `DES-ADA-006`：结构化诊断

**Covers**：`REQ-ADA-006`

`wait/find/is/alert` 统一返回诊断字段：

```json
{
  "selector": {},
  "state": "exists",
  "timeoutMs": 3000,
  "attempts": 5,
  "durationMs": 2810,
  "matchedCount": 1,
  "selectedIndex": 0
}
```

`find --first` 多命中选择 `0`，`--last` 选择最后一个；未指定且多命中返回 `ELEMENT_AMBIGUOUS`。

## `DES-ADA-007`：Batch 编排

**Covers**：`REQ-ADA-007`

`batch` 输入为 steps JSON：

```json
[
  {"command": "back"},
  {"command": "snapshot", "flags": {"interactive": true}},
  {"command": "click", "args": ["@e3"]}
]
```

执行规则：

- 串行执行。
- 共用同一 session 和 device context。
- 任一步失败则停止后续步骤。
- 顶层返回 `success=false`、`failed` step index、`steps` 明细。
- `--out` 写完整结果并作为 artifact 返回。

## `DES-ADA-008`：P1 能力

**Covers**：`REQ-ADA-008`

P1 设计按独立小模块接入：

- `alert`：候选按钮文本表，中英文 role 映射。
- `scroll`：方向、top、bottom、pixels 统一成 swipe 或 scroll helper。
- click 修饰器：`double-tap`、`hold-ms`、`count`、`interval-ms`、`jitter-px` 在公共 gesture helper 实现。
- `appstate/apps`：复用 app 模块并补齐 `source/system` 字段。
- `keyboard`：通过 adb/u2 能力查询或控制输入法状态。
- `connect/disconnect/connection status`：封装 adb connect/disconnect 与 session 更新。

## `DES-ADA-009`：兼容策略

**Covers**：`REQ-ADA-009`

兼容策略：

- 不删除、不重命名旧子命令。
- 不改变旧命令 JSON 字段语义。
- 新增错误码只作为扩展。
- 新增顶层命令使用现有 JSON result 渲染。
- Pi schema 在 Phase E 同步。

## Data Contracts

新增错误码：

```text
SNAPSHOT_REF_NOT_FOUND
SNAPSHOT_REF_INVALID
SESSION_STALE
ALERT_NOT_FOUND
BATCH_STEP_FAILED
```

batch 返回概要：

```json
{
  "success": false,
  "command": "batch",
  "serial": "emulator-5554",
  "via": "uiautomator2",
  "data": {
    "steps": [],
    "failed": 1,
    "total": 3
  },
  "artifacts": [],
  "durationMs": 1000
}
```

## Testing Strategy

- P0 顶层命令每个至少 1 成功 + 1 失败。
- target parser 覆盖 selector 和 ref 双路径。
- snapshot -> click @eN -> fill @eN 全链路使用 mock 测试。
- batch 覆盖全部成功、某步失败、非法 steps JSON、`--out` artifact。
- 旧命令兼容使用回归测试覆盖。

## Risks

- Snapshot ref 在 UI 抖动后失效：refMap 包含 `capturedAt`，失败时引导重新 snapshot。
- Session 文件并发写入：使用 filelock 和 atomic rename。
- 顶层位置参数和 shell 引号交互复杂：文档推荐显式引号，解析层兼容常见裸值。
- P1 URL 安装有供应链风险：若实现 URL 下载，需要单独补充安全策略。
