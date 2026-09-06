# codesys-mcp-inoproshop

一个由 AI 助手驱动 **InoProShop**（汇川 / Inovance，基于 CODESYS 的 IDE）的 MCP 服务器。它将 InoProShop 的脚本 API 暴露为 40+ 个工具与 3 个资源，并通过基于文件的 IPC watcher **在每次工具调用之间只保持一个 InoProShop 窗口常开**。

本项目是 [`codesys-mcp-persistent`](https://github.com/luke-harriman/Codesys-MCP)（luke-harriman）的改进分支，针对 InoProShop 做了适配，并修复了原 LIMIT 版 `InoProShop_LIMIT_MCP` 打包文件所患的**「每次调用都弹出新窗口」**缺陷。

## 相比原 LIMIT 打包文件改了什么

LIMIT 打包文件在**每次工具调用**时都新启一个 `InoProShop.exe --runscript=…`，拿到结果后再关掉——于是每来一个请求，IDE 就弹一个新窗口（并重新加载工程）。本分支只保留**一个常驻的 InoProShop 实例**：

- 只启动一个 `InoProShop.exe`（detached、无 shell），并在其内部运行一个 watcher 脚本。
- watcher 启动一个后台线程后就**返回**——释放 IDE 的 UI 线程，这样你可以在使用 AI 的同时继续操作 InoProShop。
- 每次工具调用都通过 `se.system.execute_on_primary_thread()` 调度到 IDE 的主线程执行，结果写入 `results/` 文件；Node 端轮询读取。
- MCP 服务器重启时，启动器会**接管（adopt）已经在运行的 InoProShop 会话**（按 profile + 存活 PID + `ready.signal` 匹配），而不是再开第二个窗口。

已在 **InoProShop V1.9.1.6** 上端到端验证（见 `test/integration-launch.ts`）：冷启动 → 连续 3 次工具调用 → 全部复用同一 PID，整过程只有**一个** `InoProShop.exe`；模拟断线重连可在约 0.008s 内接管会话，进程数仍为 1。

## 环境要求

- Windows
- Node.js 18+（在 22.x 上测试过）
- InoProShop **V1.9.1.6**（已验证）或 **V1.10.0.3**（见下方注意事项），并已注册对应的 profile。

> ⚠️ **V1.10.0.3 兼容性尚未验证。** 常驻模型依赖 `se.system.execute_on_primary_thread()`，而上游 CODESYS 在 V3.5 SP21+ 已移除该 API。InoProShop V1.10.0.3 是否仍暴露该接口尚不确定。若 V1.10.0.3 报 `Marshal error: … execute_on_primary_thread … no longer supported`，请以 `--mode headless` 启动（每次调用单独 spawn `--noUI`；无窗口，但也无单实例复用）。烦请反馈 V1.10.0.3 的实际表现，以便确认。

## 安装 / 构建

```bash
git clone <your-repo-url>
cd codesys-mcp-inoproshop
npm install
npm run build          # tsc + 把 src/scripts 复制到 dist/scripts
```

入口点是 `dist/bin.js`。

## 配置（WorkBuddy 的 `mcp.json`）

```json
{
  "mcpServers": {
    "inoproshop": {
      "command": "node",
      "args": [
        "D:\\codesys-mcp-inoproshop\\dist\\bin.js",
        "--codesys-path", "D:\\Inovance Control\\CODESYS\\Common\\InoProShop.exe",
        "--codesys-profile", "InoProShop(V1.9.1.6)",
        "--workspace", "D:\\your-projects"
      ],
      "timeout": 900
    }
  }
}
```

若你的 InoProShop 装在较新的 `D:\Inovance Control\InoProShop\CODESYS\Common\InoProShop.exe` 路径下，把 `--codesys-path` 相应改掉即可——两条路径下的都是 V1.9.1.6。

Claude Code / `.mcp.json`：

```json
{
  "mcpServers": {
    "inoproshop": {
      "command": "node",
      "args": [
        "D:\\codesys-mcp-inoproshop\\dist\\bin.js",
        "--codesys-path", "D:\\Inovance Control\\CODESYS\\Common\\InoProShop.exe",
        "--codesys-profile", "InoProShop(V1.9.1.6)"
      ]
    }
  }
}
```

## CLI

| Flag | 说明 | 默认值 |
|---|---|---|
| `-p, --codesys-path <path>` | `InoProShop.exe` 的路径 | `D:\Inovance Control\CODESYS\Common\InoProShop.exe` |
| `-f, --codesys-profile <name>` | InoProShop profile 名称 | `InoProShop(V1.9.1.6)` |
| `-w, --workspace <dir>` | 相对工程路径所用的工作目录 | 当前目录 |
| `-m, --mode <mode>` | `persistent` 或 `headless` | `persistent` |
| `--no-auto-launch` | 启动时不要自动启动 InoProShop | 默认自动启动 |
| `--fallback-headless` | 若常驻启动失败，回退到 headless | `true` |
| `--keep-alive` | 服务器停止后仍保留 InoProShop 运行 | `false` |
| `--kill-existing-inoproshop` | 启动前先杀掉任何正在运行的 `InoProShop.exe`（仅开发用） | `false` |
| `--timeout <ms>` | 每个命令的默认 IPC 超时 | `900000`（15 分钟；上游为 60000） |
| `--ready-timeout <ms>` | InoProShop 启动 ready 信号截止时间 | `180000`（上游为 60000） |
| `--detect` | 扫描已安装的 InoProShop 位置后退出 | - |
| `--verbose` / `--debug` | 日志输出 | - |

环境变量：

- `CODESYS_PATH`、`CODESYS_PROFILE` —— 对应 flag 的默认值（保留旧名以兼容）
- `INOPROSHOP_MCP_READY_TIMEOUT_MS` —— ready 信号截止时间（覆盖 `--ready-timeout`；也识别 `CODESYS_MCP_READY_TIMEOUT_MS`）
- `INOPROSHOP_MCP_PROFILE` —— **内部变量**：由启动器在 spawn 出的 InoProShop 上设置，以便 MCP 重启时能重新接管该会话。请勿手动设置。

## 工具

管理类：`launch_codesys`、`shutdown_codesys`、`get_codesys_status`、`eval_python`。

工程类：`open_project`、`create_project`、`list_project_templates`、`save_project`、`compile_project`、`get_compile_messages`、`create_pou`、`set_pou_code`、`create_property`、`create_method`、`create_dut`、`create_gvl`、`create_folder`、`delete_object`、`rename_object`、`get_all_pou_code`、`search_code`、`find_references`、`rename_symbol`。

在线 / 运行类：`connect_to_device`、`disconnect_from_device`、`set_credentials`、`set_simulation_mode`、`get_application_state`、`read_variable`、`write_variable`、`download_to_device`、`start_stop_application`、`monitor_variables`。

库类：`list_project_libraries`、`add_library`。

设备树类：`list_device_repository`、`inspect_device_node`、`add_device`、`set_device_parameter`、`map_io_channel`。

归档类：`create_project_archive`。

资源类：`inoproshop://project/status`、`inoproshop://project/{path}/structure`、`inoproshop://project/{path}/pou/{pou}/code`。

## 执行模式

**常驻（默认）。** 启动时，启动器会扫描 `%TEMP%/inoproshop-mcp-persistent/` 寻找存活的会话（profile 匹配、PID 存活、存在 `ready.signal`）并接管；否则就 spawn `InoProShop.exe --runscript=watcher.py`（不带 `--noUI`）。watcher 写入 `ready.signal`，然后起一个后台线程轮询 `commands/` 目录。结果落在 `results/`；Node 端以指数退避轮询。IDE 在两次调用之间保持可交互。

**Headless。** 每次工具调用都新启一个 `--noUI` 的 InoProShop 进程，跑完脚本即退出。无 UI、也无单实例复用。用于 `--mode headless`，或作为常驻启动失败时的回退。

## 探测安装

```bash
node dist/bin.js --detect
```

扫描常见的 InoProShop 安装布局（包括 `…\Inovance Control\CODESYS\Common\` 与 `…\Inovance Control\InoProShop\CODESYS\Common\`），并打印找到的可执行文件版本。

## 故障排查

- **找不到 InoProShop** —— 运行 `--detect`，或显式传入 `--codesys-path`。
- **启动时 watcher 超时** —— 首次冷启动可能超过 60s；`--ready-timeout 180000` 已经是默认值。若机器较慢可再用 `INOPROSHOP_MCP_READY_TIMEOUT_MS=300000` 调大。InoProShop 若还在启动中，直接再调一次 `launch_codesys` 即可——启动器会重新挂到存活的 PID，而不是再开第二个实例。
- **命令超时** —— 默认已改为 900000ms（15 分钟）。`compile_project`、`get_all_pou_code`、`download_to_device` 内部用 120s。可用 `--timeout <ms>` 调大。
- **MCP 重启后工程文件被锁** —— 启动器会自动接管之前的会话。若仍遇到锁，用任务管理器杀掉残留的 `InoProShop.exe`，或下次启动时加 `--kill-existing-inoproshop`（默认关闭，以免误杀你手动在用的 InoProShop）。
- **`Marshal error: … execute_on_primary_thread … no longer supported`** —— 你用的 InoProShop 构建版本已移除该 API。以 `--mode headless` 重启。

## 开发

```bash
npm install
npm run build
npm test                 # vitest 单元测试
npx tsx test/integration-launch.ts   # 真实 InoProShop 启动 + 复用 + 接管测试
npm run typecheck
```

工程结构：

```
src/
  bin.ts              CLI 入口（InoProShop 默认值、--detect）
  server.ts           MCP 工具 / 资源注册
  launcher.ts         InoProShop 进程生命周期 + 会话接管
  ipc.ts              基于文件的 IPC 传输（commands/ + results/）
  headless.ts         headless 回退执行器（--noUI）
  script-manager.ts   IronPython 2.7 模板加载 + 插值
  executor-proxy.ts   后台自动启动期间的竞态安全执行器切换
  result-parser.ts    RESULT_JSON 标记提取
  scripts/            IronPython 2.7 watcher + 辅助脚本 + 工具脚本
test/
  integration-launch.ts   真实 InoProShop 单实例验证
```

## 归属与许可

派生自 [`codesys-mcp-persistent`](https://github.com/luke-harriman/Codesys-MCP)（MIT，luke-harriman）。本文档中的 InoProShop 专属默认值、单实例加固以及更长的超时均为本分支新增。以相同的 MIT 许可分发。
