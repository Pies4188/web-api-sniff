# <# .SYNOPSIS WorkBuddy skill 一键安装（Windows）
# 下载 GitHub 仓库 tarball -> 解压 -> 运行 setup.py
# 也可直接让 WorkBuddy 用原生 git 导入：把仓库链接发给 WB + 说「帮我装上这个 skill」
$ErrorActionPreference = "Stop"
$Repo = "Pies4188/web-api-sniff"
$Ref  = "main"
$Url  = "https://github.com/$Repo/archive/refs/heads/$Ref.tar.gz"
$tmp  = Join-Path $env:TEMP ("wb-skill-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
Write-Host "[*] 下载 $Url"
Invoke-WebRequest -Uri $Url -OutFile (Join-Path $tmp "repo.tar.gz")
tar -xzf (Join-Path $tmp "repo.tar.gz") -C $tmp
$sub = Get-ChildItem $tmp -Directory | Where-Object { $_.Name -like "*-$Ref" } | Select-Object -First 1
Write-Host "[*] 运行 setup.py"
python (Join-Path $sub.FullName "setup.py")
