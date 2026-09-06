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

## 工具清单（41 个）

### 管理（4）

| 工具 | 作用 |
|---|---|
| `launch_codesys` | 预热常驻 InoProShop 实例。惰性模式下可省略——首次工具调用会自动启动。 |
| `shutdown_codesys` | 关闭常驻实例，执行器回退到 headless。 |
| `get_codesys_status` | 查询实例状态（运行态、PID、执行模式）。 |
| `eval_python` | [调试用] 在 IDE 内执行任意 IronPython 2.7。代码原样转发给 watcher，`print` 的内容进入返回结果，需打印 `SCRIPT_SUCCESS` 才算成功。内置 `scriptengine`、`sys`、`os`。⚠️ 不要调用 IDE 的 "Login" 命令（会卡住主线程）。 |

### 工程（7）

| 工具 | 作用 |
|---|---|
| `open_project` | 打开已有工程文件。 |
| `create_project` | 从模板创建新工程。默认复制内置 Standard.project；传 `templatePath` 指定 .project 文件，或传 `templateName` 用模板管理器注册的模板（如 ifm AE3100 设备包）。先用 `list_project_templates` 查可用值。 |
| `list_project_templates` | 列出本机可用模板。合并两个来源：模板管理器注册的 + `%ProgramData%/CODESYS` 下已知路径的文件系统扫描。返回 `{name, path, source}`。 |
| `save_project` | 保存当前打开的工程。 |
| `compile_project` | 编译（Build）主应用。返回结构化编译信息（错误、警告）。 |
| `get_compile_messages` | 取上次编译的信息，不触发新编译。⚠️ 如果编译后改过代码，需先跑 `compile_project` 刷新。 |
| `create_project_archive` | 把当前打开的工程存为 .projectarchive。对工程本身只读——工程必须已打开，不会切换工程。输出路径可绝对或相对 workspace。 |

### 编程对象（13）

| 工具 | 作用 |
|---|---|
| `create_pou` | 新建 Program、Function Block 或 Function。 |
| `set_pou_code` | 设置指定 POU/Method/Property 的声明和/或实现代码。某节传空字符串表示保持不变。 |
| `get_all_pou_code` | 读取工程内所有 POU/DUT/GVL 的声明和实现代码，一次返回全部，适合批量审查。 |
| `create_method` | 在 Function Block 内新建方法。 |
| `create_dut` | 新建数据类型（结构体、枚举、联合体或别名）。 |
| `create_gvl` | 新建全局变量表。 |
| `create_property` | 在 Function Block 内新建属性。 |
| `create_folder` | 在工程树中新建组织文件夹。 |
| `delete_object` | 删除工程对象（POU、DUT、GVL、文件夹等）。⚠️ 不可撤销。系统节点（Application、Device、Plc Logic 等）会被拒绝删除。 |
| `rename_object` | 重命名工程对象。 |
| `search_code` | 正则（或纯文本子串）搜索所有 POU/Method/Property/DUT/GVL 的文本体，返回 `文件:行:列`。图形体（无文本实现）会跳过。 |
| `find_references` | 查找符号的所有词边界引用（`\bsymbol\b`），覆盖范围同 `search_code`。不排除注释和字符串字面量。 |
| `rename_symbol` | 词边界文本替换（默认 `dryRun=true` 只预览）。不重命名工程对象节点（用 `rename_object`），不处理图形体。 |

### 在线/运行（10）

| 工具 | 作用 |
|---|---|
| `connect_to_device` | 登录 PLC 运行时。若传 `ipAddress` 会先设置网关和地址；否则设备必须已配置网关/地址，或已通过 `set_simulation_mode` 开启仿真。 |
| `disconnect_from_device` | 登出 PLC 运行时。未连接时为空操作（返回成功）。 |
| `set_credentials` | 设置后续登录用的默认用户名/密码。每次会话调用一次，在 `connect_to_device` 之前。⚠️ 两个字段都不能为空（CODESYS 拒绝空用户名）。运行时无认证需求则不要调用。 |
| `set_simulation_mode` | 切换项目设备的 PLC 仿真开关。无物理 PLC 时在 `connect_to_device` 之前调用，CODESYS 会在无网关情况下模拟执行。 |
| `get_application_state` | 查询运行中应用的状态（run / stop / exception）及登录状态。需先连接。 |
| `read_variable` | 读取 PLC 实时变量。路径格式：`'GVL_Name.varname'` 或 `'PRG_Name.varname'`（不带 `Application.` 前缀）。结构体成员：`'GVL.stFrame.aRoi[0].iValueMm'`。需先连接。 |
| `write_variable` | 通过 V3 的 `set_prepared_value` + `force_prepared_values` 写入变量。写入后变量被 **FORCED**（强制在新值），直到显式取消强制或运行时重启。适合控制标志和测试注入，不适合程序输出。需先连接。 |
| `download_to_device` | 下载编译好的应用到 PLC。`mode` 控制策略：`auto`（默认，先试在线变更再回退全量）、`online_change`（在线变更被拒则失败）、`full`（始终全量下载）。 |
| `start_stop_application` | 启动或停止 PLC 应用。 |
| `monitor_variables` | 以固定间隔、有限时长采样一个或多个 PLC 变量，返回时间序列。⚠️ 会阻塞 CODESYS UI 线程（上限 60s）。 |

### 库（2）

| 工具 | 作用 |
|---|---|
| `list_project_libraries` | 列出工程当前引用的所有库。 |
| `add_library` | 给工程添加库引用。库必须已安装在 CODESYS 库仓库中。 |

### 设备树（5）

| 工具 | 作用 |
|---|---|
| `list_device_repository` | 枚举本地 CODESYS 设备仓库中的设备描述符。返回 `{name, vendor, device_type, device_id, version, description, category}`。用于给 `add_device` 提供规范 ID。 |
| `inspect_device_node` | 只读查看设备节点：描述符元数据、参数列表及当前值、子设备。配合 `set_device_parameter` 发现可写 ID。 |
| `add_device` | 在已有父设备下添加子设备。用 `list_device_repository` 获取规范的 `deviceType`/`deviceId`/`version`。⚠️ ID 写错会生成语法正确但错误的节点，编译时才报错。 |
| `set_device_parameter` | [实验性] 设置设备参数值。先用 `inspect_device_node` 找可写 ID。许多现场总线参数仅 GUI 可写，此时会返回明确错误。 |
| `map_io_channel` | 把现场总线 I/O 通道绑定（或清除绑定）到全局变量符号。先用 `inspect_device_node` 查看通道布局。 |

### 资源（3）

| URI | 作用 |
|---|---|
| `inoproshop://project/status` | 工程状态 |
| `inoproshop://project/{path}/structure` | 工程树结构 |
| `inoproshop://project/{path}/pou/{pou}/code` | 指定 POU 的代码 |

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
