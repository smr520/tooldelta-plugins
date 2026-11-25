# 活力API 0.1.5
> 定时调用外部 OpenAPI 刷新登录态 Token，避免 Token 过期掉线。

> 收录自 ToolDelta 官方插件市场，原作者 `Q3CC`；本仓库有标准化修改。

## 功能
- 插件激活后在后台守护线程里定时保活：先 `GET {OpenAPI地址}/user/getLoginUserSAuth` 取 `data.sauth.sdkuid`，再 `POST {基础地址}/vitalityApi/refresh`（JSON 体 `{"sdkuid": "..."}`）刷新 Token。
- 请求头固定带 `authorization: <API密钥>` 与 `X-Caller: <调用方>`；成功时打印返回的 `ttl` 与 `expiry`。
- `启用自动保活` 为 `true` 时启动线程；`启动时立即刷新` 为 `true` 时线程启动后先立即执行一次，之后按间隔执行。
- `API密钥` 仍是默认占位值 `your-api-key-uuid` 时只打印错误、不启动保活线程。
- 本仓库版本为每次 HTTP 请求内置 30 秒超时（`timeout=30`），单次请求不会无限挂起。
- 框架退出时通知线程停止并最多等待 5 秒；线程为守护线程，不会阻止进程退出。

## 前置插件
| 插件 ID | 最低版本 | 用途 |
|---|---|---|
| 无 | - | 不依赖其它插件；另需第三方库 `requests` 与可访问的外部 OpenAPI |

## 安装
1. 将 `活力API/` 复制到实例的 `插件文件/ToolDelta类式插件/`；
2. 启动实例，或在 ToolDelta 控制台执行 `reload`，首次加载会生成配置文件；
3. 在配置文件中填写有效的 `API密钥`，再执行 `reload`（或重启实例）生效；
4. 也可以把本仓库添加为自定义插件市场源后直接安装。

## 配置
配置文件路径：`插件配置文件/活力API.json`（首次加载自动生成）

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `OpenAPI地址` | `https://nv1.nethard.pro/api/open-api` | 外部 OpenAPI 基础地址；查询接口直接拼 `/user/getLoginUserSAuth`，刷新接口由去掉 `/open-api` 后的地址拼 `/vitalityApi/refresh` |
| `API密钥` | `your-api-key-uuid`（占位） | 必填，作为请求头 `authorization`；保持占位值时不会启动保活 |
| `调用方` | `helperbot` | 作为请求头 `X-Caller`，按服务方要求填写 |
| `自动刷新间隔(分钟)` | `25` | 两次保活之间的间隔；最小按 1 分钟处理，非法值按 25 分钟处理 |
| `启用自动保活` | `true` | 为 `false` 时只打印加载提示，不启动后台线程 |
| `启动时立即刷新` | `true` | 为 `true` 时线程启动后立即执行一次，再进入定时循环 |

- 默认地址下实际请求：`https://nv1.nethard.pro/api/open-api/user/getLoginUserSAuth` 与 `https://nv1.nethard.pro/api/vitalityApi/refresh`。
- 配置在插件 `__init__` 阶段读取，修改后需要 `reload`；`API密钥` 以明文保存在配置文件中，不要提交到公开仓库。

## 指令
本插件无手动指令，只按配置自动定时保活。

## 依赖与兼容
- ToolDelta 1.3.7 类式插件（FateArk / MCSM 面板）；
- 依赖第三方库 `requests`：未随插件内置，缺失时插件加载会因 `import` 失败，可先用 `pip模块支持` 的 `pip-install requests` 安装；
- 依赖能访问 `OpenAPI地址` 的网络与有效 `API密钥`；外部服务不可达时保活失败，但不影响框架与其它插件；
- 失败表现（均只写控制台日志，插件与框架不退出，本轮跳过、下一轮再试）：
  - 网络异常、超时或 HTTP 状态错误（`RequestException`）：打印「获取 sauth 失败」或「refresh 请求异常」；
  - 响应不是 JSON 对象：按失败处理（refresh 返回 `Invalid JSON`）；
  - 未取到 `sdkuid`：打印「未获取到 sdkuid」，本轮不发刷新请求；
  - 刷新接口 `success` 不为 `true`：打印「刷新失败: <error>」。

## 版本记录
- `0.1.5`：收录官方插件市场版本（原作者 `Q3CC`）；本仓库统一文档格式，为 HTTP 请求内置 30 秒超时，其余逻辑未改动。
