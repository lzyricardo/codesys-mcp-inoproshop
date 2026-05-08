# Static checks for the Python script templates and server.ts wiring.
# Catches the recurring pitfalls: non-ASCII chars in .py (IronPython 2.7
# trip-wire), and dangling references to script files that don't exist.
#
# Run after edits, before npm run build:
#   pwsh dev/check-scripts.ps1

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$scriptsDir = Join-Path $repo 'src\scripts'
$serverTs   = Join-Path $repo 'src\server.ts'

$failed = $false

# 1. ASCII-only check on every .py file. IronPython 2.7 rejects non-ASCII
#    source unless the file has a "# -*- coding: utf-8 -*-" header. Em-dash
#    smart-quotes from copy-paste are the most common offender.
Write-Host '== ASCII check ==' -ForegroundColor Cyan
$pyFiles = Get-ChildItem -Path $scriptsDir -Filter '*.py' -Recurse
foreach ($f in $pyFiles) {
    $bytes = [System.IO.File]::ReadAllBytes($f.FullName)
    $hasHeader = (Get-Content -LiteralPath $f.FullName -TotalCount 2) -join "`n" -match 'coding[:=]\s*utf-8'
    $nonAscii = $bytes | Where-Object { $_ -gt 0x7F }
    if ($nonAscii -and -not $hasHeader) {
        Write-Host ("  FAIL: {0} contains non-ASCII bytes without a utf-8 coding header" -f $f.Name) -ForegroundColor Red
        $failed = $true
    } else {
        Write-Host ("  OK  : {0}" -f $f.Name) -ForegroundColor DarkGray
    }
}

# 2. Every script template referenced by server.ts must exist on disk.
Write-Host '== Template reference check ==' -ForegroundColor Cyan
$serverContent = Get-Content -LiteralPath $serverTs -Raw
$refMatches = [regex]::Matches($serverContent, "(?:prepareScript(?:WithHelpers)?|loadTemplate)\(\s*['""]([a-zA-Z0-9_-]+)['""]")
$referenced = @{}
foreach ($m in $refMatches) {
    $referenced[$m.Groups[1].Value] = $true
}
# Also catch helper arrays: ['_text_utils', 'ensure_project_open', ...]
$helperMatches = [regex]::Matches($serverContent, "\[\s*((?:['""][a-zA-Z0-9_-]+['""]\s*,?\s*)+)\]")
foreach ($m in $helperMatches) {
    $list = $m.Groups[1].Value
    foreach ($item in [regex]::Matches($list, "['""]([a-zA-Z0-9_-]+)['""]")) {
        $name = $item.Groups[1].Value
        # Only consider names that look like script templates (skip random arrays).
        if (Test-Path (Join-Path $scriptsDir ($name + '.py'))) {
            $referenced[$name] = $true
        }
    }
}
foreach ($name in $referenced.Keys | Sort-Object) {
    $expected = Join-Path $scriptsDir ($name + '.py')
    if (Test-Path $expected) {
        Write-Host ("  OK  : {0}.py" -f $name) -ForegroundColor DarkGray
    } else {
        Write-Host ("  FAIL: server.ts references '{0}' but {1} does not exist" -f $name, $expected) -ForegroundColor Red
        $failed = $true
    }
}

# 3. Every .py script template (excluding watcher + helpers) should be referenced
#    somewhere. Helpers _text_utils, ensure_project_open, ensure_online_connection,
#    find_object_by_path are wired via helper arrays already covered above.
Write-Host '== Orphan script check ==' -ForegroundColor Cyan
$skipUnreferenced = @('watcher')
foreach ($f in $pyFiles) {
    $name = [System.IO.Path]::GetFileNameWithoutExtension($f.Name)
    if ($skipUnreferenced -contains $name) { continue }
    if (-not $referenced.ContainsKey($name)) {
        Write-Host ("  WARN: {0}.py is not referenced from server.ts" -f $name) -ForegroundColor Yellow
    }
}

if ($failed) {
    Write-Host ''
    Write-Host 'check-scripts.ps1 FAILED' -ForegroundColor Red
    exit 1
}
Write-Host ''
Write-Host 'check-scripts.ps1 OK' -ForegroundColor Green
