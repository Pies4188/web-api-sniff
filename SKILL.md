# 站点接口直取（通用抓包方法论）

## 这是什么

绝大多数「内管平台 / 运营后台 / SaaS 后台」都是 **Vue / React + 后端 API** 架构：前端所有数据、
所有写操作都来自后端 HTTP 接口。**与其模拟点击 DOM（易卡死、易超时、易限流、易因异步渲染丢数据），
不如直接复现它发出的那个请求。** 登录拿到凭证，之后用 Python `urllib` 直连后端，稳、快、不依赖浏览器渲染。

本 skill 是**站点无关的通用方法论 + 工具**：通过 `sites/<站点名>.json` 配置驱动，把「域名 / 鉴权方式 /
固定头 / 接口字典」全部外置，脚本本身不绑定任何平台。城小智只是内置的第一个示例适配。

**触发场景（说出以下任意一句就走接口直取方式）**：

- 「抓包」「接口直取」「能不能直接调接口」「直接获取网站的接口」「绕开前端」
- 「从 XX 平台取数 / 查询 / 导出 / 写入」「这个后台的 XX 数据怎么拿」
- 任何从某个**网站后台**取数 / 操作的需求（不限城小智）

> 如果用户提到「城小智 / chengxiaozhi / 运营看板 / 维保工单 / 工单处理图 / 设备台账」，直接用本 skill 的
> `sites/chengxiaozhi.json` 适配即可；专业任务（工单→Excel、工单图→飞书）再交给对应的城小智子 skill。

## 零、自动适配模式（给 URL 即可，三步全自动）

**这是本 skill 的核心用法**：当用户给你一个**网站 URL**（或说「适配 / 抓 / 接 / 抓包 <URL>」），
**不要等用户手填 json**——直接跑下面一条命令，自动完成「探域名 → 读登录态 → 找接口 → 直连验证」：

```bash
python scripts/auto_adapt.py <网站URL> [业务关键词] [--name X] [--force]
```

- 没给关键词：先生成配置 + 自动探测鉴权，再提示给个关键词即可继续。
- 给了关键词（如「工单」「device」「list」）：完整跑完并验证接口、写回 `sites/<name>.json`。

`auto_adapt.py` 内部依次调用：`scaffold_site.py`（URL→配置）→ `probe_auth.py`（bsk 读浏览器登录态自动填
`auth`）→ `find_endpoint.py`（枚举前端 chunk 定位接口）→ 直连 GET 验证 → 把可访问接口写进 `endpoints`。

**前置（仅鉴权探测需要）**：浏览器已打开并登录该站点，且 BrowserSkill(bsk) 会话活跃。
无 bsk / 未登录时自动降级为 `token_env` 占位，**不阻断流程**，同事之后补 token 即可。

适配完成后，直接对同事说「可以开始抓了」，用 `sniff_api.py <name> get <path>` 取数。

## 一、通用工具

### `scripts/sniff_api.py` —— 配置驱动的 HTTP 工具

```python
from sniff_api import SniffSite
site = SniffSite.load("chengxiaozhi")   # 从 sites/chengxiaozhi.json 加载
tok  = site.get_token()                 # 取凭证（env → creds_file → bsk evaluate）
rows = site.api_get("/dashboard/api/...")        # 同源鉴权 GET
resp = site.api_post("/workOrder/.../list", body) # 同源鉴权 POST
```

命令行：

```bash
python scripts/sniff_api.py <site> get  <path>
python scripts/sniff_api.py <site> post <path> '<json body>'
python scripts/sniff_api.py <site> headers      # 打印将带上的 headers（不发包，调试用）
```

- **token 三级回退**：① 环境变量 `auth.token_env` → ② 凭证文件 `auth.creds_file[auth.creds_key]`
  → ③ bsk 从已登录浏览器 `evaluate(auth.token_expr)` 取。`bsk` 缺失时自动从官方脚本安装。
- **鉴权模式 `auth.mode`**：`bearer`（默认，填 `Authorization: Bearer <token>`）/`cookie`（填 `Cookie` 头）
  /`custom`（把 token 填入任意 `auth.header`，格式 `auth.header_format`，默认 `{token}`）。
- **`auth.extra_headers`**：每次请求都带的固定头（如 `x-ru-id` / `X-App-Id` 之类站点专有头）。
- **http/https 自动回退**：`scheme_hint` 指定优先 scheme；连接失败（典型 https 报 `SSL: UNEXPECTED_EOF_WHILE_READING`）
  自动换另一 scheme 重试。4xx/429 不回退（是业务/鉴权错误）。

