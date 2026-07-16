const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("octocoderDesktop", {
  isDesktop: true,
  platform: process.platform,
  arch: process.arch,
  selectProject: () => ipcRenderer.invoke("octocoder:select-project"),
  getProjects: () => ipcRenderer.invoke("octocoder:get-projects"),
  rememberProject: (projectPath) => ipcRenderer.invoke("octocoder:remember-project", projectPath),
  removeProject: (projectPath) => ipcRenderer.invoke("octocoder:remove-project", projectPath),
  edit: (command) => ipcRenderer.invoke("octocoder:edit", command),
  copyText: (text) => ipcRenderer.invoke("octocoder:copy-text", text),
  windowAction: (action) => ipcRenderer.invoke("octocoder:window-action", action),
  openLogsFolder: () => ipcRenderer.invoke("octocoder:open-logs-folder"),
  exportDiagnostics: (state) => ipcRenderer.invoke("octocoder:export-diagnostics", state),
  getAppInfo: () => ipcRenderer.invoke("octocoder:get-app-info"),
  resizeWindowStart: (direction) => ipcRenderer.invoke("octocoder:resize-window-start", direction),
  resizeWindowMove: (deltaX, deltaY) => ipcRenderer.invoke("octocoder:resize-window-move", deltaX, deltaY),
  resizeWindowEnd: () => ipcRenderer.invoke("octocoder:resize-window-end")
});
