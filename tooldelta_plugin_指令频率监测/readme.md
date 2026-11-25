# 指令频率监测 0.0.6
> 统计并限制所有插件通过框架发送指令的频率，超限自动阻断并告警。

> 收录自 ToolDelta 官方插件市场，原作者 `Mono`；本仓库有标准化修改。

## 功能
- 插件加载时接管 `game_ctrl` 的 `sendcmd`、`sendwscmd`、`sendaicmd`、`sendaicmdonly`、`sendwocmd` 并记录每次发送的时间戳，框架退出时恢复原始方法。
- 只对「玩家身份」`sendcmd` 与「WebSocket 身份」`sendwscmd` 计数限频；「AI 身份」`sendaicmd` / `sendaicmdonly` 和「WO 身份」`sendwocmd` 只统计、不限制。
- 后台线程每 0.5 秒按 1/3/5/10/30/60/120/300/600/1800/3600 秒共 11 个窗口计算频率（条/秒），任一窗口严格超过阈值即按该窗口配置的阻止时长阻断发送（默认 300 秒）。
- 5 秒窗口频率达到 `max_freq_limit` 的 50% / 70% / 90% 时，按对应 `warning_50pct_enable` / `warning_70pct_enable` / `warning_90pct_enable` 开关在控制台告警；达到 120% 且 `warning_120pct_force_exit` 为 `true` 时写退出日志并调用框架退出。
- 阻断期间 `sendcmd` / `sendwscmd` 直接返回 `None` 并打印「指令发送被阻止」；退出时把各窗口频率、命令总数与完整配置写入 `插件数据文件/指令频率监测/exit_log_<时间>.txt`。
- 提供只读查询方法：`get_frequency(window)`、`get_identity_frequency(identity, window)`、`get_total_frequency(window)`、`is_blocked()`、`get_block_remaining_time()`、`get_server_limits()`。

## 前置插件
| 插件 ID | 最低版本 | 用途 |
|---|---|---|
| 无 | - | 不依赖其它插件 |

## 安装
1. 将 `tooldelta_plugin_指令频率监测/` 复制到实例的 `插件文件/ToolDelta类式插件/`；
2. 启动实例，或在 ToolDelta 控制台执行 `reload`；
3. 也可以把本仓库添加为自定义插件市场源后直接安装。

## 配置
配置文件路径：`插件配置文件/指令频率监测.json`（首次加载自动生成；旧版默认值会被自动替换为新默认值并写回）

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `freq_limit_1s_threshold` / `freq_limit_1s_block_duration` | `20` / `300` | 1 秒窗口阈值（条/秒）与超限阻止秒数 |
| `freq_limit_3s_threshold` / `freq_limit_3s_block_duration` | `15` / `300` | 3 秒窗口 |
| `freq_limit_5s_threshold` / `freq_limit_5s_block_duration` | `10` / `300` | 5 秒窗口 |
| `freq_limit_10s_threshold` / `freq_limit_10s_block_duration` | `8` / `300` | 10 秒窗口 |
| `freq_limit_30s_threshold` / `freq_limit_30s_block_duration` | `7` / `300` | 30 秒窗口 |
| `freq_limit_60s_threshold` / `freq_limit_60s_block_duration` | `6` / `300` | 1 分钟窗口 |
| `freq_limit_120s_threshold` / `freq_limit_120s_block_duration` | `5` / `300` | 2 分钟窗口 |
| `freq_limit_300s_threshold` / `freq_limit_300s_block_duration` | `4` / `300` | 5 分钟窗口 |
| `freq_limit_600s_threshold` / `freq_limit_600s_block_duration` | `3` / `300` | 10 分钟窗口 |
| `freq_limit_1800s_threshold` / `freq_limit_1800s_block_duration` | `2` / `300` | 30 分钟窗口 |
| `freq_limit_3600s_threshold` / `freq_limit_3600s_block_duration` | `2` / `300` | 1 小时窗口 |
| `warning_50pct_enable` | `true` | 频率达到 `max_freq_limit` 50% 时告警 |
| `warning_70pct_enable` | `true` | 频率达到 70% 时告警 |
| `warning_90pct_enable` | `true` | 频率达到 90% 时告警 |
| `warning_120pct_force_exit` | `true` | 频率达到 120% 时写日志并强制退出程序 |
| `enable_command_blocking` | `true` | 设为 `false` 时只告警不阻断（告警后有与阻止时长等长的冷却，避免刷屏） |
| `max_freq_limit` | `20` | 告警百分比换算基准，按 5 秒窗口频率计算 |

- 阈值与阻止时长都按正数校验，类型不符时框架会给出配置报错。
- 只统计经 `game_ctrl` 包装方法发出的指令；插件需在本插件加载之后通过 `game_ctrl` 调用才会被拦截。

## 指令
| 位置 | 指令 / 触发词 | 权限 | 说明 |
|---|---|---|---|
| 控制台 | `指令频率` | 无 | 打印参与限制/所有方法合计/按身份的各窗口频率、命令数量与当前阻断状态 |

本插件没有聊天栏或群聊指令。

## 依赖与兼容
- ToolDelta 1.3.7 类式插件（FateArk / MCSM 面板）；
- 仅使用标准库（`time`、`threading`、`bisect`、`datetime`），无第三方库；
- 从 `tooldelta.internal.types` 导入 `FrameExit` / `Packet_CommandOutput`（内部模块，升级 ToolDelta 大版本时需留意兼容性）；
- 强制退出优先调用 `frame.exit()`，否则尝试 `launcher.update_status(SysStatus.NORMAL_EXIT)`；
- 监测线程由 `utils.createThread` 创建，重载或框架退出时随框架停止。

## 版本记录
- `0.0.6`：收录官方插件市场版本（原作者 `Mono`）；本仓库统一文档格式并核对默认配置，插件逻辑未改动。
