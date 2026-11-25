import threading

from tooldelta import Plugin, utils, plugin_entry, fmts
from tooldelta.constants import PacketIDS


class XUIDGetter(Plugin):
    name = "前置-玩家XUID获取"
    author = "System"
    version = (0, 0, 8)
    inject_signal = False

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenActive(self.on_inject)
        self.ListenPacket(PacketIDS.IDPlayerList, self.on_pkt)
        self.player_2_xuid_map: dict[str, str] = {}
        self.xuid_2_name_map: dict[str, str] = {}
        self._map_lock = threading.Lock()
        self._file_lock = threading.Lock()
        self._xuid_file_cache: dict[str, str] | None = None

    def on_inject(self):
        self.update_map()
        self.inject_signal = True
        self.frame.add_console_cmd_trigger(
            ["xuids"], None, "查看在线玩家的 XUID 列表", self.on_lookup_xuids
        )
        for k, v in self.get_map().items():
            self.record_player_xuid(k, v[-8:])

    def on_lookup_xuids(self, _):
        for k, v in self.get_map().items():
            self.print(f"{k}: {v}")

    def get_map(self):
        if not self.inject_signal:
            self.update_map()
        with self._map_lock:
            return dict(self.player_2_xuid_map)

    def update_map(self):
        players = self.frame.get_players().getAllPlayers()
        with self._map_lock:
            for player in players:
                self.player_2_xuid_map[player.name] = player.xuid
                self.xuid_2_name_map[player.xuid] = player.name

    @utils.thread_func("处理玩家 XUID")
    def on_pkt(self, pk):
        # 在登录前就获取 XUID
        is_joining = not pk["ActionType"]
        for entry in pk["Entries"]:
            playername = str(entry.get("Username", "")).strip()
            xuid = str(entry.get("XUID", "")).strip()
            if not playername or not xuid:
                # 玩家退出包和登录过程中的空条目都可能带空用户名/XUID。
                continue
            if len(xuid) > 8:
                fmts.print_err(f"忽略无效的玩家 XUID: {playername} / {xuid!r}")
                continue
            if is_joining:
                with self._map_lock:
                    self.player_2_xuid_map[playername] = xuid
                    self.xuid_2_name_map[xuid] = playername
                self.record_player_xuid(playername, xuid)
                fmts.print_inf(f"玩家 {playername} 的 XUID: {xuid}")
        return False

    def get_xuid_by_name(self, playername: str, allow_offline=False):
        """
        通过玩家名获取 XUID.
        Args:
            playername (str): 玩家名
            allow_offline (bool, optional): 是否允许搜索离线玩家, 默认为否.
        Raises:
            ValueError: 无法获取玩家的 XUID
        Returns:
            str: 玩家 XUID
        """
        player = self.frame.get_players().getPlayerByName(playername)
        if player:
            return player.xuid
        if allow_offline:
            return self.get_xuid_by_name_offline(playername)
        else:
            raise ValueError(f"无法获取 {playername} 的XUID")

    def get_name_by_xuid(self, xuid: str, allow_offline=False):
        """
        通过 XUID 获取玩家名.
        Args:
            xuid (str): XUID
            allow_offline (bool, optional): 是否允许搜索离线玩家, 默认为否.
        Raises:
            ValueError: 无法获取玩家名
        Returns:
            str: 玩家名
        """
        with self._map_lock:
            name = self.xuid_2_name_map.get(xuid)
        if name is not None:
            return name
        if allow_offline:
            return self.get_name_by_xuid_offline(xuid)
        else:
            raise ValueError(f"无法通过XUID {xuid} 获取玩家名")

    def _load_xuid_file_cache(self) -> dict[str, str]:
        if self._xuid_file_cache is None:
            path = str(self.data_path / "xuids.json")
            self._xuid_file_cache = utils.tempjson.load_and_read(
                path, need_file_exists=False, default={}
            )
        return self._xuid_file_cache

    def get_name_by_xuid_offline(self, xuid: str):
        with self._file_lock:
            try:
                return self._load_xuid_file_cache()[xuid]
            except KeyError:
                raise ValueError(f"未曾记录XUID {xuid}")

    def get_xuid_by_name_offline(self, playername: str):
        with self._file_lock:
            c = self._load_xuid_file_cache()
            for name_xuid, name in c.items():
                if name == playername:
                    return name_xuid
        raise ValueError(f"未曾记录玩家 {playername} 的XUID")

    def record_player_xuid(self, playername: str, xuid: str):
        with self._file_lock:
            c = self._load_xuid_file_cache()
            if c.get(xuid) == playername:
                return
            c[xuid] = playername
            path = str(self.data_path / "xuids.json")
            utils.tempjson.load_and_write(path, c, need_file_exists=False)


entry = plugin_entry(XUIDGetter, "XUID获取")
