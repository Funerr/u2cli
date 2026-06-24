# androidtestclii 计划

> SDD 迁移说明：本文件保留为历史路线和早期设计材料。后续涉及需求、设计、任务、验收和兼容性的改动，应以 `docs/sdd/` 为规范源：
>
> - `docs/sdd/README.md`
> - `docs/sdd/androidtestclii-core/`
> - `docs/sdd/agent-device-alignment/`

## 目标

基于 `uiautomator2` 做一个面向 Agent 的 Android CLI。

第一阶段目标不是完整移动端测试平台，而是先把 `uiautomator2` 的高价值原子能力转换成稳定、可测试、可被 Pi tool 调用的 CLI。

```text
Pi tool
  -> androidtestclii
    -> uiautomator2
      -> Android device
```

## 路线选择

本项目 **基于 CLI-Anything 起步**。

CLI-Anything 用来提供 CLI harness 的基础结构和规范，包括：

- agent-friendly CLI 结构
- `--json` 输出模式
- 命令帮助与可发现性
- 测试 harness
- Pi extension / skill 相关约定
- REPL 与 subcommand 的组织方式参考

但 `uiautomator2` 的核心执行语义由本项目自己实现，包括：

- selector schema
- 设备连接与重连
- 每台设备的 mutation 串行锁
- timeout
- 错误码
- artifact 路径
- toast 等短时信号处理
- Pi tool 返回结构

换句话说：

```text
CLI-Anything 负责起步框架和 agent CLI 规范
androidtestclii 负责 Android/uiautomator2 的真实执行语义
```

## 定位

`androidtestclii` 只负责 Android 执行层：

- 设备发现与健康检查
- App 生命周期
- 屏幕观察
- 元素查找与操作
- 基础输入手势
- Toast 捕获
- JSON 结果归一化

`androidtestclii` 不负责：

- 测试用例规划
- replay 资产治理
- 跨平台抽象
- 最终测试通过/失败判定
- 任意 Python 执行

这些职责应留给 Pi、更高层测试执行 Agent，或后续 replay/test runner。

## 为什么不用 uiautomator2 原生 CLI

`uiautomator2` 的 Python API 很强，但它自带 CLI 不是完整的 Agent 自动化接口。我们需要更严格的契约：

- stdout 只输出一个 JSON 对象
- stderr 只写日志和诊断
- selector 输入结构化且可校验
- 每条命令都有 timeout 语义
- 同一设备上的变更型命令必须串行
- 错误码稳定
- artifact 路径显式返回
- Pi tools 可以安全包装每个命令

## MVP 命令面

### 全局参数

```bash
androidtestclii --json <command>
androidtestclii --serial <device-id> <command>
androidtestclii --timeout-ms 5000 <command>
```

规则：

- 面向机器调用时默认使用 JSON 输出。
- `--serial` 指定 Android 设备。
- 变更型命令必须按设备串行加锁。
- 所有命令输出都必须包含 `success`、`command`、`serial`、`via`、`durationMs`。

### Device

```bash
androidtestclii doctor
androidtestclii devices
androidtestclii device info --serial <id>
```

职责：

- 检查 Python 版本
- 检查 `uiautomator2` 是否可 import
- 检查 `adb` 是否可用
- 检查目标设备是否在线
- 检查 u2 连接是否可建立

### App

```bash
androidtestclii app current --serial <id>
androidtestclii app start --serial <id> --package com.example.app
androidtestclii app stop --serial <id> --package com.example.app
androidtestclii app clear --serial <id> --package com.example.app
androidtestclii app install --serial <id> --apk ./app.apk
androidtestclii app uninstall --serial <id> --package com.example.app
```

### Screen

```bash
androidtestclii screen dump --serial <id>
androidtestclii screen dump --serial <id> --compact
androidtestclii screen screenshot --serial <id> --out ./artifacts/screen.png
androidtestclii screen size --serial <id>
```

`screen dump --compact` 应把原始 UI hierarchy 转换成 Agent 易读的节点列表。

### Element

```bash
androidtestclii element find --serial <id> --text 登录
androidtestclii element wait --serial <id> --text 首页 --timeout-ms 10000
androidtestclii element click --serial <id> --text 登录 --timeout-ms 5000
androidtestclii element long-click --serial <id> --text 删除 --timeout-ms 5000
androidtestclii element set-text --serial <id> --resource-id com.example:id/email --text qa@example.com
androidtestclii element clear-text --serial <id> --resource-id com.example:id/email
androidtestclii element get-text --serial <id> --resource-id com.example:id/title
```

