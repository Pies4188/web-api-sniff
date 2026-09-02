#!/usr/bin/env bash
# WorkBuddy skill 一键安装（macOS / Linux）
# 下载 GitHub 仓库 tarball -> 解压 -> 运行 setup.py
# 也可直接让 WorkBuddy 用原生 git 导入：把仓库链接发给 WB + 说「帮我装上这个 skill」
set -e
REPO="Pies4188/web-api-sniff"
REF="main"
URL="https://github.com/$REPO/archive/refs/heads/$REF.tar.gz"
TMP="$(mktemp -d)"
echo "[*] 下载 $URL"
curl -fsSL "$URL" -o "$TMP/repo.tar.gz"
tar -xzf "$TMP/repo.tar.gz" -C "$TMP"
SUB="$(find "$TMP" -maxdepth 1 -type d -name "*-$REF" | head -1)"
echo "[*] 运行 setup.py"
python3 "$SUB/setup.py"
