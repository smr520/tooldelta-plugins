# 前置_基本插件功能库 0.0.12
> 为其它插件补充游戏数据查询、聊天栏等待和魔法指令等基础 API。

## 功能
- 提供聊天栏列表选择 `list_select()`：把选项按格式发给玩家，等玩家输入序号后返回选项。
- 并发发送多条命令并收集响应 `multi_sendcmd_and_wait_resp()`。
- 等待玩家聊天栏回复 `waitMsg_with_actbar()`，玩家中途退服时抛出 `EXC_PLAYER_LEAVE`（`OSError`）。
- 旧版查询接口：计分板分数 `getScore()`、坐标 `getPos()` / `getPosXYZ()` / `getPosXYZ_Int()`、物品数量 `getItem()`、实体选择器 `getTarget()`、方块 ID `getBlockTile()`。
- 命令结果判断 `sendresultcmd()`，以及发送魔法指令（aiCommand）的 `sendaicmd()`。
- 内部监听聊天与玩家退服事件，把玩家回复转给正在等待的回调。
- 本目录为第三方插件的本地修改版：原作者 `SuperScript`。

## API
先 `api = self.GetPluginAPI("基本插件功能库")`，再调用：

| 方法 | 说明 |
|---|---|
| `list_select(player, choices_list, list_prefix, ...)` | 发列表并等玩家选序号，返回选项字符串；超时/非法输入/列表为空返回 `None` |
| `multi_sendcmd_and_wait_resp(cmds, timeout)` | 并发执行命令，返回 `{命令: Packet_CommandOutput}` |
| `waitMsg_with_actbar(who, msg, timeout=30, exc=None)` | 显示 `msg` 并等待该玩家聊天回复；超时返回 `None`（`exc` 参数当前实现未使用），玩家退服抛 `EXC_PLAYER_LEAVE` |
| `getScore(scoreboardNameToGet, targetNameToGet)` | 取计分板分数；支持 `*` 与 `@` 选择器，失败抛异常 |
| `getPos(targetNameToGet, timeout=1)` | 取坐标，返回 `{dimension, position: {x,y,z}, yRot}` |
| `getPosXYZ(player, timeout=30)` / `getPosXYZ_Int(...)` | 取坐标三元组（浮点 / 整数） |
| `getItem(targetName, itemName, itemSpecialID=-1)` | 取玩家背包物品数量 |
| `getTarget(sth, timeout=5)` | 用 `/testfor` 取符合选择器的实体列表 |
| `getBlockTile(x, y, z)` | 取指定坐标的方块 ID |
| `sendresultcmd(cmd, timeout=30)` | 执行命令并返回是否成功（`bool`） |
| `sendaicmd(cmd)` | 通过 PyRpc 的 aiCommand 发送一条魔法指令 |

`list_select()` 的 `list_format` 默认 `" %d - %s"`，`list_end` 默认 `"§7请选输入选项序号以选择："`，超时、非数字、越界、空列表的提示文案都可以另行传入。

调用示例：

```python
def on_active(self):
    api = self.GetPluginAPI("基本插件功能库")
    choice = api.list_select(
        self.game_ctrl.players.getPlayerByName("玩家名"),
        ["开始", "退出"],
        "§a请选择操作：",
    )
    pos = api.getPosXYZ_Int("玩家名")
    api.sendaicmd("/execute as @a at @s run playsound note.pling @s ~~~")
```

## 前置插件
| 插件 ID | 最低版本 | 用途 |
|---|---|---|
| 无 | - | 不依赖其它插件 |

## 安装
1. 将 `前置_基本插件功能库/` 复制到实例的 `插件文件/ToolDelta类式插件/`；
2. 启动实例，或在 ToolDelta 控制台执行 `reload`；
3. 也可以把本仓库添加为自定义插件市场源后直接安装。

## 配置
无配置文件，开箱即用；也没有数据文件，等待回复的回调只保存在内存（`waitmsg_result`）。

## 指令
本插件无手动指令；它只在后台监听聊天栏回复和玩家退服事件，供 `list_select()` / `waitMsg_with_actbar()` 使用。

## 依赖与兼容
- ToolDelta 1.3.7 类式插件（FateArk / MCSM 面板）；
- 仅使用标准库与 ToolDelta 内置模块，无第三方库；`sendaicmd()` 用到 `tooldelta.constants.netease.PYRPC_OP_SEND`（内部常量路径，升级 ToolDelta 后需要验证）；
- 查询类接口依赖游戏会话在线，`sendwscmd_with_resp` 超时或命令无效会抛异常，调用方需要处理；
- 本仓库内使用它的插件：`前置_MIDI播放器`（取 `sendaicmd()` 播放声音）；其它插件常用 `getPos()`、`getScore()`、`getItem()` 等；
- API 名与 `datas.json` 的 `plugin-id` 同为 `基本插件功能库`。

## 版本记录
- `0.0.12`（2026-10-25，原作者 `SuperScript`）：本地修复 `multi_sendcmd_and_wait_resp()` 的竞态（先建完所有 `Event` 再等待，子线程异常也会 set，等待带总超时）；修复 `waitMsg_with_actbar()` 用 `Player` 对象作键、聊天回调按玩家名查键导致收不到回复的问题，并补上等待提示的显示；官方市场最新为 0.0.13（本目录未跟进）。
