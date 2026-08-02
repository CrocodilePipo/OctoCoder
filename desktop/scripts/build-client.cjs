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

const fs = require("node:fs");
const requiredVoiceAssets = [
  "vad.worklet.bundle.min.js",
  "silero_vad_v5.onnx",
  "ort-wasm-simd-threaded.mjs",
  "ort-wasm-simd-threaded.wasm",
  "octocoder-pcm-worklet.js"
];
for (const name of requiredVoiceAssets) {
  const asset = path.join(clientRoot, "dist", "voice", name);
  if (!fs.existsSync(asset)) {
    console.error(`Missing built voice asset: ${asset}`);
    process.exit(1);
  }
}
