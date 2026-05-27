# PRD：u2cli 对齐 agent-device 风格 CLI 体验

> SDD 迁移说明：本 PRD 已拆分到 `docs/sdd/agent-device-alignment/`。后续需求、设计、任务和验收追踪以该 SDD spec 为准，本文件仅保留为背景材料。

## 文档信息

- **项目**：u2cli
- **版本**：v0.1（草案）
- **状态**：待评审
- **范围**：CLI 表层与 agent 调用契约的对齐设计；不涉及 uiautomator2 内核替换。
- **参照对象**：`DeviceTestCLI`（`/Users/funer/code/DeviceTestCLI`），其顶层命令族对齐 `agent-device` 0.15.2 的公共 CLI surface。

---

## 1. 背景

`u2cli` 已交付以 `uiautomator2` 为执行内核的 Android Agent CLI，具备完整的 `device/app/screen/element/input/toast/watcher/session/pi` 子命令树、JSON 契约、错误码、per-serial 串行锁与多后端 snapshot。

但在与多平台、多 Agent 的实际接入中，发现 `agent-device` 风格 CLI（以 `DeviceTestCLI` 为参考实现）在以下几方面对 Agent 更友好：

- 扁平顶层命令、位置参数与 `@eN` 短引用，单步调用 token 更低；
- snapshot 节点本地缓存 + bounds fast path，跨命令复用观察结果；
- session 自动 hydrate，免重复传 `--serial/--platform`；
- 多能力层自动降级 + 结构化诊断字段；
- `batch / wait / find / is / scroll / fill / alert` 等高频组合命令。

本 PRD 定义 `u2cli` 对齐这些能力的目标、范围、需求、验收标准与分阶段实施计划。**不替换** uiautomator2 执行语义、**不引入** HarmonyOS 支持、**不引入** 任意 Python/shell 执行。

---

## 2. 目标与非目标

### 2.1 目标

- **Agent 调用成本最小化**：在不破坏现有 JSON 契约的前提下，提供 `agent-device` 风格的扁平顶层命令与 `@eN` 短引用。
- **跨命令观察复用**：snapshot 结果本地缓存，`click @eN`、`fill @eN`、`get text @eN` 直接消费缓存 bounds。
- **Session 持久化**：默认从本地 session 自动注入 `serial` 与 `timeoutMs`，单设备场景不需重复传参。
- **诊断字段对齐**：`wait/find/is` 等命令返回 attempts、durationMs、matchedCount、selectedIndex 等结构化诊断。
- **能力对齐**：补齐 `open/close/back/home/fill/scroll/alert/batch` 等高频 agent 入口。

### 2.2 非目标

- 不支持 HarmonyOS、iOS、云设备。
- 不引入 `record/replay/test` 资产体系（保留为后续阶段）。
- 不引入 React Native / DevTools / Metro。
- 不暴露任意 shell / Python eval。
- 不实现 PNG 像素 diff、screenshot overlay-refs、network 线索解析（保留为后续阶段）。
- 不替换 uiautomator2 为自研 helper APK。

---

## 3. 用户与典型场景

### 3.1 主要用户

- **Pi tool / Agent 编排层**：批量调用 `u2cli`，期望低 token、稳定 JSON、可重试。
- **测试 Agent**：基于 snapshot 观察 → ref 操作 → 验证的循环。

### 3.2 典型调用流

```bash
# 1. 一次设备绑定
u2cli connect --serial emulator-5554

# 2. 观察当前界面（写入本地 session 缓存）
u2cli snapshot -i

# 3. 直接消费 ref，无需重复 selector
u2cli click @e3
u2cli fill @e7 qa@example.com
u2cli get text @e9

# 4. 失败时回退 selector
u2cli click 'text=登录'
u2cli wait text 首页 3000

# 5. 多步组合
u2cli batch --steps '[{"command":"back"},{"command":"snapshot","flags":{"interactive":true}}]'
```

---

## 4. 现状差距清单

> 对比口径：`u2cli` 现版本 vs `DeviceTestCLI` 顶层 agent-device 风格命令面。

### 4.1 u2cli 已具备 ✓

