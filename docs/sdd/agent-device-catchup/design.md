# Agent Device Catchup Design

- **Spec ID**：`agent-device-catchup`
- **Status**：`Draft`
- **Owner**：`u2cli maintainers`
- **Last Updated**：`2026-05-27`
- **Source Requirements**：`./requirements.md`

## Design Summary

追赶工作按能力域分层推进。第一层补齐可观测性和 capability metadata，让现有命令结果能说明“实际走了什么能力、是否降级、如何恢复”。第二层补齐 snapshot/full/diff/logs/trace/perf 等诊断能力。第三层补齐 replay/test 和复杂手势。平台扩展只做明确边界，不把 unsupported 伪装成可用。

## Requirement Mapping

| Requirement | Design Section |
|---|---|
| `REQ-ADC-001`、`REQ-ADC-002`、`REQ-ADC-003` | `DES-ADC-001` |
| `REQ-ADC-004`、`REQ-ADC-005` | `DES-ADC-002` |
| `REQ-ADC-006`、`REQ-ADC-007`、`REQ-ADC-008`、`REQ-ADC-009` | `DES-ADC-003` |
| `REQ-ADC-010`、`REQ-ADC-011`、`REQ-ADC-012` | `DES-ADC-004` |
| `REQ-ADC-013`、`REQ-ADC-014`、`REQ-ADC-015`、`REQ-ADC-016` | `DES-ADC-005` |
| `REQ-ADC-017`、`REQ-ADC-018`、`REQ-ADC-019` | `DES-ADC-006` |
| `REQ-ADC-020`、`REQ-ADC-021` | `DES-ADC-007` |

## `DES-ADC-001`：Capability Metadata 和状态面

**Covers**：`REQ-ADC-001`、`REQ-ADC-002`、`REQ-ADC-003`

新增 capability registry，至少区分：

```text
adb-fast-path
pure-adb-ui-query
snapshot-helper
uiautomator2
persistent-accessibility
unknown
unsupported
```

结果 metadata 建议放入 `data.metadata`，避免破坏 `u2cli-core` 顶层字段。需要披露：

- `capabilityLayer`
- `fallbackUsed`
- `fallbackMethod`
- `fallbackReason`
- `preparationState`
- `degraded`
- `failureStage`
- `recoveryHint`

新增或增强状态命令：

- `runtime status`
- `runtime clear`
- `session status`
- `session list`
- `session clear`

## `DES-ADC-002`：Full Snapshot、Diff 和 Overlay

**Covers**：`REQ-ADC-004`、`REQ-ADC-005`

`snapshot capture --full` 是显式模式，不替代默认 compact。full 结果必须说明：

- `mode`
- `full`
- `complete`
- `canProveAbsence`
- `coverage`
- `coverageFailureReason`
- `nodeCount`
- `observedNodeCount`
- `targetLocation`

`diff screenshot` 使用本地 PNG 解析生成 changedPixels、diffRatio、passed 和 overlay artifact。`diff snapshot` 对比当前 snapshot 与 session 最近 snapshot 的节点签名。`screenshot --overlay-refs` 读取最近 refMap 并把 `@eN` bounds 绘制到截图 artifact。

## `DES-ADC-003`：日志、Trace、Perf、Network

**Covers**：`REQ-ADC-006`、`REQ-ADC-007`、`REQ-ADC-008`、`REQ-ADC-009`

日志链路：

- `logs start [--restart]` 写 marker 并记录 session。
- `logs stop` 读取 marker 后日志并写 artifact。
- `logs clear` 清空 logcat。
- `logs mark` 写入 marker。
- `logs path` 返回当前 artifact 路径。
- `logs doctor` 检查 logcat 可用性。

trace 使用 Android `atrace --async_start/--async_stop` 或可用替代。perf 优先 procfs 单次 shell 采集 `/proc/meminfo`、`/proc/stat` 和可选 `ps -A`。network 从 logcat 或 logs artifact 中提取 HTTP/URL/status 线索，默认 summary，raw 输出需显式请求。

## `DES-ADC-004`：Settings、Push、App Event、Boot

**Covers**：`REQ-ADC-010`、`REQ-ADC-011`、`REQ-ADC-012`

settings 命令必须写后读回，失败返回实际状态。push 和 trigger-app-event 使用 ADB intent/broadcast 语义封装，并解析 `am broadcast` / `am start` 输出。boot 和 ensure-simulator 只做设备在线确认、session 写入和可诊断失败，不做云设备调度。

## `DES-ADC-005`：Replay、Healing、Test Runner

**Covers**：`REQ-ADC-013`、`REQ-ADC-014`、`REQ-ADC-015`、`REQ-ADC-016`

定义最小 `.ad` 脚本格式：

- 每行一条 Android CLI 命令；推荐写 `android-cli`，兼容脚本可继续写 `u2cli`。
- 支持 `context` 和 `env`。
- 支持 shell 风格引号和 `${VAR}` 变量。
- 支持注释型视觉断言，如 `# expect-screenshot baseline=... threshold=...`。

replay 失败时可基于最近 snapshot refMap 做 selector/ref healing；`--replay-update` 更新脚本。`test` 命令批量执行 replay 文件并生成 summary 和 JUnit artifact。

## `DES-ADC-006`：高级手势和录制

**Covers**：`REQ-ADC-017`、`REQ-ADC-018`、`REQ-ADC-019`

优先实现可稳定表达的 fast path：

- `gesture pan/fling` -> 平台 swipe。
- `gesture replay` -> 单指 segments 转多段 swipe。
- `screen multi-touch` / `pinch` / `expand` 如无法真多指执行，返回 structured unavailable 和 fallback 建议。
- `record start/stop` 使用 session 记录后台录屏状态，区别于一次性 `screen record`。

## `DES-ADC-007`：Unsupported 边界

**Covers**：`REQ-ADC-020`、`REQ-ADC-021`

对 HarmonyOS、React Native、React DevTools、云设备、daemon 等暂不实现能力，新增统一 unsupported 结果：

```json
{
  "available": false,
  "unsupported": true,
  "reason": "not_in_scope",
  "recoveryHint": "Use Android uiautomator2-backed commands or implement a dedicated platform adapter."
}
```

## Testing Strategy

- capability metadata 使用合约测试覆盖每类命令的 layer、fallback 和 degraded 字段。
- full snapshot 使用 fixture 验证 `canProveAbsence=false` 的 compact 语义和 full 完整性字段。
- diff/overlay 使用小 PNG fixture，避免依赖真机。
- logs/trace/perf/network 使用 fake adb 输出和 artifact 断言。
- replay/test 使用临时脚本 fixture 和 fake command runner。
- unsupported 边界使用命令级 JSON 断言。

## Risks

- 新增 `metadata` 位置可能影响调用方：优先放在 `data.metadata`，并在 Pi schema 明确。
- 任意 shell 与 settings 写入有安全风险：默认只开放结构化命令，任意 shell 另行评审。
- full snapshot 容易输出虚假完整性：宁可返回 `complete=false`，也不把降级结果标为 full 成功。
