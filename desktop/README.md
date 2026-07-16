# OctoCoder Desktop

Electron shell for the OctoCoder React client and bundled Python backend.

## Development

Build the web client first:

```powershell
cd D:\ToolChain\OctoCoder\client
npm run build
```

Start the desktop app:

```powershell
cd D:\ToolChain\OctoCoder\desktop
npm install
npm start
```

In development, Electron starts the source backend with:

```text
uv run octocoder --remote --host 127.0.0.1 --port <free-port>
```

## Bundled Backend

Build the platform backend executable:

```powershell
cd D:\ToolChain\OctoCoder\desktop
npm run build:backend
```

The output is written to:

```text
desktop/backend-dist/<platform>-<arch>/octocoder-server/
```

## Installers

Create an unpacked desktop app for the current platform:

```powershell
npm run package
```

On Windows, create a Squirrel installer after the unpacked app is built:

```powershell
npm run make
```

`npm run package:forge` and `npm run make:forge` are kept as Electron Forge alternatives.
Windows, macOS, and Linux each need to be built on their target platform so PyInstaller can produce the correct backend binary.