支持的 selector 字段：

```json
{
  "text": "登录",
  "textContains": "登",
  "resourceId": "com.example:id/login",
  "description": "Login",
  "descriptionContains": "Log",
  "className": "android.widget.Button",
  "xpath": "//*[@text='登录']",
  "index": 0
}
```

selector 规则：

- 每条命令构造一个 selector 对象。
- 若匹配多个元素，默认返回歧义错误，不猜测。
- 只有传入 `index` 时才允许选取第 N 个匹配结果。
- 支持 `xpath`，但优先使用普通 selector。
- 命令输出应包含最终 selector 和可获得的元素信息。

### Input

```bash
androidtestclii input press --serial <id> --key back
androidtestclii input tap --serial <id> --x 100 --y 200
androidtestclii input swipe --serial <id> --from 500,1600 --to 500,400 --duration-ms 400
androidtestclii input text --serial <id> --text hello
```

### Toast

```bash
androidtestclii toast get --serial <id> --timeout-ms 3000
androidtestclii toast reset --serial <id>
```

Toast 是短时信号，命令行为必须显式、可预期。

## JSON 返回契约

成功：

```json
{
  "success": true,
  "command": "element.click",
  "serial": "emulator-5554",
  "via": "uiautomator2",
  "data": {
    "selector": {"text": "登录"},
    "matched": true,
    "clicked": true
  },
  "artifacts": [],
  "durationMs": 318
}
```

失败：

```json
{
  "success": false,
  "command": "element.click",
  "serial": "emulator-5554",
  "via": "uiautomator2",
  "error": {
    "code": "ELEMENT_NOT_FOUND",
    "message": "No element matched selector",
    "details": {
      "selector": {"text": "登录"}
    }
  },
  "artifacts": [],
  "durationMs": 5004
}
```

## 错误码

第一版稳定错误码：

- `INVALID_ARGUMENT`
- `PYTHON_ENV_INVALID`
- `U2_IMPORT_FAILED`
- `ADB_NOT_FOUND`
- `DEVICE_NOT_FOUND`
- `DEVICE_OFFLINE`
- `U2_CONNECT_FAILED`
- `APP_ACTION_FAILED`
- `ELEMENT_NOT_FOUND`
- `ELEMENT_AMBIGUOUS`
- `ACTION_TIMEOUT`
- `ACTION_FAILED`
- `SCREENSHOT_FAILED`
- `TOAST_TIMEOUT`
- `INTERNAL_ERROR`

## 实施计划

### PRD agent-device alignment implementation

- 已新增顶层 agent-style 命令：`connect/disconnect/connection/apps/appstate/open/close/back/home/app-switcher/rotate/screenshot/snapshot/click/press/longpress/swipe/scroll/fill/type/focus/get/find/is/wait/alert/clipboard/keyboard/reinstall/install-from-source/batch`。
- 已新增 session hydrate：成功命令在有 serial 时写 `${ANDROIDTESTCLII_SESSION_PATH}` 或平台默认 session；未传 `--serial` 时自动读取 session；`session clear` 清理。
- 已新增 snapshot ref cache：compact 节点输出 `ref: "eN"`；完整 `refMap` 写入 session；`@eN` 支持 bounds fast path 与 cached text。
- 已新增 selector target 解析：`text=...`、`id=...`、`testid=...`、`class=...`、`desc=...`、裸文本和 `@eN`。
- 已补齐诊断字段和错误码：`SNAPSHOT_REF_NOT_FOUND`、`SNAPSHOT_REF_INVALID`、`SESSION_STALE`、`ALERT_NOT_FOUND`、`BATCH_STEP_FAILED`。
- 已更新 Pi schema 和 extension，使 Pi 可调用新的低 token 顶层命令。

### Phase 1：基于 CLI-Anything 建立 CLI 骨架

- 使用 CLI-Anything 生成或搭建初始 harness。
- 保留 CLI-Anything 推荐的 agent-friendly CLI 结构。
- 建立 Python package。
- 添加 console script：`androidtestclii`。
- 添加 JSON result helper。
- 添加错误模型。
- 添加基础命令路由。
- 添加 JSON 成功/失败格式测试。

### Phase 2：Device 与 App 命令

