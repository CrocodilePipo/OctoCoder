const { spawnSync } = require("node:child_process");
const path = require("node:path");

const repoRoot = path.resolve(__dirname, "..", "..");
const clientRoot = path.join(repoRoot, "client");
const command = process.platform === "win32" ? process.env.ComSpec || "cmd.exe" : "npm";
const args = process.platform === "win32"
  ? ["/d", "/s", "/c", "npm.cmd run build"]
  : ["run", "build"];

const result = spawnSync(command, args, {
  cwd: clientRoot,
  stdio: "inherit",
  shell: false
});

if (result.error) {
  console.error(result.error.message);
}

if (result.status !== 0) {
  process.exit(result.status || 1);
}
