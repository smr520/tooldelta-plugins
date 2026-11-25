from tooldelta import Player, Plugin, plugin_entry

AUTO_PLUGINS = [
    ("掉落物600上限清理", "每 5 秒统计三世界掉落物，合计超过阈值自动清理"),
    ("崩溃提醒", "机器人进程崩溃时向群服互通绑定群发提醒"),
    ("进服验证", "未验证玩家进服踢出，群内发送 #验证 <编号> 放行"),
    ("玩家人数限制", "在线人数超过上限时踢出非管理员新玩家"),
    ("入服欢迎", "玩家进服/退服自动执行欢迎与告别指令"),
    ("活力API", "定时刷新账号 Token，保持活力"),
    ("指令频率监测", "统计/限制插件下发指令频率，超限告警"),
]

CONSOLE_PLUGINS = [
    ("性能 / top", "性能管理：CPU、内存、JSON 缓存、线程与定时任务"),
    ("up", "控制台一键更新插件：更新全部插件并可立即重载"),
    ("pip-install <模块>", "pip模块支持：安装第三方 Python 库"),
    ("d/<指令>、dw/<指令>", "指令调试器：执行指令并打印完整返回"),
    ("白名单、OP操作", "白名单&管理员检测：交互式管理白名单与管理员"),
    ("指令频率", "指令频率监测：查看当前指令频率与阈值"),
    ("xuids", "前置_玩家XUID获取：查看在线玩家 XUID"),
    ("播放测试、停止所有播放", "前置_MIDI播放器：MIDI 播放调试"),
    ("发群 <消息> / QQ", "群服互通云链版：向绑定 QQ 群发送消息"),
    ("更新公会数据", "公会系统：修复旧版本数据字段"),
]


class PluginGuide(Plugin):
    """游戏内插件指南：统一说明本服插件怎么用。

    玩家在聊天栏发送 .指南 / .插件 查看；
    页数：1=玩家菜单，2=自动运行插件，3=控制台与 QQ 指令。
    """

    name = "插件指南"
    author = "一个高质量的神秘人"
    version = (1, 0, 0)

    def __init__(self, frame):
        super().__init__(frame)
        self.chatbar = None
        self.ListenPreload(self.on_preload)

    def on_preload(self):
        self.chatbar = self.GetPluginAPI("聊天栏菜单", force=False)
        if self.chatbar is None:
            self.print("§c未找到 聊天栏菜单，插件指南无法注册菜单项")
            return
        self.chatbar.add_new_trigger(
            ["指南", "插件"],
            [("页数", int, 1)],
            "查看本服插件用法说明",
            self.show_guide,
        )

    def _menu_entries(self, player) -> list[str]:
        entries = []
        for tri in getattr(self.chatbar, "chatbar_triggers", []):
            triggers = getattr(tri, "triggers", []) or []
            if not triggers or any(t in ("指南", "插件") for t in triggers):
                continue
            if getattr(tri, "op_only", False) and not player.is_op():
                continue
            usage = getattr(tri, "usage", "") or ""
            command = " / ".join("." + t for t in triggers[:2])
            args = ""
            ha = getattr(tri, "argument_hints_str", "")
            if ha:
                args = " " + ha
            entries.append(f"§f{command}{args} §7- §f{usage}")
        return entries

    def show_guide(self, player: Player, args: tuple):
        page = args[0] if args else 1
        page = max(1, min(3, int(page)))
        if page == 1:
            self._show_player_menu(player)
        elif page == 2:
            self._show_auto_plugins(player)
        else:
            self._show_console_qq(player)

    def _show_player_menu(self, player: Player):
        player.show("§6===== §a插件指南 · 玩家菜单§6 =====")
        player.show("§7聊天栏发送对应指令使用；分页菜单可发送 §f.help <页数>§7 查看")
        for line in self._menu_entries(player):
            player.show(line)
        player.show("§7本页/下页：§f.指南 2 §7自动运行插件；§f.指南 3 §7控制台与 QQ 指令")

    def _show_auto_plugins(self, player: Player):
        player.show("§6===== §a插件指南 · 自动运行§6 =====")
        player.show("§7以下插件无需指令，满足条件时自动工作：")
        for name, desc in AUTO_PLUGINS:
            player.show(f"§e{name}§7：§f{desc}")
        player.show("§7这些插件已开箱即用；如需调整请查看 §f插件配置文件/§7 下同名配置。")
        player.show("§7下页：§f.指南 3 §7控制台与 QQ 指令")

    def _show_console_qq(self, player: Player):
        player.show("§6===== §a插件指南 · 控制台 / QQ§6 =====")
        player.show("§7以下指令在 §fToolDelta 面板控制台§7 输入：")
        for cmd, desc in CONSOLE_PLUGINS:
            player.show(f"§e{cmd} §7- §f{desc}")
        player.show("§7QQ 群：发送 §fhelp§7 查看群服互通的全部群指令（需已连接云链）。")
        player.show("§7返回第一页：§f.指南 1")


entry = plugin_entry(PluginGuide, "插件指南")
