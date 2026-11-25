# 前置_玩家XUID获取 0.0.8
> 玩家名与 XUID 互查的前置 API，带正反向内存缓存和离线文件缓存。

## 功能
- 监听玩家列表包（`PacketIDS.IDPlayerList`）的登录动作，在玩家真正进服前拿到 `Username` ↔ `XUID`。
- 维护两个内存映射：「玩家名 → XUID」和「XUID → 玩家名」；插件激活时再用在线玩家表刷新一遍。
- 把「XUID → 玩家名」写入数据文件缓存，支持离线查询；内存与文件读写都加了线程锁。
- 控制台 `xuids` 打印当前映射表里的玩家名与 XUID。
- 无效 XUID（空值或长度超过 8）只打印错误并跳过，不再让线程抛异常。
- 本目录为第三方插件的本地修改版：原作者 `System`。

## API
先 `xuid_api = self.GetPluginAPI("XUID获取")`，再调用：

| 方法 | 说明 |
|---|---|
| `get_map()` | 返回当前「玩家名 → XUID」字典的副本 |
| `update_map()` | 从在线玩家列表刷新两个映射 |
| `get_xuid_by_name(playername, allow_offline=False)` | 按玩家名取 XUID；取不到抛 `ValueError` |
| `get_name_by_xuid(xuid, allow_offline=False)` | 按 XUID 取玩家名；取不到抛 `ValueError` |
| `get_xuid_by_name_offline(playername)` | 只查文件缓存，取不到抛 `ValueError` |
| `get_name_by_xuid_offline(xuid)` | 只查文件缓存，取不到抛 `ValueError` |
| `record_player_xuid(playername, xuid)` | 手动把「XUID → 玩家名」写入缓存 |

`allow_offline=True` 时，在线表找不到会继续查数据文件缓存。

调用示例：

```python
xuid_api = self.GetPluginAPI("XUID获取")
xuid = xuid_api.get_xuid_by_name("玩家名", allow_offline=True)
name = xuid_api.get_name_by_xuid(xuid, allow_offline=True)
```

## 前置插件
| 插件 ID | 最低版本 | 用途 |
|---|---|---|
| `聊天栏菜单` | 0.0.1 | `datas.json` 里声明的前置，但当前代码没有任何调用，属历史遗留；插件实际不依赖任何前置 |

## 安装
1. 将 `前置_玩家XUID获取/` 复制到实例的 `插件文件/ToolDelta类式插件/`；
2. 启动实例，或在 ToolDelta 控制台执行 `reload`；
3. 也可以把本仓库添加为自定义插件市场源后直接安装。

## 配置
无配置文件。数据缓存文件：`插件数据文件/前置-玩家XUID获取/xuids.json`，内容是「XUID → 玩家名」，首次记录玩家时自动创建。

## 指令
| 位置 | 指令 / 触发词 | 权限 | 说明 |
|---|---|---|---|
| 控制台 | `xuids` | 无 | 打印当前映射表里的在线玩家名与 XUID |

## 依赖与兼容
- ToolDelta 1.3.7 类式插件（FateArk / MCSM 面板）；
- 仅使用标准库（`threading`）与 ToolDelta 内置模块，无第三方库；
- 依赖玩家列表包（`IDPlayerList`）和在线玩家对象里的 `xuid` 字段；
- 本仓库内使用它的插件：`『Orion System』违规与作弊行为综合反制系统`（`pre-plugins` 声明 `XUID获取 >= 0.0.7`）、`白名单&管理员检测云链联动版`（`pre-plugins` 声明 `XUID获取 >= 0.0.1`）。
- `datas.json` 的 `plugin-id` 与 `plugin_entry` 注册的 API 名同为 `XUID获取`。

## 版本记录
- `0.0.8`（本地版本，2026-11-22 同步到实例时由 0.0.7 提到 0.0.8；官方市场最新仍为 0.0.7）；
- `0.0.7`（2026-10-25，原作者 `System`）：本地增加 XUID → 玩家名反向缓存、`xuids.json` 文件缓存和两把线程锁；无效 XUID 改为打印错误并跳过（原来直接抛 `ValueError`）；离线查询不再每次重建反向字典；改用 `self.data_path`，去掉已废弃的 `format_data_path()`。
