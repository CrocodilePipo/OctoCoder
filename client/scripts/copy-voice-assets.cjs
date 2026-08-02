const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const output = path.join(root, "public", "voice");
const files = [
  ["node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js", "vad.worklet.bundle.min.js"],
  ["node_modules/@ricky0123/vad-web/dist/silero_vad_v5.onnx", "silero_vad_v5.onnx"],
  ["node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs", "ort-wasm-simd-threaded.mjs"],
  ["node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm", "ort-wasm-simd-threaded.wasm"],
  ["node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.jsep.mjs", "ort-wasm-simd-threaded.jsep.mjs"],
  ["node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.jsep.wasm", "ort-wasm-simd-threaded.jsep.wasm"],
  ["voice-assets/octocoder-pcm-worklet.js", "octocoder-pcm-worklet.js"]
];

fs.mkdirSync(output, { recursive: true });
for (const [relativeSource, name] of files) {
  const source = path.join(root, relativeSource);
  if (!fs.existsSync(source)) {
    throw new Error(`Missing packaged voice asset: ${relativeSource}`);
  }
  fs.copyFileSync(source, path.join(output, name));
}

const outputNames = new Set(fs.readdirSync(output));
for (const [, name] of files) {
  if (!outputNames.has(name)) throw new Error(`Voice asset copy failed: ${name}`);
}
