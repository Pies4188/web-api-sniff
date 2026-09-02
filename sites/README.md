# 怎么加一个新平台（站点配置填法）

复制 `_iot_template.json`，改名成 `<平台名>.json`（**不要**以 `_` 开头，否则不会被识别为站点）。
然后按下面填。所有字段见 `_iot_template.json` 里的 `notes` 速览。

## 1. base_url —— 接口域名
打开浏览器 DevTools → Network，看任意一条**数据请求**的 URL，host 部分就是。
例如请求发往 `https://api.xxx.com/order/list`，则 `base_url = "https://api.xxx.com"`。

> ⚠️ 前端页是 `a.com`、接口却发往 `b.com`（网关/API 域名不同）很常见，**以接口请求的 host 为准**，不是看地址栏。

## 2. scheme_hint —— 优先协议
填 `http` 或 `https`。内网、政府老平台、很多物联网后台用 `http`；
如果连 `https` 报 `SSL: UNEXPECTED_EOF_WHILE_READING`，就改成 `http`。留空 `""` 则不自动回退。

## 3. auth.mode —— 鉴权方式（三选一）
- `bearer`（最常见）：token 放到 `Authorization: Bearer <token>`。
- `cookie`：整段 cookie 当 token（某些 session 老后台）。
- `custom`：放到任意自定义头，配合 `auth.header` + `auth.header_format`。

### token 三种取法（按优先级自动回退）
1. **环境变量**（最省事、可脚本化）：`auth.token_env: "XXX_TOKEN"`，运行前 `export XXX_TOKEN=...`（或系统环境变量里设好）。
2. **凭证文件**：`auth.creds_file: "creds.json"` + `auth.creds_key: "token"`，文件内容 `{"token":"..."}`。
3. **从浏览器自动读**（临时取数最推荐）：`auth.token_expr` 写一段 JS，从 `sessionStorage` / `localStorage` / `document.cookie` 取 token。
   需已登录该站点、且 BrowserSkill 已连接浏览器会话（未连会自动提示装扩展）。

#### 常见 token_expr 写法
- SPA 把用户信息存 sessionStorage 的 JSON：
  `"token_expr": "JSON.parse(sessionStorage.getItem('currentUser')).token"`
- token 直接存 localStorage 字符串：
  `"token_expr": "localStorage.getItem('token')"`
- 整段 cookie：
  `"auth": {"mode": "cookie", "token_expr": "document.cookie"}`

### IoT 平台常见「签名鉴权」怎么填
阿里云 IoT / 华为 IoTDA / 腾讯 IoT Explorer 等，通常要 `AppKey` + `Timestamp` + `Nonce` + `Signature`
（放在请求头或参数里）。这类**不是简单 token**，用 `custom` 模式：
- 固定头（AppKey、版本号等）放进 `auth.extra_headers`；
- 需要动态算的签名，**先算好**存进环境变量 / 凭证文件，再用 `auth.token_env` 读，配合 `auth.header` / `auth.header_format` 拼到目标头。
- web-api-sniff 不做签名运算，只负责「复现请求」。复杂签名建议在调用前用一小段 Python 算好写入环境变量。

## 4. extra_headers —— 固定头
每次请求都带，比如城小智的 `x-ru-id`、某些平台的 `X-App-Id`、区域/租户标识。从 Network 请求头里照抄。

## 5. endpoints —— 已知接口字典
`[{"action":"列表","method":"POST","path":"/api/xxx/list"}]`。自己抓到后沉淀进去，下次查表免重复抓包。
`find_endpoint.py <名> <关键词>` 能从前端 JS 自动发现接口路径。

## 6. notes —— 备忘
该站点的坑、命名规则、域名说明，自己记一笔。

## 验证闭环
写完别只看响应，要**回查**确认副作用真发生（写操作尤其）。token 永远从配置读，别手贴命令行。
