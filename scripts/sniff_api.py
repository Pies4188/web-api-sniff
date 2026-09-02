# -*- coding: utf-8 -*-
"""
web-api-sniff — 通用后端接口工具（站点无关）
============================================
把「任意 Vue/React 内管平台 / 物联网平台」的数据抓取从浏览器 DOM 改为后端 HTTP 直取。
**配置驱动**：每个站点一个 JSON（sites/<name>.json），脚本本身不绑定任何站点。

封装：
  - SniffSite.load(name)          : 从 sites/<name>.json 加载配置
  - site.get_token()              : 取凭证（env → creds_file → bsk evaluate token_expr）
  - site.headers                  : 当前带 token 的 headers（按 auth.mode 组装）
  - site.api_get(path_or_url)     : 同源鉴权 GET（自动 http/https 回退）
  - site.api_post(path, body)     : 同源鉴权 POST（自动 http/https 回退）

命令行：
  python sniff_api.py list                          # 列出所有站点配置（本地自检，不联网不取 token）
  python sniff_api.py <site> get  <path>
  python sniff_api.py <site> post <path> '<json body>'
  python sniff_api.py <site> headers          # 打印将要带上的 headers（不发包，便于调试）

token 三级回退：① 环境变量(auth.token_env) → ② 凭证文件(auth.creds_file[creds_key])
→ ③ bsk 从已登录浏览器 evaluate(auth.token_expr)。bsk 缺失时自动从官方脚本安装。

鉴权模式(auth.mode)：
  - "bearer"  : Authorization: Bearer <token>            （默认）
  - "cookie"  : Cookie: <token>（token 为整段 cookie 串）
  - "custom"  : 把 token 填入 auth.header，格式 auth.header_format（默认 "{token}"）
auth.extra_headers：每次请求都带的固定头（如 x-ru-id / X-App-Id 之类站点专有头）。

站点目录：
  - 默认：本 skill 的 sites/ 目录。
  - 可用环境变量 WEB_API_SNIFF_SITES 覆盖（填一个绝对目录），把你自己加的站点配置
    放在 skill 之外，升级 skill 时不丢失、也不污染官方示例。
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
# 站点目录：环境变量 WEB_API_SNIFF_SITES 指向的目录优先（同事自定义、升级不丢），
# 默认 skill 的 sites/ 作为兜底（内置示例 chengxiaozhi.json 等仍可被发现）。
_SITES_ENV = os.environ.get("WEB_API_SNIFF_SITES")
_DEFAULT_SITES = SKILL_DIR / "sites"
if _SITES_ENV:
    SITES_DIRS = [Path(os.path.expanduser(_SITES_ENV)).resolve(), _DEFAULT_SITES]
else:
    SITES_DIRS = [_DEFAULT_SITES]
# 兼容旧代码：SITES_DIR 指向首选（写入）目录
SITES_DIR = SITES_DIRS[0]
BSK = os.environ.get("BSK_PATH", "bsk")
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def _site_path(name: str):
    """返回首个存在的 sites/<name>.json 路径；不存在返回首选目录下的预期路径。"""
    for d in SITES_DIRS:
        p = d / f"{name}.json"
        if p.exists():
            return p
    return SITES_DIRS[0] / f"{name}.json"


def log(*a):
    print(*a, flush=True)


def _valid_site_names():
    """列出所有站点目录下、非模板（_ 开头）的站点配置文件名（不含 .json），去重。"""
    seen = {}
    for d in SITES_DIRS:
        if not d.exists():
            continue
        for p in d.glob("*.json"):
            if p.stem.startswith("_"):
                continue
            seen.setdefault(p.stem, d)  # 优先目录先到，后到的同名不覆盖
    return sorted(seen)


# --------------------------------------------------------------------------
# bsk 自动安装 / 调用（通用：用于从已登录浏览器 evaluate JS 取凭证）
# --------------------------------------------------------------------------
def _bsk_runs(path):
    import subprocess
    try:
        r = subprocess.run([path, "--version"], capture_output=True, text=True,
                           timeout=20, shell=False)
        return r.returncode == 0
    except Exception:
        return False


def _bsk_default_path():
    name = "bsk.exe" if os.name == "nt" else "bsk"
    return os.path.expanduser(os.path.join("~", ".local", "bin", name))


def _install_bsk():
    import subprocess
    if os.name == "nt":
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
               "irm https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.ps1 | iex"]
    else:
        cmd = ["sh", "-c",
               "curl -fsSL https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.sh | sh"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300, shell=False)
        if r.returncode != 0:
            log(f"[warn] bsk 安装脚本返回非零：{(r.stderr or r.stdout or '')[:400]}")
            return False
        return True
    except Exception as e:
        log(f"[warn] 执行 bsk 安装脚本异常：{e}")
        return False


def ensure_bsk():
    """确保 bsk 可用；缺失时自动从官方脚本安装。返回 True 表示可用。"""
    global BSK
    if BSK != "bsk" and _bsk_runs(BSK):
        return True
    if BSK == "bsk" and _bsk_runs("bsk"):
        return True
    cand = _bsk_default_path()
    if cand and _bsk_runs(cand):
        BSK = cand
        os.environ["BSK_PATH"] = cand
        return True
    log("ℹ️ 未检测到 bsk（用于自动读取浏览器登录态），正在从官方脚本自动安装…")
    if not _install_bsk():
        log("[warn] 自动安装 bsk 失败（需联网访问 github.com）。可手动安装：")
        log("  Windows    : irm https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.ps1 | iex")
        log("  macOS/Linux: curl -fsSL https://raw.githubusercontent.com/Tencent/BrowserSkill/main/install.sh | sh")
        return False
    cand = _bsk_default_path()
    if cand and _bsk_runs(cand):
        BSK = cand
        os.environ["BSK_PATH"] = cand
        return True
    if _bsk_runs("bsk"):
        BSK = "bsk"
        return True
    return False


def _bsk_evaluate(expr, auto_start=False):
    """解析一个活跃 bsk 会话，执行 JS 表达式。返回 (输出文本, 返回码)；无活跃会话返回 ('', 1)。

    关键：没有活跃会话时**绝不调用 evaluate**（否则 bsk 会挂起数十秒），直接返回空。"""
    import subprocess, json as _json
    session_id = None
    try:
        out = subprocess.run([BSK, "session", "list", "--json"],
                             capture_output=True, text=True, timeout=15)
        data = _json.loads((out.stdout or "[]").strip() or "[]")
        sess = data.get("sessions", data) if isinstance(data, dict) else data
        if isinstance(sess, list) and sess:
            session_id = sess[0].get("id") or sess[0].get("sessionId")
    except Exception:
        session_id = None
    if not session_id and auto_start:
        try:
            subprocess.run([BSK, "session", "start"],
                           capture_output=True, text=True, timeout=30)
            out = subprocess.run([BSK, "session", "list", "--json"],
                                 capture_output=True, text=True, timeout=15)
            data = _json.loads((out.stdout or "[]").strip() or "[]")
            sess = data.get("sessions", data) if isinstance(data, dict) else data
            if isinstance(sess, list) and sess:
                session_id = sess[0].get("id") or sess[0].get("sessionId")
        except Exception:
            session_id = None
    if not session_id:
        return "", 1
    cmd = [BSK, "evaluate", "--expression", expr, "--session", session_id]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return (r.stdout or "") + (r.stderr or ""), r.returncode
    except Exception as e:
        log(f"[warn] bsk 调用失败: {e}")
        return "", 1


# --------------------------------------------------------------------------
# 站点配置
# --------------------------------------------------------------------------
class SniffSite:
    def __init__(self, cfg: dict, name: str):
        self.name = name
        self.cfg = cfg
        self.base_url = (cfg.get("base_url") or "").rstrip("/")
        if not self.base_url:
            raise SystemExit(f"[{name}] 配置缺少 base_url")
        self.scheme_hint = cfg.get("scheme_hint")  # 优先 scheme：http / https / None
        self.auth = cfg.get("auth", {})

    @classmethod
    def load(cls, name: str) -> "SniffSite":
        p = _site_path(name)
        if not p.exists():
            avail = ", ".join(_valid_site_names()) or "(空)"
            raise SystemExit(f"未找到站点配置：{p}\n可用站点：{avail}")
        return cls(json.loads(p.read_text(encoding="utf-8")), name)

    # ---- token 三级回退 ----
    def get_token(self, auto_start=False) -> str:
        a = self.auth
        # ① 环境变量
        env = a.get("token_env")
        if env:
            t = os.environ.get(env)
            if t and len(t) > 8:
                return t.strip().strip('"')
        # ② 凭证文件
        cf = a.get("creds_file")
        ck = a.get("creds_key", "token")
        if cf:
            cands = [cf]
            if not os.path.isabs(cf):
                cands += [os.path.join(os.getcwd(), cf),
                          str(SKILL_DIR / cf), str(SITES_DIR / cf)]
            for c in cands:
                try:
                    if os.path.exists(c):
                        d = json.loads(Path(c).read_text(encoding="utf-8"))
                        t = d.get(ck)
                        if t and len(str(t)) > 8:
                            return str(t).strip().strip('"')
                except Exception:
                    pass
        # ③ bsk evaluate token_expr（从浏览器 sessionStorage/localStorage 取）
        expr = a.get("token_expr")
        if expr:
            ensure_bsk()
            out, _ = _bsk_evaluate(expr, auto_start=auto_start)
            if out and out.strip():
                raw = out.strip().strip('"').strip("'")
                tok = raw
                try:
                    v = json.loads(out.strip())
                    if isinstance(v, dict):
                        for k in ("token", "access_token", "jwt", "id_token", "value"):
                            if v.get(k):
                                tok = str(v[k])
                                break
                    elif isinstance(v, str):
                        tok = v
                except Exception:
                    pass
                # 若 JS 直接返回 JSON.parse 后的对象，再兜底抽 token 字段
                if tok == raw and "{" in raw:
                    m = re.search(r'"(?:token|access_token|jwt|id_token)"\s*:\s*"([^"]+)"', raw)
                    if m:
                        tok = m.group(1)
                if len(tok) > 8:
                    return tok.strip().strip('"')
        raise SystemExit(
            f"[{self.name}] 未能获取 token：\n"
            f"  ① 检查 auth.token_env 环境变量是否设置\n"
            f"  ② 检查 auth.creds_file 凭证文件是否存在且含 {ck!r}\n"
            f"  ③ 检查浏览器已登录该站点、bsk 已连接会话（auth.token_expr={expr!r}）\n"
            f"或先运行一次并把 token 存进 creds_file / 环境变量。"
        )

    # ---- 组装 headers ----
    def _headers(self, token, post=False):
        a = self.auth
        mode = a.get("mode", "bearer")
        h = {"Accept": "application/json",
             "User-Agent": "Mozilla/5.0 (web-api-sniff)"}
        if mode == "bearer":
            h["Authorization"] = f"Bearer {token}"
        elif mode == "cookie":
            h["Cookie"] = token
        elif mode == "custom":
            hdr = a.get("header", "Authorization")
            fmt = a.get("header_format", "{token}")
            h[hdr] = fmt.replace("{token}", token)
        else:
            raise SystemExit(f"[{self.name}] 未知 auth.mode={mode!r}（支持 bearer/cookie/custom）")
        for k, v in a.get("extra_headers", {}).items():
            h[k] = v
        if post:
            h["Content-Type"] = "application/json"
            if a.get("accept_language"):
                h["Accept-Language"] = a["accept_language"]
        return h

    @property
    def headers(self):
        """当前带 token 的 headers（调试用）。"""
        return self._headers(self.get_token())

    # ---- 请求（http/https 自动回退） ----
    def _open(self, url, data=None, token=None, timeout=30):
        post = data is not None
        hdrs = self._headers(token, post=post)
        req0 = urllib.request.Request(url, data=data, headers=hdrs,
                                      method="POST" if post else "GET")
        # 优先 scheme_hint；失败回退另一 scheme（典型：https 报 SSL EOF → 试 http）
        urls = [url]
        if self.scheme_hint and url.startswith(("http://", "https://")):
            host = url.split("://", 1)[1]
            alt = ("https://" if url.startswith("http://") else "http://") + host
            if self.scheme_hint == "http" and url.startswith("https://"):
                urls = [alt, url]
            elif self.scheme_hint == "https" and url.startswith("http://"):
                urls = [alt, url]
        last_err = None
        for u in urls:
            try:
                req = urllib.request.Request(u, data=data, headers=hdrs,
                                             method="POST" if post else "GET")
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    raw = r.read().decode("utf-8", "ignore")
                    try:
                        return json.loads(raw)
                    except Exception:
                        return raw
            except urllib.error.HTTPError as e:
                # 4xx/429 不回退（是业务/鉴权错误）
                if e.code in (400, 401, 403, 404, 429):
                    try:
                        body = e.read().decode("utf-8", "ignore")
                    except Exception:
                        body = ""
                    raise SystemExit(f"[{self.name}] HTTP {e.code} @ {u}\n{body[:800]}")
                last_err = e
            except Exception as e:
                last_err = e
        raise last_err or RuntimeError("请求失败")

    def api_get(self, path, token=None):
        token = token or self.get_token()
        url = path if path.startswith("http") else self.base_url + path
        return self._open(url, token=token)

    def api_post(self, path, body, token=None):
        token = token or self.get_token()
        url = path if path.startswith("http") else self.base_url + path
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        return self._open(url, data=data, token=token)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _cmd_list():
    """本地自检：列出所有站点配置并校验 JSON 合法。不联网、不取 token。"""
    if not any(d.exists() for d in SITES_DIRS):
        log(f"[warn] 站点目录不存在：{SITES_DIRS}")
        log("请先设置 WEB_API_SNIFF_SITES 或在 sites/ 下加 <name>.json。")
        return 0
    rows = []
    seen = set()
    for d in SITES_DIRS:
        if not d.exists():
            continue
        for x in sorted(d.glob("*.json")):
            if x.stem.startswith("_"):
                continue  # 模板文件（_ 开头）跳过
            if x.stem in seen:
                continue  # 同名优先目录已收录
            seen.add(x.stem)
            try:
                c = json.loads(x.read_text(encoding="utf-8"))
                base = c.get("base_url", "?")
                mode = (c.get("auth") or {}).get("mode", "bearer")
                ep = len(c.get("endpoints") or [])
                rows.append((x.stem, mode, base, ep))
            except Exception as e:
                rows.append((x.stem, "ERR", str(e), 0))
    log(f"站点目录：{SITES_DIR}")
    if not rows:
        log("（无站点配置；复制 sites/_iot_template.json 改名后填 base_url 即可）")
        return 0
    log(f"{'站点名':22s} {'鉴权':8s} {'base_url':40s} 接口数")
    for name, mode, base, ep in rows:
        log(f"{name:22s} {mode:8s} {base:40s} {ep}")
    return 0


def main():
    args = sys.argv[1:]
    if not args:
        log("用法:")
        log("  python sniff_api.py list                       # 列出站点配置（本地自检）")
        log("  python sniff_api.py <site> get  <path>")
        log("  python sniff_api.py <site> post <path> '<json body>'")
        log("  python sniff_api.py <site> headers")
        return
    if args[0] == "list":
        sys.exit(_cmd_list())
    site = SniffSite.load(args[0])
    if len(args) < 2:
        log("用法: python sniff_api.py <site> get|post|headers <path>"); return
    cmd = args[1]
    if cmd == "headers":
        for k, v in site.headers.items():
            log(f"  {k}: {v}")
        return
    if cmd == "get":
        if len(args) < 3:
            log("用法: python sniff_api.py <site> get <path>"); return
        out = site.api_get(args[2])
        log(json.dumps(out, ensure_ascii=False, indent=2)[:8000])
        return
    if cmd == "post":
        if len(args) < 4:
            log("用法: python sniff_api.py <site> post <path> '<json body>'"); return
        try:
            body = json.loads(args[3])
        except Exception as e:
            log(f"[err] body 不是合法 JSON: {e}"); return
        out = site.api_post(args[2], body)
        log(json.dumps(out, ensure_ascii=False, indent=2)[:8000])
        return
    log(f"未知命令: {cmd}")


if __name__ == "__main__":
    main()
