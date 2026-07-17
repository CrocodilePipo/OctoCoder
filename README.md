# OctoCoder

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
