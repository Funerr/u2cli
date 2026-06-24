# AndroidTestClii

本项目是面向 Agent / Pi tool 的 Android 自动化 CLI。对外推荐入口是 `AndroidTestClii`，目标是覆盖 Android 设备观察、操作、诊断、回放和调试等常用能力，并持续追赶 `agent-device` 风格 CLI 的能力面。

项目的规范产品名、CLI 入口和内部实现包已经迁移为 `AndroidTestClii` / `androidtestclii`。旧命令和旧 Python 导入名 `u2cli` 继续作为兼容入口保留。部分场景仍基于 `uiautomator2` 执行，因为这是当前可稳定落地的 Android 执行层；同时项目已经引入 ADB、snapshot helper、JAR snapshot 等后端，后续能力会按 `agent-device` catch-up backlog 扩展，而不是把项目定位限制在 u2 wrapper。

```text
Pi tool -> AndroidTestClii -> Android backend -> Android device
```

核心约定：

- stdout 永远只输出一个 JSON 对象。
- stderr 只用于日志和诊断。
- 选择器输入结构化并校验。
- 变更型命令按设备串行加锁。
- 错误码稳定，便于上层工具处理。
- 截图、录屏等文件产物通过显式路径返回。
- 每条成功结果都会在 `data.metadata.capabilityLayer` 披露实际能力层，并包含 fallback/degraded/failureStage/recoveryHint 诊断字段。

## 目录

