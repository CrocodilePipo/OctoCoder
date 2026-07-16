# OctoCoder Client

Codex-style web client for the OctoCoder Python service.

## Development

Start the service:

```powershell
cd D:\ToolChain\OctoCoder\herness
uv run octocoder --remote
```

Start the client in another terminal:

```powershell
cd D:\ToolChain\OctoCoder\client
npm install
npm run dev
```

Open `http://localhost:5173`.

## Production

Build the client:

```powershell
npm run build
```

Then run the service:

```powershell
cd D:\ToolChain\OctoCoder\herness
uv run octocoder --remote
```

The service will serve `client/dist` at `http://localhost:18888`.