### `scripts/find_endpoint.py` —— 从前端 JS 定位接口

用户只说前端动作（"点转单按钮"），不知道接口名时：

```bash
python scripts/find_endpoint.py <site> <关键词> [--ctx 320]
python scripts/find_endpoint.py chengxiaozhi batchTransWorkOrder
python scripts/find_endpoint.py chengxiaozhi 转单 --ctx 500
```

它会：下载首页 → 找 `app.js` → 枚举所有 lazy chunk → 逐个 grep 关键词 → 打印命中上下文（前后 N 字符）。
纯静态 GET，不需要 token。详见 `references/reverse_eng.md`。

## 二、站点配置规范（sites/\<name>.json）

每个目标站一个 JSON，字段如下：

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 否 | 站点中文名（注释用） |
| `base_url` | **是** | 接口域名，含 scheme，如 `http://example.com` |
| `scheme_hint` | 否 | 优先 scheme：`http` / `https`；留空则不回退 |
| `auth.mode` | 否 | `bearer`(默认) / `cookie` / `custom` |
| `auth.token_env` | 否 | 存放 token 的环境变量名 |
| `auth.creds_file` | 否 | 凭证文件名（相对 cwd 或脚本目录），内含 `auth.creds_key` 字段 |
| `auth.creds_key` | 否 | 凭证文件里的 token 字段名，默认 `token` |
| `auth.token_expr` | 否 | bsk `evaluate` 的 JS 表达式，从浏览器 `sessionStorage`/`localStorage` 取 token |
| `auth.extra_headers` | 否 | 固定头 dict（如 `{"x-ru-id": "..."}`） |
| `auth.accept_language` | 否 | POST 时附加的 `Accept-Language` |
| `auth.header` / `auth.header_format` | 否 | `custom` 模式用：`header_format` 里的 `{token}` 会被替换 |
| `endpoints` | 否 | 已知接口字典 `[{action, method, path}]`，沉淀后查表免重复抓包 |
| `notes` | 否 | 该站点的坑与命名规则 |

**token 取数三种写法示例**：

```json
// 写法 A：sessionStorage 里的 JSON 对象取 .token（最常见 SPA）
"auth": {"mode":"bearer","token_env":"TOKEN","token_expr":"JSON.parse(sessionStorage.getItem('currentUser')).token"}

// 写法 B：localStorage 直接存 token 字符串
"auth": {"mode":"bearer","token_expr":"localStorage.getItem('token')"}

// 写法 C：整段 cookie 鉴权
"auth": {"mode":"cookie","token_expr":"document.cookie"}
```

## 三、适配新站 5 步向导

> 用户用前端语言描述（"到操作台 / 点 XX 按钮"），你负责翻译成后端 HTTP 接口。标准流程见 `references/reverse_eng.md`。

1. **确认浏览器已登录 + bsk 已连接**：`bsk status`（或 `bsk session list --json`）。
   没有活跃会话时 `bsk session start` 会挂起——务必先确认已连接。
2. **定位鉴权方式**：在浏览器 DevTools → Network 里看任意一条请求的请求头，确定 token 放在哪
   （`Authorization` / `Cookie` / 自定义头）、长什么样、从哪来（`sessionStorage`/`localStorage`）。
   据此写 `auth.mode` + `token_expr`。
3. **定位接口**：先看 `endpoints` 表里有没有；没有就 `find_endpoint.py <site> <关键词>` 从 JS bundle 抓。
4. **Python 直连验证**：用 `sniff_api.py <site> get/post` 原样复现，确认返回结构。
5. **沉淀配置**：把 `base_url` / `auth` / 新发现的 `endpoints` / `notes` 写进 `sites/<name>.json`，
   下次直接复用，无需重复抓包。

**验证闭环**：写完别只看响应，要**回查**确认副作用真的发生（派单后派单池该单消失 / 跟踪池出现）。

## 四、通用必踩的坑（按顺序记牢）

1. **token 不要手贴进命令行**。JWT / cookie 很长，shell 引号易截断 → 401。永远从环境变量 / 凭证文件 /
   `token_expr` 读。
2. **站点用 `http` 还是 `https`**：很多内管用 http，urllib 直连 https 报
   `SSL: UNEXPECTED_EOF_WHILE_READING` → 设 `scheme_hint:"http"`。
