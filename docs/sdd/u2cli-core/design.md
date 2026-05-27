# u2cli Core Design

- **Spec ID**：`u2cli-core`
- **Status**：`Implemented`
- **Owner**：`u2cli maintainers`
- **Last Updated**：`2026-05-26`
- **Source Requirements**：`./requirements.md`

## Design Summary

u2cli 采用 Typer CLI + `uiautomator2` 执行内核。CLI 层负责参数解析、上下文构造、错误归一化和 JSON 渲染；命令模块负责具体 Android 能力；纯函数和适配层负责 selector、结果模型、锁、timeout、dump projection 和 Pi schema。

## Requirement Mapping

| Requirement | Design Section |
|---|---|
| `REQ-CORE-001` | `DES-CORE-001` |
| `REQ-CORE-002` | `DES-CORE-002` |
| `REQ-CORE-003` | `DES-CORE-003` |
| `REQ-CORE-004` | `DES-CORE-004` |
| `REQ-CORE-005` | `DES-CORE-005` |
| `REQ-CORE-006` | `DES-CORE-006` |
| `REQ-CORE-007` | `DES-CORE-007` |

## `DES-CORE-001`：统一 JSON 渲染

**Covers**：`REQ-CORE-001`

CLI 根入口负责构造命令上下文并统一渲染 `CommandResult`。handler 不直接写 stdout；诊断输出走 stderr logger。

顶层 JSON 字段顺序：

```text
success, command, serial, via, data|error, artifacts, durationMs
```

`via` 默认为 `uiautomator2`，保留 sidecar 或 backend 扩展空间。

## `DES-CORE-002`：核心命令模块

**Covers**：`REQ-CORE-002`

模块边界：

- `device/`：设备发现、健康检查、设备信息、受限 shell、文件传输、剪贴板、logcat、网络状态。
- `app/`：当前 App、列表、启动、停止、安装、卸载、清数据、权限、intent。
- `screen/`：UI hierarchy dump、compact dump、截图、尺寸、方向、亮灭屏、解锁、通知栏、录屏。
- `element/`：selector、查找、等待、点击、长按、文本、bounds、滑动、拖拽、滚动。
- `input/`：按键、keyevent、tap、swipe、drag、文本输入。
- `toast/`：Toast 获取和重置。
- `watcher/`：临时弹窗 watcher。
- `session/`：执行模式和 sidecar 能力探测。
- `pi/`：Pi tool schema 导出。

## `DES-CORE-003`：Selector 和歧义策略

**Covers**：`REQ-CORE-003`

Selector 使用结构化模型，字段包括：

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

校验规则：

- 至少一个非空字段。
- `xpath` 只能与 `index` 共存，不能和普通 selector 字段混用。
- 变更型元素命令默认要求唯一命中。
- 多命中且未传 `index` 返回 `ELEMENT_AMBIGUOUS`。
- 显式 `index` 越界返回稳定错误。

## `DES-CORE-004`：锁和 timeout

**Covers**：`REQ-CORE-004`

变更型命令按 serial 使用文件锁，锁目录位于系统临时目录下的 `u2cli/locks`。读命令不加锁。

所有同步设备调用通过 timeout 包装；锁等待也计入 timeout 预算。timeout 失败统一返回 `ACTION_TIMEOUT`。

默认 timeout：

- 读命令：`5000ms`。
- 变更型命令：`10000ms`。
- `toast get`：必须显式传入 `--timeout-ms`。

## `DES-CORE-005`：错误模型和退出码

**Covers**：`REQ-CORE-005`

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

- `0`：成功。
- `1`：可恢复命令失败。
- `2`：内部错误。
- `64`：参数错误。

## `DES-CORE-006`：Artifact 返回

**Covers**：`REQ-CORE-006`

截图、录屏和文件产物写入调用方指定路径或明确 artifact 路径。JSON 返回路径、类型、大小等元数据，不在 stdout 内联二进制内容。

## `DES-CORE-007`：Pi schema

**Covers**：`REQ-CORE-007`

Pi extension 使用紧凑工具 schema 包装 CLI 命令。工具定义应集中维护，避免 README、Python 和 TypeScript extension 各自维护命令列表。

## Data Contracts

成功：

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

## Testing Strategy

- `TEST-CORE-001` 至 `TEST-CORE-015` 覆盖在 CLI 契约测试、selector 测试、dump projection 测试、锁和 timeout 测试、result 测试、Pi schema 测试中。
- mock `uiautomator2` 设备用于默认单元测试。
- 真机集成测试应使用显式环境变量启用，默认不阻塞普通开发。

## Risks

- `uiautomator2` 异常类型可能随版本漂移：异常映射集中处理，并在 `details` 中保留 `exceptionType`。
- 多 Agent 抢占同设备：命令级 filelock 和 timeout 以失败优先，不做无限排队。
- Selector 误命中：默认严格唯一，放宽必须显式 `index`。
