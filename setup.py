# -*- coding: utf-8 -*-
"""WorkBuddy skill 一键安装助手（通用版，由 make_github_publish.py 生成）

自动完成：把仓库根（即 skill 本体）复制到 <home>/.workbuddy/skills/<name>，
并对 scripts/ 下全部 .py 做语法校验。仓库根即 skill（仿 BrowserSkill）。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

PUBLISH_ARTIFACTS = ("install.ps1", "install.sh", "setup.py", "README.md",
                     "安装指南.md", "AI安装指引.md", ".gitignore", "__pycache__")


def read_skill_name():
    here = os.path.dirname(os.path.abspath(__file__))
    md = os.path.join(here, "SKILL.md")
    if os.path.isfile(md):
        m = re.search(r"^name:\s*(.+)$", open(md, encoding="utf-8").read(), re.MULTILINE)
        if m:
            return m.group(1).strip()
    return None


SKILL_NAME = read_skill_name() or os.path.basename(
    os.path.dirname(os.path.abspath(__file__)))


def log(*a):
    print(*a, flush=True)


def copy_skill(home):
    repo_root = os.path.dirname(os.path.abspath(__file__))
    dst = os.path.join(home, ".workbuddy", "skills", SKILL_NAME)
    src = repo_root
    if not os.path.isfile(os.path.join(src, "SKILL.md")):
        sub = os.path.join(repo_root, SKILL_NAME)
        if os.path.isdir(sub):
            src = sub
    if not os.path.isfile(os.path.join(src, "SKILL.md")):
        if os.path.isdir(dst):
            log("[*] skill 已存在，跳过复制:", dst)
            return True
        log("[!] 找不到 SKILL.md，安装中止")
        return False
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copytree(
        src, dst, dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(*PUBLISH_ARTIFACTS, "*.pyc",
                                       "*.token.json", ".env"))
    log("[✓] skill 已复制到:", dst)
    return True


def find_python(home):
    for c in (os.path.join(home, ".workbuddy", "binaries", "python",
                           "versions", "3.13.12", "python.exe"),
              "python3", "python", "py"):
        try:
            subprocess.run([c, "--version"], capture_output=True,
                           text=True, timeout=15)
            return c
        except Exception:
            continue
    return None


def run_validate(home):
    py = find_python(home)
    if not py:
        log("[!] 未找到 Python，跳过语法校验（不影响安装）")
        return 0
    scripts = os.path.join(home, ".workbuddy", "skills", SKILL_NAME, "scripts")
    if not os.path.isdir(scripts):
        scripts = os.path.dirname(os.path.abspath(__file__))
    log("[*] 使用 Python:", py)
    bad = 0
    for root, _, files in os.walk(scripts):
        for f in files:
            if f.endswith(".py"):
                r = subprocess.run([py, "-m", "py_compile", os.path.join(root, f)],
                                   capture_output=True, text=True, timeout=60)
                if r.returncode != 0:
                    bad += 1
                    log("[✗] 语法错误:", f)
                    log(r.stderr)
    if bad == 0:
        log("[✓] 全部 .py 语法校验通过")
    return 0 if bad == 0 else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=None, help="目标 home（测试用）")
    ap.add_argument("--python", default=None)
    args = ap.parse_args()
    home = args.home or os.path.expanduser("~")
    log("== %s · 一键安装 ==" % SKILL_NAME)
    if not copy_skill(home):
        return 2
    rc = run_validate(home)
    log("\n== 安装助手结束（返回码 %d）==" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
