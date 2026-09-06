# codesys-mcp-inoproshop

**让 AI 助手直接操控 InoProShop（汇川 / Inovance，基于 CODESYS 的 IDE）——全程只开一个 IDE 窗口。**

它把 InoProShop 的脚本 API 暴露为 40+ 个 MCP 工具。你用自然语言让 AI 帮你打开工程、写 PLC 程序、编译、连设备、读写变量，IDE 全程只占一个窗口，还能边用 AI 边手动操作。

## 5 分钟上手

```bash
git clone https://github.com/lzyricardo/codesys-mcp-inoproshop.git
cd codesys-mcp-inoproshop
npm install
npm run build
```

然后在 WorkBuddy 的 `mcp.json` 里加：

```json
{
  "mcpServers": {
    "inoproshop": {
      "command": "node",
      "args": [
        "D:\\codesys-mcp-inoproshop\\dist\\bin.js",
        "--codesys-path", "D:\\Inovance Control\\CODESYS\\Common\\InoProShop.exe",
        "--codesys-profile", "InoProShop(V1.9.1.6)"
      ],
      "timeout": 900
    }
  }
}
```

重启 WorkBuddy，看到 `inoproshop` 的工具列表就装好了。

调用任意工具时 InoProShop 才会启动——**第一次约 25 秒（冷启动），之后秒开**。

> 找不到 InoProShop？跑 `node dist/bin.js --detect` 扫描本机安装位置。

## 为什么做这个

原始 `InoProShop_LIMIT_MCP` 打包文件**每来一个请求就弹一个新 IDE 窗口**——问 AI 一句话，桌面多一个 InoProShop，工程还要重新加载一遍。

本项目修复了这个缺陷：**全程只有一个 InoProShop 实例**。

| | 原始 LIMIT 版 | 本项目 |
|---|---|---|
| 每个请求 | 新开一个 IDE 窗口 | 复用同一个窗口 |
| 工程加载 | 每次重载 | 一次加载 |
| MCP 重启 | 再来一个新窗口 | 自动接管已有会话（~8ms） |
| 冷启动时机 | 连接 MCP 就启动 | 首次工具调用才启动 |

已在 **InoProShop V1.9.1.6** 端到端验证（见 `test/integration-launch.ts`）：冷启动 → 连续 3 次调用全部复用同一 PID，全程只有 1 个 `InoProShop.exe`；模拟断线重连约 0.008s 接管会话，进程数仍为 1。

## 它是怎么工作的

```
┌──────────┐   工具调用    ┌────────────┐   写文件    ┌──────────┐
│WorkBuddy │ ────────────> │ MCP Server │ ──────────> │ InoProShop│
│ (AI 助手)│ <──────────── │  (Node.js) │ <────────── │   (IDE)  │
└──────────┘   返回结果    └────────────┘   读结果文件 └──────────┘
```

三种执行模式：

- **惰性常驻（默认）** —— MCP 连接时什么都不做；第一次调用工具才启动 InoProShop，之后所有调用复用这一个实例。启动失败则自动回退到 headless，不阻塞后续调用。
- **自动常驻** —— 加 `--auto-launch`：连接 MCP 就后台启动 InoProShop（会弹一个 IDE 窗口）。想提前预热用这个。
- **Headless** —— 加 `--mode headless`：每次调用单独起一个 `--noUI` 进程，跑完就退出。无窗口、无复用，用于 InoProShop 移除了常驻所需 API 的情况。

## 环境要求

- Windows
- Node.js 18+（22.x 测试通过）
- InoProShop **V1.9.1.6**（已验证）或 **V1.10.0.3**（⚠️ 见下）

> ⚠️ **V1.10.0.3 未验证**：常驻模式依赖 `se.system.execute_on_primary_thread()`，上游 CODESYS SP21+ 已移除该 API。若 V1.10.0.3 报 `Marshal error: … no longer supported`，改用 `--mode headless`。

## CLI 参数

**常用：**

| Flag | 说明 | 默认值 |
|---|---|---|
| `-p, --codesys-path` | InoProShop.exe 路径 | `D:\Inovance Control\CODESYS\Common\InoProShop.exe` |
| `-f, --codesys-profile` | profile 名称 | `InoProShop(V1.9.1.6)` |
| `-w, --workspace` | 相对工程路径的工作目录 | 当前目录 |
| `-m, --mode` | `persistent` / `headless` | `persistent` |
| `--detect` | 扫描本机 InoProShop 安装后退出 | - |

**高级：**

