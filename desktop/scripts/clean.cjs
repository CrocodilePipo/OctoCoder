const fs = require("node:fs");
const path = require("node:path");

const desktopRoot = path.resolve(__dirname, "..");
for (const name of ["out", "backend-dist", ".pyinstaller-build", ".pyinstaller-spec", ".tmp"]) {
  fs.rmSync(path.join(desktopRoot, name), { force: true, recursive: true });
}
console.log("Cleaned desktop build output.");