3. **浏览器里调接口常被限流挂起 60–70s；Python 直连仅 ~0.3s**。数据一律 Python 直连，浏览器只用于取 token / 兜底抓包。
4. **命名三套不一致**（Excel/看板显示名 ≠ 后端返回的 name ≠ 树节点名）。一律按后端返回的精确字段匹配，别信前端显示名。
5. **LIKE / 模糊查询会误匹配**（同名设备、相似单号）。先用精确相等过滤，LIKE 仅用于召回。
6. **字段是「字符串化的 JSON」**：有些接口把数组/`bizData` 用 `JSON.stringify` 过再传，拼 body 时别重复序列化。
7. **接口路径带内容哈希 / 版本号，每次部署可能变**。不要写死旧路径；用 `find_endpoint.py` 重新枚举，或优先走稳定的 REST 前缀。

## 五、与其他 skill 的关系

- 本 skill 是**底层通用能力**（方法论 + 配置驱动工具），其余站点专属 skill 复用其鉴权与接口发现逻辑。
- 城小智相关（运营看板→Excel、工单图→飞书、自动派单）已改为走接口直取，可直接用 `sites/chengxiaozhi.json`。
- 新增任意后台站点：只需加一个 `sites/<name>.json`，无需改脚本。

## 六、同事 5 分钟上手（把本 skill 发给任何人都能用）

本 skill 是**站点无关的通用工具**，发给同事后，同事只需把**网站 URL + 一句需求**交给他的 WorkBuddy，
WB 会按「零、自动适配模式」自动跑完三步并开始抓数据——**同事不必懂 json、不必手填配置**。

### 最省事路径（推荐）
1. 把本 skill 发给同事的 WorkBuddy（GitHub 链接或 zip 安装包，见下方「怎么分发给同事」）。
2. 同事装好后，直接发：`用 web-api-sniff 适配 https://xxx.com 并抓它的工单列表`。
3. WB 自动 `auto_adapt.py` → 探域名 / 读登录态 / 找接口 / 验证，回一句「已适配，可以抓了」。

> 同事唯一要做的准备：在浏览器打开并登录目标站点，连好 BrowserSkill 扩展（用于自动读 token）。
> 这一步 WB 会提醒他，无需你口述。

### 手动路径（同事想自己控制）
- 加一个平台 = 填一个 json：复制 `sites/_iot_template.json` → 改名 `<平台名>.json` → 填 3 件事（见 `sites/README.md`）。
- 或一条命令生成骨架：`python scripts/scaffold_site.py <url>` → 再 `probe_auth.py <名>` 自动探测鉴权。

### token 三种取法（按优先级自动回退）
1. 环境变量 `auth.token_env`（最省事、可脚本化）
2. 凭证文件 `auth.creds_file`
3. 浏览器自动读 `auth.token_expr`（`probe_auth.py` 用 bsk 自动探测并写回，需 BrowserSkill 已连接已登录的会话）

### 怎么定位接口
```bash
python scripts/find_endpoint.py <平台名> <关键词>     # 从前端 JS 枚举 chunk，grep 关键词
python scripts/sniff_api.py <平台名> get  <path>        # 直连验证
python scripts/auto_adapt.py <url> <关键词>             # 一步到位（探域名+鉴权+找接口+验证）
```

### 常见 IoT 平台鉴权
- 简单 token（bearer / cookie）→ `probe_auth.py` 自动探测填入。
- 签名鉴权（AK/SK + Timestamp + Signature，如阿里云 / 华为 / 腾讯 IoT）→ 用 `custom` 模式：
  `extra_headers` 放固定头，动态签名预先算好经环境变量读入（脚本不做签名运算，只复现请求）。详见 `sites/README.md`。

### 验证闭环
写完别只看响应，要**回查**确认副作用真发生（写操作尤其）。token 永远从配置读，别手贴命令行。

### 怎么分发给同事
**★ 首选（发链接即装）**：把本 skill 的 GitHub 仓库链接发给同事的 WorkBuddy，他说一句「帮我装上这个
skill」，WB 原生克隆→审计→安装，零命令。仓库根即 skill（SKILL.md 在根）。

**备选（发 zip 附件）**：
1. 用 `skill-portable-package` 打包：
   `python package_skill.py --skill <本目录> --name web-api-sniff --out web-api-sniff-安装包.zip ...`
   （产出 zip + setup.py + AI安装指引.md + 安装指南）。
2. 把 zip 作为附件发给同事的 WorkBuddy，附一句「按压缩包里的 AI安装指引.md 帮我装好」。
3. 装好后同事把网站 URL 发给他自己的 WB，即自动适配（见「零、自动适配模式」）。