- 完整 `device/app/screen/element/input/toast/watcher/session/pi` 子命令树。
- JSON 成功/失败契约、稳定错误码、per-serial filelock。
- `screen dump` 多后端（helper/apk/jar/adb/uiautomator2）。
- `device clipboard-get/set`、`screen orientation`、`screen record`、`app intent`。
- `pi schema` 导出 Pi tool 描述。
- `session sidecar-start` 常驻进程降低冷启动。

### 4.2 DeviceTestCLI 有、u2cli 缺失（按优先级）

#### P0：直接影响 agent 单步 token 与调用成本

| 能力 | DeviceTestCLI 形态 | 当前 u2cli 替代 |
|---|---|---|
| **Snapshot ref 系统** | `click @e3` / `fill @e3` / `get text @e3` | 需重复构造 selector |
| **顶层快捷命令** | `back/home/app-switcher/open/close` | `input press --key back` 等多步 |
| **fill（聚焦+输入一体）** | `fill text="Email" qa@example.com` | `element set-text --resource-id ... --value ...` |
| **find 带动作 / --first / --last** | `find text=... click --first` | 需先 `find` 再 `click` |
| **is 断言** | `is exists text=...` | `element exists` |
| **wait 结构化诊断** | `wait text Ready 3000` 含 attempts/durationMs | `element wait` 字段较少 |
| **session 自动 hydrate** | 不需每次传 `--serial` | 必须显式 `--serial` |
| **百分比坐标点击** | `click 50 80`（百分比）/ `screen tap-percent` | 仅绝对坐标 |
| **batch 串行执行** | `batch --steps '[...]'` | 无 |

#### P1：常用设备管理 / 诊断

| 能力 | DeviceTestCLI 形态 | 当前 u2cli 替代 |
|---|---|---|
| **alert 处理** | `alert get/wait/accept/dismiss` | 无 |
| **scroll 增强** | `scroll down/top/bottom/--pixels` | `element swipe --direction` |
| **double-tap / hold-ms / count / jitter-px** | `click @e3 --double-tap` | 无 |
| **appstate 前台应用** | `appstate` | `app current` 部分覆盖 |
| **apps 列表 + source/system** | `apps --all` | `app list --kind all` 字段较少 |
| **reinstall** | `reinstall` | 需 `app uninstall` + `app install` 两步 |
| **install-from-source** | URL / 本地文件直装 | 仅本地 APK |
| **keyboard 状态** | `keyboard status/hide/show` | 无 |
| **settings（animations/wifi/airplane）** | `settings animations off` | 仅 `app grant/revoke` |
| **connect / disconnect / connection status** | 远程设备管理 | 无 |
| **boot / ensure-simulator** | 设备在线确认 + session 写入 | 无 |
| **push / trigger-app-event** | broadcast / deep link 结构化解析 | `app intent` 部分覆盖 |

#### P2：高级诊断与录制（暂不在本 PRD 范围）

- `logs start/stop/clear/mark`、`trace start/stop`、`perf` procfs 采样。
- `diff screenshot` / `diff snapshot`、`screenshot --overlay-refs`。
- `record / replay / test` 脚本与 healing。
- `gesture pinch/rotate/transform` 多指手势。
- 多能力层自动降级（u2cli 固定 uiautomator2 单层）。

---

## 5. 需求详细设计

### 5.1 顶层 agent 风格命令

新增以下顶层命令，**与现有子命令树并存**（旧命令保留兼容）。所有命令复用现有 JSON 契约：`success/command/serial/via/data/error/artifacts/durationMs`。

