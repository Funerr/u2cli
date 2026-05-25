# u2cli

`u2cli` is an agent-friendly Android automation CLI built on top of
`uiautomator2`. It turns high-value Android device operations into stable,
testable commands that always return a single JSON object on stdout.

```text
Pi tool -> u2cli -> uiautomator2 -> Android device
```

Diagnostics and logs belong on stderr. Machine-facing callers should parse only
stdout.

## Install

```bash
uv sync --extra dev
uv run u2cli --help
```

For editable local usage without installing the script:

```bash
PYTHONPATH=src python -m u2cli --help
```

Runtime requirements:

- Python `>=3.10`
- `adb` available on `PATH`
- `uiautomator2 >= 3`
- An online Android device or emulator for device-backed commands

## Global Options

```bash
u2cli --json <command>
u2cli --serial <device-id> <command>
u2cli --timeout-ms 5000 <command>
u2cli -v <command>
u2cli -vv <command>
```

`--json` is accepted for compatibility and JSON output is the default. Global
options may be placed before or after subcommands.

## Commands

### Health and Device

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

`device shell` is intentionally restricted to one command string and rejects
obvious shell chaining tokens. It is meant for bounded diagnostics, not arbitrary
script execution.

### App

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

### Screen

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

`screen dump --compact` projects raw UI hierarchy XML into an agent-readable
node list with ids, text, resource ids, bounds, state flags, depth, and parent
ids.

### Element

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

Selector fields:

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

Rules:

- At least one selector field is required.
- `xpath` may only be combined with `index`.
- Multi-match mutation commands fail with `ELEMENT_AMBIGUOUS` unless `--index`
  is provided.
- `element find`, `exists`, and `count` are read operations and do not require a
  unique match.

### Input

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

`toast get` requires an explicit timeout because toast messages are short-lived
signals.

### Watcher

```bash
u2cli watcher add --serial emulator-5554 --name allow --text Allow
u2cli watcher add --serial emulator-5554 --name ok --text OK --click-text OK
u2cli watcher run --serial emulator-5554
u2cli watcher reset --serial emulator-5554
```

Watcher commands are best-effort wrappers over uiautomator2 watcher APIs and are
intended for transient permission dialogs or system popups.

### Session and Pi

```bash
u2cli session info
u2cli session sidecar-start
u2cli pi schema
```

The current implementation uses per-command process execution. `session
sidecar-start` reports that sidecar mode is not implemented yet; this keeps the
CLI contract explicit for callers that want to probe for persistent connection
support.

`pi schema` exports a compact machine-readable tool schema for common wrappers.

## JSON Contract

Success:

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

Failure:

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

Stable error codes:

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

Exit codes:

- `0`: success
- `1`: recoverable command failure
- `2`: internal error
- `64`: invalid arguments

## Concurrency and Timeout

Mutating commands acquire a per-device file lock under the system temporary
directory. This covers app mutations, element mutations, input gestures, file
transfer, clipboard writes, screen state mutations, and related actions.

Read commands default to `5000ms`. Mutating commands default to `10000ms` when
`--timeout-ms` is not provided.

## Development

```bash
uv sync --extra dev
PYTHONPATH=src pytest -q
PYTHONPATH=src python -m ruff check .
PYTHONPATH=src python -m ruff format --check .
uv run --extra dev mypy src/u2cli
```

Real-device integration tests should be added behind `U2CLI_TEST_SERIAL`; the
current test suite uses mocked uiautomator2 devices and does not require an
Android device.

## Repository

Expected remote:

```bash
git remote add origin git@github.com:Funerr/u2cli.git
git branch -M main
git push -u origin main
```
