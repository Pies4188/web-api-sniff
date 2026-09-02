# -*- coding: utf-8 -*-
"""
scaffold_site.py —— 从网站 URL 自动生成 sites/<name>.json 骨架
===================================================================
把"加一个平台 = 手填 json"变成一条命令：给 URL 即可。

用法：
  python scripts/scaffold_site.py <url> [--name X] [--force]
  python scripts/scaffold_site.py https://weibao.shse.info

它会：
  1. 解析 host / scheme → base_url（scheme 作为 scheme_hint）
  2. 由 host 推导合法 name（如 weibao.shse.info → weibao_shse_info）
  3. 复制 _iot_template.json 填好 base_url / scheme_hint / name / _origin_url
  4. 写到 sites/<name>.json（或 WEB_API_SNIFF_SITES 指向的目录）

下一步交给 probe_auth.py 自动探测鉴权，或按 sites/README.md 手工填 auth。
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
TPL = SITES_DIR / "_iot_template.json"


def parse_url(url: str):
    url = url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url
    m = re.match(r"(https?)://([^/?#]+)(/[^?#]*)?", url)
    if not m:
        raise SystemExit(f"[err] 无法解析 URL: {url}")
    return m.group(1), m.group(2), (m.group(3) or "")


def derive_name(host: str) -> str:
    h = host.lower()
    if h.startswith("www."):
        h = h[4:]
    return re.sub(r"[^a-z0-9]+", "_", h).strip("_") or "site"


def scaffold(url: str, name: str | None = None, force: bool = False):
    scheme, host, _path = parse_url(url)
    base = f"{scheme}://{host}"
    name = name or derive_name(host)
    out = SITES_DIR / f"{name}.json"
    if out.exists() and not force:
        print(f"[exists] 已存在 {out}（用 --force 覆盖）")
        print(f"NAME={name}")
        return name, out
    if not TPL.exists():
        raise SystemExit(f"[err] 模板缺失：{TPL}")
    tpl = json.loads(TPL.read_text(encoding="utf-8"))
    tpl["name"] = host
    tpl["base_url"] = base
    tpl["scheme_hint"] = scheme
    tpl["_origin_url"] = url
    out.write_text(json.dumps(tpl, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] 已生成 {out}")
    print(f"NAME={name}  BASE={base}  SCHEME={scheme}")
    return name, out


def main():
    if len(sys.argv) < 2:
        print("用法: python scaffold_site.py <url> [--name X] [--force]")
        return
    url = sys.argv[1]
    force = "--force" in sys.argv
    name = None
    if "--name" in sys.argv:
        i = sys.argv.index("--name")
        if i + 1 < len(sys.argv):
            name = sys.argv[i + 1]
    scaffold(url, name=name, force=force)


if __name__ == "__main__":
    main()
