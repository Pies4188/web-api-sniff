# 从前端操作定位后端接口（通用逆向方法论）

> 适用：用户**只懂点界面**，用「到操作台 / 进入派单池 / 点击 xx 按钮」这类前端语言描述需求。
> 你（AI）要**自己**把前端动作翻译成后端 HTTP 接口，再调用完成操作。本文件是可复用的标准流程，与具体站点无关。

---

## 一、核心心智模型

目标站点通常是 **Vue/React + 后端 API** 的内管系统。前端所有数据、所有写操作都来自后端 HTTP 接口。
**与其模拟点击 DOM（易卡死、易超时、易限流、因异步渲染丢数据），不如直接复现它发出的那个请求。**

所以任务 = 找到「这个按钮点了之后，前端到底 POST 了什么 URL + 什么 body」，然后用 Python + 凭证原样重发。
你不需要懂逆向术语，按下面 5 步走即可。

---

## 二、前端术语 → 接口 速查表（先查这张表）

很多时候**不用抓包**就能猜到接口，先看用户说的词落在哪一类（具体映射每个站点写在 `sites/<name>.json`
的 `endpoints` 里）。典型归类：

| 用户前端说法 | 后端接口（常见形态） |
|---|---|
| 列表 / 台账 / 报表 | `GET/POST .../list`、`.../page`、`.../statistics` |
| 选组织 / 选部门 | 组织树接口 `.../orgTree` / `.../getAuthOrg` |
| 派单池（待派） | `.../selectAssign...` |
| 派单 / 分派按钮 | `.../batchAssign...` |
| 跟踪池（已派） | `.../selectTrack...` |
| 转单 / 转派按钮 | `.../batchTrans...` |
| 审批池 | `.../selectApprove...` |
| 取消 / 延期 | `.../batchCancel...` / `.../batchDelay...` |
| 选处理人 / 协同人 | `.../user/search`、`.../getUser` |
| 详情 | `.../info/<id>` 或 `.../get/<id>` |

**如果 `endpoints` 里已有 → 直接跳到第五节复现请求。** 表里没有 → 走第三节抓包。

---

## 三、静态逆向：从 JS Bundle 提取接口（表里没有时）

现代 SPA 多是 webpack / vite 打包，前端逻辑不在 `index.html` 里，而在 `/static/js/*.js`。
`app.js` 只是运行时壳，**真正的页面逻辑（含接口 URL）在 lazy chunk 里**。

### 步骤

1. **拉首页，拿到 app.js 路径**
   ```python
   GET <base_url>/
   # 解析出 <script src="/static/js/app.<hash>.js">
   ```

2. **拉 app.js，枚举 lazy chunk 文件名**
   webpack 在 app.js 里存了一张「chunk id → 文件名」映射表（形如
   `{0:"0.ab12cd.js", ...}` 或 `{"chunk-3e7351b6":"chunk-3e7351b6.ab1f8781.js",...}`）。
   用正则抽出所有 `*.js` 文件名。**这些就是候选 chunk。**

3. **逐 chunk 抓下来，搜关键词**
   你要找的是按钮对应的接口名（如 `batchTransWorkOrder` / `selectTrackWorkOrderList` / `handleTransfer`）。
   用 `find_endpoint.py` 一键完成 2–3 步：
   ```bash
   python scripts/find_endpoint.py <site> batchTransWorkOrder
   ```
   它会下载 app.js → 枚举所有 chunk → 逐个 grep → 把**命中上下文（前后 N 字符）**打印出来。

4. **从上下文还原请求体**
   chunk 里通常是 `o["a"].batchTransWorkOrder(t, e)` 这种调用 + 一个构造 `e` 的函数
   （如 `handleTransfer:function(){...}`）。把那个函数体读完整，照着拼出 JSON body。
   重点看：最外层字段、数组项结构、`JSON.stringify(...)`（说明某字段是「字符串化的 JSON」）、
   必填项（如 `taskId` / `workOrderType` / `bizData`）。

> ⚠️ chunk 文件名带内容哈希，**每次部署都会变**。不要写死某个 `chunk-xxx.<hash>.js`，
> 而要用 `find_endpoint.py` 当时重新枚举。历史文档里记的 chunk 名仅作线索，可能已失效。

---

## 四、动态逆向（静态找不到时的兜底）

如果接口是运行时拼出来的、或 chunk 结构看不懂：

1. 打开已登录的目标站点浏览器（bsk 已连接会话），手动点一次那个按钮；
2. 用浏览器 DevTools 的 Network 面板抓到真实请求（URL + Request Body + Response）；
3. 把 body 抄进 Python 脚本，**但 token 不要从浏览器复制**——
   改用 `SniffSite.get_token()` 从环境变量 / 凭证文件 / `token_expr` 读（见坑 1）。

---

## 五、复现请求并验证

```python
from sniff_api import SniffSite
site = SniffSite.load("<site>")
tok  = site.get_token()
body = { ... }              # 照 chunk 里还原的结构
r = site.api_post("/xxx/dispatch/v1/batchTransWorkOrder", body)
assert r.get("state") is True or r.get("code") == 0   # 按站点返回结构判断
```

**验证闭环**：写完别只看响应，要**回查**确认副作用真的发生——
派单后回查派单池该单消失 / 跟踪池出现；转单后回查处理人字段已变。

---

## 六、必踩的坑（按顺序记牢）

1. **token 不要手贴进命令行**。凭证很长，shell 引号易截断 → 401「token 解析出错」。
   永远从环境变量 / 凭证文件 / `token_expr` 读：`SniffSite.get_token()` 会按配置自动取。
2. **站点用 `http` 还是 `https`**：本机 urllib 直连 https 可能报 `SSL: UNEXPECTED_EOF_WHILE_READING`。
   设 `scheme_hint:"http"` 让脚本优先 http，失败再回退 https。
3. **浏览器里调接口会被限流挂起 60–70s；Python 直连仅 ~0.3s**。数据一律 Python 直连，浏览器只用于取 token / 兜底抓包。
4. **命名三套不一致**（前端显示名 ≠ 后端返回的 name ≠ 树节点名）。一律按后端返回的精确字段匹配。
5. **模糊查询误匹配**：同名设备、相似单号，LIKE 会误配。先按精确相等过滤，LIKE 仅用于召回。
6. **字段是「字符串化的 JSON」**：有些接口把数组/`bizData` 用 `JSON.stringify` 过再传，拼 body 时别重复序列化。
7. **组织/项目过滤参数格式**：有些接口传错结构会 500（如带 `projectIds` 而非 `ucOrgId`）。参数格式以抓到的真实请求为准，别凭空猜。

---

## 七、输出约定（把成果沉淀回 skill）

每次成功逆向一个新接口，把以下内容写回 `sites/<name>.json` 的 `endpoints` 与 `notes`：
- 接口 URL + 请求体完整结构（含分支）；
- 它对应哪个前端动作；
- 踩到的坑（如上面 1–7）。
这样下次用户再说同样的前端词，直接查表即可，无需重复抓包。