| Flag | 说明 | 默认值 |
|---|---|---|
| `--auto-launch` | 连接 MCP 就启动 InoProShop（否则惰性启动） | `false` |
| `--fallback-headless` | 常驻启动失败时回退 headless | `true` |
| `--keep-alive` | 服务器停止后保留 InoProShop | `false` |
| `--kill-existing-inoproshop` | 启动前杀掉已有 InoProShop（开发用） | `false` |
| `--timeout <ms>` | IPC 命令超时 | `900000`（15 分钟） |
| `--ready-timeout <ms>` | 启动 ready 信号截止 | `180000`（3 分钟） |
| `--verbose` / `--debug` | 日志输出 | - |

环境变量：`CODESYS_PATH`、`CODESYS_PROFILE`、`INOPROSHOP_MCP_READY_TIMEOUT_MS`。
`INOPROSHOP_MCP_PROFILE` 是内部变量（启动器自动设置，用于会话接管），别手动设。

## 工具清单（40+）

| 类别 | 工具 |
|---|---|
| **管理** | `launch_codesys`、`shutdown_codesys`、`get_codesys_status`、`eval_python` |
| **工程** | `open_project`、`create_project`、`save_project`、`compile_project`、`get_compile_messages`、`list_project_templates`、`create_project_archive` |
| **编程对象** | `create_pou`、`set_pou_code`、`get_all_pou_code`、`create_method`、`create_dut`、`create_gvl`、`create_property`、`create_folder`、`delete_object`、`rename_object`、`rename_symbol`、`search_code`、`find_references` |
| **在线/运行** | `connect_to_device`、`disconnect_from_device`、`set_credentials`、`set_simulation_mode`、`get_application_state`、`read_variable`、`write_variable`、`download_to_device`、`start_stop_application`、`monitor_variables` |
| **库** | `list_project_libraries`、`add_library` |
| **设备树** | `list_device_repository`、`inspect_device_node`、`add_device`、`set_device_parameter`、`map_io_channel` |

资源：`inoproshop://project/status`、`inoproshop://project/{path}/structure`、`inoproshop://project/{path}/pou/{pou}/code`

## 故障排查

| 现象 | 原因 | 解决 |
|---|---|---|
| 找不到 InoProShop | 路径不对 | 跑 `--detect`，或显式传 `--codesys-path` |
| 首次调用 watcher 超时 | 冷启动慢 | 默认已 180s；慢机器用 `INOPROSHOP_MCP_READY_TIMEOUT_MS=300000`；或再调一次 `launch_codesys`（会挂到存活 PID，不重复开窗口） |
| 命令超时 | 编译/下载耗时 | 默认 900000ms；可 `--timeout` 调大 |
| 工程文件被锁 | MCP 重启后残留进程 | 启动器自动接管；仍锁则任务管理器杀 `InoProShop.exe`，或下次加 `--kill-existing-inoproshop` |
| `Marshal error: … no longer supported` | InoProShop 版本移除了常驻 API | 改 `--mode headless` |

## 版本记录

本仓库遵循**语义化版本**（MAJOR.MINOR.PATCH），每次推送到 GitHub 都会更新 [`CHANGELOG.md`](./CHANGELOG.md)：

| 版本位 | 触发条件 | 例子 |
|---|---|---|
| **MAJOR** | 不兼容的 API 变更 | 工具重命名、参数含义改变 |
| **MINOR** | 新功能、新工具、行为改进 | 惰性启动 |
| **PATCH** | bug 修复、文档更新、内部重构 | 修复超时计算 |

commit message 用 [Conventional Commits](https://www.conventionalcommits.org/) 格式（`feat:` / `fix:` / `docs:` / `refactor:` / `chore:`），映射关系见 [`CONTRIBUTING.md`](./CONTRIBUTING.md)。

## 开发

```bash
npm install
npx tsc && cp -r src/scripts dist/scripts   # 构建（别用 npm run build，见下）
npm test                                    # vitest 单元测试
npx tsx test/integration-launch.ts          # 真机启动/复用/接管测试
npm run typecheck
```

> ⚠️ `npm run build` 含 `rimraf dist`，本机会被 safe-delete 拦截（dist 文件数超阈值）。直接跑 `npx tsc` + 复制 scripts 即可。

工程结构：

```
src/
  bin.ts              CLI 入口（默认值、--detect）
  server.ts           MCP 工具/资源注册
  launcher.ts         进程生命周期 + 会话接管
  executor-proxy.ts   惰性启动 + 执行器切换
  ipc.ts              基于文件的 IPC 传输
  headless.ts         headless 回退执行器
  script-manager.ts   IronPython 2.7 模板加载
  result-parser.ts    RESULT_JSON 标记提取
  scripts/            IronPython 2.7 watcher + 工具脚本
test/
  integration-launch.ts   真机单实例验证
```

## 归属与许可

派生自 [`codesys-mcp-persistent`](https://github.com/luke-harriman/Codesys-MCP)（MIT，luke-harriman）。InoProShop 适配、单实例加固、惰性启动、更长超时均为本分支新增。以相同的 MIT 许可分发。
