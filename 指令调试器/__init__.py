import json
import time

from tooldelta import Plugin, plugin_entry


class MCCommandDebugger(Plugin):
    name = "指令调试器"
    author = "SuperScript"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        self.frame.add_console_cmd_trigger(
            ["d/"], "[指令]", "执行指令并查看完整返回", self.test_command
        )
        self.frame.add_console_cmd_trigger(
            ["dw/"], "[指令]", "执行指令并查看完整返回（与 d/ 相同）", self.test_command
        )

    def test_command(self, args: list[str]):
        cmd = " ".join(args)
        if not cmd:
            self.print("§c用法: d/<指令> 或 dw/<指令>")
            return
        sendtime = time.time()
        try:
            res = self.game_ctrl.sendwscmd_with_resp(cmd).as_dict
        except TimeoutError:
            self.print("§c指令返回获取超时")
            return
        except Exception as err:
            self.print(f"§c执行指令失败: {err}")
            return
        use_time = time.time() - sendtime
        extra_msg = ("§c失败§r", "§a成功§r")[res["SuccessCount"] > 0]
        self.print(f"指令结果返回 ({cmd}) | {extra_msg} | 用时 {use_time:.2f}s:")
        self.print(json.dumps(res, indent=4, ensure_ascii=False))


entry = plugin_entry(MCCommandDebugger)
