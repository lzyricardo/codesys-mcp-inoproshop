# 贡献指南

## 提交前检查

```bash
# 1. 构建（不要跑 npm run build，会被 safe-delete 拦截）
npx tsc && cp -r src/scripts dist/scripts

# 2. 单元测试
npm test

# 3. 涉及真实 InoProShop 的改动，跑集成测试
npx tsx test/integration-launch.ts

# 4. 类型检查
npm run typecheck
```

## Commit 规范

使用 [Conventional Commits](https://www.conventionalcommits.org/)：

| 前缀 | 用途 | 触发版本 |
|---|---|---|
| `feat:` | 新功能、新工具 | MINOR |
| `fix:` | bug 修复 | PATCH |
| `docs:` | 文档更新 | PATCH |
| `refactor:` | 内部重构（行为不变） | PATCH |
| `test:` | 测试相关 | PATCH |
| `chore:` | 构建/依赖/工具链 | PATCH |
| `feat!:` / `fix!:` | 破坏性变更 | MAJOR |

**commit message 一律用 ASCII**（PowerShell 的 ANSI 转码会把中文写坏成 mojibake）。

## CHANGELOG 记录（每次推送必做）

每次推送到 GitHub 前，在 `CHANGELOG.md` **顶部**加一条：

```markdown
## X.Y.Z — YYYY-MM-DD (简短标题)

一句话说明改了什么、为什么。

### Added / Changed / Fixed
- **改动标题。** 具体说明（含影响范围）。
```

版本号按上面 Conventional Commits 表递增。同一天多次推送可以合并到同一条，也可以拆开——取决于改动是否独立。

## 推送流程（本机 Windows + PowerShell 5.1）

本机的 PowerShell 有几个已知坑，按下面的顺序走：

```powershell
# 0. 清理 PATH 大小写重复键
#    PS 5.1 的 Start-Process 构建环境变量字典时遇到重复键直接崩溃
$envVars = [System.Environment]::GetEnvironmentVariables()
foreach ($k in @($envVars.Keys | Where-Object { $_ -ieq 'Path' })) {
  [System.Environment]::SetEnvironmentVariable($k, $null, 'Process')
}
$sysPath = [Environment]::GetEnvironmentVariable('Path','Machine')
$usrPath = [Environment]::GetEnvironmentVariable('Path','User')
[System.Environment]::SetEnvironmentVariable('Path', "C:\Program Files\GitHub CLI;$sysPath;$usrPath", 'Process')

# 1. 提交（ASCII message）
git add <files>
git commit -m "feat: short subject" -m "详细 body"

# 2. 推送（git push 在 PS 下零输出，用 Start-Process 捕获）
$token = & 'C:\Program Files\GitHub CLI\gh.exe' auth token
git config --global http.sslVerify false   # 本机 TLS 被锁，推送前临时关
$url = "https://x-access-token:${token}@github.com/lzyricardo/codesys-mcp-inoproshop.git"
$p = Start-Process -FilePath 'git' -ArgumentList @('-c','http.sslVerify=false','push',$url,'main:main') -Wait -NoNewWindow -PassThru -RedirectStandardOutput 'out.txt' -RedirectStandardError 'err.txt'
Write-Host "exit=$($p.ExitCode)"
Get-Content err.txt -Raw    # git 的进度信息走 stderr
git config --global http.sslVerify true   # 推完立刻恢复
Remove-Item out.txt, err.txt
```

## 发布清单

- [ ] 代码改完，`npx tsc` 通过
- [ ] `npm test` 通过
- [ ] README 同步更新（参数表 / 执行模式 / 故障排查 / 工具清单）
- [ ] `CHANGELOG.md` 顶部加条目（版本号 + 日期 + 说明）
- [ ] commit（Conventional Commits 格式，ASCII message）
- [ ] 推送成功（看 `err.txt` 里有 `main -> main`）
- [ ] 确认工作树干净：`git status --short` 无输出