```bash
u2cli devices                                  # = u2cli devices（已存在）
u2cli apps [--kind all|user]                    # = u2cli app list 增强字段
u2cli appstate                                  # = u2cli app current 结构化
u2cli open <package> [--activity ...] [--relaunch]
u2cli close [<package>] [--shutdown]
u2cli back
u2cli home
u2cli app-switcher
u2cli rotate <portrait|landscape|0|90|180|270>
u2cli screenshot [--out ...]
u2cli snapshot [-i|--compact|--full] [--target-text TEXT]
u2cli click <x> <y> | click @eN | click 'text=...' [--double-tap] [--hold-ms N] [--count N] [--jitter-px N]
u2cli press ...                                 # alias of click（按 DeviceTestCLI 习惯保留）
u2cli longpress <target> [--duration-ms N]
u2cli swipe <fromX> <fromY> <toX> <toY> [--duration-ms N] [--count N]
u2cli scroll <direction|top|bottom> [--pixels N]
u2cli fill <target> <text> [--delay-ms N]
u2cli type <text>                               # = u2cli input text
u2cli focus <target>
u2cli get <attr> <target>                       # attr ∈ text/attrs/bounds
u2cli find <selector> [click|fill ...] [--first|--last]
u2cli is <state> <selector>                     # state ∈ exists/visible/enabled/checked
u2cli wait <kind> <value> <timeout-ms>          # kind ∈ text/resource-id/...
u2cli alert <get|wait|accept|dismiss> [--timeout-ms N]
u2cli clipboard <read|write> [<text>]
u2cli keyboard <status|hide|show>
u2cli batch --steps '<json>' [--out ...]
u2cli connect --address <host:port>
u2cli disconnect
u2cli connection status
```

### 5.2 Snapshot ref 系统

**核心契约**：

- `snapshot -i` / `snapshot --compact` 返回的每个 `nodes[i]` 附加 `ref: "e<N>"`，N 为节点扁平下标。
- 完整 `refMap` **只写本地 session 文件**，不进入 stdout，避免污染 compact 输出。

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

**消费规则**：

- `click @eN` / `press @eN` / `longpress @eN`：优先 `bounds` 中心点 + 坐标 fast path；缺少可信 bounds 时回退到 selector。
- `fill @eN <text>`：先 tap bounds 中心，再走 `input.text`。
- `get text @eN`：直接读 cached `text`，不查设备。
- 引用不存在 → `SNAPSHOT_REF_NOT_FOUND`，含 `details.capturedAt`。
- 引用 selector 缺失 → `SNAPSHOT_REF_INVALID`。

**正向缓存**：`find text=...`、`is exists text=...`、`wait text ...`、`get text=...` 在最近 compact snapshot 命中时直接返回缓存结果；未命中、歧义或跨设备时仍查询设备，**不把缓存当作不存在证明**。

### 5.3 Session 自动 hydrate

- **存储位置**：`${HOME}/.config/u2cli/session.json`（macOS：`~/Library/Application Support/u2cli/session.json`）。
- **字段**：`serial`、`timeoutMs`、`lastSnapshot`（refMap + capturedAt）、`updatedAt`。
- **写入触发**：任意成功命令在 `--serial` 已知时持久化；`snapshot` 写 `lastSnapshot`。
- **读取触发**：CLI 启动时若 `--serial` 未传，从 session 注入；显式 `--serial` 始终覆盖 session。
- **清理**：`session clear` 命令；连接异常时标记 `stale` 但不自动清空。
- **多设备**：当前 PRD 仅支持单 session；多设备并发由调用方显式 `--serial` 覆盖。

### 5.4 选择器扩展

新增位置参数语法（与现有 `--text/--resource-id` 长选项并存）：

```text
text=登录          → Selector(text="登录")
id=login           → Selector(resourceId="login")
testid=...         → Selector(resourceId=...)        # alias
class=Button       → Selector(className="Button")
description=...    → Selector(description=...)
desc=...           → alias of description
@e3                → 从 session.lastSnapshot.refMap 解析
'text="带空格 文本"' → 支持引号包裹
```

校验规则沿用现有 `Selector` 模型（pydantic）。新解析逻辑集中在 `selector.from_target(value: str) -> Selector`。

### 5.5 结构化诊断字段

`wait/find/is/alert` 命令统一返回：

```json
{
  "selector": {...},
  "state": "exists|visible|...",
  "timeoutMs": 3000,
  "attempts": 5,
  "durationMs": 2810,
  "matchedCount": 1,
  "selectedIndex": 0
}
```

`find --first` 在多匹配时返回 `selectedIndex=0`，`--last` 返回 `len-1`，未指定且 `matchedCount > 1` → `ELEMENT_AMBIGUOUS`。

### 5.6 batch 命令

```bash
u2cli batch --steps '[
  {"command":"back"},
  {"command":"snapshot","flags":{"interactive":true}},
  {"command":"click","args":["@e3"]}
]' --out ./run.json
```

