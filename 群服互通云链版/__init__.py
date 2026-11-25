"""群服互通云链版：QQ 群 <-> 网易我的世界服务器互通插件。

单群消息转发、权限管理、玩家查询、背包图片（内置素材，无需 Pillow）、
Orion 封禁联动、断线重连、消息去重和发送限速。
"""

import base64
import inspect
import json
import os
import queue
import re
import struct
import threading
import time
import zlib
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Tuple

import websocket
from tooldelta import (
    FrameExit,
    InternalBroadcast,
    Plugin,
    cfg,
    fmts,
    plugin_entry,
    utils,
)

# ================ 常量 ================

# 发送：单线程队列 + 限速，避免突发刷屏和跨线程 send 竞争
MAX_MESSAGE_LENGTH = 900
SEND_INTERVAL = 0.2  # 每条消息最小间隔，约 5 条/秒
SEND_QUEUE_SIZE = 2000

# 消息去重：记住最近 500 个 message_id，防止云链重连后重放旧消息
DEDUP_CACHE_SIZE = 500

# 指令限频：非超管两次指令最小间隔（秒）
COMMAND_COOLDOWN = 1.0
COOLDOWN_CACHE_SIZE = 200

# 非超管不能用的高危 MC 指令（移动机器人 + 服务器管理）
MOVEMENT_MC_COMMANDS = ("tp", "teleport", "ride", "spreadplayers")
DANGEROUS_MC_COMMANDS = MOVEMENT_MC_COMMANDS + ("op", "deop", "stop")
BLOCKED_MC_PATTERN = re.compile(
    r"^(" + "|".join(DANGEROUS_MC_COMMANDS) + r")\b"
)
EXECUTE_BLOCKED_PATTERN = re.compile(r"\b(" + "|".join(MOVEMENT_MC_COMMANDS) + r")\b")

# 断线时待在发送队列里等待重连的最长时间
SEND_RECONNECT_WAIT = 10.0

# 心跳 / 重连
RECONNECT_BASE_DELAY = 5
RECONNECT_MAX_DELAY = 60
RECONNECT_NOTICE_WINDOW = 3600
RECONNECT_NOTICE_LIMIT = 5

# 背包素材（由 tools/build_group_bridge_assets.py 从 素材源/ 打包）
INVENTORY_ASSET_FILE = "assets.bin"
INVENTORY_ASSET_MAGIC = b"GQB1"
INVENTORY_ASSET_FORMAT = "rgba8888"
INVENTORY_IMAGE_UI_SIZE = (176, 166)
INVENTORY_IMAGE_ICON_SIZE = (16, 16)
INVENTORY_PAGE_SIZE = 20

DIMENSION_NAMES = {0: "主世界", 1: "下界", 2: "末地"}

# 3x5 像素数字，用于背包图片右下角的堆叠数量
DIGIT_GLYPHS = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
}

CQ_CLEAN_PATTERN = re.compile(r"\[CQ:[^\]]*\]")
CQ_PATTERN = re.compile(r"\[CQ:([a-zA-Z]+)(?:,[^\]]*)?\]")
COLOR_CODE_PATTERN = re.compile(r"§.")
CQ_REPLACEMENTS = {
    "image": "[图片]",
    "video": "[视频]",
    "file": "[文件]",
    "face": "[表情]",
    "at": "[@]",
    "reply": "[回复]",
}

# ================ 模块级工具函数 ================


def _inventory_value(obj: Any, *names: str, default: Any = None) -> Any:
    """同时读取背包响应中的 dict 字段和对象属性。"""
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def normalize_inventory_dataset(dataset: Any) -> dict:
    """兼容 FateArk 的 DataSet 字典、Val 字符串和普通背包字典。"""
    value = dataset
    for _ in range(6):
        if isinstance(value, str):
            value = json.loads(value)
            continue
        if isinstance(value, dict) and "Val" in value:
            value = value["Val"]
            continue
        break

    if not isinstance(value, dict):
        raise ValueError(f"无法解析背包返回：{type(value).__name__}")
    status_code = value.get("statusCode")
    if status_code not in (None, 0):
        raise ValueError(f"背包查询状态异常：{status_code}")
    inventory = value.get("inventory")
    if inventory is None and "slots" in value:
        inventory = value
    if not isinstance(inventory, dict):
        raise ValueError("背包返回中缺少 inventory")
    if not isinstance(inventory.get("slots"), list):
        raise ValueError("背包返回中缺少 slots")
    return inventory


def parse_inventory_assets(data: bytes) -> dict:
    """解析 assets.bin。

    文件格式：``b"GQB1" + uint32(压缩块长度) + zlib(uint32(头长度) + json 头 + 像素)``，
    像素 = 背包 UI（RGBA） + 按头里 items 顺序排列的 16x16 图标（RGBA）。
    """
    if len(data) < 12 or data[:4] != INVENTORY_ASSET_MAGIC:
        raise ValueError("背包素材文件头不正确")
    chunk_size = struct.unpack(">I", data[4:8])[0]
    chunk = data[8:8 + chunk_size]
    if len(chunk) != chunk_size:
        raise ValueError("背包素材文件不完整")
    raw = zlib.decompress(chunk)
    if len(raw) < 4:
        raise ValueError("背包素材内容不完整")

    header_size = struct.unpack(">I", raw[:4])[0]
    header = json.loads(raw[4:4 + header_size].decode("utf-8"))
    if not isinstance(header, dict):
        raise ValueError("背包素材头格式不正确")
    if header.get("format") != INVENTORY_ASSET_FORMAT:
        raise ValueError(f"不支持的背包素材格式：{header.get('format')}")

    ui_size = (int(header["ui_size"][0]), int(header["ui_size"][1]))
    icon_size = (int(header["icon_size"][0]), int(header["icon_size"][1]))
    ui_bytes = ui_size[0] * ui_size[1] * 4
    icon_bytes = icon_size[0] * icon_size[1] * 4
    item_ids = [str(item_id) for item_id in header["items"]]
    payload = raw[4 + header_size:]
    if len(payload) != ui_bytes + icon_bytes * len(item_ids):
        raise ValueError("背包素材长度与物品数量不匹配")

    icons = {}
    offset = ui_bytes
    for item_id in item_ids:
        icons[item_id] = payload[offset:offset + icon_bytes]
        offset += icon_bytes

    return {
        "ui_size": ui_size,
        "icon_size": icon_size,
        "ui_rgba": payload[:ui_bytes],
        "icons": icons,
        "item_names": {
            str(item_id): str(cn_name)
            for item_id, cn_name in header.get("item_names", {}).items()
        },
        "enchantments": {
            int(ench_id): str(cn_name)
            for ench_id, cn_name in header.get("enchantments", {}).items()
        },
    }


def clean_cq_code(content: str) -> str:
    """移除文本中的 CQ 码。"""
    if not content:
        return content
    return CQ_CLEAN_PATTERN.sub("", content)


def replace_cq_tags(content: str) -> str:
    """把 CQ 码替换成可读文字。"""
    if not content:
        return content

    def replace_func(match):
        return CQ_REPLACEMENTS.get(match.group(1), "")

    return CQ_PATTERN.sub(replace_func, content)


def remove_color(text: str) -> str:
    """去掉 MC 聊天文本里的 § 颜色代码。"""
    if not text:
        return text
    return COLOR_CODE_PATTERN.sub("", str(text))


# ================ 触发器 ================
class QQMsgTrigger:
    """QQ 群消息触发器。"""

    def __init__(
        self,
        triggers: List[str],
        argument_hint: str,
        usage: str,
        func: Callable,
        args_validator: Callable[[int, List[str]], bool] = lambda _, __: True,
        op_only: bool = False,
        super_op_only: bool = False,
        example: str = "",
        accepts_server_id: bool = True,
    ):
        self.triggers = triggers
        self.argument_hint = argument_hint
        self.usage = usage
        self.func = func
        self.args_validator = args_validator
        self.op_only = op_only
        self.super_op_only = super_op_only
        self.example = example
        self.accepts_server_id = accepts_server_id
        # 长的触发词优先，避免 /查询背包 被 / 抢先匹配
        self.sorted_triggers = sorted(
            (trigger for trigger in triggers if trigger), key=len, reverse=True
        )

    def match(self, msg: str) -> Optional[str]:
        """匹配触发词。

        短英文触发词（list/help）必须完全相等或后面跟空白，避免 listxxx 误触；
        ``/`` 仍然按前缀匹配，用于执行 MC 指令。
        """
        msg = msg.strip()
        for trigger in self.sorted_triggers:
            if trigger == "/":
                if msg.startswith("/"):
                    return trigger
                continue
            if msg == trigger:
                return trigger
            if (
                msg.startswith(trigger)
                and len(msg) > len(trigger)
                and msg[len(trigger)].isspace()
            ):
                return trigger
        return None


