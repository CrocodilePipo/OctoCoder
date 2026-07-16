const { app, BrowserWindow, Menu, dialog, ipcMain, shell, clipboard } = require("electron");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");

let mainWindow = null;
let backendProcess = null;
let backendPort = 0;
let backendLaunch = null;
let backendLog = "";
let resizeSession = null;

const MAX_RECENT_PROJECTS = 24;

const isWindows = process.platform === "win32";
const exeName = isWindows ? "octocoder-server.exe" : "octocoder-server";
const squirrelEvent = process.argv.find((arg) => arg.startsWith("--squirrel-"));

function handleSquirrelEvent() {
  if (!isWindows || !squirrelEvent) return false;

  const appFolder = path.dirname(process.execPath);
  const rootFolder = path.resolve(appFolder, "..");
  const updateExe = path.join(rootFolder, "Update.exe");
  const appExe = path.basename(process.execPath);
  const runUpdate = (args) => {
    try {
      spawn(updateExe, args, { detached: true, stdio: "ignore", windowsHide: true }).unref();
    } catch {
      // Squirrel handles missing Update.exe gracefully during partial installs.
    }
  };

  if (squirrelEvent === "--squirrel-install" || squirrelEvent === "--squirrel-updated") {
    runUpdate(["--createShortcut", appExe]);
  } else if (squirrelEvent === "--squirrel-uninstall") {
    runUpdate(["--removeShortcut", appExe]);
  }

  setTimeout(() => app.quit(), 1000);
  return true;
}

function platformArch() {
  return `${process.platform}-${process.arch}`;
}

function repoRoot() {
  return path.resolve(__dirname, "..", "..", "..");
}

function localWorkspaceRoot() {
  const candidates = [
    repoRoot(),
    path.resolve(process.resourcesPath || "", "..", "..", "..", "..")
  ];
  for (const candidate of candidates) {
    if (
      candidate &&
      fs.existsSync(path.join(candidate, "herness", "octocoder")) &&
      fs.existsSync(path.join(candidate, "client"))
    ) {
      return candidate;
    }
  }
  return null;
}

function hasProjectConfig(directory) {
  return fs.existsSync(path.join(directory, ".octocoder", "config.yaml"));
}

function projectsStorePath() {
  return path.join(app.getPath("userData"), "projects.json");
}

function logsDirectory() {
  return path.join(app.getPath("userData"), "logs");
}

function appendBackendLog(stream, chunk) {
  const line = `[${new Date().toISOString()}] [${stream}] ${chunk.toString()}`;
  backendLog = (backendLog + line).slice(-100000);
}

function writeBackendLogFile() {
  const directory = logsDirectory();
  fs.mkdirSync(directory, { recursive: true });
  const file = path.join(directory, "backend.log");
  fs.writeFileSync(file, backendLog || "No backend output captured yet.\n", "utf8");
  return file;
}

function projectName(projectPath) {
  const parsed = path.parse(projectPath);
  return path.basename(projectPath) || parsed.root || projectPath;
}

function projectInfo(projectPath) {
  const resolved = path.resolve(projectPath);
  return {
    name: projectName(resolved),
    path: resolved,
    lastOpened: Date.now()
  };
}

function readProjects() {
  try {
    const raw = fs.readFileSync(projectsStorePath(), "utf8");
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item.path === "string")
      .map((item) => ({
        name: typeof item.name === "string" && item.name ? item.name : projectName(item.path),
        path: path.resolve(item.path),
        lastOpened: Number(item.lastOpened || 0)
      }))
      .filter((item) => fs.existsSync(item.path) && fs.statSync(item.path).isDirectory())
      .sort((a, b) => b.lastOpened - a.lastOpened)
      .slice(0, MAX_RECENT_PROJECTS);
  } catch {
    return [];
  }
}

function writeProjects(projects) {
  const file = projectsStorePath();
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(projects.slice(0, MAX_RECENT_PROJECTS), null, 2), "utf8");
}

function rememberProject(projectPath) {
  if (!projectPath || !fs.existsSync(projectPath) || !fs.statSync(projectPath).isDirectory()) {
    throw new Error(`Project folder does not exist: ${projectPath || ""}`);
  }
  const next = projectInfo(projectPath);
  const projects = readProjects().filter((item) => path.resolve(item.path) !== next.path);
  projects.unshift(next);
  writeProjects(projects);
  return next;
}

