# -*- coding: utf-8 -*-
"""
probe_auth.py —— 自动探测并写回站点鉴权（auth 块）
=================================================
用 BrowserSkill(bsk) 在已登录浏览器里 evaluate 一段 JS，扫描
sessionStorage / localStorage / cookie 中的 token，据此自动填好
sites/<name>.json 的 auth（bearer / cookie / custom）。

用法：
  python scripts/probe_auth.py <site>
  python scripts/probe_auth.py weibao_shse_info

前置：浏览器已打开并登录该站点，bsk 会话活跃（bsk session list 有记录）。
无 bsk / 无活跃会话时优雅降级：写 token_env 占位并提示同事手动补 token。

本脚本复用 sniff_api 的 ensure_bsk / _bsk_evaluate（无活跃会话绝不挂起）。
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
from sniff_api import ensure_bsk, _bsk_evaluate  # noqa: E402

JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

PROBE_JS = r"""
(function(){
  function scan(store, get){
    var res={};
    try{
      for(var i=0;i<store.length;i++){
        var k=store.key(i); if(!k) continue;
        var v=get(k);
        if(v==null) continue;
        v=String(v);
        if(/token|jwt|auth|session|ticket|accesstoken|authorization|login|user/i.test(k)){
          var jwt=v.match(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/);
          if(jwt){ res[k]={type:'jwt', value:jwt[0].slice(0,24)}; }
          else { res[k]={type:(v.trim()[0]=='{'?'json':'str'), value:v.slice(0,120)}; }
        }
      }
    }catch(e){ res._err=String(e); }
    return res;
  }
  return JSON.stringify({
    sessionStorage: scan(sessionStorage, function(k){return sessionStorage.getItem(k);}),
    localStorage: scan(localStorage, function(k){return localStorage.getItem(k);}),
    cookie: (document.cookie||'').slice(0,300)
  });
})()
"""


def _find_token(store_obj):
    """从探测结果里挑一个最像 token 的键。返回 (key, type, value)。"""
    if not isinstance(store_obj, dict):
        return None
    # 优先 jwt
    for k, v in store_obj.items():
        if isinstance(v, dict) and v.get("type") == "jwt":
            return k, "jwt", v.get("value", "")
    # 再 json 对象
    for k, v in store_obj.items():
        if isinstance(v, dict) and v.get("type") == "json":
            return k, "json", v.get("value", "")
    # 再 str
    for k, v in store_obj.items():
        if isinstance(v, dict) and v.get("type") == "str" and len(v.get("value", "")) > 8:
            return k, "str", v.get("value", "")
    return None


def probe(site: str):
    p = SITES_DIR / f"{site}.json"
    if not p.exists():
        avail = ", ".join(sorted(x.stem for x in SITES_DIR.glob("*.json") if not x.stem.startswith("_"))) or "(空)"
        raise SystemExit(f"[err] 未找到站点配置：{p}\n可用站点：{avail}")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    base = cfg.get("base_url", "?")
    print(f"站点: {site}  base={base}")

    # 1) 确保 bsk 可用
    if not ensure_bsk():
        print("[warn] 未检测到 bsk（浏览器扩展）。写入 token_env 占位，请你手动提供 token。")
        cfg["auth"] = {
            "mode": "bearer",
            "token_env": f"{site.upper()}_TOKEN",
            "token_expr": "",
            "_note": "bsk 不可用：请先 `pip/脚本安装 BrowserSkill` 并在浏览器连接已登录会话，"
                     "或把 token 存入环境变量 %s" % f"{site.upper()}_TOKEN",
        }
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] 已写占位 auth → {p}（token_env={site.upper()}_TOKEN）")
        return cfg["auth"]

    # 2) 探测登录态
    out, rc = _bsk_evaluate(PROBE_JS)
    if rc != 0 or not out.strip():
        print("[warn] 没有活跃 bsk 会话或 evaluation 失败。请在浏览器打开并登录"
              f" {base}，确认 bsk session 活跃后重试；本次写 token_env 占位。")
        cfg["auth"] = {"mode": "bearer", "token_env": f"{site.upper()}_TOKEN",
                       "_note": "无活跃会话：登录后重跑 probe_auth.py 可自动探测"}
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] 已写占位 auth → {p}")
        return cfg["auth"]

    try:
        data = json.loads(out.strip())
    except Exception as e:
        print(f"[warn] 探测结果非 JSON：{out[:200]}；写 token_env 占位。")
        cfg["auth"] = {"mode": "bearer", "token_env": f"{site.upper()}_TOKEN"}
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        return cfg["auth"]

    # 3) 选 token
    for store_name in ("sessionStorage", "localStorage"):
        found = _find_token(data.get(store_name))
        if found:
            key, typ, val = found
            if typ == "jwt":
                expr = f"{store_name}.getItem('{key}')"
                auth = {"mode": "bearer", "token_expr": expr,
                        "_note": f"探测自 {store_name}.{key}（JWT 直存）"}
            elif typ == "json":
                expr = f"JSON.parse({store_name}.getItem('{key}')).token"
                auth = {"mode": "bearer", "token_expr": expr,
                        "_note": f"探测自 {store_name}.{key}（JSON 对象取 .token）"}
            else:
                expr = f"{store_name}.getItem('{key}')"
                auth = {"mode": "bearer", "token_expr": expr,
                        "_note": f"探测自 {store_name}.{key}（字符串 token）"}
            cfg["auth"] = auth
            p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[ok] 自动探测到鉴权：{store_name}.{key} → {typ}")
            print(f"     已写 auth → {p}")
            print(f"     token_expr: {expr}")
            return auth

    # 4) cookie 兜底
    cookie = data.get("cookie", "")
    if "token" in cookie.lower() or JWT_RE.search(cookie):
        cfg["auth"] = {"mode": "cookie", "token_expr": "document.cookie",
                       "_note": "探测自 document.cookie"}
        p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] 自动探测到鉴权：cookie → 已写 auth → {p}")
        return cfg["auth"]

    # 5) 都没找到
    print("[warn] 在 sessionStorage/localStorage/cookie 未找到明显 token。写 token_env 占位。")
    print("      探测到的键（供手工判断）：")
    for sn in ("sessionStorage", "localStorage"):
        for k, v in (data.get(sn) or {}).items():
            if k == "_err":
                continue
            print(f"      {sn}.{k} = {v}")
    cfg["auth"] = {"mode": "bearer", "token_env": f"{site.upper()}_TOKEN",
                   "_note": "自动探测未命中：请查看上方键名，手工填 auth（见 sites/README.md）"}
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg["auth"]


def main():
    if len(sys.argv) < 2:
        print("用法: python probe_auth.py <site>")
        return
    probe(sys.argv[1])


if __name__ == "__main__":
    main()
