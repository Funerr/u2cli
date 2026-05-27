# Android CLI Core Requirements

- **Spec ID**：`u2cli-core`
- **Status**：`Implemented`
- **Owner**：`u2cli maintainers`
- **Last Updated**：`2026-05-27`
- **Source**：`PLAN.md`、`README.md`

## Context

Android CLI 是面向 Agent / Pi tool 的 Android 自动化 CLI。对外推荐入口是 `android-cli`；`u2cli` 保留为 Python 包名、源码目录名、历史 spec 名和兼容命令名。

核心目标是把常用 Android 设备操作封装为稳定、可测试、适合 Agent / Pi tool 调用的命令接口。部分元素操作、watcher 和 Toast 场景仍使用 `uiautomator2`，但项目定位不是 u2 wrapper；ADB、snapshot helper、JAR snapshot 等后端可以按能力需要并存。

本 spec 固化已存在的核心 CLI 契约。后续对现有命令面、JSON 返回、错误码、selector、锁、timeout、Pi schema 的行为改动，都应先更新本 spec。

## Goals

- `REQ-CORE-001`：提供面向机器调用的稳定 CLI 输出契约。
- `REQ-CORE-002`：提供 Android 设备、App、屏幕、元素、输入、Toast、Watcher、Session、Pi schema 等核心命令族。
- `REQ-CORE-003`：提供结构化 selector，并对多匹配和非法输入给出稳定行为。
- `REQ-CORE-004`：为变更型命令提供按设备串行锁和 timeout 保护。
- `REQ-CORE-005`：提供稳定错误码和退出码，便于上层 Agent / Pi tool 恢复与诊断。
- `REQ-CORE-006`：文件产物必须通过 artifact 路径显式返回，不内联大体积数据。
- `REQ-CORE-007`：Pi tool schema 与 CLI 契约保持同源或可追踪同步。

## Non-Goals

- 不负责测试用例规划和最终通过/失败判定。
- 不负责 record/replay/test 资产治理。
- 不提供跨平台抽象。
- 不暴露任意 Python eval 能力。
- 不暴露任意 shell 脚本执行能力。
- 不负责云设备租赁或多 Agent 调度。

## Requirements

### `REQ-CORE-001`：机器可解析输出

**Statement**：每条命令的 stdout 必须只输出一个 JSON 对象；stderr 只用于日志和诊断。

**Acceptance**：

- `TEST-CORE-001`：所有 CLI 命令成功和失败路径的 stdout 都能被解析为单个 JSON 对象。
- `TEST-CORE-002`：调试、诊断和日志不会写入 stdout。

### `REQ-CORE-002`：核心命令族

**Statement**：CLI 应提供以下命令族：`doctor/devices/device/app/screen/element/input/toast/watcher/session/pi`，覆盖设备发现、App 生命周期、屏幕观察、元素查询和操作、输入手势、Toast、Watcher、Session 能力探测和 Pi schema 导出。

**Acceptance**：

- `TEST-CORE-003`：`android-cli --help` 可发现核心命令族，兼容入口 `u2cli --help` 行为保持可用。
- `TEST-CORE-004`：每个核心命令族至少有成功路径和失败路径测试。

### `REQ-CORE-003`：Selector 契约

**Statement**：元素命令必须通过结构化 selector 输入，支持 `text`、`textContains`、`resourceId`、`description`、`descriptionContains`、`className`、`xpath`、`index`。非法 selector 返回 `INVALID_ARGUMENT`；变更型元素命令默认要求唯一命中。

**Acceptance**：

- `TEST-CORE-005`：空 selector、`xpath` 与普通字段混用等非法输入返回 `INVALID_ARGUMENT`。
- `TEST-CORE-006`：未传 `index` 且多命中时，变更型元素命令返回 `ELEMENT_AMBIGUOUS`。
- `TEST-CORE-007`：显式 `index` 可选择第 N 个匹配元素，越界返回稳定错误。

### `REQ-CORE-004`：并发和 timeout

**Statement**：变更型命令必须按设备 serial 串行加锁；所有设备交互应受 timeout 预算约束。

**Acceptance**：

- `TEST-CORE-008`：同一 serial 的变更型命令会竞争同一文件锁。
- `TEST-CORE-009`：锁等待或设备调用超时返回 `ACTION_TIMEOUT`。

### `REQ-CORE-005`：错误码和退出码稳定

**Statement**：失败结果必须包含稳定错误码；退出码必须区分成功、可恢复失败、内部错误和参数错误。

**Acceptance**：

- `TEST-CORE-010`：已定义错误路径返回固定错误码。
- `TEST-CORE-011`：成功退出码为 `0`，可恢复失败为 `1`，内部错误为 `2`，参数错误为 `64`。

### `REQ-CORE-006`：Artifact 契约

**Statement**：截图、录屏、拉取文件等产物必须写入显式路径，并在 JSON 的 `artifacts` 或 `data.path` 中返回路径和必要元数据。

**Acceptance**：

- `TEST-CORE-012`：截图命令写入文件并返回 artifact path。
- `TEST-CORE-013`：stdout 不内联截图、录屏等大体积二进制内容。

### `REQ-CORE-007`：Pi schema 同步

**Statement**：Pi integration 使用的工具定义必须与 CLI 契约保持同源或有明确同步路径，避免 README、Python schema 和 TypeScript extension 维护互相漂移的命令列表。

**Acceptance**：

- `TEST-CORE-014`：`android-cli pi schema` 能导出可消费的工具 schema，兼容入口 `u2cli pi schema` 行为保持可用。
- `TEST-CORE-015`：Pi extension 和 CLI schema 的命令列表可从同一源文件或可追踪生成路径验证。

## Compatibility

- stdout JSON：固定顶层字段为 `success`、`command`、`serial`、`via`、`data` 或 `error`、`artifacts`、`durationMs`。
- stderr 日志：仅用于日志和诊断。
- 退出码：`0` 成功，`1` 可恢复命令失败，`2` 内部错误，`64` 参数错误。
- 错误码：详见 [design.md](./design.md)。
- Pi schema：需要随命令契约同步。
- 旧命令兼容：本 spec 固化现有核心子命令树和 `u2cli` 兼容入口，后续不应破坏旧命令行为，除非有新的 approved spec 明确替代。

## Open Questions

- 真机集成测试是否进入默认 CI 仍待单独决策。
- sidecar 是否升级为默认执行模式不在本 spec 范围内。
