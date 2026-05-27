# SDD 文档体系

本目录是 u2cli 后续需求、设计和任务拆解的唯一规范入口。所有影响产品行为、命令契约、错误码、数据结构、架构边界或测试验收的改动，都应先落到一个 SDD spec，再进入实现。

## 目录结构

```text
docs/sdd/
  README.md
  _template/
    requirements.md
    design.md
    tasks.md
  <spec-id>/
    requirements.md
    design.md
    tasks.md
```

当前 spec：

- [u2cli-core](./u2cli-core/requirements.md)：u2cli 已有 Android Agent CLI 核心契约。
- [agent-device-alignment](./agent-device-alignment/requirements.md)：对齐 agent-device 风格 CLI 体验。

## 文档职责

- `requirements.md` 只描述需求、边界和可验收行为，不写实现细节。
- `design.md` 描述满足需求的架构、模块、接口、数据契约、错误模型和测试策略。
- `tasks.md` 拆解可执行任务，必须能追踪到需求编号，并带验收检查。
- `README.md` 面向使用者，只保留安装、使用、当前命令说明和 SDD 入口链接。
- 根目录 `PLAN.md`、历史 PRD 可作为背景材料，但不再作为新改动的规范源。

## 编号规则

每个 spec 使用独立编号前缀：

- `REQ-<SPEC>-NNN`：需求。
- `DES-<SPEC>-NNN`：设计决策或设计章节。
- `TASK-<SPEC>-NNN`：实施任务。
- `TEST-<SPEC>-NNN`：验收或测试项。

示例：

```text
REQ-CORE-001 -> DES-CORE-001 -> TASK-CORE-001 -> TEST-CORE-001
REQ-ADA-001  -> DES-ADA-001  -> TASK-ADA-001  -> TEST-ADA-001
```

## 状态规则

每个 SDD 文件顶部必须包含：

- `Spec ID`
- `Status`
- `Owner`
- `Last Updated`
- `Source`、`Source Requirements` 或 `Source Design`

允许状态：

- `Draft`：草案，可讨论。
- `Review`：待评审，不建议并行实现。
- `Approved`：可作为实现依据。
- `Implemented`：对应任务已完成并验收。
- `Superseded`：被新的 spec 或版本替代。

## 改动流程

1. 判断改动是否影响行为契约、架构边界、命令面、错误码、数据 schema 或测试验收。
2. 若影响，先新增或更新对应 `docs/sdd/<spec-id>/requirements.md`。
3. 在 `design.md` 中补齐设计映射，说明涉及模块、接口、数据结构、兼容策略和风险。
4. 在 `tasks.md` 中增加任务，任务必须引用一个或多个 `REQ-*`。
5. 实现时只做 `tasks.md` 中覆盖的范围。
6. 完成后更新任务状态、验收项和必要的 README 使用说明。

## 追踪矩阵要求

每个 `tasks.md` 必须包含追踪矩阵，至少覆盖：

| Requirement | Design | Task | Verification |
|---|---|---|---|
| `REQ-...` | `DES-...` | `TASK-...` | `TEST-...` |

未进入追踪矩阵的需求视为未计划，未引用需求的任务视为范围外任务。

## 兼容性要求

u2cli 是 Agent 调用型 CLI，文档中的任何行为变更必须显式说明：

- stdout JSON 契约是否变化。
- stderr 日志契约是否变化。
- 命令退出码是否变化。
- 错误码集合是否变化。
- Pi tool schema 是否需要同步。
- 旧命令是否保持兼容。

## 新 spec 创建方式

复制 `_template` 目录下三个文件到 `docs/sdd/<spec-id>/`，再按以下顺序填写：

1. `requirements.md`
2. `design.md`
3. `tasks.md`

没有明确需求编号前，不应先写任务；没有设计映射前，不应开始实现跨模块改动。
