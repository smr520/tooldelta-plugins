# 前置_循环获取玩家背包 0.0.1

> 用 WebSocket 指令循环查询全部在线玩家背包，提供对象/字典缓存、即时查询与广播 API。

> 收录自 ToolDelta 官方插件市场，原作者 小六神；本仓库仅做文件名/文档规范统一，未改动插件功能代码。

## 功能

- 连入服务器（`ListenActive`）后启动后台线程，按固定间隔用 `sendwscmd` 发送 `codebuilder_actorinfo inventory "<玩家名>"` 查询在线玩家背包，包含 ToolDelta 机器人。
- 每轮并发查询所有在线玩家；查询成功的玩家进入缓存，本轮失败或已离线的玩家会从缓存中移除。
- 每轮结束后通过内部广播 `ggpi:publish_player_inventory` 发布「玩家背包（`QueriedInventory` 对象）」「玩家背包字典（原生 dict）」「失败玩家」「更新时间」。
- 提供即时查询单个玩家、强制刷新全部玩家、读取缓存与失败信息等对外方法，并提供 `queryInventory` 驼峰别名。
- 接入点不支持 WebSocket 指令时插件仍会加载，但只打印一次警告并暂停轮询。
- 纯前置 API，安装后不会主动产生游戏内效果。

## 前置插件

无。

## 安装

1. 将 `前置_循环获取玩家背包/` 复制到实例的 `插件文件/ToolDelta类式插件/`；
2. 启动实例，或在 ToolDelta 控制台执行 `reload`；
3. 也可以把本仓库添加为自定义插件市场源后直接安装。

## 配置

配置文件路径：`插件配置文件/前置-循环获取玩家背包.json`（首次加载自动生成，文件名取自插件类内名称）

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `发送命令间隔时长(单位：秒)` | `3` | 一轮全部玩家查询完成后，等待多久开始下一轮；必须为正数 |
| `单次查询超时时间(秒)` | `1` | 单个玩家背包查询的等待超时；必须为正数 |

- 两个配置项在 `config.py` 中通过 `cfg.PNumber` 校验为正数。
- 运行时可用 `set_cycle()` 或广播 `ggpi:set_cycle` 临时修改轮询间隔，不会写回配置文件。

## API

其它插件在 `on_preload` 中获取实例：

```python
api = self.GetPluginAPI("循环获取玩家背包", (0, 0, 1))
inv = api.get_cached_inventory("玩家名")
```

| 方法 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `query_inventory` | `player_name: str`；`timeout: Optional[float] = None`（默认取配置的单次超时） | `QueriedInventory` | 立即查询一个当前在线玩家并更新其缓存；玩家不在线时抛 `ValueError` |
| `queryInventory` | 同上 | 同上 | `query_inventory` 的驼峰别名 |
| `force_update` | 无 | `dict`（插件暂停时返回 `None`） | 立即并发刷新全部在线玩家并广播 |
| `get_cached_inventory` | `player_name: str` | `QueriedInventory`（没有缓存时为 `None`） | 返回缓存副本 |
| `get_cached_inventories` | 无 | `dict[str, QueriedInventory]` | 返回全部缓存的对象副本 |
| `get_cached_inventories_dict` | 无 | `dict[str, dict]` | 返回全部缓存的原生字典形式 |
| `get_last_failures` | 无 | `dict[str, dict]` | 最近一轮的失败玩家信息，含 `错误`、`失败原因`、`时间` |
| `set_cycle` | `seconds: float` | 无 | 修改内存中的轮询间隔；必须为大于 0 的有限数，否则抛 `ValueError` |

内部广播：

| 接口 | 方向 | 数据 | 说明 |
|---|---|---|---|
| `ggpi:publish_player_inventory` | 本插件发布 | `{"玩家背包": {...}, "玩家背包字典": {...}, "失败玩家": {...}, "更新时间": "ISO-8601 时间"}` | 每轮查询完成后发布一次 |
| `ggpi:force_update` | 其它插件请求 | `{}` | 立即刷新；监听回调可返回本轮快照，暂停时为 `None` |
| `ggpi:set_cycle` | 其它插件请求 | `{"间隔": 5}`，也兼容 `{"cycle": 5}` | 修改轮询间隔，回调返回当前间隔 |

- 返回的 `QueriedInventory` 与字典都是副本，修改不会影响插件内部缓存。
- 更完整的接口说明见同目录 `API调用文档.md`。

## 指令

本插件无手动指令。

## 依赖与兼容

- ToolDelta 1.3.7 类式插件（FateArk / MCSM 面板）
- 无第三方库依赖
- 需要接入点支持 WebSocket 指令通道（`sendwscmd`）；不支持时插件暂停轮询并打印一次警告
- 背包数据结构使用 ToolDelta 的 `QueriedInventory`（来自 `tooldelta.internal.types.inventory_querier`），升级 ToolDelta 时需留意该内部类型是否变化

## 版本记录

- `0.0.1`：收录自 ToolDelta 官方插件市场；本仓库未改动插件功能代码，仅新增统一格式的 `readme.md`

## 说明

- 代码组织：`__init__.py` 为插件入口与对外方法，`config.py` 为配置模板与默认值，`core.py` 为查询、缓存与广播实现。
- 轮询由 `ListenActive` 启动、`ListenFrameExit` 时停止；未连接服务器时不会发起查询。
- 兼容 `DataSet` 直接返回库存对象、`{"inventory": {...}}` 包装、UTF-8 BOM、嵌套 JSON 字符串与被转义的 JSON 文本等返回格式。
