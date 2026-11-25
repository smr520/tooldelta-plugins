import json
import logging
import re
import threading
import time

from tooldelta import Plugin, plugin_entry


CRASH_MESSAGE = "⚠️ 机器人进程崩溃，游戏服务器不受影响。"

# 只在明确的崩溃/掉线日志上触发，避免把普通插件报错当成崩溃
CRASH_KEYWORDS = (
    "conn dead",
    "fateark 已崩溃",
    "启动器框架崩溃",
    "接入点进程已崩溃",
    "memoryerror",
    "fateark掉线",
)

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class CrashLogHandler(logging.Handler):
    """监听框架日志，出现崩溃关键词时通知插件。"""

    def __init__(self, plugin):
        super().__init__(level=logging.WARNING)
        self.plugin = plugin

    def emit(self, record):
        try:
            self.plugin.on_log(record)
        except Exception:
            # 崩溃路径上绝不能再抛异常
            pass


class CrashNotifier(Plugin):
    name = "崩溃提醒"
    author = "一个高质量的神秘人"
    version = (0, 0, 1)

    def __init__(self, frame):
        super().__init__(frame)
        self._lock = threading.Lock()
        self._last_notify = 0.0
        self._qql = None
        self._handler = CrashLogHandler(self)
        logging.getLogger().addHandler(self._handler)
        self.ListenActive(self.on_active)
        self.ListenFrameExit(self.on_frame_exit)

    def on_active(self):
        self._qql = self.GetPluginAPI("群服互通", force=False)
        if self._qql is None:
            self.print("崩溃提醒已启用：暂未找到 群服互通")
        else:
            self.print("崩溃提醒已启用：监听机器人进程崩溃日志")

    def on_log(self, record):
        text = ANSI_RE.sub("", record.getMessage()).lower()
        if not any(keyword in text for keyword in CRASH_KEYWORDS):
            return

        now = time.monotonic()
        with self._lock:
            if now - self._last_notify < 30:
                return
            self._last_notify = now

        # 崩溃时日志线程会被框架直接带走。这里用守护线程抢在退出前
        # 把消息直接写进现有 WS，最多等 1.5 秒，不走发送队列。
        sender = threading.Thread(
            target=self._send_now,
            name="崩溃提醒发送",
            daemon=True,
        )
        sender.start()
        sender.join(1.5)

    def _send_now(self):
        qql = self._qql
        if qql is None:
            try:
                qql = self.GetPluginAPI("群服互通", force=False)
            except Exception:
                qql = None

        if qql is None:
            self.print("崩溃提醒：未找到 群服互通，无法发送")
            return

        ws = getattr(qql, "ws", None)
        if not getattr(qql, "ws_connected", False) or ws is None:
            self.print("崩溃提醒：云链未连接，无法发送")
            return

        payload = {
            "action": "send_group_msg",
            "params": {
                "group_id": qql.linked_group,
                "message": CRASH_MESSAGE,
            },
        }

        try:
            with qql._send_lock:
                ws.send(json.dumps(payload, ensure_ascii=False))
            self.print("崩溃提醒：已发送到群")
        except Exception as exc:
            self.print(f"崩溃提醒：发送失败: {exc}")

    def on_frame_exit(self, _evt):
        try:
            logging.getLogger().removeHandler(self._handler)
        except Exception:
            pass


entry = plugin_entry(CrashNotifier, "崩溃提醒")
