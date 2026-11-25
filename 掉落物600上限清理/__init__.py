"""掉落物清理插件。

只统计 Minecraft 的 item 实体。三个维度合计严格超过阈值时，清理全部维度
已加载的掉落物，不处理玩家、生物、经验球或其他实体。
"""

from __future__ import annotations

import threading
from typing import Any

from tooldelta import Plugin, cfg, fmts, plugin_entry

from .drop_cleanup_core import (
    DIMENSIONS,
    build_cleanup_command,
    build_count_command,
    extract_success_count,
    should_cleanup,
    total_dropped_items,
    validate_threshold,
)


class DroppedItemCleanup(Plugin):
    name = "掉落物600上限清理"
    author = "一个高质量的神秘人"
    version = (1, 0, 1)
    description = "仅统计掉落物实体，三世界合计超过600时自动全部清理"

    CFG_DEFAULT = {
        "启用": True,
        "数量阈值": 600,
        "检查间隔秒": 5,
        "清理所有维度": True,
        "输出统计日志": False,
        "控制台指令": ["drop_cleanup", "掉落物清理"],
    }

    def __init__(self, frame):
        super().__init__(frame)
        self.config: dict[str, Any] = {}
        self._enabled = False
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._scan_lock = threading.Lock()
        self._error_printed = False
        self.ListenPreload(self.on_def)
        self.ListenActive(self.on_active)
        self.ListenFrameExit(self._on_frame_exit)

    def on_def(self):
        self.config, _version = cfg.get_plugin_config_and_version(
            self.name,
            cfg.auto_to_std(self.CFG_DEFAULT),
            self.CFG_DEFAULT,
            self.version,
        )
        self.frame.add_console_cmd_trigger(
            list(self.config.get("控制台指令", self.CFG_DEFAULT["控制台指令"])),
            None,
            "掉落物清理 | drop_cleanup status",
            self._on_console_command,
        )
        self._enabled = bool(self.config.get("启用", True))

    def on_active(self):
        if not self._enabled:
            self.print("§e掉落物600上限清理未启用")
            return
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._scan_loop,
            name="DroppedItemCleanup",
            daemon=True,
        )
        self._worker.start()
        self.print(
            "§a掉落物600上限清理已启用 | "
            f"阈值={self._threshold()} | 仅清理 item 实体"
        )

    def on_plugin_unload(self):
        self._shutdown()

    def _on_frame_exit(self, _event):
        self._shutdown()

    def _shutdown(self):
        self._enabled = False
        self._stop_event.set()
        worker = self._worker
        self._worker = None
        if (
            worker is not None
            and worker.is_alive()
            and worker is not threading.current_thread()
        ):
            worker.join(timeout=2.0)

    _COUNT_TIMEOUT_SECONDS = 4
    _CLEANUP_TIMEOUT_SECONDS = 5

    def _threshold(self) -> int:
        return validate_threshold(self.config.get("数量阈值", 600))

    def _interval(self) -> float:
        try:
            return max(1.0, float(self.config.get("检查间隔秒", 5)))
        except (TypeError, ValueError):
            return 5.0

    def _scan_loop(self):
        while not self._stop_event.is_set():
            if self._stop_event.wait(self._interval()):
                return
            try:
                self._scan_once()
            except Exception as error:
                fmts.print_err(f"掉落物清理扫描异常: {error}")

    def _count_dimension(self, dimension: str) -> int | None:
        try:
            response = self.game_ctrl.sendwscmd_with_resp(
                build_count_command(dimension, self._threshold()),
                self._COUNT_TIMEOUT_SECONDS,
            )
        except Exception:
            # 服务器卡顿时 testfor 可能超时。单个维度超时按“未知”处理，
            # 本轮不清理，下一轮重试，不再每 5 秒刷一条报错日志。
            return None
        return extract_success_count(response)

    def _count_all_dimensions(self) -> tuple[list[int], bool]:
        counts: list[int] = []
        unknown = False
        for dimension in DIMENSIONS:
            count = self._count_dimension(dimension)
            if count is None:
                unknown = True
                counts.append(0)
            else:
                counts.append(count)
        return counts, unknown

    def _scan_once(self) -> bool:
        if not self._enabled:
            return False
        with self._scan_lock:
            counts, unknown = self._count_all_dimensions()
            total = total_dropped_items(counts)
            if bool(self.config.get("输出统计日志", False)):
                self.print(
                    f"§7掉落物统计: 主世界={counts[0]}, 下界={counts[1]}, "
                    f"末地={counts[2]}, 合计={total}, 阈值={self._threshold()}"
                )
            if unknown and total <= self._threshold():
                if not self._error_printed:
                    self.print(
                        "§e掉落物统计响应不完整，本轮不清理，下一轮重试"
                    )
                    self._error_printed = True
                return False
            self._error_printed = False
            if not should_cleanup(counts, self._threshold()):
                return False
            self._cleanup_all_dimensions(total)
            return True

    def _cleanup_all_dimensions(self, detected_total: int):
        removed = 0
        failed_dimensions: list[str] = []
        dimensions = DIMENSIONS if self.config.get("清理所有维度", True) else ("overworld",)
        for dimension in dimensions:
            try:
                response = self.game_ctrl.sendwscmd_with_resp(
                    build_cleanup_command(dimension),
                    self._CLEANUP_TIMEOUT_SECONDS,
                )
                count = extract_success_count(response)
                if count is None:
                    failed_dimensions.append(dimension)
                else:
                    removed += count
            except Exception as error:
                failed_dimensions.append(dimension)
                fmts.print_err(f"清理 {dimension} 掉落物失败: {error}")
        self.print(
            f"§a掉落物超过阈值，已触发清理 | 检测={detected_total}, "
            f"实际移除={removed}"
        )
        if failed_dimensions:
            self.print(
                "§c以下维度清理结果未知，将在下一轮重新检查: "
                + ", ".join(failed_dimensions)
            )

    def _on_console_command(self, args: list[str]):
        action = (args[0].lower() if args else "status")
        prefixes = {
            str(prefix).lower()
            for prefix in self.config.get(
                "控制台指令",
                self.CFG_DEFAULT["控制台指令"],
            )
        }
        if args and action in prefixes:
            action = args[1].lower() if len(args) > 1 else "status"
        if action not in {"status", "count"}:
            self.print("§c用法: drop_cleanup status")
            return
        with self._scan_lock:
            counts, unknown = self._count_all_dimensions()
        self.print(
            f"§e掉落物统计: 主世界={counts[0]}, 下界={counts[1]}, "
            f"末地={counts[2]}, 合计={total_dropped_items(counts)}, "
            f"阈值={self._threshold()}"
        )
        if unknown:
            self.print("§e部分维度统计响应不完整")


entry = plugin_entry(DroppedItemCleanup, "掉落物600上限清理")
