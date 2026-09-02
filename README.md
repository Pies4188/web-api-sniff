# web-api-sniff 通用抓包 · WorkBuddy skill 安装包

仓库根即 skill 本体（仿 BrowserSkill 结构）。两种安装方式任选其一：

## 方式一：让 WorkBuddy 原生安装（推荐，零命令）

把本仓库链接发给你的 WorkBuddy，说一句：

> 帮我装上这个 skill：https://github.com/Pies4188/web-api-sniff

WorkBuddy 会原生拉取、安全审计并安装到 `~/.workbuddy/skills/`，全程不用敲命令。

## 方式二：终端一行命令

Windows（PowerShell）：

```powershell
irm https://raw.githubusercontent.com/Pies4188/web-api-sniff/main/install.ps1 | iex
```

macOS / Linux：

```bash
curl -fsSL https://raw.githubusercontent.com/Pies4188/web-api-sniff/main/install.sh | bash
```


## ⚠️ 浏览器扩展必装（本 skill 依赖 BrowserSkill）
- 装完命令行后，**必须**在浏览器安装对应的 BrowserSkill 扩展并连接一次。
- **建议用 Edge**：Chrome 网上应用店国内需通过代理访问，Edge 外接程序商店国内可直接访问，连扩展更顺。
- 仅命令行装好、未连扩展 = 用不了（最易遗漏的一步）。
## 给同事的转发话术

直接把下面这段发同事即可：

> 你把这个链接发给你的 WorkBuddy，说「帮我装上这个 skill」就能自动装好：
> https://github.com/Pies4188/web-api-sniff