- 实现 `doctor`。
- 实现 `devices`。
- 实现 `device info`。
- 实现 `app current/start/stop/clear`。
- 使用 mock 的 u2 和 subprocess 写单元测试。

### Phase 3：Screen 与 Selector 核心

- 实现 selector parser。
- 实现 `screen dump`。
- 实现 compact node projection。
- 实现 `screen screenshot`。
- 添加 selector 归一化与 compact dump 测试。

### Phase 4：Element 与 Input 命令

- 实现 `element find/wait/click/long-click/set-text/clear-text/get-text`。
- 实现 `input press/tap/swipe/text`。
- 增加每设备 mutation lock。
- 增加 timeout 处理。

### Phase 5：Toast 与诊断

- 实现 `toast get/reset`。
- 归一化 u2 连接异常和动作异常。
- 失败返回中补充诊断字段。
- 支持 screenshot artifact path。

### Phase 6：Pi 集成

- 将 Pi tools 定义为 `androidtestclii` 的 typed wrapper。
- Pi tool schema 要比 CLI flags 更窄。
- 将 CLI JSON failure 映射为 Pi tool error。
- 增加 `androidtestclii doctor` preflight tool。

## 后续：Python Sidecar

MVP 可以每次 tool call 启动一次 `androidtestclii`。如果进程启动或 `u2.connect()` 延迟影响执行效率，再把核心命令抽成常驻 Python sidecar：

```text
Pi tool
  -> localhost JSON-RPC
    -> androidtestclii sidecar
      -> cached u2 device connection
```

sidecar 必须复用同一套命令 schema 和 JSON 返回契约，这样 Pi tool 不需要改。

## 第一版非目标

- iOS 支持
- HarmonyOS 支持
- record/replay/test 资产
- 任意 shell 执行
- 任意 Python 执行
- 视觉 diff
- 云设备租赁
- 多 Agent 调度

## MVP 验收标准

- `androidtestclii doctor --json` 返回结构化健康检查。
- `androidtestclii devices --json` 返回已连接 Android 设备列表。
- `androidtestclii screen dump --compact --json` 返回 Agent 易读元素。
- `androidtestclii element click --text ... --json` 能执行语义点击，或返回稳定错误。
- `androidtestclii element set-text ... --json` 能输入文本，或返回稳定错误。
- `androidtestclii screen screenshot --out ... --json` 写入截图 artifact 并返回路径。
- 每条命令 stdout 都是合法 JSON。
- 不暴露任意 Python eval 能力。

---

## 详细实施计划

以下是上文路线图的可执行版本。每节都给出落地决策，避免实现期再做选择。

### A. 技术选型

- **Python**：`>=3.10`，与 `uiautomator2` 现版本兼容，且支持 `match`、`X | None` 类型语法。
- **CLI 框架**：`typer >= 0.12`（基于 click，type hint 自然映射 subcommand）。
- **数据校验**：`pydantic >= 2`（selector / result / dump 节点模型）。
- **设备 SDK**：`uiautomator2 >= 3`，传递依赖 `adbutils`。
- **进程级锁**：`filelock >= 3`。
- **打包**：`pyproject.toml` + `hatchling` 或 `setuptools`，开发期使用 `uv`。
- **测试**：`pytest`、`pytest-mock`、`typer.testing.CliRunner`。
- **静态检查**：`ruff`（lint+format）、`mypy`（在 `src/androidtestclii` 上 strict）。
- **入口**：`[project.scripts] androidtestclii = "androidtestclii.cli:app"`。

### B. 项目结构

```text
androidtestclii/
  pyproject.toml
  README.md
  src/androidtestclii/
    __init__.py
    __main__.py              # python -m androidtestclii 入口
    cli.py                   # typer 根 app + 全局 callback
    context.py               # CommandContext + 全局 flag 解析
    result.py                # CommandResult.success/failure，统一渲染
    errors.py                # ErrorCode 枚举、U2CliError、异常映射
    logging.py               # stderr 结构化 JSON logger
    locks.py                 # per-serial filelock 包装
    timeouts.py              # 把同步 u2 调用包到线程 + future.timeout
    device/
      connect.py             # u2.connect 缓存与重连
      health.py              # doctor / devices / info handler
    app/commands.py          # current/start/stop/clear/install/uninstall
    screen/
      dump.py                # full + compact projection
      screenshot.py
      size.py
    element/
      selector.py            # Selector 模型 + 解析 + 与 u2 locator 适配
      query.py               # find / wait
      action.py              # click / long-click / set-text / clear-text / get-text
    input/commands.py        # press / tap / swipe / text
    toast/commands.py
    pi/tool_schema.py        # 导出 Pi tool 描述（Phase 6）
  tests/
    conftest.py
    fixtures/
      hierarchy_*.xml
      contracts/*.json
    test_result.py
    test_errors.py
    test_selector.py
    test_dump_projection.py
    test_doctor.py
    test_devices.py
    test_app_commands.py
    test_element_*.py
    test_input_*.py
    test_toast.py
    test_locks.py
```