# ================ 插件主体 ================
class QQLinker(Plugin):
    """群服互通插件主类。"""

    version = (0, 3, 1)  # 0.3.1：结构收敛 + 指令限频 + 缺图标物品改进
    name = "群服互通"
    QQMsgTrigger = QQMsgTrigger

    # 默认配置 - 仅作占位，实际值由实例本地配置提供。
    # 注意：schema 不能随意增删键，否则老实例的配置文件会校验失败。
    CFG_DEFAULT = {
        "云链设置": {
            "地址": "ws://127.0.0.1:3001",
            "校验码": "",
        },
        "服务器标识配置": {},
        "权限设置": {
            "超级管理员QQ号": 0,
            "初始普通指令权限QQ号": [],
            "初始屏蔽QQ号": [],
        },
        "消息转发设置": {
            "链接的群聊": 0,
            "游戏到群": {
                "是否启用": True,
                "转发格式": "<[玩家名]> [消息]",
                "仅转发以下符号开头的消息(列表为空则全部转发)": [],
                "屏蔽以下字符串开头的消息": [],
            },
            "群到游戏": {
                "是否启用": True,
                "转发格式": "<[昵称]> [消息]",
            },
        },
    }

    # ---------------------------------------------------------------
    # 生命周期
    # ---------------------------------------------------------------
    def __init__(self, frame):
        super().__init__(frame)
        self._init_paths()
        self._init_config()
        self._init_state()
        self._init_inventory_assets()
        self._init_item_translations()
        self._init_enchantment_translations()
        self._setup_event_listeners()

    def _init_paths(self):
        self.items_file = str(self.data_path / "items.json")
        self.permissions_file = str(self.data_path / "qq_permissions.json")
        self.blocked_file = str(self.data_path / "blocked_qqs.json")

    def _setup_event_listeners(self):
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_active)
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPlayerLeave(self.on_player_leave)
        self.ListenChat(self.on_player_message)
        self.ListenFrameExit(self.on_frame_exit)

    def on_def(self):
        """预加载阶段：取可选插件 API。"""
        self.tps_calc = self.GetPluginAPI("tps计算器", (0, 0, 1), False)
        # Orion 可选：没装/未启用时 orban/orunban 只回复不可用
        self.orion = self.GetPluginAPI("Orion_System", (0, 4, 0), False)

    @utils.thread_func("WS连接主线程")
    def on_active(self):
        """插件激活阶段。

        先注册指令、启动消息/发送/心跳线程，再连接云链；
        这样即使首次连接失败，重连成功后指令也能直接使用。
        """
        self._stop_event.clear()
        self._start_message_workers()
        self._start_sender()
        self.init_basic_triggers()
        self._start_heartbeat()
        self.connect_to_websocket()

    def on_frame_exit(self, _evt: FrameExit):
        self._graceful_shutdown()

    # ---------------------------------------------------------------
    # 配置
    # ---------------------------------------------------------------
    def _init_config(self):
        cfg_std = cfg.auto_to_std(self.CFG_DEFAULT)
        # auto_to_std 无法从空列表推断元素类型；显式声明，兼容线上老配置里
        # 的 int / 字符串 QQ 列表和空字符串列表。
        cfg_std["权限设置"]["初始普通指令权限QQ号"] = cfg.JsonList((int, str), -1)
        cfg_std["权限设置"]["初始屏蔽QQ号"] = cfg.JsonList((int, str), -1)
        cfg_std["消息转发设置"]["游戏到群"][
            "仅转发以下符号开头的消息(列表为空则全部转发)"
        ] = cfg.JsonList(str, -1)
        cfg_std["消息转发设置"]["游戏到群"][
            "屏蔽以下字符串开头的消息"
        ] = cfg.JsonList(str, -1)
        self.cfg, _ = cfg.get_plugin_config_and_version(
            self.name, cfg_std, self.CFG_DEFAULT, self.version
        )

        perm_settings = self.cfg["权限设置"]
        msg_settings = self.cfg["消息转发设置"]
        game2qq = msg_settings["游戏到群"]
        ws_settings = self.cfg["云链设置"]

        self.super_op_qq = self._to_int(perm_settings["超级管理员QQ号"], 0)
        self.linked_group = self._to_int(msg_settings["链接的群聊"], 0)
        if self.linked_group <= 0:
            fmts.print_war(f"群服互通：链接的群聊配置无效（{self.linked_group}），不会处理群消息")
        self.enable_game_2_group = game2qq["是否启用"]
        self.enable_group_2_game = msg_settings["群到游戏"]["是否启用"]
        self.group2game_format = msg_settings["群到游戏"]["转发格式"]
        self.game2qq_trans_chars = game2qq[
            "仅转发以下符号开头的消息(列表为空则全部转发)"
        ]
        self.game2qq_block_prefixs = game2qq["屏蔽以下字符串开头的消息"]
        try:
            self.heartbeat_interval = max(5, int(ws_settings.get("心跳间隔", 30)))
        except (TypeError, ValueError):
            self.heartbeat_interval = 30

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _init_state(self):
        self.ws = None
        self.ws_connected = False
        self.triggers: List[QQMsgTrigger] = []
        self.orion = None
        self.tps_calc = None

        # 线程 / 连接
        self._stop_event = threading.Event()
        self._connection_lock = threading.RLock()
        self._send_lock = threading.Lock()
        self._is_connecting = False

        # 重连
        self._reconnect_attempts = 0
        self._reconnect_notice_times: List[float] = []

        # 消息处理
        self._message_queue: "queue.Queue[dict]" = queue.Queue(maxsize=5000)
        self._message_workers: List[threading.Thread] = []
        self._seen_message_ids: deque = deque()
        self._seen_message_id_set = set()
        self._dedup_lock = threading.Lock()
        self._init_notify_sent = False

        # 发送
        self._send_queue: "queue.Queue[Tuple[int, str]]" = queue.Queue(
            maxsize=SEND_QUEUE_SIZE
        )
        self._sender_thread: Optional[threading.Thread] = None
        self._next_send_time = 0.0

        # 心跳 / 统计
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stats = {
            "messages_received": 0,
            "messages_sent": 0,
            "commands_executed": 0,
            "errors": 0,
            "start_time": time.time(),
        }
        self._stats_lock = threading.Lock()

        # 指令限频
        self._cmd_cooldowns: Dict[int, float] = {}
        self._cooldown_lock = threading.Lock()

        # 权限 / 屏蔽名单
        self._perm_lock = threading.RLock()
        self.extra_super_op_qqs = self._load_extra_super_ops()
        self.normal_perms = self._load_or_merge_qq_list(
            self.permissions_file, "normal_perms", "初始普通指令权限QQ号"
        )
        self.blocked_qqs = self._load_or_merge_qq_list(
            self.blocked_file, "blocked_qqs", "初始屏蔽QQ号"
        )

    def _load_or_merge_qq_list(self, file_path: str, key: str, initial_key: str) -> List[int]:
        """读取名单并合并配置里的初始名单；读取失败时不覆盖磁盘文件。"""
        loaded = self._load_json_list(file_path, key)
        merged = list(set((loaded or []) + self._initial_int_list(initial_key)))
        if loaded is not None and merged != loaded:
            self._save_json_list(file_path, key, merged)
        return merged

    def _initial_int_list(self, key: str) -> List[int]:
        result = []
        for raw_qq in self.cfg["权限设置"].get(key, []):
            try:
                qq = int(raw_qq)
            except (TypeError, ValueError):
                continue
            if qq > 0:
                result.append(qq)
        return result

    def _load_extra_super_ops(self) -> List[int]:
        """兼容多超管实例：主超管之外的超管放在可选键里。"""
        result = []
        for raw_qq in self.cfg["权限设置"].get("额外超级管理员QQ号", []):
            try:
                qq = int(raw_qq)
            except (TypeError, ValueError):
                continue
            if qq > 0 and qq != self.super_op_qq and qq not in result:
                result.append(qq)
        return result

    # ---------------------------------------------------------------
    # 背包素材 / 名称表
    # ---------------------------------------------------------------
    def _init_inventory_assets(self):
        """加载 assets.bin。插件自己拼图并用标准库编码 PNG，因此不依赖 Pillow。"""
        self.inventory_assets_ready = False
        self._asset_ui_size = INVENTORY_IMAGE_UI_SIZE
        self._asset_icon_size = INVENTORY_IMAGE_ICON_SIZE
        self._asset_ui_rgba = b""
        self._asset_icons: Dict[str, bytes] = {}
        self._asset_item_names: Dict[str, str] = {}
        self._asset_enchantments: Dict[int, str] = {}

        asset_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), INVENTORY_ASSET_FILE
        )
        try:
            with open(asset_path, "rb") as f:
                assets = parse_inventory_assets(f.read())
        except FileNotFoundError:
            fmts.print_war(
                f"未找到背包素材 {INVENTORY_ASSET_FILE}，.查背包 只输出文字版"
            )
            return
        except Exception as e:
            fmts.print_err(f"加载背包素材失败：{e}；.查背包 只输出文字版")
            return

        self._asset_ui_size = assets["ui_size"]
        self._asset_icon_size = assets["icon_size"]
        self._asset_ui_rgba = assets["ui_rgba"]
        self._asset_icons = assets["icons"]
        self._asset_item_names = assets["item_names"]
        self._asset_enchantments = assets["enchantments"]
        self.inventory_assets_ready = True
        fmts.print_suc(
            f"背包图片素材已加载：{len(self._asset_icons)} 个物品图标、"
            f"{len(self._asset_item_names)} 条物品名称"
        )

    def _init_item_translations(self):
        """物品中文名：内置 assets.bin 表 + 实例数据目录 items.json 覆盖。"""
        self.item_cn2en: Dict[str, str] = {}
        self.item_en2cn: Dict[str, str] = {}
        for item_id, cn_name in self._asset_item_names.items():
            self._register_item_name(item_id, cn_name)

        if not os.path.exists(self.items_file):
            return
        try:
            with open(self.items_file, "r", encoding="utf-8") as f:
                item_data = json.load(f)
        except Exception as e:
            fmts.print_err(f"加载 {self.items_file} 失败：{e}")
            return
        if not isinstance(item_data, dict):
            return
        for item_id, cn_name in item_data.items():
            self._register_item_name(item_id, cn_name)

    def _register_item_name(self, item_id: Any, cn_name: Any):
        if not isinstance(item_id, str) or not isinstance(cn_name, str):
            return
        item_id = item_id.strip().lower()
        if ":" in item_id:
            item_id = item_id.split(":", 1)[1]
        cn_name = cn_name.strip()
        if not item_id or not cn_name:
            return
        self.item_en2cn[item_id] = cn_name
        self.item_cn2en.setdefault(cn_name, item_id)

    def _init_enchantment_translations(self):
        self.enchantment_name_map: Dict[int, str] = dict(self._asset_enchantments)

    # ---------------------------------------------------------------
    # 文件读写（权限 / 屏蔽名单 / items.json）
    # ---------------------------------------------------------------
    def _load_json_list(self, file_path: str, key: str) -> Optional[List[int]]:
        """读取 int 列表；文件不存在返回空表，读取失败返回 None（不覆盖磁盘）。"""
        if not os.path.exists(file_path):
            return []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [int(item) for item in data.get(key, [])]
        except Exception as e:
            fmts.print_err(f"读取 {file_path} 失败（保留原文件）：{e}")
            return None

    def _save_json_list(self, file_path: str, key: str, items: List[int]):
        """先写临时文件再 os.replace，避免写一半被读到。"""
        tmp_path = f"{file_path}.tmp"
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump({key: items}, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, file_path)
        except Exception as e:
            fmts.print_err(f"保存 {file_path} 失败：{e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

    def _save_permissions(self):
        with self._perm_lock:
            self._save_json_list(
                self.permissions_file, "normal_perms", list(self.normal_perms)
            )

    def _save_blocked_qqs(self):
        with self._perm_lock:
            self._save_json_list(
                self.blocked_file, "blocked_qqs", list(self.blocked_qqs)
            )

    # ---------------------------------------------------------------
    # WebSocket 连接
    # ---------------------------------------------------------------
    @utils.thread_func("云链群服连接进程")
    def connect_to_websocket(self):
        """单循环连接 + 自动重连。

        旧实现靠 on_error/on_close 各自调度 Timer，容易重复调度并快速耗尽重连
        次数；这里在循环里按 5/10/20/40/60 秒退避，只有插件退出才停止。
        """
        with self._connection_lock:
            if self._is_connecting:
                return
            if self._stop_event.is_set():
                return
            self._is_connecting = True
        try:
            while not self._stop_event.is_set():
                ws_url = self.cfg["云链设置"]["地址"]
                auth_code = self.cfg["云链设置"]["校验码"]
                headers = {"Authorization": f"Bearer {auth_code}"} if auth_code else None
                try:
                    with self._send_lock:
                        self.ws = websocket.WebSocketApp(
                            ws_url,
                            header=headers,
                            on_message=self.on_ws_message,
                            on_error=self.on_ws_error,
                            on_close=self.on_ws_close,
                            on_open=self.on_ws_open,
                        )
                    self.ws.run_forever(
                        ping_interval=30, ping_timeout=10, ping_payload="ping"
                    )
                except Exception as e:
                    if not self._stop_event.is_set():
                        fmts.print_err(f"云链连接异常：{e}")
                finally:
                    self.ws_connected = False
                    with self._send_lock:
                        if self.ws is not None:
                            try:
                                self.ws.close()
                            except BaseException:
                                pass
                            self.ws = None

                if self._stop_event.is_set():
                    break
                delay = min(
                    RECONNECT_BASE_DELAY * (2 ** min(self._reconnect_attempts, 4)),
                    RECONNECT_MAX_DELAY,
                )
                self._reconnect_attempts += 1
                self._log_reconnect(delay)
                if self._stop_event.wait(delay):
                    break
        finally:
            with self._connection_lock:
                self._is_connecting = False

    def _log_reconnect(self, delay: float):
        """限制重连日志频率：一小时最多提示 5 次。"""
        now = time.time()
        self._reconnect_notice_times = [
            t for t in self._reconnect_notice_times
            if now - t < RECONNECT_NOTICE_WINDOW
        ]
        if len(self._reconnect_notice_times) < RECONNECT_NOTICE_LIMIT:
            self._reconnect_notice_times.append(now)
            fmts.print_war(
                f"云链连接已断开，{delay:.1f} 秒后自动重连"
                f"（第 {self._reconnect_attempts} 次）"
            )

    def on_ws_open(self, _ws):
        self.ws_connected = True
        self._reconnect_attempts = 0
        self._reconnect_notice_times.clear()
        if not self._init_notify_sent:
            self._init_notify_sent = True
            self._send_init_notify()

    def on_ws_error(self, _ws, error):
        self.ws_connected = False
        if isinstance(error, KeyboardInterrupt):
            return
        if self._reconnect_attempts == 0 and not self._stop_event.is_set():
            fmts.print_err(f"云链连接错误：{error}")

    def on_ws_close(self, _ws, _code, _msg):
        self.ws_connected = False

    # ---------------------------------------------------------------
    # 消息接收
    # ---------------------------------------------------------------
    def on_ws_message(self, _ws, message):
        if not self.ws_connected:
            return
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            fmts.print_err(f"云链消息解析失败：{e}")
            return
        except Exception as e:
            fmts.print_err(f"云链消息处理异常：{e}")
            return
        self._put_message(data)

    def _put_message(self, data: dict):
        """入队但不阻塞 WS 回调线程；队列满时丢最旧的一条再入队。"""
        try:
            self._message_queue.put_nowait(data)
            return
        except queue.Full:
            pass
        try:
            self._message_queue.get_nowait()
            self._message_queue.task_done()
        except queue.Empty:
            pass
        fmts.print_err(f"消息队列已满，丢弃一条消息：{str(data)[:100]}...")
        try:
            self._message_queue.put_nowait(data)
        except queue.Full:
            pass

    def _start_message_workers(self, worker_count: int = 1):
        """启动消息处理线程；reload 后旧的死线程不会阻止重新启动。"""
        self._message_workers = [w for w in self._message_workers if w.is_alive()]
        if self._message_workers:
            return
        for i in range(max(1, min(worker_count, 4))):
            worker = threading.Thread(
                target=self._message_worker_loop,
                name=f"消息处理工作者-{i}",
                daemon=True,
            )
            worker.start()
            self._message_workers.append(worker)

    def _message_worker_loop(self):
        try:
            while not self._stop_event.is_set():
                batch = []
                for _ in range(10):
                    try:
                        batch.append(self._message_queue.get(timeout=0.1))
                    except queue.Empty:
                        break
                for data in batch:
                    try:
                        self._handle_ws_message(data)
                    except Exception as e:
                        fmts.print_err(f"处理云链消息异常：{e}")
                    finally:
                        self._message_queue.task_done()
                if not batch:
                    time.sleep(0.1)
        except Exception as e:
            fmts.print_err(f"消息处理工作者异常：{e}")

    def _is_duplicate_message(self, message_id) -> bool:
        """按 message_id 去重（只保留最近 500 条），防止重连后重放。"""
        key = str(message_id)
        with self._dedup_lock:
            if key in self._seen_message_id_set:
                return True
            if len(self._seen_message_ids) >= DEDUP_CACHE_SIZE:
                self._seen_message_id_set.discard(self._seen_message_ids.popleft())
            self._seen_message_ids.append(key)
            self._seen_message_id_set.add(key)
            return False

    def _handle_ws_message(self, data: Dict):
        if data.get("post_type") != "message":
            return
        message_id = data.get("message_id")
        if message_id is not None and self._is_duplicate_message(message_id):
            return
        self._update_stat("messages_received", 1)

        # 融合 1.0.0：把原始消息广播给其它插件（有插件接管则不再走内置逻辑）
        if self._broadcast("群服互通/数据json", data):
            return

        try:
            if data["message_type"] != "group":
                return
            user_id = int(data["sender"]["user_id"])
            self._handle_group_message(data, user_id)
        except KeyError as e:
            self._update_stat("errors")
            fmts.print_err(f"云链消息缺少必要字段：{e}")
        except Exception as e:
            self._update_stat("errors")
            fmts.print_err(f"处理消息内容时异常：{e}")

    def _handle_group_message(self, data: Dict, user_id: int):
        try:
            if int(data["group_id"]) != self.linked_group:
                return
        except (KeyError, TypeError, ValueError):
            return

        msg = self._extract_message_text(data["message"])
        if msg is None:
            return

        sender = data.get("sender") or {}
        nickname = sender.get("card") or sender.get("nickname") or ""
        if self._broadcast(
            "群服互通/链接群消息",
            {"QQ号": user_id, "昵称": nickname, "消息": data["message"]},
        ):
            return

        if self.execute_triggers(user_id, msg, "group"):
            return
        # 被屏蔽的人不转发到游戏；但上面的指令检查会回一句“你已被屏蔽”
        if self.is_blocked(user_id):
            return
        if self.enable_group_2_game and self.ws_connected:
            # 去掉群昵称/消息里的 § 颜色代码，避免游戏里出现控制符
            formatted_msg = utils.simple_fmt(
                {
                    "[昵称]": remove_color(str(nickname)),
                    "[消息]": replace_cq_tags(remove_color(msg)),
                },
                self.group2game_format,
            )
            self.game_ctrl.say_to("@a", formatted_msg)

    @staticmethod
    def _extract_message_text(message) -> Optional[str]:
        """从云链消息体提取文本（兼容字符串和 NapCat 的数组格式）。"""
        if isinstance(message, str):
            return message
        if isinstance(message, list):
            text_parts = []
            for item in message:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("data", {}).get("text", ""))
            return "".join(text_parts) if text_parts else None
        return None

    def _broadcast(self, name: str, data) -> bool:
        """向其它插件广播；有插件返回非空即视为已接管。"""
        try:
            return any(self.BroadcastEvent(InternalBroadcast(name, data)))
        except Exception as e:
            fmts.print_err(f"广播 {name} 失败：{e}")
            return False

    # ---------------------------------------------------------------
    # 消息发送
    # ---------------------------------------------------------------
    def _start_sender(self):
        if self._sender_thread is not None and self._sender_thread.is_alive():
            return
        self._sender_thread = threading.Thread(
            target=self._sender_loop, name="群服互通发送线程", daemon=True
        )
        self._sender_thread.start()

    def _wait_until_connected(self, timeout: float = SEND_RECONNECT_WAIT) -> bool:
        """断线时让待发消息在队列里等一会儿，而不是直接丢。"""
        deadline = time.monotonic() + timeout
        while not self._stop_event.is_set():
            if self.ws_connected and self.ws is not None:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            if self._stop_event.wait(min(0.5, remaining)):
                return False
        return False

    def _sender_loop(self):
        """按固定速率串行发送群消息，避免突发刷屏和跨线程 send 竞争。"""
        while not self._stop_event.is_set():
            try:
                item = self._send_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                self._send_queue.task_done()
                break
            try:
                group_id, message = item
                if not self._wait_until_connected():
                    fmts.print_err("云链仍未连接，丢弃一条待发群消息")
                    continue
                wait = self._next_send_time - time.monotonic()
                if wait > 0 and self._stop_event.wait(wait):
                    break
                payload = {
                    "action": "send_group_msg",
                    "params": {"group_id": group_id, "message": message},
                }
                sent = False
                with self._send_lock:
                    ws = self.ws
                    if ws is not None and self.ws_connected:
                        ws.send(json.dumps(payload, ensure_ascii=False))
                        sent = True
                if not sent:
                    # 连接在等待期间又断了：放回队列，下一轮再试
                    try:
                        self._send_queue.put_nowait(item)
                    except queue.Full:
                        pass
                    continue
                self._next_send_time = (
                    max(time.monotonic(), self._next_send_time) + SEND_INTERVAL
                )
                self._update_stat("messages_sent")
            except Exception as e:
                self._update_stat("errors")
                fmts.print_err(f"发送群消息失败：{e}")
            finally:
                self._send_queue.task_done()

    def sendmsg(self, group_id: int, message: str, split: bool = True):
        """发送群消息（保留 CQ 码），实际发送由单线程队列完成。

        split=False 用于背包图片这类不能按长度切分的消息。
        """
        if not self.ws or not self.ws_connected:
            fmts.print_err("云链未连接，无法发送群消息")
            return
        if message is None:
            return
        text = str(message)
        chunks = self._split_message(text) if split else [text]
        for chunk in chunks:
            try:
                self._send_queue.put_nowait((group_id, chunk))
            except queue.Full:
                fmts.print_err("发送队列已满，丢弃一条群消息")
                break

    @staticmethod
    def _safe_cut_index(text: str, limit: int) -> int:
        """找一个不会把 [CQ:...] 码切断的切分位置。"""
        cut = min(limit, len(text))
        # 允许匹配到切点之后，覆盖 "[CQ:" 前缀本身被切开的情况
        open_pos = text.rfind("[CQ:", 0, cut + 4)
        if open_pos != -1:
            closing = text.find("]", open_pos)
            if closing == -1 or closing >= cut:
                if open_pos > 0:
                    return open_pos
                return (closing + 1) if closing != -1 else len(text)
        return max(1, cut)

    @staticmethod
    def _split_message(message: str) -> List[str]:
        """按长度拆分长消息，优先在换行处断开，且不切断 CQ 码。"""
        if len(message) <= MAX_MESSAGE_LENGTH:
            return [message]

        chunks: List[str] = []
        current = ""
        for line in message.splitlines(keepends=True):
            while len(line) > MAX_MESSAGE_LENGTH:
                if current:
                    chunks.append(current)
                    current = ""
                cut = QQLinker._safe_cut_index(line, MAX_MESSAGE_LENGTH)
                chunks.append(line[:cut])
                line = line[cut:]
            if len(current) + len(line) > MAX_MESSAGE_LENGTH:
                if current:
                    chunks.append(current)
                current = line
            else:
                current += line
        if current:
            chunks.append(current)
        return chunks or [message[:MAX_MESSAGE_LENGTH]]

    def _send_reply(self, qqid: int, message: str, msg_type: str = "group"):
        """群内 @ 回复；私聊已不支持。"""
        if not self.ws_connected:
            fmts.print_err(f"云链未连接，无法回复 {qqid}")
            return
        if msg_type == "group":
            self.sendmsg(self.linked_group, f"[CQ:at,qq={qqid}] {message}")

    def _send_group(self, message: str):
        """兼容旧版外部插件：直接往链接群发消息。"""
        self.sendmsg(self.linked_group, message)

    def _send_init_notify(self):
        if not self.ws_connected:
            return
        version = ".".join(str(part) for part in self.version)
        status = "云链：已连接"
        try:
            status += f"  |  在线：{len(self.game_ctrl.players.getAllPlayers())} 人"
        except Exception:
            pass
        if self.inventory_assets_ready:
            status += "  |  背包图片：可用"
        self.sendmsg(
            self.linked_group,
            f"✅ 群服互通已上线（v{version}）\n{status}\n发送 help 查看指令",
        )
        fmts.print_suc(f"📢 初始化通知已发送至QQ群 ({self.linked_group})")

    # ---------------------------------------------------------------
    # 触发器 / 权限
    # ---------------------------------------------------------------
    def add_trigger(
        self,
        triggers,
        argument_hint,
        usage,
        func,
        args_validator=lambda _, __: True,
        op_only=False,
        super_op_only=False,
        example="",
    ):
        self.triggers.append(
            QQMsgTrigger(
                triggers, argument_hint, usage, func,
                args_validator, op_only, super_op_only, example,
                accepts_server_id=self._accepts_server_id(func),
            )
        )

    @staticmethod
    def _accepts_server_id(func: Callable) -> bool:
        """自己的指令是 4 参回调；外部插件可能注册 3 参回调，两者都兼容。"""
        try:
            parameters = list(inspect.signature(func).parameters.values())
        except (TypeError, ValueError):
            return True
        if any(p.kind == p.VAR_POSITIONAL for p in parameters):
            return True
        positional = [
            p for p in parameters
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        return len(positional) >= 4

    def _call_trigger(self, trigger: QQMsgTrigger, qqid: int, args: List[str], msg_type: str):
        if trigger.accepts_server_id:
            return trigger.func(qqid, args, msg_type, None)
        return trigger.func(qqid, args, msg_type)

    def execute_triggers(self, qqid: int, msg: str, msg_type: str = "group") -> bool:
        if not self.ws_connected:
            self._send_reply(qqid, "⚠️ 云链暂未连接，请稍后再试。", msg_type)
            return True
        if msg_type == "private":
            self._send_reply(qqid, "⚠️ 请在群里发送指令，私信暂不支持。", msg_type)
            return True

        for trigger in self.triggers:
            trigger_match = trigger.match(msg)
            if not trigger_match:
                continue
            args_str = msg[len(trigger_match):].strip()
            args = args_str.split() if args_str else []

            if not self._check_permissions(qqid, trigger, msg_type):
                return True
            if not self._allow_command(qqid):
                self._send_reply(qqid, "⏳ 操作太频繁，请稍后再试。", msg_type)
                return True
            if not trigger.args_validator(qqid, args):
                usage_line = f"{trigger_match} {trigger.argument_hint}".rstrip()
                lines = ["❌ 指令格式不对", f"用法：{usage_line}"]
                if trigger.usage:
                    lines.append(f"说明：{trigger.usage}")
                if trigger.example:
                    lines.append(f"示例：{trigger.example}")
                self._send_reply(qqid, "\n".join(lines), msg_type)
                return True

            try:
                result = self._call_trigger(trigger, qqid, args, msg_type)
            except Exception as e:
                self._update_stat("errors")
                fmts.print_err(f"执行指令 {trigger_match} 异常：{e}")
                self._send_reply(qqid, f"❌ 指令执行异常：{e}", msg_type)
                return True
            self._update_stat("commands_executed")
            # 外部插件回调可能返回一段要发到群里的文本
            if isinstance(result, str) and result.strip():
                self._send_reply(qqid, result.strip(), msg_type)
            return True
        return False

    def _check_permissions(self, qqid: int, trigger: QQMsgTrigger, msg_type: str) -> bool:
        if self.is_blocked(qqid):
            self._send_reply(qqid, "🚫 你已被屏蔽，无法使用群服互通。", msg_type)
            return False
        if trigger.super_op_only and not self.is_super_op(qqid):
            self._send_reply(qqid, "🔒 该指令仅超级管理员可用。", msg_type)
            return False
        if trigger.op_only and not self.has_normal_perm(qqid):
            self._send_reply(
                qqid, "🔒 你还没有使用该指令的权限，请联系超级管理员添加。", msg_type
            )
            return False
        return True

    def _allow_command(self, qqid: int) -> bool:
        """非超管的指令限频，防止群里连续刷指令。"""
        if self.is_super_op(qqid):
            return True
        now = time.monotonic()
        with self._cooldown_lock:
            if now - self._cmd_cooldowns.get(qqid, 0.0) < COMMAND_COOLDOWN:
                return False
            self._cmd_cooldowns[qqid] = now
            if len(self._cmd_cooldowns) > COOLDOWN_CACHE_SIZE:
                for old_qq in [q for q, t in self._cmd_cooldowns.items()
                               if now - t > 600]:
                    self._cmd_cooldowns.pop(old_qq, None)
        return True

    def is_super_op(self, qqid: int) -> bool:
        return qqid == self.super_op_qq or qqid in self.extra_super_op_qqs

    def has_normal_perm(self, qqid: int) -> bool:
        return self.is_super_op(qqid) or qqid in self.normal_perms

    def is_blocked(self, qqid: int) -> bool:
        return qqid in self.blocked_qqs

    def _parse_qq_arg(self, qqid: int, args: List[str], msg_type: str) -> Optional[int]:
        try:
            target_qq = int(args[0])
            if target_qq < 10000:
                raise ValueError("QQ号需大于10000")
        except (TypeError, ValueError) as e:
            self._send_reply(qqid, f"❌ 无效 QQ 号：{e}", msg_type)
            return None
        return target_qq

    def _get_online_player(
        self, qqid: int, player_name: str, msg_type="group", server_id=None
    ):
        player = self.game_ctrl.players.getPlayerByName(player_name)
        if player is None:
            if msg_type == "group":
                reply = f"❌ 玩家「{player_name}」当前不在线。"
            else:
                reply = f"❌ 服务器{server_id} 中不存在该玩家。"
            self._send_reply(qqid, reply, msg_type)
        return player

    # ---------------------------------------------------------------
    # 基础触发器注册
    # ---------------------------------------------------------------
    def init_basic_triggers(self):
        """注册所有群指令。``/查询背包`` 必须排在 ``/`` 之前。"""
        self.add_trigger(
            triggers=["/查询背包"],
            argument_hint="<玩家名>",
            usage="获取玩家背包，默认输出背包图片",
            func=self._query_inventory,
            op_only=True,
            args_validator=lambda _, args: len(args) >= 1,
            example="/查询背包 玩家名",
        )
        self.add_trigger(
            triggers=["/"],
            argument_hint="<MC指令>",
            usage="执行游戏指令",
            func=self._execute_mc_command,
            op_only=True,
            args_validator=lambda _, args: len(args) >= 1,
            example="/time set day",
        )
        self.add_trigger(
            triggers=["list", "玩家列表"],
            argument_hint="",
            usage="查看在线玩家和 TPS",
            func=self._send_player_list,
        )
        self.add_trigger(
            triggers=[".查计分板"],
            argument_hint="<玩家名> <计分板名>",
            usage="查询计分板分数",
            func=self._query_scoreboard,
            op_only=True,
            args_validator=lambda _, args: len(args) == 2,
            example=".查计分板 玩家名 金币",
        )
        self.add_trigger(
            triggers=[".查坐标"],
            argument_hint="<玩家名>",
            usage="查询玩家坐标",
            func=self._query_position,
            op_only=True,
            args_validator=lambda _, args: len(args) == 1,
            example=".查坐标 玩家名",
        )
        self.add_trigger(
            triggers=[".查物品数量"],
            argument_hint="<玩家名> <物品名/ID>",
            usage="查询物品数量（支持中文）",
            func=self._query_item_count,
            op_only=True,
            args_validator=lambda _, args: len(args) == 2,
            example=".查物品数量 玩家名 泥土",
        )
        self.add_trigger(
            triggers=[".查背包"],
            argument_hint="<玩家名> [页码]",
            usage="查询玩家背包：默认发背包图片，带页码时发文字版（每页 20 格）",
            func=self._query_inventory,
            op_only=True,
            args_validator=lambda _, args: len(args) >= 1,
            example=".查背包 玩家名 2",
        )
        # Orion 联动封禁/解封（仅超管，避免普通管理员误封）
        self.add_trigger(
            triggers=["orban", "猎户封禁"],
            argument_hint="<玩家名/XUID> <时长> [原因]",
            usage="通过 Orion 封禁玩家；时长可写 1日、2小时、-1（永久）",
            func=self._orion_ban_command,
            super_op_only=True,
            args_validator=lambda _, args: len(args) >= 2,
            example="orban 玩家名 1日 刷屏",
        )
        self.add_trigger(
            triggers=["orunban", "猎户解封"],
            argument_hint="<玩家名/XUID>",
            usage="通过 Orion 解封玩家",
            func=self._orion_unban_command,
            super_op_only=True,
            args_validator=lambda _, args: len(args) == 1,
            example="orunban 玩家名",
        )
        self.add_trigger(
            triggers=[".添加权限QQ"],
            argument_hint="<QQ号>",
            usage="给指定 QQ 添加普通指令权限",
            func=self._add_normal_permission,
            super_op_only=True,
            args_validator=lambda _, args: len(args) == 1,
            example=".添加权限QQ 123456789",
        )
        self.add_trigger(
            triggers=[".移除权限QQ"],
            argument_hint="<QQ号>",
            usage="移除指定 QQ 的普通指令权限",
            func=self._remove_normal_permission,
            super_op_only=True,
            args_validator=lambda _, args: len(args) == 1,
            example=".移除权限QQ 123456789",
        )
        self.add_trigger(
            triggers=[".屏蔽玩家"],
            argument_hint="<QQ号>",
            usage="屏蔽指定 QQ，禁止其使用群服互通",
            func=self._block_player,
            super_op_only=True,
            args_validator=lambda _, args: len(args) == 1,
            example=".屏蔽玩家 123456789",
        )
        self.add_trigger(
            triggers=[".取消屏蔽玩家"],
            argument_hint="<QQ号>",
            usage="取消对指定 QQ 的屏蔽",
            func=self._unblock_player,
            super_op_only=True,
            args_validator=lambda _, args: len(args) == 1,
            example=".取消屏蔽玩家 123456789",
        )
        self.add_trigger(
            triggers=[".查看权限列表"],
            argument_hint="",
            usage="查看权限/屏蔽列表",
            func=self._view_permission_list,
            super_op_only=True,
        )
        self.add_trigger(
            triggers=[".诊断", ".状态", ".stats"],
            argument_hint="",
            usage="诊断插件状态",
            func=self._diagnose_plugin,
            super_op_only=True,
        )
        self.add_trigger(
            triggers=["help", "帮助"],
            argument_hint="",
            usage="查看帮助",
            func=self._show_help,
        )
        self.frame.add_console_cmd_trigger(
            ["QQ", "发群"], "[消息]", "在群内发消息测试", self._send_test_message
        )

    # ---------------------------------------------------------------
    # 指令：执行 MC 指令
    # ---------------------------------------------------------------
    @utils.thread_func("执行MC指令")
    def _execute_mc_command(self, qqid, args, msg_type="group", server_id=None):
        command = " ".join(args)
        # 只拦截非超管的高危指令；超管（服主本人）不受限
        if not self.is_super_op(qqid) and self._is_blocked_mc_command(command):
            self._send_reply(
                qqid,
                "⚠️ 该指令可能会移动机器人或影响服务器管理，已被安全策略阻止。",
                msg_type,
            )
            return
        self._send_reply(qqid, self._execute_command_with_response(command), msg_type)

    @staticmethod
    def _is_blocked_mc_command(command: str) -> bool:
        """非超管禁用：移动机器人的指令 + op/deop/stop 等高危管理指令。"""
        normalized = command.strip().lstrip("/").lower()
        if BLOCKED_MC_PATTERN.match(normalized):
            return True
        return normalized.startswith("execute") and bool(
            EXECUTE_BLOCKED_PATTERN.search(normalized)
        )

    def _execute_command_with_response(self, command: str) -> str:
        try:
            result = self.game_ctrl.sendwscmd_with_resp(command, 10)
            if result is None:
                return "⚠️ 游戏控制器无响应，请稍后重试。"

            messages = getattr(result, "OutputMessages", None) or []
            first = getattr(messages[0], "Message", "") if messages else ""
            if first in ("commands.generic.syntax", "commands.generic.unknown"):
                return f'❌ 未知的 MC 指令："{command}"'

            output = self._format_command_output(messages)
            if not hasattr(result, "SuccessCount"):
                return f"✅ 指令已执行：\n{output}" if output else "✅ 指令已执行。"
            if result.SuccessCount > 0:
                return f"✅ 指令执行成功：\n{output}" if output else "✅ 指令执行成功（无返回消息）"
            return f"❌ 指令执行失败：\n{output}" if output else "❌ 指令执行失败。"
        except TimeoutError:
            return "⏱️ 指令执行超时，请稍后重试。"
        except Exception as e:
            fmts.print_err(f"执行MC指令时发生异常：{e}")
            return f"❌ 执行异常：{e}"

    @staticmethod
    def _format_command_output(messages) -> str:
        """把 OutputMessages 里的 %s/%n$s 占位符替换成实际参数。"""
        lines = []
        for message in messages:
            text = getattr(message, "Message", "")
            params = getattr(message, "Parameters", None)
            if params:
                for index, param in enumerate(params, 1):
                    placeholder = f"%{index}$s" if index > 1 else "%s"
                    if placeholder in text:
                        text = text.replace(placeholder, str(param))
                    else:
                        text += f" {param}"
            lines.append(text)
        return "\n".join(lines)

    # ---------------------------------------------------------------
    # 指令：查询类
    # ---------------------------------------------------------------
    @utils.thread_func("查看玩家列表")
    def _send_player_list(self, qqid, _args, msg_type="group", server_id=None):
        players = self.game_ctrl.players.getAllPlayers()
        if players:
            message = f"🟢 在线玩家（{len(players)} 人）\n" + "\n".join(
                f"{index + 1}. {player.name}" for index, player in enumerate(players)
            )
        else:
            message = "🟢 当前没有在线玩家。"
        if self.tps_calc:
            try:
                message += f"\nTPS：{round(self.tps_calc.get_tps(), 1)}/20"
            except Exception:
                pass
        self._send_reply(qqid, message, msg_type)

    @utils.thread_func("查询计分板")
    def _query_scoreboard(self, qqid, args, msg_type="group", server_id=None):
        player_name, scoreboard_name = args
        player = self._get_online_player(qqid, player_name, msg_type, server_id)
        if player is None:
            return
        try:
            score = player.getScore(scoreboard_name)
            self._send_reply(
                qqid, f"✅ 「{player_name}」的「{scoreboard_name}」分数：{score}", msg_type
            )
        except (TimeoutError, ValueError, AttributeError, KeyError):
            self._send_reply(
                qqid, f"❌ 查询失败：计分板「{scoreboard_name}」可能不存在。", msg_type
            )

    @utils.thread_func("查询坐标")
    def _query_position(self, qqid, args, msg_type="group", server_id=None):
        player_name = args[0]
        player = self._get_online_player(qqid, player_name, msg_type, server_id)
        if player is None:
            return
        try:
            dimension, x, y, z = player.getPos()
            self._send_reply(
                qqid,
                f"✅ 「{player_name}」坐标\n"
                f"维度：{DIMENSION_NAMES.get(dimension, f'维度{dimension}')}\n"
                f"X: {round(x, 1)}  Y: {round(y, 1)}  Z: {round(z, 1)}",
                msg_type,
            )
        except TimeoutError:
            self._send_reply(qqid, "⏱️ 查询超时，请稍后重试。", msg_type)
        except Exception as e:
            self._send_reply(qqid, f"❌ 查询坐标失败：{e}", msg_type)

    @utils.thread_func("查询物品数量")
    def _query_item_count(self, qqid, args, msg_type="group", server_id=None):
        player_name, item_input = args
        item_id = self.item_cn2en.get(item_input, item_input).lower()
        player = self._get_online_player(qqid, player_name, msg_type, server_id)
        if player is None:
            return
        try:
            count = player.getItemCount(item_id)
            item_name = self.item_en2cn.get(item_id, item_id)
            self._send_reply(
                qqid, f"✅ 「{player_name}」背包内「{item_name}」数量：{count}", msg_type
            )
        except TimeoutError:
            self._send_reply(qqid, "⏱️ 查询超时，请稍后重试。", msg_type)
        except Exception as e:
            self._send_reply(
                qqid, f"❌ 查询失败：{e}。请检查物品名，或改用英文 ID。", msg_type
            )

    # ---------------------------------------------------------------
    # 指令：背包查询 / 背包图片
    # ---------------------------------------------------------------
    @utils.thread_func("查询玩家背包")
    def _query_inventory(self, qqid, args, msg_type="group", server_id=None):
        """查询玩家背包：默认发图片；带页码参数时发文字分页。"""
        player_name, page = self._parse_inventory_args(qqid, args, msg_type)
        if player_name is None:
            return

        player = self._get_online_player(qqid, player_name, msg_type, server_id)
        if player is None:
            return

        try:
            slots, total_slots = self._fetch_inventory_slots(player)
        except TimeoutError:
            self._send_reply(qqid, "⏱️ 背包查询超时，请稍后重试。", msg_type)
            return
        except Exception as e:
            self._send_reply(qqid, f"❌ 背包查询异常：{e}", msg_type)
            return

        filled_items = [
            (index, slot) for index, slot in enumerate(slots) if slot is not None
        ]
        if page is None and self.inventory_assets_ready:
            try:
                image_bytes = self._render_inventory_image_bytes(slots)
            except Exception as e:
                fmts.print_err(f"渲染背包图片失败：{e}")
                image_bytes = None
            if image_bytes:
                self._send_inventory_image(
                    qqid, player_name, image_bytes, slots,
                    len(filled_items), total_slots, msg_type,
                )
                return
        self._send_reply(
            qqid,
            self._build_inventory_text_page(player_name, filled_items, total_slots, page or 1),
            msg_type,
        )

    def _parse_inventory_args(self, qqid, args, msg_type) -> Tuple[Optional[str], Optional[int]]:
        """解析 ``<玩家名> [页码]``，支持带空格玩家名；错误时已回复。"""
        if len(args) == 1:
            return args[0], None
        last = args[-1]
        if last.isdigit():
            page = int(last)
            if page < 1:
                self._send_reply(qqid, "❌ 页码必须大于 0。", msg_type)
                return None, None
            return " ".join(args[:-1]), page
        if len(args) == 2:
            self._send_reply(
                qqid,
                "❌ 页码必须是正整数。\n用法：.查背包 玩家名 [页码]\n示例：.查背包 玩家名 2",
                msg_type,
            )
            return None, None
        return " ".join(args), None

    def _fetch_inventory_slots(self, player) -> Tuple[List, int]:
        """读取玩家背包槽位（兼容 FateArk 的 DataSet 字典返回）。"""
        response = self.game_ctrl.sendwscmd_with_resp(
            f"codebuilder_actorinfo inventory {player.safe_name}", 30
        )
        if int(getattr(response, "SuccessCount", 0) or 0) < 1:
            raise ValueError("背包查询命令未成功")
        inventory = normalize_inventory_dataset(getattr(response, "DataSet", None))
        slots = inventory["slots"]
        total_slots = int(inventory.get("slotCount", len(slots)) or len(slots))
        return slots, total_slots

    def _send_inventory_image(
        self, qqid, player_name, image_bytes, slots,
        filled_slots, total_slots, msg_type,
    ):
        """先发背包图片（单独一条，不按长度拆分），再发文字说明。"""
        image_cq = (
            "[CQ:image,file=base64://"
            + base64.b64encode(image_bytes).decode("ascii")
            + "]"
        )
        if msg_type == "group":
            self.sendmsg(self.linked_group, image_cq, split=False)
        self._send_reply(
            qqid,
            f"【背包 · {player_name}】\n"
            f"总槽位：{total_slots}    已占用：{filled_slots}\n"
            + self._generate_text_inventory(slots),
            msg_type,
        )

    def _build_inventory_text_page(
        self, player_name: str, filled_items: List[Tuple[int, Any]],
        total_slots: int, page: int,
    ) -> str:
        """生成背包文字版（每页 20 格）。"""
        total_pages = max(1, (len(filled_items) + INVENTORY_PAGE_SIZE - 1) // INVENTORY_PAGE_SIZE)
        page = max(1, min(int(page or 1), total_pages))
        start = (page - 1) * INVENTORY_PAGE_SIZE
        page_items = filled_items[start:start + INVENTORY_PAGE_SIZE]

        lines = [
            f"【背包 · {player_name}】",
            f"总槽位：{total_slots}    已占用：{len(filled_items)}",
            f"第 {page}/{total_pages} 页",
            "",
        ]
        if not filled_items:
            lines.append("该玩家背包是空的。")
            return "\n".join(lines)

        for slot_index, slot in page_items:
            lines.append(self._format_inventory_slot_line(slot_index, slot))
        if total_pages > 1:
            next_page = page + 1 if page < total_pages else 1
            lines.append(f"➡️ 下一页：.查背包 {player_name} {next_page}")
        return "\n".join(lines)

    def _format_inventory_slot_line(self, slot_index: int, slot) -> str:
        stack_size = _inventory_value(slot, "stackSize", default=0)
        max_stack = _inventory_value(slot, "maxStackSize", default=0)
        aux_data = _inventory_value(slot, "aux", default=0)
        line = (
            f"槽位{slot_index}：{self._localize_item(slot)}"
            f" 数量：{stack_size}/{max_stack} 特殊值：{aux_data}"
        )
        enchant_names = self._enchant_names(
            _inventory_value(slot, "enchantments", default=[]) or []
        )
        if enchant_names:
            line += " | 附魔：" + "+".join(enchant_names)
        return line

    def _generate_text_inventory(self, slots: List) -> str:
        """按「快捷栏 / 主背包」排版背包文字版，用于图片下方的说明。"""
        def format_slot(index: int, slot) -> str:
            name = self._localize_item(slot)
            count = int(_inventory_value(slot, "stackSize", default=0) or 0)
            aux = _inventory_value(slot, "aux", default=0)
            text = f"[{index}] {name} x{count}"
            enchant_names = self._enchant_names(
                _inventory_value(slot, "enchantments", default=[]) or []
            )
            if enchant_names:
                text += " " + " ".join(enchant_names)
            elif aux not in (0, None, ""):
                text += f" (数据:{aux})"
            return text

        hotbar = [
            format_slot(index, slots[index])
            for index in range(min(9, len(slots))) if slots[index] is not None
        ]
        main = [
            format_slot(index, slots[index])
            for index in range(9, min(36, len(slots))) if slots[index] is not None
        ]
        lines: List[str] = []
        if hotbar:
            lines.append("▶ 快捷栏")
            lines.extend("  " + item for item in hotbar)
        if main:
            if hotbar:
                lines.append("")
            lines.append("▶ 主背包")
            lines.extend("  " + item for item in main)
        return "\n".join(lines) if lines else "背包是空的"

    @staticmethod
    def _get_full_item_id(slot) -> str:
        """拼接物品完整 id（命名空间:id）。"""
        item_id = str(_inventory_value(slot, "id", default="") or "").strip()
        namespace = str(_inventory_value(slot, "namespace", default="") or "").strip()
        if ":" in item_id:
            return item_id
        if namespace and not namespace.endswith(":"):
            namespace += ":"
        return f"{namespace}{item_id}" if (namespace or item_id) else ""

    def _localize_item(self, slot) -> str:
        """把背包槽位翻译成中文物品名；查不到就保留原 id。"""
        full_id = self._get_full_item_id(slot)
        if not full_id:
            return ""
        item_id = full_id.split(":", 1)[1] if ":" in full_id else full_id
        return self.item_en2cn.get(item_id.lower(), full_id)

    def _enchant_names(self, enchantments) -> List[str]:
        """把附魔列表转成 [中文名]，优先用服务端给出的名称。"""
        names: List[str] = []
        for ench in enchantments or []:
            name = _inventory_value(ench, "name", default="")
            if name:
                names.append(f"[{name}]")
                continue
            try:
                ench_type = int(_inventory_value(ench, "type", default=None))
            except (TypeError, ValueError):
                continue
            cn_name = self.enchantment_name_map.get(ench_type)
            if cn_name:
                names.append(f"[{cn_name}]")
        return names

    @staticmethod
    def _get_slot_position(slot_index: int) -> Optional[Tuple[int, int]]:
        """背包槽位在 176x166 UI 图片上的左上角像素坐标。"""
        grid_x, grid_y, hotbar_y, step = 8, 84, 142, 18
        if 0 <= slot_index <= 8:
            return (grid_x + slot_index * step, hotbar_y)
        if 9 <= slot_index <= 35:
            slot_in_main = slot_index - 9
            return (grid_x + (slot_in_main % 9) * step, grid_y + (slot_in_main // 9) * step)
        return None

    @staticmethod
    def _fill_box(canvas, canvas_size, position, box_size, color: bytes):
        """在没有贴图的槽位上画一个纯色方块。"""
        canvas_w, canvas_h = canvas_size
        box_w, box_h = box_size
        x0, y0 = position
        for y in range(box_h):
            cy = y0 + y
            if cy < 0 or cy >= canvas_h:
                continue
            row_offset = cy * canvas_w * 4
            for x in range(box_w):
                cx = x0 + x
                if 0 <= cx < canvas_w:
                    offset = row_offset + cx * 4
                    canvas[offset:offset + 4] = color

    @staticmethod
    def _blit_icon(canvas, canvas_size, position, icon_size, icon: bytes):
        """把 RGBA 图标按 alpha 合成进画布。"""
        canvas_w, canvas_h = canvas_size
        icon_w, icon_h = icon_size
        x0, y0 = position
        for y in range(icon_h):
            cy = y0 + y
            if cy < 0 or cy >= canvas_h:
                continue
            row_offset = cy * canvas_w * 4
            for x in range(icon_w):
                cx = x0 + x
                if cx < 0 or cx >= canvas_w:
                    continue
                source = (y * icon_w + x) * 4
                alpha = icon[source + 3]
                if alpha == 0:
                    continue
                offset = row_offset + cx * 4
                if alpha == 255:
                    canvas[offset:offset + 4] = icon[source:source + 4]
                    continue
                inv = 255 - alpha
                canvas[offset] = (icon[source] * alpha + canvas[offset] * inv) // 255
                canvas[offset + 1] = (icon[source + 1] * alpha + canvas[offset + 1] * inv) // 255
                canvas[offset + 2] = (icon[source + 2] * alpha + canvas[offset + 2] * inv) // 255
                canvas[offset + 3] = max(canvas[offset + 3], alpha)

    @staticmethod
    def _draw_number(canvas, canvas_size, position, text: str):
        """在槽位右下角画白色堆叠数量（带黑色描边）。"""
        canvas_w, canvas_h = canvas_size
        glyph_w, glyph_h = 3, 5
        start_x = position[0] + 15 - (len(text) * (glyph_w + 1) - 1)
        start_y = position[1] + 15 - glyph_h
        for shadow, color in ((1, b"\x00\x00\x00\xff"), (0, b"\xff\xff\xff\xff")):
            for index, char in enumerate(text):
                glyph = DIGIT_GLYPHS.get(char)
                if glyph is None:
                    continue
                base_x = start_x + index * (glyph_w + 1) + shadow
                base_y = start_y + shadow
                for gy, glyph_row in enumerate(glyph):
                    for gx, bit in enumerate(glyph_row):
                        if bit != "1":
                            continue
                        px, py = base_x + gx, base_y + gy
                        if 0 <= px < canvas_w and 0 <= py < canvas_h:
                            offset = (py * canvas_w + px) * 4
                            canvas[offset:offset + 4] = color

    @staticmethod
    def _encode_png(width: int, height: int, rgba: bytes) -> bytes:
        """把 RGBA 像素编码成 PNG（纯标准库实现，不依赖 Pillow）。"""
        stride = width * 4
        if len(rgba) != stride * height:
            raise ValueError("像素数据长度与图片尺寸不匹配")

        filtered = bytearray()
        for y in range(height):
            filtered.append(0)  # filter type: none
            filtered += rgba[y * stride:(y + 1) * stride]

        def make_chunk(tag: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + tag
                + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
            )

        ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
        return (
            b"\x89PNG\r\n\x1a\n"
            + make_chunk(b"IHDR", ihdr)
            + make_chunk(b"IDAT", zlib.compress(bytes(filtered), 6))
            + make_chunk(b"IEND", b"")
        )

    @staticmethod
    def _missing_icon_color(item_id: str) -> bytes:
        """没有贴图的物品用由 id 派生的颜色画块，方便一眼区分。"""
        digest = zlib.crc32(item_id.encode("utf-8")) & 0xFFFFFF
        return bytes((
            60 + (digest >> 16) % 140,
            60 + (digest >> 8) % 140,
            60 + digest % 140,
            180,
        ))

    def _render_inventory_image_bytes(self, slots: List) -> bytes:
        """把背包槽位画到背包 UI 底图上，返回 PNG 字节。"""
        if not self.inventory_assets_ready:
            raise RuntimeError("背包素材未加载")

        canvas_w, canvas_h = self._asset_ui_size
        canvas = bytearray(self._asset_ui_rgba)
        icon_size = self._asset_icon_size

        for index, slot in enumerate(slots):
            if slot is None:
                continue
            position = self._get_slot_position(index)
            if position is None:
                continue
            full_id = self._get_full_item_id(slot)
            item_id = full_id.split(":", 1)[1].lower() if ":" in full_id else full_id.lower()
            icon = self._asset_icons.get(item_id)
            if icon is None:
                self._fill_box(
                    canvas, self._asset_ui_size, position, icon_size,
                    self._missing_icon_color(item_id),
                )
            else:
                self._blit_icon(canvas, self._asset_ui_size, position, icon_size, icon)
            count = int(_inventory_value(slot, "stackSize", default=0) or 0)
            if count > 1:
                self._draw_number(canvas, self._asset_ui_size, position, str(count))
        return self._encode_png(canvas_w, canvas_h, bytes(canvas))

    # ---------------------------------------------------------------
    # 指令：Orion 封禁联动
    # ---------------------------------------------------------------
    def _get_orion(self):
        if self.orion is None:
            self.orion = self.GetPluginAPI("Orion_System", (0, 4, 0), False)
        return self.orion

    def _resolve_orion_target(self, target: str):
        """把玩家名或 XUID 解析成 (xuid, 玩家名, 错误信息)。"""
        orion = self._get_orion()
        if orion is None:
            return None, None, "Orion 未安装或未启用"
        getter = getattr(orion, "xuid_getter", None)
        if getter is None:
            return None, None, "Orion 的 XUID 获取器尚未初始化"

        try:
            xuid = getter.get_xuid_by_name(target, True)
        except Exception:
            xuid = None
        if xuid:
            try:
                return xuid, getter.get_name_by_xuid(xuid, True), None
            except Exception:
                return xuid, target, None
        if re.fullmatch(r"[0-9a-fA-F]{8,32}", target):
            try:
                return target, getter.get_name_by_xuid(target, True), None
            except Exception:
                return target, target, None
        return None, None, f"找不到玩家或 XUID：{target}"

    def _orion_ban_player(self, target: str, ban_time_raw: str, reason: str):
        """按 XUID 写入 Orion 封禁记录，并在玩家在线时踢出。"""
        orion = self._get_orion()
        if orion is None:
            return False, "Orion 未安装或未启用"
        xuid, player_name, error = self._resolve_orion_target(target)
        if error:
            return False, error

        try:
            # wait_for_op=False：不要在 QQ 指令线程里等能力包，避免卡 20 秒
            if orion.utils.in_whitelist(player_name, False):
                return False, f"玩家 {player_name} 在 Orion 反制白名单内，已拒绝封禁"
        except Exception as e:
            return False, f"检查 Orion 白名单失败：{e}"

        try:
            ban_time = orion.utils.ban_time_format(ban_time_raw)
        except Exception as e:
            return False, f"解析封禁时长失败：{e}"
        if ban_time == 0:
            return False, "封禁时长无效；永久封禁请输入 -1"

        try:
            timestamp_now, date_now = orion.utils.now()
            path = os.path.join(
                str(orion.data_path), str(orion.config_mgr.xuid_dir), f"{xuid}.json"
            )
            with orion.lock_ban_xuid:
                ban_data = orion.utils.disk_read(path)
                timestamp_end, date_end = orion.utils.calculate_ban_end_time(
                    ban_data, ban_time, timestamp_now
                )
                if timestamp_end is False:
                    return False, f"玩家 {player_name} 已经是永久封禁"
                orion.utils.disk_write(path, {
                    "xuid": xuid,
                    "name": player_name,
                    "ban_start_real_time": date_now,
                    "ban_start_timestamp": timestamp_now,
                    "ban_end_real_time": date_end,
                    "ban_end_timestamp": timestamp_end,
                    "ban_reason": reason,
                })
        except Exception as e:
            fmts.print_err(f"Orion 封禁失败：{e}")
            return False, f"封禁失败：{e}"

        try:
            if player_name in self.game_ctrl.allplayers:
                orion.utils.kick(
                    player_name, f"由于{reason}，您被系统封禁至：{date_end}"
                )
        except Exception as e:
            fmts.print_err(f"Orion 封禁后踢出玩家失败：{e}")
        return True, f"已封禁 {player_name}（XUID: {xuid}）至 {date_end}"

    def _orion_unban_player(self, target: str):
        orion = self._get_orion()
        if orion is None:
            return False, "Orion 未安装或未启用"
        xuid, player_name, error = self._resolve_orion_target(target)
        if error:
            return False, error
        path = os.path.join(
            str(orion.data_path), str(orion.config_mgr.xuid_dir), f"{xuid}.json"
        )
        try:
            with orion.lock_ban_xuid:
                if not os.path.exists(path):
                    return False, f"玩家 {player_name} 当前不在 Orion 的 XUID 封禁列表中"
                os.remove(path)
        except Exception as e:
            fmts.print_err(f"Orion 解封失败：{e}")
            return False, f"解封失败：{e}"
        return True, f"已解封 {player_name}（XUID: {xuid}）"

    @utils.thread_func("Orion封禁")
    def _orion_ban_command(self, qqid, args, msg_type="group", server_id=None):
        reason = " ".join(args[2:]).strip() or "群聊管理员封禁"
        ok, message = self._orion_ban_player(args[0], args[1], reason)
        self._send_reply(qqid, ("✅ " if ok else "❌ ") + message, msg_type)

    @utils.thread_func("Orion解封")
    def _orion_unban_command(self, qqid, args, msg_type="group", server_id=None):
        ok, message = self._orion_unban_player(args[0])
        self._send_reply(qqid, ("✅ " if ok else "❌ ") + message, msg_type)

    # ---------------------------------------------------------------
    # 指令：权限 / 屏蔽管理
    # ---------------------------------------------------------------
    @utils.thread_func("添加普通权限")
    def _add_normal_permission(self, qqid, args, msg_type="group", server_id=None):
        target = self._parse_qq_arg(qqid, args, msg_type)
        if target is None:
            return
        if target in self.normal_perms or self.is_super_op(target):
            self._send_reply(qqid, f"❌ QQ {target} 已经有权限了。", msg_type)
            return
        with self._perm_lock:
            self.normal_perms.append(target)
            self._save_permissions()
        self._send_reply(qqid, f"✅ 已为 QQ {target} 添加普通权限。", msg_type)

    @utils.thread_func("移除普通权限")
    def _remove_normal_permission(self, qqid, args, msg_type="group", server_id=None):
        target = self._parse_qq_arg(qqid, args, msg_type)
        if target is None:
            return
        if self.is_super_op(target):
            self._send_reply(qqid, "❌ 不能移除超级管理员的权限。", msg_type)
            return
        if target not in self.normal_perms:
            self._send_reply(qqid, f"❌ QQ {target} 没有普通权限。", msg_type)
            return
        with self._perm_lock:
            self.normal_perms.remove(target)
            self._save_permissions()
        self._send_reply(qqid, f"✅ 已移除 QQ {target} 的普通权限。", msg_type)

    @utils.thread_func("屏蔽玩家")
    def _block_player(self, qqid, args, msg_type="group", server_id=None):
        target = self._parse_qq_arg(qqid, args, msg_type)
        if target is None:
            return
        if target in self.blocked_qqs or self.is_super_op(target):
            self._send_reply(qqid, f"❌ QQ {target} 已被屏蔽，或它是超级管理员。", msg_type)
            return
        with self._perm_lock:
            self.blocked_qqs.append(target)
            self._save_blocked_qqs()
        self._send_reply(qqid, f"✅ 已屏蔽 QQ {target}。", msg_type)

    @utils.thread_func("取消屏蔽")
    def _unblock_player(self, qqid, args, msg_type="group", server_id=None):
        target = self._parse_qq_arg(qqid, args, msg_type)
        if target is None:
            return
        if target not in self.blocked_qqs:
            self._send_reply(qqid, f"❌ QQ {target} 没有被屏蔽。", msg_type)
            return
        with self._perm_lock:
            self.blocked_qqs.remove(target)
            self._save_blocked_qqs()
        self._send_reply(qqid, f"✅ 已取消屏蔽 QQ {target}。", msg_type)

    def _view_permission_list(self, qqid, _args, msg_type="group", server_id=None):
        super_list = [self.super_op_qq] + list(self.extra_super_op_qqs)
        self._send_reply(
            qqid,
            "\n".join([
                "【权限与屏蔽】",
                f"超级管理员（{len(super_list)}）：" + "、".join(map(str, super_list)),
                f"普通管理员（{len(self.normal_perms)}）："
                + ("、".join(map(str, self.normal_perms)) or "（无）"),
                f"已屏蔽（{len(self.blocked_qqs)}）："
                + ("、".join(map(str, self.blocked_qqs)) or "（无）"),
            ]),
            msg_type,
        )

    # ---------------------------------------------------------------
    # 指令：诊断 / 帮助 / 控制台测试
    # ---------------------------------------------------------------
    def _diagnose_plugin(self, qqid, _args, msg_type="group", server_id=None):
        try:
            stats = self.get_stats()
            alive_workers = sum(1 for w in self._message_workers if w.is_alive())
            sender_alive = self._sender_thread is not None and self._sender_thread.is_alive()
            lines = [
                "【群服互通 · 诊断】",
                f"版本：{'.'.join(map(str, self.version))}"
                f"    云链：{'✅ 已连接' if self.ws_connected else '❌ 未连接'}",
                f"连接循环：{'运行中' if self._is_connecting else '已停止'}"
                f"    重连尝试：{self._reconnect_attempts} 次",
                f"消息队列：{self._message_queue.qsize()}"
                f"    发送队列：{self._send_queue.qsize()}",
                f"工作线程：消息 {alive_workers}  发送 {'✅' if sender_alive else '❌'}",
                "背包图片："
                + (
                    f"可用（{len(self._asset_icons)} 图标 / "
                    f"{len(self._asset_item_names)} 物品名）"
                    if self.inventory_assets_ready else "❌ 素材未加载，仅文字版"
                ),
                f"运行时间：{stats['运行时间']}",
                f"接收 / 发送 / 指令 / 错误："
                f"{stats['接收消息']} / {stats['发送消息']} / "
                f"{stats['执行指令']} / {stats['错误次数']}",
            ]
            if not self.ws_connected and self._is_connecting:
                lines.append("⚠️ 正在尝试连接云链，请稍候。")
            self._send_reply(qqid, "\n".join(lines), msg_type)
        except Exception as e:
            self._send_reply(qqid, f"❌ 诊断失败：{e}", msg_type)

    def _show_help(self, sender, _args, msg_type="group", server_id=None):
        version = ".".join(map(str, self.version))
        status_parts = [f"版本 {version}", f"云链：{'已连接' if self.ws_connected else '未连接'}"]
        try:
            status_parts.append(f"在线：{len(self.game_ctrl.players.getAllPlayers())} 人")
        except Exception:
            pass
        if self.tps_calc:
            try:
                status_parts.append(f"TPS：{round(self.tps_calc.get_tps(), 1)}")
            except Exception:
                pass
        lines = [
            "【群服互通 · 帮助】",
            " | ".join(status_parts),
            "",
            "■ 常用",
            "  list / 玩家列表        在线玩家和 TPS",
            "  help / 帮助            显示本菜单",
            "  /<MC指令>              例：/time set day",
            "",
            "■ 查询（需权限）",
            "  .查坐标 <玩家>",
            "  .查计分板 <玩家> <计分板>",
            "  .查物品数量 <玩家> <物品>",
            "  .查背包 <玩家>         发背包图片",
            "  .查背包 <玩家> [页码]  发文字版，每页 20 格",
            "  /查询背包 <玩家>       同 .查背包",
            "",
            "■ 超管",
            "  .添加权限QQ <QQ>",
            "  .移除权限QQ <QQ>",
            "  .屏蔽玩家 <QQ>",
            "  .取消屏蔽玩家 <QQ>",
            "  .查看权限列表",
            "  orban <玩家/XUID> <时长> [原因]",
            "  orunban <玩家/XUID>",
            "  .诊断",
            "",
            "提示：非超管不能用 /tp、/teleport、/ride、/spreadplayers、/op、/deop、/stop；"
            "指令有 1 秒限频。",
        ]
        self._send_reply(sender, "\n".join(lines), msg_type)

    def _send_test_message(self, args):
        if self.ws_connected:
            self.sendmsg(self.linked_group, " ".join(args) if args else "测试消息")
            fmts.print_suc(f"✅ 测试消息已发送到群 {self.linked_group}")
        else:
            fmts.print_err("❌ 云链未连接，测试消息未发送")

    # ---------------------------------------------------------------
    # 游戏事件
    # ---------------------------------------------------------------
    def on_player_join(self, player):
        if self.ws_connected and self.enable_game_2_group:
            self.sendmsg(self.linked_group, f"🟢 {player.name} 加入了游戏")

    def on_player_leave(self, player):
        if self.ws_connected and self.enable_game_2_group:
            self.sendmsg(self.linked_group, f"🔴 {player.name} 退出了游戏")

    def on_player_message(self, chat):
        if not self.ws_connected or not self.enable_game_2_group:
            return
        message = chat.msg
        if not self._check_message_forwarding(message):
            return
        formatted = utils.simple_fmt(
            {
                "[玩家名]": remove_color(chat.player.name),
                "[消息]": remove_color(clean_cq_code(message)),
            },
            self.cfg["消息转发设置"]["游戏到群"]["转发格式"],
        )
        self.sendmsg(self.linked_group, formatted)

    def _check_message_forwarding(self, message: str) -> bool:
        """游戏到群：屏蔽前缀优先，其次只转发指定前缀（列表为空则全部转发）。"""
        if any(message.startswith(prefix) for prefix in self.game2qq_block_prefixs):
            return False
        if self.game2qq_trans_chars:
            return any(message.startswith(prefix) for prefix in self.game2qq_trans_chars)
        return True

    # ---------------------------------------------------------------
    # 心跳 / 统计 / 收尾
    # ---------------------------------------------------------------
    def _start_heartbeat(self):
        """单个守护线程做心跳，避免 Timer 重激活时出现两个定时器。"""
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            return

        def heartbeat_loop():
            while not self._stop_event.is_set():
                try:
                    if self.ws_connected:
                        # 不要用“群内 90 秒没消息”判断断线（安静时段会误判）；
                        # 只看底层 socket，半开连接交给 run_forever 的 ping/pong。
                        sock = getattr(self.ws, "sock", None)
                        if sock is None or not getattr(sock, "connected", True):
                            self.ws_connected = False
                            with self._send_lock:
                                if self.ws:
                                    try:
                                        self.ws.close()
                                    except BaseException:
                                        pass
                except Exception:
                    pass
                if self._stop_event.wait(self.heartbeat_interval):
                    break

        self._heartbeat_thread = threading.Thread(
            target=heartbeat_loop, name="群服互通心跳", daemon=True
        )
        self._heartbeat_thread.start()

    def get_stats(self) -> Dict[str, Any]:
        with self._stats_lock:
            uptime = time.time() - self._stats["start_time"]
        return {
            "运行时间": f"{int(uptime // 3600)}小时{int(uptime % 3600 // 60)}分钟",
            "接收消息": self._stats["messages_received"],
            "发送消息": self._stats["messages_sent"],
            "执行指令": self._stats["commands_executed"],
            "错误次数": self._stats["errors"],
        }

    def _update_stat(self, key: str, value: int = 1):
        with self._stats_lock:
            if key in self._stats:
                self._stats[key] += value

    def _cleanup_all_resources(self):
        """清理消息/发送队列，并尽量等工作线程结束（最多约 3 秒）。"""
        for work_queue in (self._message_queue, self._send_queue):
            while not work_queue.empty():
                try:
                    work_queue.get_nowait()
                    work_queue.task_done()
                except queue.Empty:
                    break
        for worker in self._message_workers:
            try:
                if worker.is_alive():
                    worker.join(timeout=1.5)
            except Exception:
                pass
        try:
            if self._sender_thread is not None and self._sender_thread.is_alive():
                self._sender_thread.join(timeout=1.5)
        except Exception:
            pass

    def _graceful_shutdown(self):
        self._stop_event.set()
        with self._send_lock:
            if self.ws:
                try:
                    self.ws.close()
                except BaseException:
                    pass
        try:
            self._send_queue.put_nowait(None)
        except queue.Full:
            pass
        self._cleanup_all_resources()


# ================ 插件入口 ================
entry = plugin_entry(QQLinker, "群服互通")