function removeProject(projectPath) {
  const resolved = path.resolve(String(projectPath || ""));
  const projects = readProjects().filter((item) => path.resolve(item.path) !== resolved);
  writeProjects(projects);
  return projects;
}

function backendWorkingDirectory() {
  const explicit = process.env.OCTOCODER_BACKEND_CWD;
  if (explicit && fs.existsSync(explicit)) {
    return explicit;
  }

  const workspace = localWorkspaceRoot();
  if (workspace) {
    const herness = path.join(workspace, "herness");
    if (hasProjectConfig(herness)) {
      return herness;
    }
  }

  return app.getPath("userData");
}

function clientIndexPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "dist", "index.html");
  }
  return path.join(repoRoot(), "client", "dist", "index.html");
}

function packagedBackendPath() {
  const base = app.isPackaged
    ? path.join(process.resourcesPath, "backend-dist")
    : path.join(repoRoot(), "desktop", "backend-dist");
  return path.join(base, platformArch(), "octocoder-server", exeName);
}

function sourceBackendCommand(port) {
  const root = repoRoot();
  const herness = path.join(root, "herness");
  const uv = isWindows ? "uv.exe" : "uv";
  return {
    command: uv,
    args: ["run", "--no-sync", "octocoder", "--remote", "--host", "127.0.0.1", "--port", String(port)],
    cwd: herness,
    env: {
      ...process.env,
      UV_CACHE_DIR: path.join(herness, ".uv-cache"),
      UV_PYTHON_INSTALL_DIR: path.join(herness, ".uv-python")
    }
  };
}

function backendCommand(port) {
  const bundled = packagedBackendPath();
  if (fs.existsSync(bundled)) {
    return {
      command: bundled,
      args: ["--remote", "--host", "127.0.0.1", "--port", String(port)],
      cwd: backendWorkingDirectory(),
      env: process.env
    };
  }
  return sourceBackendCommand(port);
}

function getFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 18888;
      server.close(() => resolve(port));
    });
  });
}

function waitForStatus(port, timeoutMs = 30000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(`http://127.0.0.1:${port}/api/status`, (res) => {
        res.resume();
        if (res.statusCode === 200) {
          resolve();
          return;
        }
        retry();
      });
      req.on("error", retry);
    };
    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        reject(new Error("OctoCoder backend did not become ready in time."));
        return;
      }
      setTimeout(tick, 350);
    };
    tick();
  });
}

async function startBackend() {
  backendPort = await getFreePort();
  const launch = backendCommand(backendPort);
  backendLaunch = {
    command: launch.command,
    args: launch.args,
    cwd: launch.cwd
  };
  let backendReady = false;
  let stdoutLog = "";
  let stderrLog = "";
  const appendLog = (current, chunk) => (current + chunk.toString()).slice(-6000);
  const backendSummary = () => {
    const details = [stderrLog.trim(), stdoutLog.trim()].filter(Boolean).join("\n");
    return details ? `\n\nBackend output:\n${details}` : "";
  };

  backendProcess = spawn(launch.command, launch.args, {
    cwd: launch.cwd,
    env: launch.env,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"]
  });

  backendProcess.stdout.on("data", (chunk) => {
    appendBackendLog("stdout", chunk);
    stdoutLog = appendLog(stdoutLog, chunk);
    console.log(`[octocoder-server] ${chunk.toString().trimEnd()}`);
  });
  backendProcess.stderr.on("data", (chunk) => {
    appendBackendLog("stderr", chunk);
    stderrLog = appendLog(stderrLog, chunk);
    console.error(`[octocoder-server] ${chunk.toString().trimEnd()}`);
  });

  const exitBeforeReady = new Promise((resolve, reject) => {
    backendProcess.once("exit", (code, signal) => {
      console.log(`[octocoder-server] exited code=${code} signal=${signal}`);
      backendProcess = null;
      if (backendReady) {
        resolve();
        return;
      }
      reject(new Error(`OctoCoder backend exited before it became ready (code=${code}, signal=${signal}).${backendSummary()}`));
    });
  });

  try {
    await Promise.race([
      waitForStatus(backendPort, 90000).catch((error) => {
        throw new Error(`${error.message}${backendSummary()}`);
      }),
      exitBeforeReady
    ]);
    backendReady = true;
  } catch (error) {
    stopBackend();
    throw error;
  }
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 980,
    minHeight: 720,
    backgroundColor: "#ffffff",
    show: false,
    resizable: true,
    title: "OctoCoder",
    titleBarStyle: "hidden",
    titleBarOverlay: {
      color: "#f5f5f4",
      symbolColor: "#74777c",
      height: 32
    },
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });

  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  const devUrl = process.env.OCTOCODER_CLIENT_URL;
  const ws = `ws://127.0.0.1:${backendPort}/ws`;
  if (devUrl) {
    const url = new URL(devUrl);
    url.searchParams.set("ws", ws);
    await mainWindow.loadURL(url.toString());
  } else {
    const index = clientIndexPath();
    if (!fs.existsSync(index)) {
      throw new Error(`Client build not found: ${index}`);
    }
    await mainWindow.loadFile(index, { query: { ws } });
  }
}