### C. 全局执行流

1. `cli.py` 注册根 `Typer`，使用 `@app.callback()` 解析 `--json/--serial/--timeout-ms/-v`。
2. callback 构造 `CommandContext` 并放入 `typer.Context.obj`。
3. 每个 handler 签名：`def handler(ctx: typer.Context, ...) -> None`，内部调用纯函数 `run(...) -> CommandResult`。
4. 渲染层只在 `cli.py` 的统一出口调用一次 `print(result.to_json())`。
5. handler 内 **禁止** `print`、`sys.stdout.write`，stderr 走 `logging.py`。
6. 进程退出码：成功 0；可恢复失败 1；INTERNAL_ERROR 2；INVALID_ARGUMENT 64。

### D. JSON 结果契约（实现层）

- `CommandResult` 字段固定顺序：`success, command, serial, via, data?, error?, artifacts, durationMs`。
- `via` MVP 恒为 `"uiautomator2"`；预留 sidecar 切换。
- `durationMs` 由 `time.perf_counter()` 在 callback 入口与渲染前计算。
- `artifacts` 元素结构：`{"type":"screenshot|file","path":"...","sizeBytes":N}`。
- 渲染规则：`json.dumps(..., ensure_ascii=False, separators=(",", ":"))`。

### E. 错误模型与异常映射

`U2CliError(code: ErrorCode, message: str, details: dict | None)`，handler 顶层 `try/except` 用如下表归一：

| 来源异常 | ErrorCode |
|---|---|
| `pydantic.ValidationError` / typer 参数错误 | `INVALID_ARGUMENT` |
| import 阶段失败（`uiautomator2`） | `U2_IMPORT_FAILED` |
| Python 版本不达标 | `PYTHON_ENV_INVALID` |
| `FileNotFoundError("adb")` / `adbutils.AdbError("adb not found")` | `ADB_NOT_FOUND` |
| `adbutils.AdbError("device offline")` | `DEVICE_OFFLINE` |
| 设备列表中无该 serial | `DEVICE_NOT_FOUND` |
| `uiautomator2.exceptions.ConnectError` / 启动 atx-agent 失败 | `U2_CONNECT_FAILED` |
| `uiautomator2.exceptions.UiObjectNotFoundError` | `ELEMENT_NOT_FOUND` |
| 自检命中多元素且未传 index | `ELEMENT_AMBIGUOUS` |
| 线程 future timeout / `concurrent.futures.TimeoutError` | `ACTION_TIMEOUT` |
| `uiautomator2.exceptions.GatewayError` 等动作失败 | `ACTION_FAILED` |
| 截图保存失败 / IO 错误 | `SCREENSHOT_FAILED` |
| toast 等待超时无消息 | `TOAST_TIMEOUT` |
| `app install/uninstall` adb 返回非 0 | `APP_ACTION_FAILED` |
| 其它未识别异常 | `INTERNAL_ERROR`（details 含 `exceptionType`、`traceback` 摘要） |

### F. Selector 模型与歧义策略

- pydantic `Selector` 模型，全部字段 Optional：`text, textContains, resourceId, description, descriptionContains, className, xpath, index`。
- 校验：
  - 至少一个非空字段，否则 `INVALID_ARGUMENT`。
  - `xpath` 仅与 `index` 共存；与其它字段同时给 → `INVALID_ARGUMENT`。
  - `resourceId` 接受 `package:id/name` 与裸 `name`；裸名做精确匹配但记录 warning。
- 转 u2：返回 `(kind, payload)`，`kind ∈ {u2, xpath}`，`u2` 时 `d(**payload)`，`xpath` 时 `d.xpath(payload["xpath"])[index]`。
- 歧义：`find/click/long-click/set-text/clear-text/get-text` 默认要求唯一命中：
  - `count == 0` → `ELEMENT_NOT_FOUND`。
  - `count > 1 && index is None` → `ELEMENT_AMBIGUOUS`，`details.matchCount`。
  - 显式 `--index N`：`N >= count` → `ELEMENT_NOT_FOUND`，`details.matchCount`。
