# OctoCoder 中文说明

仓库默认首页 [README.md](README.md) 已使用中文，本文件保留标准语言文件名，便于文档工具和外部链接识别。

## Agent 评测与 EDD

OctoCoder 使用混合评测模式：

- `scripted`：不调用模型，无需 API Key，可确定性重放工具事件和文件效果，适合 PR/CI 门禁。
- `real`：在隔离 fixture 中启动真实 OctoCoder 子进程，评估模型和 Agent 的实际表现。
- 两种模式使用相同的事件规范、轨迹检查、结果检查、分维度判定、硬门禁和报告格式。

```powershell
cd herness
uv run octocoder-eval validate --all
uv run octocoder-eval run --suite smoke
uv run octocoder-eval run --case reference-forbidden-tool
uv run octocoder-eval compare ../evals/baselines/smoke.json ../evals/runs/<run>/suite-report.json
```

目录约定：

- `evals/cases/`：版本化 YAML 任务定义。
- `evals/fixtures/`：每次运行都会复制的只读项目初始状态。
- `evals/suites/`：smoke、nightly、release 等任务集合和回归阈值。
- `evals/runs/`：生成的事件、轨迹、patch、判定结果和报告，不提交 Git。
- `evals/baselines/`：经审核后提交的基线报告。

轨迹断言支持必需/禁用工具、参数约束、次数限制、精确顺序和子序列。结果断言支持命令退出码、文件存在/缺失、内容匹配、Git diff 和工作区边界。安全禁用行为、必需检查和框架错误属于硬门禁，不能被平均分抵消。

退出码：`0` 通过，`1` 评测失败，`2` Schema/框架错误，`3` 检测到基线回归。

EDD 约束：修复 Agent 行为缺陷时，先添加一个稳定复现问题的评测 case，再修改实现，并把该 case 纳入合适的 suite。

## 上下文管理评测

上下文 case 使用可选 `context` 字段定义 setup、压力、checkpoint 和 resume 阶段，并声明关键事实、有效/已废弃指令、任务状态、Token 容差、压缩限制及恢复等价字段。`scripted` 提供确定性 checkpoint，`real` 使用同一 Schema 和检查/报告链路执行真实 Agent。

```powershell
uv run octocoder-eval run --suite context-smoke
uv run octocoder-eval run --case context-stale-contamination
# 显式 opt-in，可能产生 Provider 费用
uv run octocoder-eval run --suite context-nightly
```

context 维度分别检查事实保留、指令遵循、任务连续性、恢复一致性、Token 准确度、压缩效果和污染。报告使用具体耗时、Token、压缩量和检查数量；只有语义相似度使用百分比，Provider 未上报 Token 时显示 `n/a`。关键上下文丢失、工具调用配对破坏、恢复分歧、溢出或过期事实残留可声明为硬门禁。

运行产物额外包含 `context-events.jsonl`、`context-checkpoints.json`、`context-metrics.json`，报告会定位首次失败的 stage/checkpoint，并聚合保留率、Token 误差、压缩率和压缩次数。真实探针默认不进入 PR；GitHub Actions 仅在仓库变量 `OCTOCODER_REAL_CONTEXT_EVALS=true` 且定时或手动选择 `context-nightly` 时运行。

上下文 EDD 规则：先在 `evals/cases/context/` 新增可复现 case，再修改生产上下文算法。
