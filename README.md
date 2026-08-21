# OctoCoder

[English](README.en.md)

OctoCoder 是一个本地 AI 编程助手项目，包含 Python 后端、React/Vite Web 客户端，以及 Electron 桌面客户端。桌面端会打包本地后端，用户打开软件后在设置里配置模型，即可选择本地项目并开始工作，不需要手动在终端里启动服务。

## 项目结构

```text
OctoCoder/
  herness/   Python 后端与终端 CLI
  client/    React + Vite + TypeScript 客户端
  desktop/   Electron 桌面壳、后端打包与安装包脚本
```

## 功能特性

- 终端 CLI：`uv run octocoder`
- 远程后端模式，供 Web/桌面客户端连接
- 类 Codex 的桌面界面，支持聊天、项目选择、模型配置、最近项目
- 桌面安装包内置本地后端
- Windows 桌面目录包与 Squirrel 安装包构建脚本

## 环境要求

- Python 3.11+
- `uv`
- Node.js 与 npm
- 当前安装包构建流程主要面向 Windows

Python 包配置位于 `herness/pyproject.toml`。Web 客户端和桌面壳分别在 `client/` 与 `desktop/` 目录下维护各自的 `package.json`。

## 后端

安装 Python 依赖：

```powershell
cd herness
uv sync
```

运行终端助手：

```powershell
uv run octocoder
```

以远程服务模式启动后端：

```powershell
uv run octocoder --remote
```

运行测试：

```powershell
uv run pytest
```

## 客户端

安装前端依赖：

```powershell
cd client
npm install
```

启动 Vite 开发服务：

```powershell
npm run dev
```

构建生产版客户端：

```powershell
npm run build
```

如果直接使用 Web 客户端，需要先启动后端远程服务。

## 桌面端

安装桌面端依赖：

```powershell
cd desktop
npm install
```

开发模式启动 Electron：

```powershell
npm start
```

构建 React 客户端和内置后端，并生成本地桌面应用目录：

```powershell
npm run package
```

生成 Windows 安装包：

```powershell
npm run make
```

常见输出路径：

```text
desktop/out/OctoCoder-win32-x64/OctoCoder.exe
desktop/out/make/squirrel.windows/x64/OctoCoderSetup.exe
desktop/backend-dist/win32-x64/
```

## 配置方式

新用户打开桌面客户端后，应先进入设置页配置模型服务。配置检测成功后，即可正常使用 OctoCoder。

桌面客户端支持：

- API Key 与模型配置
- 选择本地项目文件夹
- 不选择项目时，在默认工作路径内直接提问
- 最近项目列表
- 从帮助菜单导出诊断信息和打开日志目录

## 开发说明

- 后端代码放在 `herness/`。
- 前端 UI 代码放在 `client/`。
- Electron、打包、安装器相关代码放在 `desktop/`。
- 桌面端打包会复制构建后的 React 客户端，并把 PyInstaller 构建出的后端一并放入 Electron 应用。
- 平台相关的后端二进制文件需要在目标平台上构建。

## 常见问题

如果桌面端启动后端失败：

1. 打开“帮助 -> 导出诊断信息”。
2. 打开“帮助 -> 打开日志目录”。
3. 检查设置里的模型配置是否正确。
4. 确认内置后端存在于 `desktop/backend-dist/<platform>-<arch>/`。

如果提示找不到 `uv`，请将 `uv` 加入 `PATH`，或重新安装 `uv`。

如果安装包构建时在写入元数据后出现 warning，请先检查 `desktop/out/` 下是否已经生成了安装包和本地应用目录。

## Agent 评测与 EDD

OctoCoder 内置混合评测体系：`scripted` 模式用于离线、确定性的 PR 门禁，`real` 模式运行真实 Agent 和模型。两种模式共享事件规范、轨迹检查、结果检查、硬门禁和报告流水线。

`real` 模式会在隔离 fixture 中工作，但仍从启动评测命令的目录和用户目录读取现有 OctoCoder 配置；配置文件不会复制到 fixture 或评测产物中。环境变量凭据必须在 case 的 `execution.env_allowlist` 中显式声明。

校验全部 case 和 suite：

```powershell
cd herness
uv run octocoder-eval validate --all
```

运行无需密钥和网络的 smoke suite：

```powershell
uv run octocoder-eval run --suite smoke
```

运行单个失败参考 case，验证检查器能发现问题：

```powershell
uv run octocoder-eval run --case reference-forbidden-tool
```

比较基线和候选报告；发现回归时命令返回退出码 `3`：

```powershell
uv run octocoder-eval compare ../evals/baselines/smoke.json ../evals/runs/<run>/suite-report.json
```

评测定义放在 `evals/cases/`，不可变 fixture 放在 `evals/fixtures/`，suite 放在 `evals/suites/`。每次运行生成 case 快照、原始/规范化事件、工具轨迹、工作区 patch、stderr、分维度检查结果和 Markdown 报告。退出码：`0` 通过，`1` 评测失败，`2` Schema/框架错误，`3` 基线回归。

轨迹断言支持必需/禁用工具、参数 `equals`/`contains`/`matches`/`glob`/`exists`、调用次数、精确顺序、子序列、失败调用和重复调用上限。结果断言支持命令退出码、文件存在/缺失、文件内容、Git diff 和工作区边界。

EDD 规则：每次修复 Agent 行为缺陷，都要先新增一个能稳定复现缺陷的评测 case，再提交实现修复。

### 上下文管理评测

上下文用例在普通评测 case 上增加可选的 `context` 字段，以 stage 表达 setup、压力、checkpoint 和 resume。事实、有效/已废弃指令、任务状态、Token 容差、压缩要求和恢复前后等价字段都在 YAML 中声明；脚本模式直接提供确定性 checkpoint，真实模式要求 Agent 输出有界 JSON checkpoint。

```powershell
# PR 使用的离线门禁，无需 API Key 或网络
uv run octocoder-eval run --suite context-smoke

# 单独验证检查器会捕获过期事实
uv run octocoder-eval run --case context-stale-contamination

# 显式运行真实 Provider 的重复探针，可能产生费用
uv run octocoder-eval run --suite context-nightly
```

上下文维度包含事实保留、指令遵循、任务连续性、恢复一致性、Token 准确度、压缩效果和污染七类检查。关键事实/指令丢失、工具调用配对破坏、恢复分歧、上下文溢出和过期事实残留可设为硬门禁，任一硬门禁失败即判定失败。

每个上下文运行额外生成 `context-events.jsonl`、`context-checkpoints.json` 和 `context-metrics.json`。报告直接展示耗时、输入/输出 Token、Token 估算误差、压缩前后 Token、回收 Token、保留尾部、落盘字符数和压缩次数，不计算百分制总分或平均分；Provider 未上报 Token 时显示 `n/a`。事实保留、指令遵循、任务连续性和恢复一致性属于语义匹配指标，使用百分比表示。Suite 回归阈值使用失败运行增加数、耗时增加毫秒数、Token 增加数、工具调用增加数等绝对量；只有语义匹配下降使用比例阈值。

真实探针默认不进入 PR。GitHub Actions 只有在仓库变量 `OCTOCODER_REAL_CONTEXT_EVALS=true` 且定时任务或手动选择 `context-nightly` 时才执行。修复任何上下文行为缺陷时，先在 `evals/cases/context/` 添加稳定复现用例，再修改上下文算法。
