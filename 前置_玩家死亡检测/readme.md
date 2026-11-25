# 前置_玩家死亡检测 0.0.1

> 监听 PyRpc 数据包中的 `OnPlayerDie` 事件，为其它插件提供玩家死亡/重生回调。

> 收录自 ToolDelta 官方插件市场，原作者 ToolDelta；本仓库仅做文件名/文档规范统一，未改动插件功能代码。

## 功能

- 监听 `PacketIDS.PyRpc` 数据包，解析 `ModEventS2C` 事件中的 `OnPlayerDie` 事件。
- 按事件里的 `die` 字段区分：`true` 表示玩家死亡，`false` 表示玩家重生。
- 通过 `pid`（玩家 `uniqueId`）找到对应 `Player` 对象后，逐个调用已注册的死亡或重生回调。
- 找不到对应玩家时忽略该事件；不拦截 PyRpc 数据包（回调固定返回 `False`）。
- 纯前置 API，安装后不会主动产生游戏内效果。

## 前置插件

无。

## 安装

1. 将 `前置_玩家死亡检测/` 复制到实例的 `插件文件/ToolDelta类式插件/`；
2. 启动实例，或在 ToolDelta 控制台执行 `reload`；
3. 也可以把本仓库添加为自定义插件市场源后直接安装。

## 配置

无配置文件，开箱即用。

## API

其它插件在 `on_preload` 中获取实例并注册回调：

```python
class MyPlugin(Plugin):
    name = "示例"

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPreload(self.on_preload)

    def on_preload(self):
        api = self.GetPluginAPI("玩家死亡检测", (0, 0, 1))
        api.listen_player_die(self.on_die)
        api.listen_player_respawn(self.on_respawn)

    def on_die(self, player: Player):
        pass

    def on_respawn(self, player: Player):
        pass
```

| 方法 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `listen_player_die` | `cb: Callable[[Player], None]`：死亡回调 | 无 | 注册玩家死亡监听，回调参数为死亡的 `Player` 对象 |
| `listen_player_respawn` | `cb: Callable[[Player], None]`：重生回调 | 无 | 注册玩家重生监听，回调参数为重生后的 `Player` 对象 |

- 本插件没有提供注销接口；监听器随插件实例在重载时一起重建。
- 事件解析依赖 `pk["Value"]` 的固定结构（`ModEventS2C`、`OnPlayerDie`、`pid`、`die`），服务器协议变化时可能失效。

## 指令

本插件无手动指令。

## 依赖与兼容

- ToolDelta 1.3.7 类式插件（FateArk / MCSM 面板）
- 无第三方库依赖
- 依赖接入点上报 `PyRpc` 数据包，且需能收到 `ModEventS2C` 形式的 `OnPlayerDie` 事件

## 版本记录

- `0.0.1`：收录自 ToolDelta 官方插件市场；本仓库未改动插件功能代码，仅统一 `readme` 文件名与格式

## 说明

- 本插件是纯前置 API，单独安装没有可见效果；需要死亡/重生事件的插件应在自己的 `pre-plugins` 中声明它。
- 死亡与重生是两个独立回调列表，需要同时处理时请分别注册。
