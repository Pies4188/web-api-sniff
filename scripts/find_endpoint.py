# -*- coding: utf-8 -*-
"""
find_endpoint.py —— 从任意站点前端 JS Bundle 自动定位后端接口（通用版）
=========================================================================
用户只说前端动作（"点转单按钮"），你不知道接口名时，用本脚本：
  1. 下载站点首页 → 找到 app.js（主入口）
  2. 从 app.js 枚举所有 lazy chunk 文件名（webpack chunk map）
  3. 逐个 chunk 下载并 grep 关键词（如 batchTransWorkOrder / 转单）
  4. 打印命中上下文（前后 N 字符），据此还原请求体

用法：
  python find_endpoint.py <site> <关键词> [--ctx 320]
  python find_endpoint.py chengxiaozhi batchTransWorkOrder
  python find_endpoint.py chengxiaozhi 转单 --ctx 500

<site> 对应 sites/<site>.json 里的 base_url。纯静态 GET，不需要 token。
注意：chunk 文件名带内容哈希，每次部署都变；本脚本每次都重新枚举，不要写死旧 chunk 名。
"""
from __future__ import annotations
import sys
import os
import re
import json
import urllib.request
import urllib.error
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
_env = os.environ.get("WEB_API_SNIFF_SITES")
_DEFAULT_SITES = SKILL_DIR / "sites"
if _env:
    SITES_DIRS = [Path(os.path.expanduser(_env)).resolve(), _DEFAULT_SITES]
else:
    SITES_DIRS = [_DEFAULT_SITES]
SITES_DIR = SITES_DIRS[0]


def _site_base(site: str) -> str:
    p = None
    for d in SITES_DIRS:
        cand = d / f"{site}.json"
        if cand.exists():
            p = cand
            break
    if p is None:
        avail = ", ".join(sorted(
            x.stem for d in SITES_DIRS for x in d.glob("*.json")
            if not x.stem.startswith("_")
        )) or "(空)"
        raise SystemExit(f"未找到站点配置：{SITES_DIRS[0] / (site + '.json')}\n可用站点：{avail}")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    base = (cfg.get("base_url") or "").rstrip("/")
    if not base:
        raise SystemExit(f"[{site}] 配置缺少 base_url")
    # 首页探测优先 http（很多内管 http 直连 https 会 SSL EOF），回退 https
    return base


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={
        "Accept": "*/*",
        "User-Agent": "Mozilla/5.0 (web-api-sniff)",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def _get_fallback(url, timeout=30):
    """先按 url 原 scheme，失败回退另一 scheme。"""
    last = None
    for u in [url]:
        try:
            return _get(u, timeout)
        except Exception as e:
            last = e
    if url.startswith("http://"):
        alt = "https://" + url.split("://", 1)[1]
    else:
        alt = "http://" + url.split("://", 1)[1]
    try:
        return _get(alt, timeout)
    except Exception as e:
        last = e
    raise last


def _chunk_files_from(text):
    """从 app.js 抠出所有 lazy chunk 文件名（webpack chunk map）。"""
    files = set()
    for m in re.finditer(r'static/js/([A-Za-z0-9_.\-]+\.js)', text):
        files.add(m.group(1))
    # 仅解析喂给 ".js" 的哈希表： {...}[e]+".js"
    m = re.search(r'\{([^{}]*)\}\[e\]\+"\.js"', text)
    if m:
        block = m.group(1)
        for km in re.finditer(r'"([A-Za-z0-9_\-]+)"\s*:\s*"([0-9a-f]{6,})"', block):
            cid, h = km.group(1), km.group(2)
            files.add("%s.%s.js" % (cid, h))
    return files


def find(site, kw, ctx=320):
    """从站点前端 JS 枚举 chunk 并 grep 关键词，返回命中列表 [(src, segment), ...]。"""
    BASE = _site_base(site)
    try:
        html = _get_fallback(BASE + "/")
    except Exception as e:
        return [("__err__", f"无法下载首页: {e}")]

    all_srcs = re.findall(r'static/js/([A-Za-z0-9_.\-]+\.js)', html)
    app_path = None
    for s in all_srcs:
        if re.match(r'app\.[0-9a-f]+\.js$', s):
            app_path = s
            break
    if not app_path and all_srcs:
        app_path = all_srcs[-1]
    if not app_path:
        app_path = "static/js/app.js"
    app_url = BASE + "/" + app_path
    try:
        app = _get_fallback(app_url)
    except Exception as e:
        return [("__err__", f"无法下载 app.js: {e}")]

    files = _chunk_files_from(app) | _chunk_files_from(html)
    files.add(app_path.split("/")[-1])

    hits = []

    def scan(text, src):
        for mm in re.finditer(re.escape(kw), text):
            s = max(0, mm.start() - ctx)
            e = min(len(text), mm.end() + ctx)
            hits.append((src, text[s:e].replace("\n", " ")))

    scan(app, app_path)
    for f in sorted(files):
        url = BASE + "/static/js/" + f
        try:
            t = _get_fallback(url, timeout=20)
        except Exception:
            continue
        if kw in t:
            scan(t, f)
    return hits


def main():
    if len(sys.argv) < 3:
        print("用法: python find_endpoint.py <site> <关键词> [--ctx 320]")
        return
    site = sys.argv[1]
    kw = sys.argv[2]
    ctx = 320
    if "--ctx" in sys.argv:
        i = sys.argv.index("--ctx")
        if i + 1 < len(sys.argv):
            try:
                ctx = int(sys.argv[i + 1])
            except ValueError:
                pass

    BASE = _site_base(site)
    print(f"站点: {site}  base={BASE}  关键词: {kw}")
    hits = find(site, kw, ctx)
    if hits and hits[0][0] == "__err__":
        print(f"[err] {hits[0][1]}")
        return
    print(f"\n=== 命中 {len(hits)} 处 ===")
    for idx, (src, seg) in enumerate(hits[:12], 1):
        print(f"\n### [{idx}] {src}")
        print(seg)
        print("-" * 60)


if __name__ == "__main__":
    main()