- 串行执行；失败时**保留已执行步骤**与失败 step 的结构化错误。
- 顶层 JSON：`{success, steps:[{command, success, data?, error?, durationMs}], failed, total}`。
- `--out` 写完整结果为 artifact，stdout 仍是合法 JSON。
- batch 内每个 step 不再触发 sidecar 重启；共用 session 与同一 device 句柄。

### 5.7 修饰器（点击/滑动）

| 选项 | 适用命令 | 语义 |
|---|---|---|
| `--double-tap` | click/press | 连续两次 tap，与 `--hold-ms` 互斥 |
| `--hold-ms N` | click/press/longpress | 在原地 swipe N 毫秒模拟长按 |
| `--count N` | click/press/swipe | 重复 N 次；u2cli 用纯 Python 循环（不引入 bulk-shell） |
| `--interval-ms N` | click/press/swipe | 重复间隔 |
| `--jitter-px N` | click/press | 基于 (x,y) 的确定性抖动，seed 可复现 |

### 5.8 顶层 alert 自动处理

候选按钮文本表（中英双语）写在 `u2cli/agent/alert.py`：

```python
ALERT_BUTTONS = (
    ("Allow", "accept"), ("OK", "accept"), ("Yes", "accept"),
    ("允许", "accept"), ("确定", "accept"), ("同意", "accept"),
    ("Cancel", "dismiss"), ("Deny", "dismiss"),
    ("取消", "dismiss"), ("拒绝", "dismiss"),
    ...
)
```

- `alert get`：扫描候选，返回 `{present, matchedCount, candidates:[{text, role, selector}]}`。
- `alert wait`：含 attempts 轮询直到 `--timeout-ms`。
- `alert accept/dismiss`：点击首个 role 匹配的候选。

### 5.9 错误码新增

| 错误码 | 触发场景 |
|---|---|
| `SNAPSHOT_REF_NOT_FOUND` | `@eN` 在最近 snapshot 不存在 |
| `SNAPSHOT_REF_INVALID` | refMap 条目缺少可执行 selector 或 bounds |
| `SESSION_STALE` | session 中的 serial 已不在线 |
| `ALERT_NOT_FOUND` | `alert accept/dismiss` 找不到候选 |
| `BATCH_STEP_FAILED` | batch 内某步失败（顶层 success=false 时使用） |

### 5.10 不破坏既有契约

- 现有 `device/app/screen/element/input/toast/watcher/session/pi` 子命令树保持不变。
- 现有 JSON 字段顺序 `success/command/serial/via/data/error/artifacts/durationMs` 不变。
- 顶层新增命令的 `command` 字段使用扁平命名：`click`、`fill`、`snapshot`、`batch`，不带子命令前缀。

---

## 6. 验收标准

### 6.1 P0 验收（最小可用 agent 体验）

- `u2cli connect --serial X` 后，后续命令默认无须 `--serial`。
- `u2cli snapshot -i` 输出每个节点含 `ref: "eN"`；`refMap` 写入 session，stdout 不含完整 refMap。
- `u2cli click @eN`、`u2cli fill @eN <text>`、`u2cli get text @eN` 走 bounds fast path，命令延迟 ≤ 同设备 `element click` 的 80%。
- `u2cli back/home/open <pkg>/close` 单步可用。
- `u2cli wait text 首页 3000` 返回 `attempts/durationMs/matchedCount`。
- `u2cli batch --steps '[...]'` 在 step2 失败时保留 step1 数据并 `success=false`、退出码 1。
- selector 位置参数 `text=登录`、`id=login`、`@e3` 解析等价于对应长选项。
- 旧命令 `u2cli element click --text 登录 --json` 行为完全不变。

### 6.2 P1 验收

- `u2cli alert accept --timeout-ms 3000` 在中英文确认弹窗下都能命中。
- `u2cli scroll down/top/bottom`、`u2cli scroll --pixels 500` 可用。
- `u2cli click @e3 --double-tap`、`--hold-ms 800`、`--count 3 --interval-ms 100`、`--jitter-px 4` 表现稳定。
- `u2cli reinstall --app pkg --path app.apk` 走通卸载 + 重装。
- `u2cli appstate`、`u2cli apps --kind all` 字段含 `package/activity/source/system`。
- `u2cli keyboard status/hide/show` 返回 `shown/currentIme/servedView`。
- `u2cli connect --address 1.2.3.4:5555` 能通过 `adb connect` 建立远程并验证在线。

