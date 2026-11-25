# ToolDelta 插件库

个人维护的 [ToolDelta](https://github.com/ToolDelta-Basic/ToolDelta) 类式插件集合，同时可以直接作为 ToolDelta 的**自定义插件市场源**使用。

仓库结构遵循 ToolDelta 官方插件市场（[PluginMarket](https://github.com/ToolDelta-Basic/PluginMarket)）的规范：根目录下每个中文目录就是一个插件，插件目录内包含 `__init__.py`、`datas.json` 和 `readme.md`。

## 插件列表

| 插件 | 版本 | 作者 | 说明 |
|---|---|---|---|
| [掉落物600上限清理](掉落物600上限清理) | 1.0.1 | Codex（自建） | 三世界掉落物合计超过 600 时自动清理，只清 `item` 实体 |
| [崩溃提醒](崩溃提醒) | 0.0.1 | OpenCode（自建） | 机器人进程崩溃时，通过 `群服互通` 向绑定群发提醒 |
| [pip模块支持](pip模块支持) | 0.0.6 | SuperScript | 为 ToolDelta 安装第三方 pip 库 |
| [前置_MIDI播放器](前置_MIDI播放器) | 0.2.8 | SuperScript | MIDI 解析与播放 API 前置 |
| [前置_tps计算器](前置_tps计算器) | 0.0.2 | SuperScript | 按时间包估算服务器 TPS |
| [前置_玩家XUID获取](前置_玩家XUID获取) | 0.0.8 | System | 玩家名 ↔ XUID 互查，带缓存 |
| [前置_基本插件功能库](前置_基本插件功能库) | 0.0.12 | SuperScript | 基本组件 API 前置 |
| [前置_聊天栏菜单](前置_聊天栏菜单) | 0.4.1 | SuperScript | 聊天栏菜单 API 前置 |
| [FateArk掉线检测](FateArk掉线检测) | 0.0.1 | 渊思 | 检查机器人是否掉线 |
| [白名单&管理员检测云链联动版](白名单&管理员检测云链联动版) | 1.1.3 | 猫七街 | 白名单与管理员权限检测 |
| [无邪玩家互传](无邪玩家互传) | 1.0.0 | 无邪 | 玩家互传系统，支持拼音搜索 |
| [『Orion System』违规与作弊行为综合反制系统](『Orion System』违规与作弊行为综合反制系统) | 0.4.4 | style_天枢『猎户座』 | 封禁与反作弊综合系统 |
| [群服互通云链版](群服互通云链版) | 0.3.1 | 大庆油田 / SuperScript | 群服消息互通、查询、背包图片、Orion 联动 |

## 作为插件市场源使用

在实例的 `ToolDelta基本配置.json` 中把 `插件市场源` 改成：

```text
https://raw.githubusercontent.com/smr520/tooldelta-plugins/main
```

如果访问 GitHub 需要镜像（国内直连 raw 可能超时），按 ToolDelta 的镜像格式填写，例如：

```text
https://ghproxy.net/https://raw.githubusercontent.com/smr520/tooldelta-plugins/main
```

然后启动 ToolDelta，在控制台输入 `插件市场` 即可浏览和安装本仓库的插件。

## 手动安装

1. 把需要的插件目录整个复制到实例的：

   ```text
   插件文件/ToolDelta类式插件/<插件目录>/
   ```

2. 启动实例，或在控制台执行 `reload`；
3. 需要配置的插件，配置文件会生成在 `插件配置文件/` 下，首次加载后按插件 `readme.md` 修改。

## 仓库结构

```text
.
├── <插件目录>/
│   ├── __init__.py
│   ├── datas.json
│   ├── readme.md
│   └── ...（插件需要的其它文件）
├── market_tree.json        # 插件市场索引（自动生成）
├── plugin_ids_map.json     # 插件 ID → 目录名（自动生成）
├── latest_versions.json    # 各插件最新版本（自动生成）
├── directory_tree.json     # 文件树，客户端按此下载（自动生成）
└── _workflow.py            # 索引生成脚本
```

修改、增删插件后，运行：

```bash
python _workflow.py
```

即可重新生成索引文件，再提交。

## 来源与许可

- 本仓库包含自建插件，以及对 ToolDelta 官方插件市场中部分插件的**本地修改版**。第三方插件的版权归原作者所有，来源与改动说明见 [NOTICE.md](NOTICE.md)。
- 本仓库中由维护者编写的部分（自建插件、索引脚本、文档）使用 [BSD 3-Clause License](LICENSE)。
- 仓库不包含面板凭据、云链密钥、QQ 群号、实例 UUID 或运行时配置。

维护：`smr520`
