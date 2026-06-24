# Agent Device Catchup Requirements

- **Spec ID**：`agent-device-catchup`
- **Status**：`Implemented`
- **Owner**：`androidtestclii maintainers`
- **Last Updated**：`2026-05-28`
- **Source**：`/Users/funer/code/DeviceTestCLI/README.md`、`/Users/funer/code/DeviceTestCLI/specs/*`、`docs/sdd/agent-device-alignment/`

## Context

`agent-device-alignment` 已覆盖 AndroidTestClii 对齐 agent-device 风格的 P0/P1 命令面，包括顶层短命令、snapshot ref、session hydrate、结构化诊断、batch、alert、keyboard、connect、reinstall 等。`androidtestclii` 作为历史包名和兼容命令名保留，但 catchup 工作应以 AndroidTestClii 能力面为目标。

本 spec 记录进一步追赶 `DeviceTestCLI` / agent-device 风格参考实现时仍存在的能力差距。它不重复 `agent-device-alignment` 中已有 P0/P1 任务，而是把剩余高级能力拆成可排期的 catchup backlog。

## Current Coverage

以下能力已在 `agent-device-alignment` 范围内，不在本 spec 重复拆解：

- 顶层 agent 风格入口：`apps/appstate/open/close/back/home/app-switcher/rotate/screenshot/snapshot/click/press/longpress/swipe/scroll/fill/type/focus/get/find/is/wait/alert/clipboard/keyboard/reinstall/install-from-source/batch/connect/disconnect/connection`。
- `@eN` snapshot ref、refMap session 缓存、bounds fast path。
- selector 位置参数：`text=...`、`id=...`、`testid=...`、`class=...`、`desc=...`、裸文本和 `@eN`。
- P1 alert、scroll、click 修饰器、apps/appstate 增强、keyboard、远程连接。

## Remaining Gaps

### P0：Agent 可观测性和可信诊断

- `REQ-ADC-001`：每条命令披露实际 capability layer 和 fallback metadata。
- `REQ-ADC-002`：提供 runtime/session 状态查询和清理，区分基础 ADB、snapshot helper、持久监听和最近 snapshot 状态。
- `REQ-ADC-003`：补齐失败阶段、恢复建议和 busy/empty/degraded snapshot 诊断。

### P1：Snapshot 和视觉诊断

- `REQ-ADC-004`：提供显式 `snapshot capture --full` 语义，区分 compact/default 与 full，不把 compact 未命中当作不存在证明。
- `REQ-ADC-005`：提供 `diff screenshot`、`diff snapshot` 和 `screenshot --overlay-refs`。

### P1：日志、性能和系统诊断

- `REQ-ADC-006`：提供结构化 `logs start/stop/clear/mark/path/doctor`，支持 marker 后过滤和 artifact。
- `REQ-ADC-007`：提供 `trace start/stop` 采集，并把结果作为 artifact 返回。
- `REQ-ADC-008`：提供 `perf collect` 或顶层 `perf`，至少覆盖 procfs 内存/CPU 快照和可选进程指标。
- `REQ-ADC-009`：提供 `network` 顶层诊断，支持从 logcat 中提取网络线索并可输出 summary。

### P1：系统控制和 App 事件

- `REQ-ADC-010`：提供 `settings` 顶层命令，支持 animations、wifi、airplane、permission 的写入和读回验证。
- `REQ-ADC-011`：提供 `push` 和 `trigger-app-event`，封装 broadcast、deep link、intent 参数和输出解析。
- `REQ-ADC-012`：提供 `boot`、`ensure-simulator` 和更完整的 connection/session stale 校验。

### P2：脚本化执行和测试资产

- `REQ-ADC-013`：提供 `.ad` 或等价 replay 脚本执行能力，支持 context、env、变量、引号参数和串行命令执行。
- `REQ-ADC-014`：提供 replay healing，至少支持基于最近 snapshot `refMap` 的 selector/ref 修复和 `--replay-update`。
- `REQ-ADC-015`：提供 `test` 命令，支持批量脚本、失败汇总、JUnit report artifact。
- `REQ-ADC-016`：支持 `# expect-screenshot` 或等价视觉断言，复用 screenshot diff。

### P2：高级手势和录制

- `REQ-ADC-017`：提供 `gesture pan/fling/replay`、`screen multi-touch`、`screen pinch/expand`，对真多指不可用场景返回结构化 unavailable 和 fallback 建议。
- `REQ-ADC-018`：提供 `gesture record` 或兼容占位，至少返回 replay JSON 模板和 unavailable 诊断。
- `REQ-ADC-019`：完善 `record start/stop` 顶层录屏控制，与现有 `screen record` 区分后台 session 化录制。

### P3：平台和生态扩展

- `REQ-ADC-020`：评估 HarmonyOS 支持边界，若不实现则返回稳定 unsupported，而不是伪装能力。
- `REQ-ADC-021`：对 React Native、React DevTools、云设备、daemon 等非当前范围能力提供稳定 unsupported 或占位结果。

## Non-Goals

- 本 spec 不要求移除现有 `uiautomator2` 路径；部分场景继续基于 u2 是兼容和稳定性选择。
- 本 spec 不要求完全复制 DeviceTestCLI 的 Android runtime 架构。
- 本 spec 不要求立即支持 HarmonyOS；只要求明确边界和稳定 unsupported。
- 本 spec 不替代 `agent-device-alignment` P0/P1 任务。

## Compatibility

- stdout JSON：沿用 `androidtestclii-core` 单对象契约。
- stderr 日志：仅用于诊断。
- 退出码：沿用现有退出码；如新增 unsupported 分类，需要单独更新 `androidtestclii-core`。
- 错误码：新增错误码必须在本 spec 和 `androidtestclii-core` compatibility 中登记。
- Pi schema：新增顶层命令必须同步 Pi tool schema。
- 旧命令兼容：不得破坏现有子命令树和 agent alignment 命令。

## Evidence

- `DeviceTestCLI/README.md` 列出 agent-device 风格公共 surface：`record`、`trace`、`logs`、`network`、`settings`、`push`、`trigger-app-event`、`replay`、`test`、`session list`、`diff screenshot/snapshot`、`screenshot --overlay-refs`。
- `DeviceTestCLI/specs/001-align-uiautomation-runtime/spec.md` 要求 capability layer metadata、runtime/session 状态、低层能力零部署、高级能力 fallback、失败阶段和恢复建议。
- `DeviceTestCLI/specs/002-snapshot-full-elements/spec.md` 要求 compact/default 与 full snapshot 并存，full 才能证明目标不存在，compact 未命中不得作为不存在证明。
- `DeviceTestCLI/src/devicetestcli/cli/capability_map.py` 给出命令到 capability layer 的参考映射。

## Open Questions

- 是否为 AndroidTestClii 引入统一 `metadata` 顶层字段，还是把 capability metadata 放入 `data.metadata` 以保持现有顶层字段不变。
- `device shell` 当前是受限 shell；追赶 `shell run` 任意命令是否应作为显式非默认能力，需单独安全评审。
- `install-from-source` 是否允许远程 URL 下载，若允许需要校验下载路径、大小、hash 和超时。
