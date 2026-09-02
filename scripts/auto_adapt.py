# -*- coding: utf-8 -*-
"""
auto_adapt.py —— 自动适配一个新平台（给 URL 即可，一步到位）
=============================================================
把"加配置 → 找接口 → 直连验证"三步自动串起来。同事/同事的 WorkBuddy
只要拿到一个网站 URL，就能自动完成适配并可以开始抓数据。

用法：
  python scripts/auto_adapt.py <url> [关键词] [--name X] [--force]
  python scripts/auto_adapt.py https://weibao.shse.info 工单
  python scripts/auto_adapt.py https://iot.xxx.com            # 只做探域名+鉴权，待给关键词

流程：
  1. scaffold_site  : 由 URL 生成 sites/<name>.json（base_url / scheme_hint）
  2. probe_auth     : 自动探测鉴权（bsk 读登录态），写回 auth 块
  3. find_endpoint  : 按关键词枚举前端 chunk，定位后端接口候选
  4. 直连验证       : 对候选只读 GET 接口试连，能取到数据即锁定进 endpoints
  5. 回写配置       : endpoints / notes 写回 json，打印适配结果

前置（仅鉴权探测需要）：浏览器已打开并登录该站点，bsk 会话活跃。
无 bsk / 未登录时自动降级为 token_env 占位，不阻断流程。
"""
from __future__ import annotations
import sys
import os
import re
import json
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
_env = os.environ.get("WEB_API_SNIFF_SITES")
SITES_DIR = Path(os.path.expanduser(_env)).resolve() if _env else (SKILL_DIR / "sites")
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from scaffold_site import scaffold          # noqa: E402
from probe_auth import probe               # noqa: E402
from find_endpoint import find             # noqa: E402
from sniff_api import SniffSite            # noqa: E402

PATH_RE = re.compile(r"(?<!\w)(/[A-Za-z0-9_][A-Za-z0-9_./\-]{2,})")
STATIC_RE = re.compile(r"\.(js|css|png|jpg|jpeg|svg|woff2?|ttf|map|html?|ico)$", re.I)


def _candidate_paths(hits):
    paths = set()
    for _src, seg in hits:
        for m in PATH_RE.finditer(seg):
            p = m.group(1).rstrip("/")
            if len(p) < 4:
                continue
            if STATIC_RE.search(p):
                continue
            if p.startswith(("/static/", "/assets/", "/@vite", "/node_modules")):
                continue
            # 去掉疑似模板字符串 / 查询参数残留
            p = p.split("${")[0].split("?")[0]
            if p.count("/") >= 1:
                paths.add(p)
    return sorted(paths)


def _verify(site: SniffSite, paths):
    """对候选路径试只读 GET，返回 (可访问路径列表, 诊断)。"""
    ok, diag = [], []
    for p in paths[:8]:
        try:
            r = site.api_get(p)
            if isinstance(r, (dict, list)):
                ok.append(p)
                diag.append(f"  ✅ GET {p} → 命中({len(json.dumps(r))} 字节)")
            else:
                diag.append(f"  ⚠️  GET {p} → 非 JSON（需参数/POST，留待手工）")
        except SystemExit as e:
            msg = str(e).splitlines()[0] if str(e) else str(e)
            diag.append(f"  ❌ GET {p} → {msg[:80]}")
        except BaseException as e:  # noqa: BLE001
            diag.append(f"  ❌ GET {p} → {type(e).__name__}: {str(e)[:80]}")
    return ok, diag


def auto_adapt(url, keyword=None, name=None, force=False):
    print("──────── ① 探域名 / 生成配置 ────────")
    sname, spath = scaffold(url, name=name, force=force)
    print("\n──────── ② 自动探测鉴权 ────────")
    probe(sname)
    print("\n──────── ③ 定位接口 ────────")
    if not keyword:
        print("[提示] 未给关键词。配置 + 鉴权已就绪；给个业务关键词即可继续找接口，例如：")
        print(f"  python scripts/auto_adapt.py {url} 工单")
        return sname
    hits = find(sname, keyword)
    if not hits or hits[0][0] == "__err__":
        print(f"[warn] 接口定位失败：{hits[0][1] if hits else '无命中'}")
        return sname
    cands = _candidate_paths(hits)
    print(f"前端命中 {len(hits)} 处，提取候选接口 {len(cands)} 个：")
    for p in cands[:12]:
        print(f"  · {p}")
    print("\n──────── ④ 直连验证 ────────")
    site = SniffSite.load(sname)
    ok, diag = _verify(site, cands)
    for d in diag:
        print(d)
    # 回写 endpoints
    cfg = json.loads(spath.read_text(encoding="utf-8"))
    eps = cfg.get("endpoints") or []
    seen = {e.get("path") for e in eps}
    for p in ok:
        if p not in seen:
            eps.append({"action": f"{keyword}（自动发现）", "method": "GET", "path": p})
            seen.add(p)
    cfg["endpoints"] = eps
    if ok:
        cfg.setdefault("notes", "")
        cfg["notes"] = (cfg.get("notes") or "") + f"\n自动适配 {keyword}：验证通过接口 {', '.join(ok)}"
    spath.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n──────── ⑤ 适配完成 ────────")
    print(f"站点: {sname}  配置: {spath}")
    print(f"已验证可直连接口: {ok if ok else '（暂无，需手工补参数/POST）'}")
    print(f"下一步: python scripts/sniff_api.py {sname} get <path>   取数")
    return sname


def main():
    if len(sys.argv) < 2:
        print("用法: python auto_adapt.py <url> [关键词] [--name X] [--force]")
        return
    url = sys.argv[1]
    keyword = None
    for a in sys.argv[2:]:
        if not a.startswith("--"):
            keyword = a
            break
    force = "--force" in sys.argv
    name = None
    if "--name" in sys.argv:
        i = sys.argv.index("--name")
        if i + 1 < len(sys.argv):
            name = sys.argv[i + 1]
    auto_adapt(url, keyword=keyword, name=name, force=force)


if __name__ == "__main__":
    main()
