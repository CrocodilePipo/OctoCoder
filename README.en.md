# OctoCoder

[中文](README.md)

OctoCoder is a local AI coding assistant with a Python backend, a React/Vite web client, and an Electron desktop shell. The desktop app bundles the backend so users can open the client, configure their model settings, choose a local project, and start working without running terminal commands manually.

## Project Layout

```text
OctoCoder/
  herness/   Python backend and terminal CLI
  client/    React + Vite + TypeScript desktop/web client
  desktop/   Electron shell, backend bundling, and installers
```

## Features

- Terminal CLI: `uv run octocoder`
- Remote backend mode for the desktop/web client
- Codex-style desktop UI with chat, project picker, configurable model settings, and recent projects
- Bundled backend distribution for desktop installs
- Windows desktop package and Squirrel installer scripts

## Requirements

- Python 3.11+
- `uv`
- Node.js and npm
- Windows for the current packaged installer workflow

The Python package is configured in `herness/pyproject.toml`. The web client and desktop shell have separate `package.json` files under `client/` and `desktop/`.

## Backend

Install Python dependencies:

```powershell
cd herness
uv sync
```

Run the terminal assistant:

```powershell
uv run octocoder
```

Run the backend in remote mode for the client:

```powershell
uv run octocoder --remote
```

Run tests:

```powershell
uv run pytest
```

## Client

Install client dependencies:

```powershell
cd client
npm install
```

Start the Vite development server:

```powershell
npm run dev
```

Build the production client:

```powershell
npm run build
```

When using the web client directly, start the backend in remote mode first.

## Desktop

Install desktop dependencies:

```powershell
cd desktop
npm install
```

Start Electron in development:

```powershell
npm start
```

Build the React client and bundled backend, then create a local desktop app directory:

```powershell
npm run package
```

Create a Windows installer:

```powershell
npm run make
```

Common output paths:

```text
desktop/out/OctoCoder-win32-x64/OctoCoder.exe
desktop/out/make/squirrel.windows/x64/OctoCoderSetup.exe
desktop/backend-dist/win32-x64/
```

## Configuration

New users should open the desktop app and configure the model provider in Settings. After the configuration check succeeds, OctoCoder can be used immediately.

The desktop app supports:

- API key and model settings
- Selecting a local project folder
- Asking questions in the default working directory without selecting a project
- Recent projects
- Diagnostic export and log folder access from the Help menu

## Development Notes

- Keep backend code in `herness/`.
- Keep UI code in `client/`.
- Keep Electron, packaging, and installer code in `desktop/`.
- Desktop packaging copies the built React client and a PyInstaller-built backend into the Electron app.
- Build platform-specific backend binaries on the target platform.

## Troubleshooting

If the desktop app fails to start the backend:

1. Open Help -> Export Diagnostics.
2. Open Help -> Open Logs Folder.
3. Confirm model settings in Settings.
4. Confirm the bundled backend exists under `desktop/backend-dist/<platform>-<arch>/`.

If `uv` is not recognized, add it to `PATH` or install it again from the official installer.

If the installer build reports a metadata edit warning after writing artifacts, check whether the installer and unpacked app were still generated under `desktop/out/`.

## Agent Evaluations and EDD

OctoCoder includes a hybrid evaluation framework. `scripted` mode provides deterministic, offline PR gates; `real` mode runs the actual agent and model. Both modes share one event, trajectory, outcome, hard-gate, and reporting pipeline.

Real runs work inside an isolated fixture while still discovering OctoCoder configuration from the directory that launched the evaluation and from the user configuration directory. Configuration files are never copied into fixtures or artifacts. Environment-based credentials must be explicitly named in the case `execution.env_allowlist`.

```powershell
cd herness
uv run octocoder-eval validate --all
uv run octocoder-eval run --suite smoke
uv run octocoder-eval run --case reference-forbidden-tool
uv run octocoder-eval compare ../evals/baselines/smoke.json ../evals/runs/<run>/suite-report.json
```

Cases live under `evals/cases/`, immutable fixtures under `evals/fixtures/`, and suites under `evals/suites/`. Every run writes the case snapshot, raw and normalized events, canonical tool trajectory, workspace patch, stderr, per-dimension check verdicts, and a Markdown report. Exit codes are `0` for success, `1` for evaluation failure, `2` for schema/framework errors, and `3` for baseline regressions.

Trajectory expectations cover required and forbidden tools, argument operators, call counts, exact/subsequence order, failures, and repeated-call limits. Outcome checks cover command exits, file presence/content, Git diffs, and workspace boundaries.

EDD rule: every agent behavior fix must first add a deterministic evaluation case that reproduces the defect.

### Context Management Evaluations

Context cases extend a normal evaluation case with an optional `context` field. Stages represent setup, pressure, checkpoints, and resume. YAML expectations declare facts, active and superseded instructions, task state, token tolerances, compression limits, and fields that must remain equivalent across resume. Scripted cases provide deterministic checkpoints; real cases ask the Agent for bounded JSON checkpoints.

```powershell
# Offline PR gate; no API key or network required
uv run octocoder-eval run --suite context-smoke

# Prove stale-value contamination is detected
uv run octocoder-eval run --case context-stale-contamination

# Explicit repeated real-provider probes; may incur provider charges
uv run octocoder-eval run --suite context-nightly
```

The context dimension checks retention, instruction adherence, task continuity, resume consistency, token accuracy, compression behavior, and contamination separately. Critical fact or instruction loss, broken tool pairing, resume divergence, overflow, and stale-fact survival can be hard gates; any failed hard gate fails the run.

Context runs add `context-events.jsonl`, `context-checkpoints.json`, and `context-metrics.json`. Reports expose duration, input/output tokens, token-estimation error, before/after compaction tokens, reclaimed tokens, retained tail, spilled characters, and compaction count. They do not calculate a 100-point total or average; only semantic similarity metrics use percentages, and unreported provider usage is shown as `n/a`. Suite thresholds use absolute increases in failures, milliseconds, tokens, calls, and turns, while similarity drops remain ratios.

Real probes are excluded from pull requests by default. GitHub Actions runs them only when repository variable `OCTOCODER_REAL_CONTEXT_EVALS=true` and a schedule fires or `context-nightly` is selected manually. For every context-management defect, add a reproducing case under `evals/cases/context/` before changing the production algorithm.
