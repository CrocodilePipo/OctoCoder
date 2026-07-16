const fs = require("node:fs");
const path = require("node:path");
const { createWindowsInstaller, convertVersion } = require("electron-winstaller");

const desktopRoot = path.resolve(__dirname, "..");
const packageJson = require(path.join(desktopRoot, "package.json"));
const productName = packageJson.productName || "OctoCoder";
const platform = process.platform;
const arch = process.arch;

if (platform !== "win32") {
  console.log("[make-win] Skipping Windows installer because this host is not Windows.");
  process.exit(0);
}

const appDirectory = path.join(desktopRoot, "out", `${productName}-${platform}-${arch}`);
const outputDirectory = path.join(desktopRoot, "out", "make", "squirrel.windows", arch);

if (!fs.existsSync(path.join(appDirectory, `${productName}.exe`))) {
  throw new Error(`Packaged app is missing: ${appDirectory}`);
}

function normalizeSetupExe() {
  const preferred = path.join(outputDirectory, "OctoCoderSetup.exe");
  const fallback = path.join(outputDirectory, "Setup.exe");
  if (!fs.existsSync(preferred) && fs.existsSync(fallback)) {
    fs.renameSync(fallback, preferred);
  }
  return preferred;
}

function validateArtifacts() {
  const nupkgVersion = convertVersion(packageJson.version);
  const artifacts = [
    normalizeSetupExe(),
    path.join(outputDirectory, "RELEASES"),
    path.join(outputDirectory, `OctoCoder-${nupkgVersion}-full.nupkg`)
  ];

  for (const artifact of artifacts) {
    if (!fs.existsSync(artifact)) {
      throw new Error(`Installer artifact was not created: ${artifact}`);
    }
  }
}

async function main() {
  fs.rmSync(outputDirectory, { recursive: true, force: true });
  fs.mkdirSync(outputDirectory, { recursive: true });

  const options = {
    appDirectory,
    outputDirectory,
    authors: "OctoCoder",
    copyright: "Copyright 2026 OctoCoder",
    description: packageJson.description,
    exe: `${productName}.exe`,
    name: "OctoCoder",
    title: productName,
    version: packageJson.version,
    setupExe: "OctoCoderSetup.exe",
    noMsi: true,
    noDelta: true,
    skipUpdateIcon: true
  };

  try {
    await createWindowsInstaller(options);
  } catch (error) {
    try {
      validateArtifacts();
      console.warn(`[make-win] Squirrel reported a metadata edit error after writing artifacts: ${error.message}`);
    } catch {
      throw error;
    }
  }

  validateArtifacts();
  console.log(`[make-win] Wrote ${outputDirectory}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
