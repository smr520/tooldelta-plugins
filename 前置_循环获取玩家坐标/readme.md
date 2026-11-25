# 前置_循环获取玩家坐标 0.0.5

> 循环执行 `/querytarget @a` 获取全服玩家坐标，并通过内部广播分发给其它插件。

> 收录自 ToolDelta 官方插件市场，原作者 ToolDelta；本仓库仅做文件名/文档规范统一，未改动插件功能代码。

## 功能

- 与服务器建立连接（`ListenActive`）后启动后台线程，默认每 1 秒执行一次 `/querytarget @a` 获取全服玩家坐标。
- 把结果整理成「玩家名 → 坐标信息」的字典，通过内部广播 `ggpp:publish_player_position` 发布。
- 坐标信息固定包含 `x`、`y`、`z`、`yRot`、`dimension`（维度编号，整数）五个字段。
- 支持通过内部广播 `ggpp:force_update` 立即刷新一次，或用 `ggpp:set_crycle` 在运行时修改轮询周期。
- 查询失败或超时会在控制台打印原因并跳过本轮发布。
- 纯前置 API，安装后不会主动产生游戏内效果。

## 前置插件

无。

## 安装

1. 将 `前置_循环获取玩家坐标/` 复制到实例的 `插件文件/ToolDelta类式插件/`；
2. 启动实例，或在 ToolDelta 控制台执行 `reload`；
3. 也可以把本仓库添加为自定义插件市场源后直接安装。

## 配置

无配置文件。轮询周期默认 1 秒（类属性 `CYCLE = 1`），可在运行时通过广播 `ggpp:set_crycle` 临时修改，重启插件或实例后恢复为 1 秒。

## API

本插件注册的 API 名为 `循环获取玩家坐标`（版本 0.0.5），实际使用以内部广播为主：

```python
api = self.GetPluginAPI("循环获取玩家坐标", (0, 0, 5))
self.ListenInternalBroadcast("ggpp:publish_player_position", self.on_player_pos)
```

| 接口 | 方向 | 数据 | 说明 |
|---|---|---|---|
| `ggpp:publish_player_position` | 本插件发布 | `{玩家名: {"x": float, "y": float, "z": float, "yRot": float, "dimension": int}}` | 每轮查询完成后发布一次 |
| `ggpp:force_update` | 其它插件请求 | `{}` | 立即执行一次查询并发布 |
| `ggpp:set_crycle` | 其它插件请求 | `{"cycle": float}` | 修改轮询周期（秒），事件名保留代码中的拼写 `crycle` |

- 周期修改只影响当前运行中的线程，不写入配置文件。
- 事件名中的 `crycle` 是代码中的实际拼写，调用时必须原样书写。
- 广播的监听回调参数为 `InternalBroadcast`，坐标字典位于 `evt.data`。

## 指令

本插件无手动指令。

## 依赖与兼容

- ToolDelta 1.3.7 类式插件（FateArk / MCSM 面板）
- 无第三方库依赖
- 依赖接入点的 WebSocket 指令通道（`sendwscmd_with_resp`）执行 `/querytarget @a`
- 依赖 `game_ctrl.players_uuid`，把查询结果中的 `uniqueId` 映射回玩家名

## 版本记录

- `0.0.5`：收录自 ToolDelta 官方插件市场；本仓库未改动插件功能代码，仅统一 `readme` 文件名与格式

## 说明

- 本插件是纯前置 API，单独安装没有可见效果；需要玩家坐标的插件应在自己的 `pre-plugins` 中声明它。
- 只有成功连入服务器后才会开始循环查询；查询不到玩家时本轮不会广播数据。
- 每轮查询的玩家名以服务器返回的 `uniqueId` 经 `players_uuid` 反查；若反查失败，当前代码未捕获该异常，循环可能中断。
