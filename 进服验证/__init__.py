import random
from time import time

from tooldelta import plugin_entry, Plugin, ToolDelta, Player, cfg
from tooldelta.utils import tempjson

CODE_TTL_SECONDS = 600


class PlayerJoinverify(Plugin):
    """进服验证：玩家进服先踢出，到指定 QQ 群发送 #验证 <编号> 后放行。

    原始版本依赖官方群服互通的内部列表，这里改为监听本仓库群服互通云链版
    的「群服互通/链接群消息」广播，无需改动群服互通本身。
    """

    name = "进服验证"
    author = "大庆油田"
    version = (0, 0, 2)

    def __init__(self, frame: ToolDelta):
        super().__init__(frame)
        self.ListenPlayerJoin(self.PlayerJoin)
        self.path = str(self.data_path / "验证数据.json")
        self.ListenPreload(self.on_preload)
        CFG_DEFAULT = {"用于接收验证的群": 0}
        cfg_std = cfg.auto_to_std(CFG_DEFAULT)
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, cfg_std, CFG_DEFAULT, self.version
        )
        self.group = int(self.cfg.get("用于接收验证的群") or 0)
        self.reply_group = self.group
        self.qfht = None

    def on_preload(self):
        if self.group <= 0:
            self.print("§c未配置「用于接收验证的群」，进服验证暂不生效")
            return
        self.qfht = self.GetPluginAPI("群服互通", force=False)
        if self.qfht is None:
            self.print("§c未找到 群服互通，群内验证功能不可用")
            return
        linked_group = int(getattr(self.qfht, "linked_group", 0) or 0)
        if linked_group > 0 and linked_group != self.group:
            self.print_war(
                f"配置的验证群({self.group})与群服互通链接群({linked_group})不一致，"
                f"将使用群服互通链接群接收验证消息"
            )
            self.reply_group = linked_group
        self.ListenInternalBroadcast("群服互通/链接群消息", self.on_group_message)

    def get(self) -> dict:
        data = tempjson.load_and_read(
            self.path,
            need_file_exists=False,
            default={"白名单": [], "验证码时间": {}},
        )
        data.setdefault("白名单", [])
        data.setdefault("验证码时间", {})
        return data

    def set(self, data):
        tempjson.load_and_write(self.path, data)

    @staticmethod
    def _message_text(message) -> str:
        if isinstance(message, str):
            return message
        if isinstance(message, list):
            parts = []
            for item in message:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("data", {}).get("text", "")))
            return "".join(parts)
        return ""

    def _send_group(self, message: str):
        if self.qfht is not None:
            self.qfht.sendmsg(self.reply_group or self.group, message)

    def _new_code(self, saved: dict) -> str:
        while True:
            code = str(random.randint(100000, 999999))
            if code not in saved:
                return code

    def _cleanup_codes(self, saved: dict):
        now = int(time())
        times = saved.setdefault("验证码时间", {})
        for code in list(times.keys()):
            if now - int(times[code]) > CODE_TTL_SECONDS:
                times.pop(code, None)
                saved.pop(code, None)

    def on_group_message(self, evt) -> bool | None:
        data = getattr(evt, "data", None) or {}
        message = self._message_text(data.get("消息")).strip()
        if not message.startswith("#验证"):
            return None
        parts = message.split()
        if len(parts) < 2:
            self._send_group("用法：#验证 <编号>（编号见玩家被踢出时的提示）")
            return True
        code = parts[1]
        saved = self.get()
        self._cleanup_codes(saved)
        xuid = saved.get(code)
        if not xuid:
            self._send_group("验证码无效或已过期，请重新进服获取新编号")
            return True
        if xuid not in saved["白名单"]:
            saved["白名单"].append(xuid)
        saved.pop(code, None)
        saved.get("验证码时间", {}).pop(code, None)
        self.set(saved)
        self._send_group("验证成功，可以重新进服了")
        return True

    def PlayerJoin(self, player: Player):
        if self.group <= 0 or self.qfht is None:
            return 0
        saved = self.get()
        self._cleanup_codes(saved)

        if player.xuid not in saved["白名单"]:
            code = self._new_code(saved)
            saved[code] = player.xuid
            saved.setdefault("验证码时间", {})[code] = int(time())
            target_group = self.reply_group or self.group
            self.game_ctrl.sendwocmd(
                f'kick "{player.name}" 您已被踢出游戏：在 {target_group} 发送 #验证 {code}'
            )
        self.set(saved)
        return 0


entry = plugin_entry(PlayerJoinverify, "进服验证")