function installAppMenu() {
  Menu.setApplicationMenu(null);
}

function getAppInfo() {
  return {
    name: app.getName(),
    version: app.getVersion(),
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node,
    platform: process.platform,
    arch: process.arch,
    userData: app.getPath("userData"),
    logsDir: logsDirectory(),
    backendPort,
    backendPid: backendProcess?.pid || null
  };
}

function resizeBounds(start, direction, deltaX, deltaY, minWidth, minHeight) {
  let { x, y, width, height } = start;

  if (direction.includes("e")) {
    width = start.width + deltaX;
  }
  if (direction.includes("s")) {
    height = start.height + deltaY;
  }
  if (direction.includes("w")) {
    width = start.width - deltaX;
    x = start.x + deltaX;
    if (width < minWidth) {
      x = start.x + start.width - minWidth;
      width = minWidth;
    }
  }
  if (direction.includes("n")) {
    height = start.height - deltaY;
    y = start.y + deltaY;
    if (height < minHeight) {
      y = start.y + start.height - minHeight;
      height = minHeight;
    }
  }

  return {
    x: Math.round(x),
    y: Math.round(y),
    width: Math.max(minWidth, Math.round(width)),
    height: Math.max(minHeight, Math.round(height))
  };
}

function installIpcHandlers() {
  ipcMain.handle("octocoder:get-projects", () => readProjects());

  ipcMain.handle("octocoder:remember-project", (_event, projectPath) => {
    return rememberProject(String(projectPath || ""));
  });

  ipcMain.handle("octocoder:remove-project", (_event, projectPath) => {
    return removeProject(String(projectPath || ""));
  });

  ipcMain.handle("octocoder:select-project", async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: "\u9009\u62e9 OctoCoder \u9879\u76ee\u6587\u4ef6\u5939",
      properties: ["openDirectory", "createDirectory"]
    });
    if (result.canceled || !result.filePaths.length) {
      return { canceled: true, projects: readProjects() };
    }
    const project = rememberProject(result.filePaths[0]);
    return { canceled: false, project, projects: readProjects() };
  });

  ipcMain.handle("octocoder:get-app-info", () => getAppInfo());

  ipcMain.handle("octocoder:copy-text", (_event, text) => {
    clipboard.writeText(String(text || ""));
  });

  ipcMain.handle("octocoder:edit", (event, command) => {
    const allowed = new Set(["undo", "redo", "cut", "copy", "paste", "selectAll"]);
    const name = String(command || "");
    if (!allowed.has(name)) return;
    const webContents = event.sender;
    if (typeof webContents[name] === "function") {
      webContents[name]();
    }
  });

  ipcMain.handle("octocoder:window-action", (event, action) => {
    const webContents = event.sender;
    const window = BrowserWindow.fromWebContents(webContents) || mainWindow;
    switch (String(action || "")) {
      case "quit":
        app.quit();
        break;
      case "reload":
        webContents.reloadIgnoringCache();
        break;
      case "toggleFullscreen":
        if (window) window.setFullScreen(!window.isFullScreen());
        break;
      case "toggleDevTools":
        if (webContents.isDevToolsOpened()) {
          webContents.closeDevTools();
        } else {
          webContents.openDevTools({ mode: "detach" });
        }
        break;
      case "zoomIn": {
        const factor = Math.min(2.5, Math.round((webContents.getZoomFactor() + 0.1) * 10) / 10);
        webContents.setZoomFactor(factor);
        break;
      }
      case "zoomOut": {
        const factor = Math.max(0.5, Math.round((webContents.getZoomFactor() - 0.1) * 10) / 10);
        webContents.setZoomFactor(factor);
        break;
      }
      case "zoomReset":
        webContents.setZoomFactor(1);
        break;
      default:
        break;
    }
  });

  ipcMain.handle("octocoder:resize-window-start", (event, direction) => {
    const window = BrowserWindow.fromWebContents(event.sender) || mainWindow;
    if (!window || window.isFullScreen()) {
      resizeSession = null;
      return;
    }
    const [minWidth, minHeight] = window.getMinimumSize();
    resizeSession = {
      window,
      direction: String(direction || ""),
      bounds: window.getBounds(),
      minWidth,
      minHeight
    };
  });

  ipcMain.handle("octocoder:resize-window-move", (_event, deltaX, deltaY) => {
    if (!resizeSession?.window || resizeSession.window.isDestroyed()) return;
    if (!/^(n|s|e|w|nw|ne|sw|se)$/.test(resizeSession.direction)) return;
    const bounds = resizeBounds(
      resizeSession.bounds,
      resizeSession.direction,
      Number(deltaX) || 0,
      Number(deltaY) || 0,
      resizeSession.minWidth || 980,
      resizeSession.minHeight || 720
    );
    resizeSession.window.setBounds(bounds);
  });

  ipcMain.handle("octocoder:resize-window-end", () => {
    resizeSession = null;
  });

  ipcMain.handle("octocoder:open-logs-folder", async () => {
    writeBackendLogFile();
    const directory = logsDirectory();
    fs.mkdirSync(directory, { recursive: true });
    const error = await shell.openPath(directory);
    if (error) {
      throw new Error(error);
    }
    return { path: directory };
  });

  ipcMain.handle("octocoder:export-diagnostics", async (_event, clientState) => {
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    const result = await dialog.showSaveDialog(mainWindow, {
      title: "\u5bfc\u51fa OctoCoder \u8bca\u65ad\u4fe1\u606f",
      defaultPath: `octocoder-diagnostics-${stamp}.json`,
      filters: [{ name: "JSON", extensions: ["json"] }]
    });
    if (result.canceled || !result.filePath) {
      return { canceled: true };
    }

    const backendLogFile = writeBackendLogFile();
    const payload = {
      generatedAt: new Date().toISOString(),
      app: getAppInfo(),
      backend: {
        launch: backendLaunch,
        pid: backendProcess?.pid || null,
        port: backendPort,
        logFile: backendLogFile,
        logTail: backendLog.slice(-20000)
      },
      desktop: {
        appPath: app.getAppPath(),
        executable: process.execPath,
        packaged: app.isPackaged,
        resourcesPath: process.resourcesPath
      },
      recentProjects: readProjects(),
      client: clientState || null
    };

    fs.writeFileSync(result.filePath, JSON.stringify(payload, null, 2), "utf8");
    return { canceled: false, filePath: result.filePath };
  });
}

async function boot() {
  try {
    await startBackend();
    await createWindow();
  } catch (error) {
    dialog.showErrorBox("OctoCoder failed to start", error instanceof Error ? error.message : String(error));
    app.quit();
  }
}

function stopBackend() {
  if (!backendProcess) return;
  const child = backendProcess;
  backendProcess = null;
  if (process.platform === "win32") {
    spawn("taskkill", ["/pid", String(child.pid), "/f", "/t"], { windowsHide: true });
  } else {
    child.kill("SIGTERM");
  }
}

if (!handleSquirrelEvent()) {
  app.whenReady().then(() => {
    installAppMenu();
    installIpcHandlers();
    return boot();
  });

  app.on("before-quit", stopBackend);

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow().catch((error) => {
        dialog.showErrorBox("OctoCoder failed to open", error instanceof Error ? error.message : String(error));
      });
    }
  });
}