- `element find` 总是返回 `matched, matchCount`，不视多命中为错误。

### G. Per-serial 串行锁

- 实现：`filelock.FileLock("${TMPDIR}/androidtestclii/locks/${serial}.lock")`。
- **加锁**命令集合：`app.start/stop/clear/install/uninstall`、`element.click/long-click/set-text/clear-text`、`input.press/tap/swipe/text`。
- **不加锁**命令：`doctor/devices/device info`、`screen.*`、`element.find/wait/get-text`、`toast.get/reset`。
- 等待预算 = `--timeout-ms`；获取不到 → `ACTION_TIMEOUT`，`details.lock="busy"`。
- 锁内调用结束立即释放，不复用跨命令。

### H. Timeout 实现

- 所有 u2 同步调用统一通过 `timeouts.run_with_timeout(fn, timeout_ms)`：
  - 用 `ThreadPoolExecutor(max_workers=1)` 跑 `fn`，`future.result(timeout_s)`。
  - 超时则尝试取消（u2 阻塞通常无法真正中断，记录 warning）。
- 默认值：
  - 读型命令 `5000ms`；
  - 变更型命令 `10000ms`；
  - `element wait` 必须显式 `--timeout-ms`，缺省 `5000ms`；
  - `toast get` 必须显式 `--timeout-ms`。

### I. Compact dump projection

输入：`d.dump_hierarchy()` 的 XML。输出：

```json
{
  "screenSize": [1080, 2400],
  "package": "com.example",
  "activity": ".MainActivity",
  "nodes": [
    {
      "id": 17,
      "cls": "Button",
      "text": "登录",
      "desc": null,
      "rid": "com.example:id/login",
      "bounds": [40, 1200, 720, 1320],
      "clickable": true,
      "enabled": true,
      "checked": false,
      "selected": false,
      "depth": 4,
      "parent": 12
    }
  ]
}
```

projection 规则：

- 解析 `bounds="[x1,y1][x2,y2]"` 为 4 元数组。
- 丢弃同时满足以下条件的节点：无 `text`、无 `content-desc`、无 `resource-id`、且 `clickable/long-clickable/scrollable/checkable` 全为 false。
- 父节点即使被丢弃，子节点仍按原始深度保留，`parent` 指向最近未被丢弃的祖先。
- `cls` 只保留最后一段（`android.widget.Button` → `Button`）。
- `text` 长度 > 200 截断，附加 `textTruncated: true`。
- `id` 为扁平后下标，可用作下一次命令的 `--index`。

### J. 日志契约（stderr）

- 单行 JSON：`{"ts","level","cmd","serial","msg","kv"}`。
- 默认 level=`warn`；`-v` → `info`；`-vv` → `debug`。
- handler 不得写 stdout；任何调试输出走 logger。

### K. 每命令 `data` 字段表

| 命令 | data 字段 |
|---|---|
| `doctor` | `python:{version,ok}, u2:{version,ok}, adb:{path,version,ok}, devices:[...], checks:[{name,ok,detail}]` |
| `devices` | `devices:[{serial,state,model,brand,sdk}]` |
| `device info` | `serial,model,brand,sdk,abi,display:{w,h,density},battery:{level,status}` |
| `app current` | `package,activity,pid` |
| `app start` | `package,launched:bool,activity?` |
| `app stop` | `package,stopped:bool` |
| `app clear` | `package,cleared:bool` |
| `app install` | `package?,apkPath,installed:bool` |
| `app uninstall` | `package,uninstalled:bool` |
| `screen dump` | 见 §I |
| `screen screenshot` | `path,width,height,bytes` + `artifacts:[{type:"screenshot",path,sizeBytes}]` |
| `screen size` | `width,height,density` |
| `element find` | `selector,matched:bool,matchCount,element?,nodeId?` |
| `element wait` | `selector,matched:bool,elapsedMs` |
| `element click` | `selector,clicked:bool,matchCount` |
| `element long-click` | `selector,clicked:bool,durationMs` |
| `element set-text` | `selector,setText:bool,text` |
| `element clear-text` | `selector,cleared:bool` |
| `element get-text` | `selector,text` |
| `input press` | `key,pressed:bool` |
| `input tap` | `x,y,tapped:bool` |
| `input swipe` | `from:[x,y],to:[x,y],durationMs,swiped:bool` |
| `input text` | `text,sent:bool` |
| `toast get` | `message?,timestamp?,timeoutHit:bool` |
| `toast reset` | `reset:bool` |

