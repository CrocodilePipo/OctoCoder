const fs = require("node:fs");
const path = require("node:path");

const desktopRoot = path.resolve(__dirname, "..");
const workspaceRoot = path.resolve(desktopRoot, "..");
const packageJson = require(path.join(desktopRoot, "package.json"));

const productName = packageJson.productName || "OctoCoder";
const platform = process.platform;
const arch = process.arch;
const outRoot = path.join(desktopRoot, "out");
const outDir = path.join(outRoot, `${productName}-${platform}-${arch}`);
const resourcesDir = path.join(outDir, "resources");

function assertInside(parent, target) {
  const rel = path.relative(parent, target);
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    throw new Error(`Refusing to write outside ${parent}: ${target}`);
  }
}

function copyDir(source, target) {
  if (!fs.existsSync(source)) {
    throw new Error(`Required build artifact is missing: ${source}`);
  }
  fs.cpSync(source, target, { recursive: true, force: true });
}

function electronExecutableName() {
  if (platform === "win32") return "electron.exe";
  if (platform === "linux") return "electron";
  throw new Error(`Local directory packaging is not implemented for ${platform}. Use Forge on this platform.`);
}

function appExecutableName() {
  if (platform === "win32") return `${productName}.exe`;
  if (platform === "linux") return productName;
  throw new Error(`Unsupported platform: ${platform}`);
}

async function decorateWindowsExecutable(exePath) {
  if (platform !== "win32") return;

  try {
    const { resedit } = require("@electron/packager/dist/resedit.js");
    await resedit(exePath, {
      productVersion: packageJson.version,
      fileVersion: packageJson.version,
      productName,
      win32Metadata: {
        CompanyName: "OctoCoder",
        FileDescription: productName,
        InternalName: productName,
        OriginalFilename: path.basename(exePath),
        ProductName: productName
      }
    });
  } catch (error) {
    console.warn(`[package-local] Windows metadata was not written: ${error.message}`);
  }
}

async function main() {
  const electronDist = path.join(desktopRoot, "node_modules", "electron", "dist");
  const sourceExe = path.join(electronDist, electronExecutableName());
  if (!fs.existsSync(sourceExe)) {
    throw new Error(`Electron runtime is missing: ${sourceExe}`);
  }

  assertInside(outRoot, outDir);
  fs.rmSync(outDir, { recursive: true, force: true });
  fs.mkdirSync(outDir, { recursive: true });

  copyDir(electronDist, outDir);

  const renamedExe = path.join(outDir, appExecutableName());
  fs.renameSync(path.join(outDir, electronExecutableName()), renamedExe);

  fs.rmSync(path.join(resourcesDir, "default_app.asar"), { force: true });

  const appDir = path.join(resourcesDir, "app");
  fs.mkdirSync(appDir, { recursive: true });
  copyDir(path.join(desktopRoot, "src"), path.join(appDir, "src"));
  fs.writeFileSync(
    path.join(appDir, "package.json"),
    `${JSON.stringify(
      {
        name: packageJson.name,
        productName,
        version: packageJson.version,
        description: packageJson.description,
        main: packageJson.main
      },
      null,
      2
    )}\n`
  );

  copyDir(path.join(workspaceRoot, "client", "dist"), path.join(resourcesDir, "dist"));
  copyDir(path.join(desktopRoot, "backend-dist"), path.join(resourcesDir, "backend-dist"));

  await decorateWindowsExecutable(renamedExe);
  console.log(`[package-local] Wrote ${outDir}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
