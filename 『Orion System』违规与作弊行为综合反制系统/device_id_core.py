"""设备号(DeviceID)解析与刷新工具。

本模块只包含纯函数，不依赖 ToolDelta，便于单元测试。
"""

from __future__ import annotations

import re

# PlayerList 的 SkinID 只有自定义皮肤(Custom/CustomSlim)才内嵌 32 位设备号
_SKIN_ID_DEVICE_RE = re.compile(r"(?:CustomSlim|Custom)([a-fA-F0-9]{32})")
_DEVICE_ID_RE = re.compile(r"^[A-F0-9]{32}$")


def parse_device_id_from_skin_id(skin_id: str | None) -> str | None:
    """从 PlayerList 数据包的 SkinID 中解析设备号。

    只有自定义皮肤会内嵌设备号；Steve/Alex、4D 皮肤以及普通皮肤都解析不到，
    返回 None。设备号统一转成大写，避免与 AddPlayer 来源的大小写不一致。
    """
    if not skin_id or not isinstance(skin_id, str):
        return None
    match = _SKIN_ID_DEVICE_RE.search(skin_id)
    if match is None:
        return None
    return match.group(1).upper()


def normalize_device_id(device_id: object) -> str | None:
    """规范化 ToolDelta 已解析出的 device_id；非法或空值返回 None。"""
    if not isinstance(device_id, str):
        return None
    normalized = device_id.strip().upper()
    if not _DEVICE_ID_RE.match(normalized):
        return None
    return normalized


def build_bot_refresh_command(player: str, bot_name: str) -> str | None:
    """构造用于刷新 AddPlayer 数据包的机器人传送指令。

    服务端只会把机器人附近的实体通过 AddPlayer 发给机器人；机器人离玩家很远时
    永远拿不到该玩家的 DeviceID。把机器人短时传送到目标玩家正上方 ~500 格，
    即可让服务端补发 AddPlayer，从而解析出设备号。
    """
    if not player or not bot_name:
        return None
    safe_player = str(player).replace('"', "")
    safe_bot = str(bot_name).replace('"', "")
    if not safe_player or not safe_bot:
        return None
    return f'/execute at @a[name="{safe_player}"] run tp @a[name="{safe_bot}"] ~ 500 ~'