### L. 测试策略

- **纯函数层**：`result/errors/selector/dump projection/locks/timeouts` 全部独立测试，禁止依赖真机。
- **CLI 层**：`CliRunner` 跑每个 subcommand，至少 1 成功 + 1 失败。
- **u2 mock**：`tests/conftest.py` 提供 `fake_device` fixture，行为可注入（`text`、`exists`、`info`、`dump_hierarchy` 等）；通过 `monkeypatch` 替换 `u2.connect`。
- **契约 golden**：`tests/fixtures/contracts/<command>.success.json` / `.failure.json`，断言 schema 与关键字段（去除 `durationMs`）。
- **集成**：标 `@pytest.mark.integration`，需 `ANDROIDTESTCLII_TEST_SERIAL` 环境变量；CI 默认跳过。
- 覆盖率门槛：`src/androidtestclii` 行覆盖 ≥ 85%（不含 `pi/`）。

### M. CLI-Anything 接入策略

**采纳**：

- subcommand 树组织、`--json` 全局 flag 与渲染层位置。
- typed result helper 模板。
- pytest harness 模板与 `CliRunner` 用法。

**不采纳**（本项目自实现以保证设备语义正确）：

- 与设备相关的默认 timeout、重试、循环等待。
- 任意 Python / shell 执行能力。
- 任何与 selector 类似的 DSL，`androidtestclii` 自己定义。

**接入步骤**：

1. 用 CLI-Anything 脚手架生成 `androidtestclii` 包骨架，确认 `androidtestclii --help` 可跑。
2. 把脚手架自带示例命令删除，落入本计划 §B 的目录。
3. 替换其 result/error/logging 三个模块为本项目契约。
4. 保留其测试入口，新增 §L 中的 fixture/契约测试。

### N. 分阶段退出条件

- **Phase 1（骨架）**
  - `androidtestclii --json doctor` 返回合法 JSON（即便检查项为 stub）。
  - `androidtestclii --help` 列出全部 subcommand 占位。
  - `pytest` 运行 result/errors/CliRunner 烟雾测试全绿。
- **Phase 2（Device + App）**
  - 在无设备机器上 `androidtestclii --json devices` 返回 `devices: []`，退出码 0。
  - mock 设备下 `device info` 字段齐全。
  - `app current/start/stop/clear` 在 mock 下走通成功与 `APP_ACTION_FAILED` 路径。
- **Phase 3（Screen + Selector）**
  - 用 fixture XML 调 `screen dump --compact` 输出固定结构（golden 对齐）。
  - selector 解析每字段、xpath 互斥、ambiguity 三类用例全过。
- **Phase 4（Element + Input）**
  - `element click` 在 mock 下覆盖：成功、not_found、ambiguous、timeout。
  - `input swipe/tap/press/text` 全部接入 lock；并发抢占测试可证 `ACTION_TIMEOUT`。
- **Phase 5（Toast + 诊断）**
  - 无 toast 场景按 `--timeout-ms` 触发 `TOAST_TIMEOUT`。
  - 截图失败模拟下返回 `SCREENSHOT_FAILED` 且不污染 stdout。
  - `doctor` 真实返回 `python/u2/adb` 三块状态。
- **Phase 6（Pi 集成）**
  - 导出 `pi/tool_schema.py` JSON，字段窄于 CLI flag。
  - Pi 端能成功调用 `doctor` 与 `element click`，CLI 失败 JSON 转换为 Pi tool error。

### O. 风险与对策

- **u2 连接慢**：MVP 容忍；后续移入 sidecar（已在「后续」章节）。
- **u2 异常类型在版本间漂移**：异常映射集中在 `errors.py` + 兜底 `INTERNAL_ERROR`，并在 details 暴露 `exceptionType`，便于线上反查。
- **多 Agent 抢占同设备**：filelock + 命令级 timeout，宁可失败也不排队。
- **selector 易误命中**：默认严格唯一；放宽必须显式 `--index`。
- **Toast 在新版 u2 弱化**：保留命令面，缺数据时统一 `TOAST_TIMEOUT`。
- **截图大体积污染输出**：截图只走 `artifacts`，`data.bytes` 仅给大小，不内联 base64。
