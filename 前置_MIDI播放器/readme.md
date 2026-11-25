# 前置_MIDI播放器 0.2.8
> 解析并播放 MIDI 音乐的前置 API，供其它插件调用。

## 功能
- 把 `.mid` 文件解析为 ToolSound 音符序列：`Musicreater.MidiConvert.from_midi_file()` → `to_sequence()`。
- 支持把 MIDI 转换成 ToolSound 序列文件，也支持直接读取已转换的序列文件（比现场解析快）。
- 提供三种播放方式：独立线程异步播放（返回线程 ID，可随时停止）、同步阻塞播放、按音符逐个产出。
- 播放时通过前置 `基本插件功能库` 的 `sendaicmd()` 发送 `/execute as <目标> at @s run playsound <乐器> @s ~~~ <音量> <音高>`。
- 控制台提供 `播放测试`、`停止所有播放` 两个指令。
- 本目录为第三方插件的本地修改版：原作者 `SuperScript`。

## API
先 `midi = self.GetPluginAPI("MIDI播放器")`，再调用：

| 方法 | 说明 |
|---|---|
| `load_midi_file(path, as_name)` | 解析 MIDI 文件，按 `as_name` 存入内存缓存（慢，需要 `Musicreater`） |
| `load_sound_seq_file(path, as_name)` | 读取已转换的 ToolSound 序列文件并载入缓存（快） |
| `translate_midi_to_seq_file(path, path1)` | 把 MIDI 转成 ToolSound 序列文件 |
| `read_midi_file_to_sequence(path)` | 把 MIDI 直接解析成 `ToolSoundSequence` 对象返回 |
| `playsound_at_target(name_or_seq, target)` | 开线程播放，返回播放线程 ID；失败返回 `0` |
| `stop_playing(idc)` | 停止指定播放线程，成功返回 `True`，ID 不存在返回 `False` |
| `playsound_at_target_sync(name_or_seq, target)` | 同步播放，会阻塞调用线程 |
| `iter_playsound(name_or_seq)` | 迭代器，逐个产出 `(乐器, 音量, 音高, 延迟秒)` |

- `ToolSoundSequence` 可迭代，另有 `.duration`（总时长，秒）和 `.dump_seq()`（导出二进制序列）。
- 已载入的音乐按 `as_name` 缓存在 `midi_seqs`；`target` 传命令目标选择器字符串（如 `@a`、`@p`）。

调用示例：

```python
def on_preload(self):
    midi = self.GetPluginAPI("MIDI播放器")
    midi.load_midi_file("歌曲.mid", "song")       # 也可用 load_sound_seq_file 读已转换序列
    tid = midi.playsound_at_target("song", "@a")  # 返回线程 ID，失败为 0
    # midi.stop_playing(tid)                      # 需要时停止
```

## 前置插件
| 插件 ID | 最低版本 | 用途 |
|---|---|---|
| `基本插件功能库` | 0.0.12 | 取 `sendaicmd()` 发送播放命令；已在 `datas.json` 的 `pre-plugins` 声明 |

`datas.json` 的 `plugin-id` 为 `MC-MIDIPlayer`（与官方市场一致），`plugin_entry` 注册的 API 名是 `MIDI播放器`；前置声明用前者，`GetPluginAPI` 用后者。

## 安装
1. 将 `前置_MIDI播放器/` 复制到实例的 `插件文件/ToolDelta类式插件/`；
2. 确认运行环境能 `import Musicreater`（见「依赖与兼容」）；
3. 启动实例，或在 ToolDelta 控制台执行 `reload`；
4. 也可以把本仓库添加为自定义插件市场源后直接安装。

## 配置
无配置文件，开箱即用。已载入的音乐序列只保存在内存（`midi_seqs`），不会落盘。

## 指令
| 位置 | 指令 / 触发词 | 权限 | 说明 |
|---|---|---|---|
| 控制台 | `播放测试` | 无 | 在 ToolDelta 当前目录找第一个 `.mid` 文件，载入并播放给 `@a` |
| 控制台 | `停止所有播放` | 无 | 停止当前所有正在播放的音乐线程 |

## 依赖与兼容
- ToolDelta 1.3.7 类式插件（FateArk / MCSM 面板）；
- 第三方库：`Musicreater`（MIDI 解析/转换，内部还依赖 `mido`）。本目录未内置这两个库：官方市场版把 `Musicreater/`、`mido/` 作为插件目录内的子包一起分发，本仓库目录只有 `__init__.py` 和 `datas.json`；若运行环境也没安装该库，加载会直接报 `ModuleNotFoundError: No module named 'Musicreater'`，需要自行补回子包或先安装库；
- 需要同时安装 `基本插件功能库`；播放依赖魔法指令（PyRpc）通道；
- 本仓库内暂无插件直接调用它的 API，它面向需要 MIDI 解析/播放的外部插件。

## 版本记录
- `0.2.8`（2026-10-25，原作者 `SuperScript`）：本地把同步播放和后台播放线程改为按绝对时间排程（用 `time.monotonic()` 累加每个音符延迟，只等待正差值），避免逐音符 `time.sleep` 的累积漂移；版本号沿用官方 0.2.8（官方市场最新为 0.2.9，本目录未跟进）。