- [安装](#安装)
- [定位和兼容性](#定位和兼容性)
- [项目结构](#项目结构)
- [文档规范](#文档规范)
- [全局参数](#全局参数)
- [命令总览](#命令总览)
- [Pi integration](#pi-integration)
- [Selector 规则](#selector-规则)
- [JSON 返回契约](#json-返回契约)
- [错误码和退出码](#错误码和退出码)
- [并发和超时](#并发和超时)
- [开发和测试](#开发和测试)
- [English Summary](#english-summary)

## 安装

推荐使用 `uv`：

```bash
uv sync --extra dev
uv run AndroidTestClii --help
```

也可以在源码目录直接运行：

```bash
PYTHONPATH=src python -m androidtestclii --help
```

运行环境要求：

- Python `>=3.10`
- `adb` 已安装并在 `PATH` 中
- `uiautomator2 >= 3`
- 执行真机命令时需要在线 Android 设备或模拟器

## 定位和兼容性

- `AndroidTestClii` 是新的推荐 CLI 名称。
- `androidtestclii` 是小写推荐别名，`android-cli` 和 `u2cli` 是兼容 CLI 名称；`u2cli` 也继续作为旧 Python 导入代理和历史 spec 命名，不代表项目只做 uiautomator2 包装。
- 当前元素操作、watcher、部分 Toast 场景仍使用 `uiautomator2`，因为这些路径已有稳定实现和测试覆盖。
- 多窗口 snapshot、Toast history、ADB fast path、JAR snapshot 等能力已经脱离单纯 u2 API。
- 追赶 `agent-device` 能力面的新增工作记录在 [agent-device-catchup](docs/sdd/agent-device-catchup/requirements.md)，包括 logs、trace、perf、settings、push、replay、test、视觉 diff 和 overlay refs 等。

## 项目结构

```text
androidtestclii/
├── PLAN.md
├── docs/sdd/
├── README.md
├── pyproject.toml
├── uv.lock
├── android-snapshot-helper/
├── android-snapshot-jar/
├── scripts/
├── src/androidtestclii/
│   ├── cli.py
│   ├── context.py
│   ├── result.py
│   ├── errors.py
│   ├── locks.py
│   ├── timeouts.py
│   ├── logging.py
│   ├── device/
│   ├── app/
│   ├── screen/
│   ├── element/
│   ├── input/
│   ├── toast/
│   ├── watcher/
│   ├── session/
│   └── pi/
└── tests/
```

顶层文件：

- `docs/sdd/`：SDD 规范源，后续需求、设计、任务和验收追踪以这里为准。
- `PLAN.md`：历史项目路线和早期设计材料；新改动应迁移到 SDD spec。
- `README.md`：面向使用者和维护者的项目说明。
- `pyproject.toml`：Python 包元数据、依赖、入口脚本、pytest/ruff/mypy 配置。
- `uv.lock`：`uv` 生成的依赖锁文件，保证开发环境可复现。
- `.gitignore`：忽略虚拟环境、缓存和构建产物。
- `android-snapshot-helper/`：与 agent-device 对齐的 instrumentation APK helper，用于多窗口 accessibility snapshot 和 Toast history。
- `android-snapshot-jar/`：可选的 no-install JAR snapshot 后端，不能捕获 Toast history。
- `scripts/`：构建 Android helper/JAR artifact 的脚本。

## 文档规范

本项目采用 SDD（Specification-Driven Development）组织后续需求和设计：

- SDD 入口：[docs/sdd/README.md](docs/sdd/README.md)
- 核心 CLI 契约：[docs/sdd/androidtestclii-core/requirements.md](docs/sdd/androidtestclii-core/requirements.md)
- agent-device 对齐规格：[docs/sdd/agent-device-alignment/requirements.md](docs/sdd/agent-device-alignment/requirements.md)

任何影响命令行为、JSON 契约、错误码、数据结构、架构边界或测试验收的改动，都应先更新对应 SDD spec，再进入实现。旧的 `PLAN.md` 和 PRD 文档保留为背景材料，不再作为新改动的规范源。

核心模块：

- `src/androidtestclii/cli.py`：Typer CLI 入口，注册所有命令和全局参数，并负责统一 JSON 输出。
- `src/androidtestclii/context.py`：命令上下文，包括 `serial`、timeout、日志等级和耗时统计。
- `src/androidtestclii/result.py`：成功/失败 JSON 结果模型。
- `src/androidtestclii/errors.py`：稳定错误码、异常类型和异常归一化逻辑。
- `src/androidtestclii/locks.py`：按设备序列号创建文件锁，保证变更型命令串行执行。
- `src/androidtestclii/timeouts.py`：把同步 `uiautomator2` 调用包装成带 timeout 的执行单元。
- `src/androidtestclii/logging.py`：stderr JSON 日志辅助模块。

命令模块：

- `src/androidtestclii/device/`：设备发现、健康检查、设备信息、受限 shell、文件传输、剪贴板、logcat、网络状态。
- `src/androidtestclii/app/`：App 当前状态、列表、启动/停止、安装/卸载、清数据、权限、intent。
- `src/androidtestclii/screen/`：UI hierarchy dump、compact dump、截图、屏幕尺寸、方向、亮灭屏、解锁、通知栏、录屏。
- `src/androidtestclii/element/`：selector 模型、元素查找、等待、点击、长按、文本、bounds、滑动、拖拽、滚动。
- `src/androidtestclii/input/`：按键、keyevent、tap、swipe、drag、文本输入。
- `src/androidtestclii/toast/`：Toast 获取和重置。
- `src/androidtestclii/watcher/`：临时弹窗 watcher 的添加、运行和重置。
- `src/androidtestclii/session/`：当前执行模式和 sidecar 能力探测。
- `src/androidtestclii/pi/`：导出 Pi tool 可消费的工具 schema。

测试目录：

- `tests/conftest.py`：mock `uiautomator2` 设备、元素、Toast 和图片对象。
- `tests/test_commands.py`：CLI 命令级契约测试。
- `tests/test_selector.py`：selector 校验和转换测试。
- `tests/test_dump_projection.py`：compact dump XML 投影测试。
- `tests/test_locks_timeouts.py`：设备锁和 timeout 测试。
- `tests/test_result.py`：JSON 返回契约测试。

## 全局参数

```bash
AndroidTestClii --json <command>
AndroidTestClii --serial <device-id> <command>
AndroidTestClii --timeout-ms 5000 <command>
AndroidTestClii -v <command>
AndroidTestClii -vv <command>
```

说明：

- `--json` 用于兼容机器调用场景；当前默认输出 JSON。
- `--serial` 指定 Android 设备序列号。
- `--timeout-ms` 指定命令超时预算。
- `-v` / `-vv` 调整 stderr 日志详细程度。
- 全局参数可以放在子命令前后。

## 命令总览

### Agent-style 顶层命令

对齐 agent-device 风格后，AndroidTestClii 同时保留原有子命令树，并新增更适合 Agent 单步调用的扁平命令：

```bash
AndroidTestClii connect --serial emulator-5554
AndroidTestClii snapshot -i
AndroidTestClii snapshot capture --full --target-text "关于手机"
AndroidTestClii screenshot ./artifacts/screen.png --overlay-refs
AndroidTestClii diff screenshot ./artifacts/current.png --baseline ./artifacts/baseline.png --threshold 1% --out ./artifacts/diff.png
AndroidTestClii diff snapshot
AndroidTestClii logs start ./artifacts/run.log --restart
AndroidTestClii logs mark checkpoint
AndroidTestClii logs stop
AndroidTestClii trace start ./artifacts/trace.html
AndroidTestClii trace stop
AndroidTestClii perf collect --app com.example.app --out ./artifacts/perf.json
AndroidTestClii network --include summary --limit 20
AndroidTestClii settings animations off
AndroidTestClii settings permission grant com.example.app android.permission.CAMERA
AndroidTestClii push com.example.app '{"action":"com.example.PUSH","id":1}'
AndroidTestClii trigger-app-event screenshot_taken '{"id":1}'
AndroidTestClii boot --serial emulator-5554
AndroidTestClii ensure-simulator --serial emulator-5554 --boot
AndroidTestClii replay ./flows/login.ad --replay-env EMAIL=qa@example.com
AndroidTestClii test ./flows/*.ad --report-junit ./artifacts/replay.xml
AndroidTestClii gesture pan 100 200 0 -400 300
AndroidTestClii gesture replay --file ./artifacts/gesture.json
AndroidTestClii record start ./artifacts/recording.mp4
AndroidTestClii record stop
AndroidTestClii click @e0
AndroidTestClii fill @e0 qa@example.com
AndroidTestClii get text @e0
AndroidTestClii click text=登录
AndroidTestClii click 50 80
AndroidTestClii wait text 首页 3000
AndroidTestClii batch --steps '[{"command":"back"},{"command":"snapshot","flags":{"interactive":true}}]'
```

`connect --serial X` 会写入本地 session。之后命令若未显式传 `--serial`，会自动复用 session 中的 serial 和 timeout；显式 `--serial` 永远覆盖 session。可用 `session status` 查看 stale 诊断，`session list` 以 agent-device 兼容形式列出当前活动 session，`session clear` 清空。

`runtime status` 返回基础 ADB、snapshot helper、snapshot JAR、持久监听占位和最近 snapshot 状态；`runtime clear` 清理 runtime 状态但保留当前 session。`data.metadata` 中的 `capabilityLayer` 可能是 `adb-fast-path`、`pure-adb-ui-query`、`snapshot-helper`、`uiautomator2`、`persistent-accessibility`、`unknown` 或 `unsupported`。

`snapshot -i` / `screen dump --compact` 会给每个 compact 节点附加 canonical `ref: "@eN"`，返回 `snapshotId`、`rawArtifactPath`、`compactArtifactPath`、`refMapPath` 和 compact `nodes`。完整 raw XML、compact JSON 和 ref map 都会落盘；stdout 中只返回给 Agent 看的 compact presentation，不内联完整 raw dump。compact/default snapshot 明确 `snapshot.canProveAbsence=false`，未命中目标不能证明视口外目标不存在。`snapshot capture --full` 是显式 full 入口；当前后端若只能提供当前窗口诊断，会返回 `full=false`、`complete=false`、`canProveAbsence=false` 和 `coverageFailureReason`，不会伪造完整覆盖。`click @eN`、`fill @eN` 会优先使用缓存 bounds 中心点，`get text @eN` 会直接读缓存文本。普通位置参数 selector 支持 `text=...`、`id=...`、`testid=...`、`class=...`、`desc=...` 和裸文本。

`diff screenshot` 对两个本地 PNG 做像素级比较，输出 `changedPixels`、`diffRatio`、`thresholdRatio` 和 `passed`；指定 `--out` 时生成红色 diff overlay artifact。`diff snapshot` 会采集当前 compact snapshot，并与 session 中上一次 snapshot 的节点签名做 added/removed/common 对比。`screenshot --overlay-refs` 读取最近 snapshot 写入的 `refMap`，把 `@eN` bounds 标到截图上，并额外返回 `screenshot-overlay` artifact。

`logs start [path] --restart` 会清空 logcat 后写入 session marker，`logs stop` 读取 `logcat -d -v brief`，只保存 marker 之后的日志并返回 `logs` artifact。`logs clear` 清空 logcat，`logs mark <message>` 写入诊断标记，`logs path` 和 `logs doctor` 返回当前 capture 状态、默认 artifact 路径和下一步建议。

`trace start/stop` 使用 Android `atrace --async_start/--async_stop` 做 session 化采集，stop 时写入 trace artifact。`perf collect` 从 `/proc/meminfo`、`/proc/stat` 和 `ps -A` 采集一次性性能快照。顶层 `network` 从 logcat 或 `--log-path` 指定的 logs artifact 中提取 URL、HTTP method、status 和 duration，默认 `--include summary` 不返回 raw 行，`--include all` 保留原始日志片段。

`settings` 支持 `animations/wifi/airplane` 的写入后读回验证，以及 `settings permission grant|revoke <package> <permission>` 的 `dumpsys package` 验证。`push` 封装 Android broadcast，`trigger-app-event` 封装 deep-link `am start` 并解析启动输出。`boot` 和 `ensure-simulator` 不创建云设备，只确认 adb 设备在线并写入本地 session。

`replay <file.ad>` 执行最小 `.ad` 脚本格式：每行一条 `AndroidTestClii`/`androidtestclii` 兼容命令，支持 `context`、`env`、shell 风格引号和 `${VAR}`。失败时会基于最近 snapshot `refMap` 尝试 selector/ref healing，`--replay-update` 会备份并规范化脚本。`test <paths...>` 批量运行 replay，返回 passed/failed summary，`--report-junit` 写入 JUnit artifact；`# expect-screenshot baseline.png threshold=0.01` 会复用截图 diff 做视觉断言。

`gesture pan/fling/replay` 提供单指 fast path，`gesture record` 当前返回 replay JSON 模板和 structured unavailable。`screen multi-touch` 对单指 absolute payload 执行 replay；`screen pinch/expand` 和真多指形态返回 `available=false`、`unsupported=true` 和 fallback 建议。顶层 `record start/stop` 是 session 化后台录屏控制，区别于一次性 `screen record`。

HarmonyOS、React Native、React DevTools、cloud device 和 daemon 入口当前返回稳定 structured unsupported，不把未实现平台/生态能力伪装为可用。

常用顶层命令：

```bash
AndroidTestClii apps --kind all
AndroidTestClii appstate
AndroidTestClii open com.example.app --activity .MainActivity --relaunch
AndroidTestClii close com.example.app
AndroidTestClii back
AndroidTestClii home
AndroidTestClii app-switcher
AndroidTestClii rotate portrait
AndroidTestClii scroll down --pixels 500
AndroidTestClii alert accept --timeout-ms 3000
AndroidTestClii clipboard read
AndroidTestClii clipboard write hello
AndroidTestClii keyboard status
AndroidTestClii reinstall --app com.example.app --path ./app.apk
AndroidTestClii install-from-source ./app.apk
AndroidTestClii install-from-source https://example.com/app.apk
AndroidTestClii connection status
AndroidTestClii runtime status
AndroidTestClii session status
AndroidTestClii session list
```

### 健康检查和设备

```bash
AndroidTestClii doctor
AndroidTestClii devices
AndroidTestClii device info --serial emulator-5554
AndroidTestClii device shell --serial emulator-5554 --command "getprop ro.build.version.sdk"
AndroidTestClii device push --serial emulator-5554 --local ./file.txt --remote /sdcard/file.txt
AndroidTestClii device pull --serial emulator-5554 --remote /sdcard/file.txt --local ./file.txt
AndroidTestClii device clipboard-get --serial emulator-5554
AndroidTestClii device clipboard-set --serial emulator-5554 --text hello
AndroidTestClii device logcat --serial emulator-5554 --lines 200
AndroidTestClii device logcat --serial emulator-5554 --clear
AndroidTestClii device network --serial emulator-5554
```

`device shell` 只接受单条受限命令，会拒绝明显的 shell 串联符号。它用于受控诊断，不用于执行任意脚本。

### App 生命周期

```bash
AndroidTestClii app current --serial emulator-5554
AndroidTestClii app list --serial emulator-5554
AndroidTestClii app list --serial emulator-5554 --kind running
AndroidTestClii app info --serial emulator-5554 --package com.example.app
AndroidTestClii app start --serial emulator-5554 --package com.example.app
AndroidTestClii app launch --serial emulator-5554 --package com.example.app --activity .MainActivity
AndroidTestClii app stop --serial emulator-5554 --package com.example.app
AndroidTestClii app stop-all --serial emulator-5554
AndroidTestClii app clear --serial emulator-5554 --package com.example.app
AndroidTestClii app install --serial emulator-5554 --apk ./app.apk
AndroidTestClii app uninstall --serial emulator-5554 --package com.example.app
AndroidTestClii app grant --serial emulator-5554 --package com.example.app --permission android.permission.CAMERA
AndroidTestClii app revoke --serial emulator-5554 --package com.example.app --permission android.permission.CAMERA
AndroidTestClii app intent --serial emulator-5554 --package com.example.app --activity .MainActivity
AndroidTestClii app intent --serial emulator-5554 --action android.intent.action.VIEW --data https://example.com
```

### 屏幕观察和状态

```bash
AndroidTestClii screen dump --serial emulator-5554
AndroidTestClii screen dump --serial emulator-5554 --compact
AndroidTestClii screen dump --serial emulator-5554 --backend helper --helper-install-policy missing-or-outdated
AndroidTestClii screen dump --serial emulator-5554 --backend helper --helper-apk ./android-snapshot-helper/dist/androidtestclii-android-snapshot-helper-0.1.0.apk
AndroidTestClii screen dump --serial emulator-5554 --backend jar --snapshot-jar ./android-snapshot-jar/dist/androidtestclii-android-snapshot-jar-0.1.0.jar
AndroidTestClii screen dump --serial emulator-5554 --backend adb --compact
AndroidTestClii screen screenshot --serial emulator-5554 --out ./artifacts/screen.png
AndroidTestClii screen size --serial emulator-5554
AndroidTestClii screen orientation --serial emulator-5554
AndroidTestClii screen orientation --serial emulator-5554 --set left
AndroidTestClii screen wake --serial emulator-5554
AndroidTestClii screen sleep --serial emulator-5554
AndroidTestClii screen unlock --serial emulator-5554
AndroidTestClii screen notification --serial emulator-5554 --action open
AndroidTestClii screen notification --serial emulator-5554 --action quick-settings
AndroidTestClii screen notification --serial emulator-5554 --action close
AndroidTestClii screen record --serial emulator-5554 --out ./artifacts/record.mp4 --duration-sec 10
```

`screen dump` 默认使用 `--backend auto`。优先级是 APK helper、可选 no-install JAR、direct ADB `uiautomator dump`、最后回退到 `uiautomator2` 的 `dump_hierarchy()`。APK helper 使用与 agent-device 相同的 `com.callstack.androidtestclii.snapshothelper` 包名、`androidtestclii-snapshot-helper-v1` 协议和 `am instrument` 输出格式；它通过 `UiAutomation.getWindows()` 捕获多窗口 accessibility snapshot，并通过同包 `ToastAccessibilityService` 读取 Toast history。Toast capture 需要用户或设备策略启用该 AccessibilityService；未启用时 XML snapshot 仍可用，metadata 会返回 `toastCapture.status=disabled`。

helper APK 会按 `--helper-install-policy` 安装，默认 `missing-or-outdated`，也可以设为 `always` 或 `never`。可通过 `--helper-apk` 或 `ANDROIDTESTCLII_ANDROID_SNAPSHOT_HELPER_APK` 指定 APK。JAR 后端仅作为不需要安装 APK 的可选降级路径，可通过 `--snapshot-jar` 或 `ANDROIDTESTCLII_ANDROID_SNAPSHOT_JAR` 指定；它不提供 Toast history。

`screen dump --compact` 会把原始 UI hierarchy XML 转换成 Agent 更容易读取的 compact snapshot。返回对象包含 `snapshotId`、`rawArtifactPath`、`compactArtifactPath`、`refMapPath` 和 `nodes`；每个节点包含 `ref`、`text`、`contentDesc`、`resourceId`、`className`、`packageName`、`role`、`bounds`、`center`、可见/启用/可点击等状态、`actions`、`parentRef` 和 `stableKey`。raw XML 默认写入 `artifacts/snapshots/<snapshotId>/raw.xml`，compact JSON 和 ref map 分别写入同目录的 `compact.json` 和 `ref-map.json`，不会直接塞进返回体。

compact 降噪只做平台通用处理：保留可见或可交互节点以及必要 label/heading/nearby text，裁剪 invisible、zero-size、offscreen 和无语义 wrapper/container，并按 normalized signature 折叠重复 sibling。u2cli 不根据 test step intent、MemoryPack、keyPath、caseId、报告采纳规则或 healer recovery strategy 做业务语义筛选；这些仍属于 MobileTestAgent/Agent workflow。

### 元素查询和操作

```bash
AndroidTestClii element find --serial emulator-5554 --text 登录
AndroidTestClii element exists --serial emulator-5554 --text 登录
AndroidTestClii element count --serial emulator-5554 --text 登录
AndroidTestClii element bounds --serial emulator-5554 --resource-id com.example:id/login
AndroidTestClii element wait --serial emulator-5554 --text 首页 --timeout-ms 10000
AndroidTestClii element click --serial emulator-5554 --text 登录
AndroidTestClii element click --serial emulator-5554 --target '{"ref":"@e3","snapshotId":"2026-06-24T12-34-56.789Z-ab12cd34"}'
AndroidTestClii element long-click --serial emulator-5554 --text 删除
AndroidTestClii element set-text --serial emulator-5554 --resource-id com.example:id/email --text qa@example.com
AndroidTestClii element set-text --serial emulator-5554 --target '{"ref":"@e4","snapshotId":"2026-06-24T12-34-56.789Z-ab12cd34"}' --value qa@example.com
AndroidTestClii element clear-text --serial emulator-5554 --resource-id com.example:id/email
AndroidTestClii element get-text --serial emulator-5554 --resource-id com.example:id/title
AndroidTestClii element swipe --serial emulator-5554 --resource-id com.example:id/list --direction up
AndroidTestClii element drag-to --serial emulator-5554 --text Item --x 500 --y 1200
AndroidTestClii element scroll-to --serial emulator-5554 --text Settings
```

`element click`、`element set-text` 和 `element wait` 仍支持原有 selector flags，也支持 `--target` 传 selector 字符串、selector JSON 或 `{"ref":"@eN","snapshotId":"..."}`。ref 目标会通过 `refMapPath` 指向的 snapshot ref map 解析，优先使用 bounds center，必要时回退到 selector；ref 过期或不可解析时会返回包含 `code`、`message`、`snapshotId`、`ref`、`candidateRefs` 和 raw artifact 路径的结构化错误。

### 输入手势

```bash
AndroidTestClii input press --serial emulator-5554 --key back
AndroidTestClii input keyevent --serial emulator-5554 --code 4
AndroidTestClii input tap --serial emulator-5554 --x 100 --y 200
AndroidTestClii input swipe --serial emulator-5554 --from 500,1600 --to 500,400 --duration-ms 400
AndroidTestClii input drag --serial emulator-5554 --from 100,200 --to 800,1200 --duration-ms 500
AndroidTestClii input text --serial emulator-5554 --text hello
```

### Toast

```bash
AndroidTestClii toast get --serial emulator-5554 --timeout-ms 3000
AndroidTestClii toast reset --serial emulator-5554
```

`toast get` 必须显式传入 `--timeout-ms`，因为 Toast 是短时信号。

与 snapshot 统一的 Toast history 位于 APK helper 的 `toastCapture` metadata 中；这是对齐 agent-device 的路径。单独的 `toast get/reset` 仍保留 `uiautomator2` toast API 兼容行为。

### Watcher

```bash
AndroidTestClii watcher add --serial emulator-5554 --name allow --text Allow
AndroidTestClii watcher add --serial emulator-5554 --name ok --text OK --click-text OK
AndroidTestClii watcher run --serial emulator-5554
AndroidTestClii watcher reset --serial emulator-5554
```

Watcher 是对 `uiautomator2` watcher API 的轻量包装，主要用于授权弹窗、系统弹窗等短时 UI。

### Session 和 Pi

```bash
AndroidTestClii session info
AndroidTestClii session clear
AndroidTestClii session sidecar-start
AndroidTestClii pi schema
```

当前实现是每条命令独立连接设备。`session sidecar-start` 会明确返回 sidecar 尚未实现，便于调用方探测能力边界。

`pi schema` 会导出一份面向 Pi tool 的紧凑工具描述。

## Pi integration

本仓库内置 Pi extension，可直接作为 Pi package 临时加载：

```bash
pi -e git:github.com/Funerr/u2cli
```

也可以安装到当前项目：

```bash
pi install -l git:github.com/Funerr/u2cli
```

固定到 tag 或 commit：

```bash
pi install -l git:github.com/Funerr/u2cli@<tag-or-commit>
```

Pi extension 会自动注册新的 `AndroidTestClii_*` 工具，同时保留旧的 `android_cli_*` 和 `u2cli_*` 工具作为兼容别名。执行顺序是：

1. `ANDROIDTESTCLII_BIN`
2. `ANDROID_CLI_BIN`
3. `U2CLI_BIN`
4. `PATH` 中的 `AndroidTestClii`
5. `PATH` 中的 `androidtestclii`
6. `PATH` 中的 `android-cli`
7. `PATH` 中的 `u2cli`
8. `uvx --from git+https://github.com/Funerr/u2cli.git AndroidTestClii`
9. `uvx --from git+https://github.com/Funerr/u2cli.git androidtestclii`
10. `uvx --from git+https://github.com/Funerr/u2cli.git android-cli`
11. `uvx --from git+https://github.com/Funerr/u2cli.git u2cli`

在带 subagent 角色的项目中，Pi extension 会读取 `PI_AGENT_ROLE` 收敛工具面：

- 未设置 `PI_AGENT_ROLE`：注册全部工具，适合独立使用。
- `PI_AGENT_ROLE=executor`：注册全部工具。
- `PI_AGENT_ROLE=planner` 或 `PI_AGENT_ROLE=healer`：只注册只读工具。
- 其他角色（例如 `memory`）：不注册 Android 设备工具。

如果宿主项目希望主控进程在未设置 `PI_AGENT_ROLE` 时不拿到设备工具，可在 `.pi/settings.json` 增加：

```json
{
  "AndroidTestClii": {
    "requireAgentRole": true
  }
}
```

也可以用环境变量 `ANDROIDTESTCLII_PI_REQUIRE_AGENT_ROLE=1` 或旧别名 `U2CLI_PI_REQUIRE_AGENT_ROLE=1` 达到同样效果。

如果要预先安装 CLI 本体：

```bash
uv tool install git+https://github.com/Funerr/u2cli
```

如果要使用自定义路径：

```bash
export ANDROIDTESTCLII_BIN=/path/to/androidtestclii
```

新集成推荐使用：

```bash
export ANDROIDTESTCLII_BIN=/path/to/AndroidTestClii
```

历史 `android-cli` 路径也继续可用：

```bash
export ANDROID_CLI_BIN=/path/to/android-cli
```

历史 `u2cli` 路径也继续可用：

```bash
export U2CLI_BIN=/path/to/u2cli
```

Pi extension 的工具定义和 `AndroidTestClii pi schema` 共享 `src/androidtestclii/pi/tools.json`，避免 README、Python schema 和 TypeScript extension 维护多份命令列表。

## Selector 规则

支持字段：

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

规则：

- 至少需要一个 selector 字段。
- `xpath` 只能和 `index` 共存，不能和普通 selector 字段混用。
- 默认要求变更型元素命令唯一命中；多命中会返回 `ELEMENT_AMBIGUOUS`。
- 只有显式传入 `--index` 时才会选择第 N 个匹配元素。
- `element find`、`element exists`、`element count` 是读命令，不要求唯一命中。

## JSON 返回契约

成功示例：

```json
{
  "success": true,
  "command": "element.click",
  "serial": "emulator-5554",
  "via": "uiautomator2",
  "data": {
    "selector": {"text": "登录"},
    "clicked": true,
    "matchCount": 1
  },
  "artifacts": [],
  "durationMs": 318
}
```

失败示例：

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

固定顶层字段：

- `success`
- `command`
- `serial`
- `via`
- `data` 或 `error`
- `artifacts`
- `durationMs`

## 错误码和退出码

稳定错误码：

```text
INVALID_ARGUMENT
PYTHON_ENV_INVALID
U2_IMPORT_FAILED
ADB_NOT_FOUND
DEVICE_NOT_FOUND
DEVICE_OFFLINE
U2_CONNECT_FAILED
APP_ACTION_FAILED
ELEMENT_NOT_FOUND
ELEMENT_AMBIGUOUS
ACTION_TIMEOUT
ACTION_FAILED
SCREENSHOT_FAILED
TOAST_TIMEOUT
INTERNAL_ERROR
```

退出码：

- `0`：成功
- `1`：可恢复命令失败
- `2`：内部错误
- `64`：参数错误

## 并发和超时

变更型命令会按设备加文件锁，锁文件位于系统临时目录下的 `androidtestclii/locks`。这覆盖 App 变更、元素变更、输入手势、文件传输、剪贴板写入、屏幕状态变更等操作。

默认超时：

- 读命令：`5000ms`
- 变更型命令：未显式设置时使用 `10000ms`
- `toast get`：必须显式设置 `--timeout-ms`

## 开发和测试

```bash
uv sync --extra dev
PYTHONPATH=src pytest -q
PYTHONPATH=src python -m ruff check .
PYTHONPATH=src python -m ruff format --check .
uv run --extra dev mypy src/androidtestclii
```

构建内置 Android snapshot helper：

```bash
scripts/build-android-snapshot-helper.sh 0.1.0
```

该脚本需要 `ANDROID_HOME` 或 `ANDROID_SDK_ROOT` 指向包含 `platforms/android-36` 和 build tools 的 Android SDK；未设置时会尝试 `/opt/homebrew/share/android-commandlinetools`。构建产物写入 `android-snapshot-helper/dist/`，并随 wheel 打包。

当前单元测试使用 mock 的 `uiautomator2` 设备，不依赖真机。真机集成测试建议后续使用 `ANDROIDTESTCLII_TEST_SERIAL` 控制开启。

## GitHub

仓库地址：

```text
git@github.com:Funerr/u2cli.git
```

## English Summary

This project is an agent-friendly Android automation CLI. The recommended
command is `AndroidTestClii`; `androidtestclii` is the lowercase alias, while
`android-cli` and `u2cli` remain compatibility commands. The canonical Python
package name is `androidtestclii`; `u2cli` remains a compatibility import proxy.

It provides structured JSON commands for:

- device health and diagnostics
- app lifecycle
- screen observation and screen state
- element query and actions
- input gestures
- toast capture
- watcher handling
- Pi tool schema export

Machine callers should parse stdout only. Every command returns a single JSON
object with stable fields and stable error codes. Mutating commands are
serialized per Android device by a file lock.

Quick start:

```bash
uv sync --extra dev
uv run AndroidTestClii --help
AndroidTestClii --serial emulator-5554 screen dump --compact
AndroidTestClii --serial emulator-5554 element click --text 登录
```
