"""```
『Orion System 猎户座』违规与作弊行为综合反制系统
╔════════════════════════════════════════════════════════════╗
║    ██████╗     ██████╗     ██╗     ██████╗     ██╗   ██╗   ║
║   ██╔═══██╗    ██   ██╗    ██║    ██╔═══██╗    ███╗  ██║   ║
║   ██║   ██║    ██   ██║    ██║    ██║   ██║    ████╗ ██║   ║
║   ██║   ██║    ██████╔╝    ██║    ██║   ██║    ██╔██╗██║   ║
║   ██║   ██║    ██╔██═╝     ██║    ██║   ██║    ██║ ████║   ║
║   ██║   ██║    ██║ ██╗     ██║    ██║   ██║    ██║  ███║   ║
║   ╚██████╔╝    ██║  ██╗    ██║    ╚██████╔╝    ██║   ██║   ║
║    ╚═════╝     ╚═╝  ╚═╝    ╚═╝     ╚═════╝     ╚═╝   ╚═╝   ║
╚════════════════════════════════════════════════════════════╝
```"""

from tooldelta import Plugin, fmts, plugin_entry, TYPE_CHECKING
from threading import Lock
import os
from importlib import reload

from . import config
from . import core
from . import ban_system
from . import utils

reload(config)
reload(core)
reload(ban_system)
reload(utils)


class _ReShim:
    """标准库 re 的兼容层：把 regex 库专有的 \\p{Han} 翻译成等价的 CJK 范围。"""

    @staticmethod
    def compile(pattern: str):
        import re

        return re.compile(pattern.replace("\\p{Han}", "\u4e00-\u9fff"))


class Orion_System(Plugin):
    """插件主类"""

    name = "『Orion System』违规与作弊行为综合反制系统"
    author = "style_天枢『猎户座』"
    version = (0, 4, 4)

    def __init__(self, frame) -> None:
        """
        初始化插件
        Args:
            frame (ToolDelta): ToolDelta框架
        """
        super().__init__(frame)
        self.config_mgr = config.OrionConfig(self)
        self.utils = utils.OrionUtils(self)
        self.config_mgr.load_config()
        self.config_mgr.upgrade_plugin_data()
        self.create_lock()
        self.create_dir()
        self.core = core.OrionCore(self)
        self.ban_system = ban_system.BanSystem(self)
        server_number = getattr(self.frame.launcher, "serverNumber", None)
        if (
            self.config_mgr.load_in_trial_server is False
            and server_number in self.config_mgr.trial_server_list
        ):
            fmts.print_inf(f"§b发现本服({server_number})为测试服，猎户座将不会启动")
            return
        self.ListenPreload(self.on_preload)
        self.ListenActive(self.on_active)
        self.core.entry()

    def on_preload(self) -> None:
        """插件加载完成后调用此方法"""
        self.xuid_getter = self.GetPluginAPI("XUID获取")
        self.chatbar = self.GetPluginAPI("聊天栏菜单")
        self.regex = self.load_regex_module()

        # 进行类型检查
        if TYPE_CHECKING:
            from 前置_玩家XUID获取 import XUIDGetter
            from 前置_聊天栏菜单 import ChatbarMenu

            self.xuid_getter: XUIDGetter
            self.chatbar: ChatbarMenu

    def load_regex_module(self):
        """加载正则模块。

        优先使用 regex 库（支持 \\p{Han} 等语法）；当实例没有安装 pip 前置插件
        或 regex 库不可用时，退回标准库 re，并把 \\p{Han} 翻译成等价的 CJK 范围。
        """
        try:
            pip = self.GetPluginAPI("pip")
            pip.require({"regex": "regex"})
            import regex

            return regex
        except Exception as error:
            fmts.print_war(
                f"未能加载 regex 库，已退回标准库 re: {error}"
            )
            return _ReShim()

    def on_active(self) -> None:
        """机器人进入租赁服后调用此方法"""
        self.utils.print_inf(self.config_mgr.info_top_message)
        self.ban_system.entry()
        self.core.active_entry()

    def create_lock(self) -> None:
        """创建插件需要的线程锁"""
        # 这是获取玩家设备号函数的线程锁，要求当多个玩家连续登录时逐个获取设备号，而不是连续tp最后啥也没得到
        self.lock_get_device_id = Lock()
        # 这是玩家封禁函数的线程锁，要求在封禁玩家时如果有相同路径读取操作时逐一读取磁盘，防止出现冲突或报错
        self.lock_ban_xuid = Lock()
        self.lock_ban_device_id = Lock()
        # 这是用于刷新“检测发言频率”和“检测重复刷屏”缓存的计时器的线程锁，防止异步资源访问时出现冲突
        self.lock_timer = Lock()

    def create_dir(self) -> None:
        """创建插件需要的目录和依赖文件"""
        os.makedirs(f"{self.data_path}/{self.config_mgr.xuid_dir}", exist_ok=True)
        os.makedirs(f"{self.data_path}/{self.config_mgr.device_id_dir}", exist_ok=True)
        player_data_path = f"{self.data_path}/{self.config_mgr.player_data_file}"
        if not os.path.exists(player_data_path):
            utils.OrionUtils.disk_write(player_data_path, {})


entry = plugin_entry(Orion_System, "Orion_System")
