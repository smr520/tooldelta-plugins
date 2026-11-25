# 前置_Cb2Bot通信 0.0.2

> 让命令方块通过 `tellraw` 把数据发给机器人，并提供按前缀注册回调的通信 API。

> 收录自 ToolDelta 官方插件市场，原作者 SuperScript；本仓库仅做文件名/文档规范统一，未改动插件功能代码。

## 功能

- 监听文本数据包（`PacketIDS.IDText`）中 `TextType == 9` 的 rawtext JSON 消息，解析命令方块 `tellraw` 发出的数据。
- 以 `tellraw` 的第一段 `text` 作为「消息前缀」，把其余 `text` 片段分发给注册过该前缀的回调。
- 同一前缀可注册多个回调，按 `priority` 从高到低执行；优先级高的回调先执行，返回 `True` 可提前结束。
- 只要前缀匹配成功，该文本包处理后即被拦截（`ListenPacket` 返回 `True`），不再交给其它文本监听者。
- rawtext JSON 解析失败时通过 `@a` 提示「无法处理数据：…」，且不拦截该数据包。
- 纯前置 API，安装后不会主动产生游戏内效果。

## 前置插件

无。

## 安装

1. 将 `前置_Cb2Bot通信/` 复制到实例的 `插件文件/ToolDelta类式插件/`；
2. 启动实例，或在 ToolDelta 控制台执行 `reload`；
3. 也可以把本仓库添加为自定义插件市场源后直接安装。

## 配置

无配置文件，开箱即用。

## API

在其它插件的 `on_preload` 中获取本插件实例：

```python
def on_trigger(args: list[str]):
    print("回调参数:", args)

api = self.GetPluginAPI("Cb2Bot通信", (0, 0, 2))
api.regist_message_cb("example-trigger", on_trigger)
```

| 方法 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `regist_message_cb` | `prefix: str`：消息前缀（`tellraw` 第一段 `text`）；`cb: Callable[[list[str]], Any]`：回调；`priority: int = 1`：优先级，数值越大越先执行 | 无 | 注册一个该前缀的回调。`cb` 返回 `True` 时立即停止执行同前缀的后续回调；返回其它值则继续执行。 |

`cb` 收到的参数是 `rawtext` 中除前缀外的 `text` 片段列表；`selector`、`score` 等不含 `text` 字段的片段会被忽略。

命令方块示例：

```text
tellraw @a[tag=robot] {"rawtext":[{"text":"example-trigger"},{"text":"nihao"},{"text":"shijie"}]}
```

上述消息触发后，`cb` 收到 `["nihao", "shijie"]`。

## 指令

本插件无手动指令。

## 依赖与兼容

- ToolDelta 1.3.7 类式插件（FateArk / MCSM 面板）
- 无第三方库依赖，仅使用标准库与 ToolDelta 自带模块
- 需要游戏把 `tellraw` 文本作为 `Text` 数据包发给机器人；常见做法是给机器人玩家打 `tag`，再用 `@a[tag=robot]` 作为目标

## 版本记录

- `0.0.2`：收录自 ToolDelta 官方插件市场；本仓库未改动功能代码，仅统一 `readme` 文件名与格式（原 `readme.txt` 内容已并入本文件）

## 说明

- 本插件只有前置 API，单独安装不会产生可见效果；使用命令方块通信的插件通常会在自己的 `pre-plugins` 中声明它。
- 前缀被匹配后，即使没有回调返回 `True`，该文本包也会被拦截，这是代码中的既定行为。
