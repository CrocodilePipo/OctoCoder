# OctoCoder

[English](README.en.md)

OctoCoder 是一个本地 AI 编程助手项目，包含 Python 后端、React/Vite Web 客户端，以及 Electron 桌面客户端。桌面端会打包本地后端，用户打开软件后在设置里配置模型，即可选择本地项目并开始工作，不需要手动在终端里启动服务。

## 项目结构

```text
OctoCoder/
  herness/   Python 后端与终端 CLI
  client/    React + Vite + TypeScript 客户端
  desktop/   Electron 桌面壳、后端打包与安装包脚本
```

## 功能特性

- 终端 CLI：`uv run octocoder`
- 远程后端模式，供 Web/桌面客户端连接
- 类 Codex 的桌面界面，支持聊天、项目选择、模型配置、最近项目
- 桌面安装包内置本地后端
- Windows 桌面目录包与 Squirrel 安装包构建脚本

## 环境要求

- Python 3.11+
- `uv`
- Node.js 与 npm
- 当前安装包构建流程主要面向 Windows

Python 包配置位于 `herness/pyproject.toml`。Web 客户端和桌面壳分别在 `client/` 与 `desktop/` 目录下维护各自的 `package.json`。

## 后端

安装 Python 依赖：

```powershell
cd herness
uv sync
```

运行终端助手：

```powershell
uv run octocoder
```

以远程服务模式启动后端：

```powershell
uv run octocoder --remote
```

运行测试：

```powershell
uv run pytest
```

## 客户端

安装前端依赖：

```powershell
cd client
npm install
```

启动 Vite 开发服务：

```powershell
npm run dev
```

构建生产版客户端：

```powershell
npm run build
```

如果直接使用 Web 客户端，需要先启动后端远程服务。

## 桌面端

安装桌面端依赖：

```powershell
cd desktop
npm install
```

开发模式启动 Electron：

```powershell
npm start
```

构建 React 客户端和内置后端，并生成本地桌面应用目录：

```powershell
npm run package
```

生成 Windows 安装包：

```powershell
npm run make
```

常见输出路径：

```text
desktop/out/OctoCoder-win32-x64/OctoCoder.exe
desktop/out/make/squirrel.windows/x64/OctoCoderSetup.exe
desktop/backend-dist/win32-x64/
```

## 配置方式

新用户打开桌面客户端后，应先进入设置页配置模型服务。配置检测成功后，即可正常使用 OctoCoder。

桌面客户端支持：

- API Key 与模型配置
- 选择本地项目文件夹
- 不选择项目时，在默认工作路径内直接提问
- 最近项目列表
- 从帮助菜单导出诊断信息和打开日志目录

## 开发说明

- 后端代码放在 `herness/`。
- 前端 UI 代码放在 `client/`。
- Electron、打包、安装器相关代码放在 `desktop/`。
- 桌面端打包会复制构建后的 React 客户端，并把 PyInstaller 构建出的后端一并放入 Electron 应用。
- 平台相关的后端二进制文件需要在目标平台上构建。

## 常见问题

如果桌面端启动后端失败：

1. 打开“帮助 -> 导出诊断信息”。
2. 打开“帮助 -> 打开日志目录”。
3. 检查设置里的模型配置是否正确。
4. 确认内置后端存在于 `desktop/backend-dist/<platform>-<arch>/`。

如果提示找不到 `uv`，请将 `uv` 加入 `PATH`，或重新安装 `uv`。

如果安装包构建时在写入元数据后出现 warning，请先检查 `desktop/out/` 下是否已经生成了安装包和本地应用目录。
