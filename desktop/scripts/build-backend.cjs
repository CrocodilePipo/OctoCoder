const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const desktopRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(desktopRoot, "..");
const backendRoot = path.join(repoRoot, "herness");
const platformArch = `${process.platform}-${process.arch}`;
const distPath = path.join(desktopRoot, "backend-dist", platformArch);
const workPath = path.join(desktopRoot, ".pyinstaller-build", platformArch);
const specPath = path.join(desktopRoot, ".pyinstaller-spec", platformArch);
const uv = process.platform === "win32" ? path.join(backendRoot, ".tools", "uv.exe") : "uv";

fs.rmSync(distPath, { force: true, recursive: true });
fs.mkdirSync(distPath, { recursive: true });
fs.mkdirSync(workPath, { recursive: true });
fs.mkdirSync(specPath, { recursive: true });

const args = [
  "run",
  "--no-sync",
  "--with",
  "pyinstaller",
  "pyinstaller",
  "--noconfirm",
  "--clean",
  "--onedir",
  "--name",
  "octocoder-server",
  "--distpath",
  distPath,
  "--workpath",
  workPath,
  "--specpath",
  specPath,
  "--collect-all",
  "octocoder",
  path.join("octocoder", "__main__.py")
];

const env = {
  ...process.env,
  UV_CACHE_DIR: path.join(backendRoot, ".uv-cache"),
  UV_PYTHON_INSTALL_DIR: path.join(backendRoot, ".uv-python")
};

const result = spawnSync(uv, args, {
  cwd: backendRoot,
  env,
  stdio: "inherit",
  shell: false
});

if (result.status !== 0) {
  process.exit(result.status || 1);
}

const exeName = process.platform === "win32" ? "octocoder-server.exe" : "octocoder-server";
const exePath = path.join(distPath, "octocoder-server", exeName);
if (!fs.existsSync(exePath)) {
  console.error(`Expected backend executable was not created: ${exePath}`);
  process.exit(1);
}

console.log(`Backend built: ${exePath}`);
