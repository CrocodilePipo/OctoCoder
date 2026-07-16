const path = require("node:path");
const fs = require("node:fs");

const electronVersion = require("electron/package.json").version;
const electronZipDir = path.join(__dirname, ".npm-cache");
const electronZipName = `electron-v${electronVersion}-${process.platform}-${process.arch}.zip`;

const packagerConfig = {
  asar: true,
  executableName: "OctoCoder",
  extraResource: [
    path.join(__dirname, "..", "client", "dist"),
    path.join(__dirname, "backend-dist")
  ]
};

if (fs.existsSync(path.join(electronZipDir, electronZipName))) {
  packagerConfig.electronZipDir = electronZipDir;
}

module.exports = {
  packagerConfig,
  rebuildConfig: {},
  makers: [
    {
      name: "@electron-forge/maker-squirrel",
      config: {
        name: "OctoCoder",
        setupExe: "OctoCoderSetup.exe"
      }
    },
    {
      name: "@electron-forge/maker-zip",
      platforms: ["darwin", "win32", "linux"]
    },
    {
      name: "@electron-forge/maker-deb",
      config: {}
    },
    {
      name: "@electron-forge/maker-rpm",
      config: {}
    }
  ]
};
