# u2cli

`u2cli` 是一个基于 `uiautomator2` 的 Android 自动化命令行工具。项目目标是把常用 Android 设备操作封装为稳定、可测试、适合 Agent / Pi tool 调用的 CLI。

```text
Pi tool -> u2cli -> uiautomator2 -> Android device
```

核心约定：

- stdout 永远只输出一个 JSON 对象。
- stderr 只用于日志和诊断。
- 选择器输入结构化并校验。
- 变更型命令按设备串行加锁。
- 错误码稳定，便于上层工具处理。
- 截图、录屏等文件产物通过显式路径返回。

## 目录

- [安装](#安装)
- [项目结构](#项目结构)
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
uv run u2cli --help
```

也可以在源码目录直接运行：

```bash
PYTHONPATH=src python -m u2cli --help
```

运行环境要求：

- Python `>=3.10`
- `adb` 已安装并在 `PATH` 中
- `uiautomator2 >= 3`
- 执行真机命令时需要在线 Android 设备或模拟器

## 项目结构

```text
u2cli/
├── PLAN.md
├── README.md
├── pyproject.toml
├── uv.lock
├── src/u2cli/
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

- `PLAN.md`：项目路线、命令面、JSON 契约、错误码和验收标准。
- `README.md`：面向使用者和维护者的项目说明。
- `pyproject.toml`：Python 包元数据、依赖、入口脚本、pytest/ruff/mypy 配置。
- `uv.lock`：`uv` 生成的依赖锁文件，保证开发环境可复现。
- `.gitignore`：忽略虚拟环境、缓存和构建产物。

核心模块：

- `src/u2cli/cli.py`：Typer CLI 入口，注册所有命令和全局参数，并负责统一 JSON 输出。
- `src/u2cli/context.py`：命令上下文，包括 `serial`、timeout、日志等级和耗时统计。
- `src/u2cli/result.py`：成功/失败 JSON 结果模型。
- `src/u2cli/errors.py`：稳定错误码、异常类型和异常归一化逻辑。
- `src/u2cli/locks.py`：按设备序列号创建文件锁，保证变更型命令串行执行。
- `src/u2cli/timeouts.py`：把同步 `uiautomator2` 调用包装成带 timeout 的执行单元。
- `src/u2cli/logging.py`：stderr JSON 日志辅助模块。

命令模块：

- `src/u2cli/device/`：设备发现、健康检查、设备信息、受限 shell、文件传输、剪贴板、logcat、网络状态。
- `src/u2cli/app/`：App 当前状态、列表、启动/停止、安装/卸载、清数据、权限、intent。
- `src/u2cli/screen/`：UI hierarchy dump、compact dump、截图、屏幕尺寸、方向、亮灭屏、解锁、通知栏、录屏。
- `src/u2cli/element/`：selector 模型、元素查找、等待、点击、长按、文本、bounds、滑动、拖拽、滚动。
- `src/u2cli/input/`：按键、keyevent、tap、swipe、drag、文本输入。
- `src/u2cli/toast/`：Toast 获取和重置。
- `src/u2cli/watcher/`：临时弹窗 watcher 的添加、运行和重置。
- `src/u2cli/session/`：当前执行模式和 sidecar 能力探测。
- `src/u2cli/pi/`：导出 Pi tool 可消费的工具 schema。

测试目录：

- `tests/conftest.py`：mock `uiautomator2` 设备、元素、Toast 和图片对象。
- `tests/test_commands.py`：CLI 命令级契约测试。
- `tests/test_selector.py`：selector 校验和转换测试。
- `tests/test_dump_projection.py`：compact dump XML 投影测试。
- `tests/test_locks_timeouts.py`：设备锁和 timeout 测试。
- `tests/test_result.py`：JSON 返回契约测试。

## 全局参数

```bash
u2cli --json <command>
u2cli --serial <device-id> <command>
u2cli --timeout-ms 5000 <command>
u2cli -v <command>
u2cli -vv <command>
```

说明：

- `--json` 用于兼容机器调用场景；当前默认输出 JSON。
- `--serial` 指定 Android 设备序列号。
- `--timeout-ms` 指定命令超时预算。
- `-v` / `-vv` 调整 stderr 日志详细程度。
- 全局参数可以放在子命令前后。

## 命令总览

### 健康检查和设备

```bash
u2cli doctor
u2cli devices
u2cli device info --serial emulator-5554
u2cli device shell --serial emulator-5554 --command "getprop ro.build.version.sdk"
u2cli device push --serial emulator-5554 --local ./file.txt --remote /sdcard/file.txt
u2cli device pull --serial emulator-5554 --remote /sdcard/file.txt --local ./file.txt
u2cli device clipboard-get --serial emulator-5554
u2cli device clipboard-set --serial emulator-5554 --text hello
u2cli device logcat --serial emulator-5554 --lines 200
u2cli device logcat --serial emulator-5554 --clear
u2cli device network --serial emulator-5554
```

`device shell` 只接受单条受限命令，会拒绝明显的 shell 串联符号。它用于受控诊断，不用于执行任意脚本。

### App 生命周期

```bash
u2cli app current --serial emulator-5554
u2cli app list --serial emulator-5554
u2cli app list --serial emulator-5554 --kind running
u2cli app info --serial emulator-5554 --package com.example.app
u2cli app start --serial emulator-5554 --package com.example.app
u2cli app launch --serial emulator-5554 --package com.example.app --activity .MainActivity
u2cli app stop --serial emulator-5554 --package com.example.app
u2cli app stop-all --serial emulator-5554
u2cli app clear --serial emulator-5554 --package com.example.app
u2cli app install --serial emulator-5554 --apk ./app.apk
u2cli app uninstall --serial emulator-5554 --package com.example.app
u2cli app grant --serial emulator-5554 --package com.example.app --permission android.permission.CAMERA
u2cli app revoke --serial emulator-5554 --package com.example.app --permission android.permission.CAMERA
u2cli app intent --serial emulator-5554 --package com.example.app --activity .MainActivity
u2cli app intent --serial emulator-5554 --action android.intent.action.VIEW --data https://example.com
```

### 屏幕观察和状态

```bash
u2cli screen dump --serial emulator-5554
u2cli screen dump --serial emulator-5554 --compact
u2cli screen screenshot --serial emulator-5554 --out ./artifacts/screen.png
u2cli screen size --serial emulator-5554
u2cli screen orientation --serial emulator-5554
u2cli screen orientation --serial emulator-5554 --set left
u2cli screen wake --serial emulator-5554
u2cli screen sleep --serial emulator-5554
u2cli screen unlock --serial emulator-5554
u2cli screen notification --serial emulator-5554 --action open
u2cli screen notification --serial emulator-5554 --action quick-settings
u2cli screen notification --serial emulator-5554 --action close
u2cli screen record --serial emulator-5554 --out ./artifacts/record.mp4 --duration-sec 10
```

`screen dump --compact` 会把原始 UI hierarchy XML 转换成 Agent 更容易读取的节点列表，包括节点 id、文本、resource id、bounds、状态、层级和父节点。

### 元素查询和操作

```bash
u2cli element find --serial emulator-5554 --text 登录
u2cli element exists --serial emulator-5554 --text 登录
u2cli element count --serial emulator-5554 --text 登录
u2cli element bounds --serial emulator-5554 --resource-id com.example:id/login
u2cli element wait --serial emulator-5554 --text 首页 --timeout-ms 10000
u2cli element click --serial emulator-5554 --text 登录
u2cli element long-click --serial emulator-5554 --text 删除
u2cli element set-text --serial emulator-5554 --resource-id com.example:id/email --text qa@example.com
u2cli element clear-text --serial emulator-5554 --resource-id com.example:id/email
u2cli element get-text --serial emulator-5554 --resource-id com.example:id/title
u2cli element swipe --serial emulator-5554 --resource-id com.example:id/list --direction up
u2cli element drag-to --serial emulator-5554 --text Item --x 500 --y 1200
u2cli element scroll-to --serial emulator-5554 --text Settings
```

### 输入手势

```bash
u2cli input press --serial emulator-5554 --key back
u2cli input keyevent --serial emulator-5554 --code 4
u2cli input tap --serial emulator-5554 --x 100 --y 200
u2cli input swipe --serial emulator-5554 --from 500,1600 --to 500,400 --duration-ms 400
u2cli input drag --serial emulator-5554 --from 100,200 --to 800,1200 --duration-ms 500
u2cli input text --serial emulator-5554 --text hello
```

### Toast

```bash
u2cli toast get --serial emulator-5554 --timeout-ms 3000
u2cli toast reset --serial emulator-5554
```

`toast get` 必须显式传入 `--timeout-ms`，因为 Toast 是短时信号。

### Watcher

```bash
u2cli watcher add --serial emulator-5554 --name allow --text Allow
u2cli watcher add --serial emulator-5554 --name ok --text OK --click-text OK
u2cli watcher run --serial emulator-5554
u2cli watcher reset --serial emulator-5554
```

Watcher 是对 `uiautomator2` watcher API 的轻量包装，主要用于授权弹窗、系统弹窗等短时 UI。

### Session 和 Pi

```bash
u2cli session info
u2cli session sidecar-start
u2cli pi schema
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

Pi extension 会自动注册 `u2cli_*` 工具，并复用现有 `u2cli` CLI 执行 Android 自动化逻辑。执行顺序是：

1. `U2CLI_BIN`
2. `PATH` 中的 `u2cli`
3. `uvx --from git+https://github.com/Funerr/u2cli.git u2cli`

如果要预先安装 CLI 本体：

```bash
uv tool install git+https://github.com/Funerr/u2cli
```

如果要使用自定义路径：

```bash
export U2CLI_BIN=/path/to/u2cli
```

Pi extension 的工具定义和 `u2cli pi schema` 共享 `src/u2cli/pi/tools.json`，避免 README、Python schema 和 TypeScript extension 维护多份命令列表。

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

变更型命令会按设备加文件锁，锁文件位于系统临时目录下的 `u2cli/locks`。这覆盖 App 变更、元素变更、输入手势、文件传输、剪贴板写入、屏幕状态变更等操作。

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
uv run --extra dev mypy src/u2cli
```

当前单元测试使用 mock 的 `uiautomator2` 设备，不依赖真机。真机集成测试建议后续使用 `U2CLI_TEST_SERIAL` 控制开启。

## GitHub

仓库地址：

```text
git@github.com:Funerr/u2cli.git
```

## English Summary

`u2cli` is an agent-friendly Android automation CLI built on top of
`uiautomator2`.

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
uv run u2cli --help
u2cli --serial emulator-5554 screen dump --compact
u2cli --serial emulator-5554 element click --text 登录
```