### 6.3 不变量

- 所有命令 stdout 单行合法 JSON。
- 错误码集合 ∈ §5.9 + 现有错误码。
- 现有 pytest 套件全绿；新增命令至少各 1 成功 + 1 失败 + 1 选择器解析用例。
- 覆盖率门槛 `src/u2cli` ≥ 85%（不含 `pi/`、新增 `agent/` 视实施进度调整）。

---

## 7. 实施路线

### Phase A：snapshot ref + session hydrate（P0 基石）

- 新增 `u2cli/session/store.py`（基于 `pydantic` + 文件锁）。
- `screen dump --compact` 在节点上挂 `ref` 字段；写 `refMap` 到 session。
- `cli.py` 入口在 `--serial` 缺省时从 session 注入。
- selector 增加 `from_target(value)`，支持 `text=...`、`id=...`、`@eN`。
- 单测：refMap 写入、ref 解析、stale session 处理。

### Phase B：顶层 agent 命令（P0 主要面）

- 新增 `u2cli/agent/cli.py`，注册顶层命令 `click/press/longpress/fill/type/focus/get/find/is/wait/back/home/app-switcher/open/close/snapshot/screenshot/scroll/swipe/rotate/clipboard/keyboard/connect/disconnect`。
- 复用 `element/input/screen/app/device` 现有 handler，避免重复语义。
- 修饰器 `--double-tap/--hold-ms/--count/--interval-ms/--jitter-px` 在共用 helper 实现。
- 单测：每个顶层命令 1 成功 + 1 失败；ref 与 selector 双路径。

### Phase C：组合命令（P0 补全）

- `batch` handler；step JSON schema + 串行执行 + artifact 写入。
- `wait/find/is` 结构化诊断字段补齐。
- 错误码新增 `SNAPSHOT_REF_NOT_FOUND/INVALID`、`SESSION_STALE`、`BATCH_STEP_FAILED`。
- 集成测试：snapshot → click @eN → fill @eN 全链路 mock 用例。

### Phase D：P1 能力补齐

- `alert get/wait/accept/dismiss` + 候选表。
- `scroll down/top/bottom/--pixels`。
- `appstate/apps（增强）/reinstall/install-from-source`。
- `keyboard status/hide/show`。
- `connect/disconnect/connection status`。

### Phase E：Pi tool 与文档

- 更新 `pi/tool_schema.py`，把顶层命令导出为 Pi tool（schema 比 CLI flag 更窄）。
- 更新 `README.md` agent-style 章节。
- 更新 `PLAN.md` 与本 PRD 的实施回执。

---

## 8. 风险与对策

| 风险 | 对策 |
|---|---|
| 新顶层命令与子命令树命名冲突 | 顶层使用扁平命名；冲突命令（如 `devices`）走兼容 alias |
| Snapshot ref 在 UI 抖动后失效 | refMap 含 `capturedAt`；执行时若 selector 解析失败回退 selector 路径 |
| Session 文件并发写入 | 复用现有 `filelock`；写入走 atomic rename |
| `@eN` 引用让 agent 误以为永久有效 | 错误码 `SNAPSHOT_REF_NOT_FOUND` 明确指引重新 `snapshot -i` |
| batch 执行延迟累积 | 复用 sidecar 模式；单 step 仍走原 timeout |
| 中英文 alert 候选漏匹配 | 候选表可配置 `${HOME}/.config/u2cli/alert-buttons.json` 覆盖默认 |
| 顶层位置参数 selector 与 shell 引号交互 | 文档强调 `'text="..."'` 推荐写法；解析层兼容裸值（视作 text） |

---

## 9. 不在本 PRD 范围（后续 PRD）

- HarmonyOS 平台支持。
- `record/replay/test` 脚本与 healing。
- `logs/trace/perf` 诊断链路。
- `diff screenshot/snapshot`、`screenshot --overlay-refs`。
- 多能力层自动降级（adb-fast-path → pure-adb-ui-query → temporary-uiautomation → persistent-accessibility）。
- 多 Agent 多设备并发 session。
