import time
import os
import sys

from tooldelta import Plugin, plugin_entry, utils, fmts


class FateArkBotAliveChecker(Plugin):

    name = "FateArk掉线检测"
    author = "渊思"
    version = (0, 0, 1)


    def __init__(self, frame):
        super().__init__(frame)
        self.ListenActive(self.Start)


    def Start(self):
        utils.createThread(
            self.Check,
            (),
            "FateArk掉线检测"
        )


    def Check(self):

        fail = 0

        while True:

            try:

                self.game_ctrl.sendwscmd(
                    "testfor @a",
                    waitForResp=True,
                    timeout=10
                )

                fail = 0

            except TimeoutError:

                fail += 1

                fmts.print_war(
                    f"MC响应超时 ({fail}/3)"
                )


            except Exception as e:

                # 任何连续异常都视为一次失败，避免非 TimeoutError 时无限空转
                fail += 1

                fmts.print_err(
                    f"检测异常 ({fail}/3): {e}"
                )


            if fail >= 3:

                fmts.print_err(
                    "FateArk掉线，正在关闭MCSM"
                )

                self.stop_mcsm()

                break


            time.sleep(8)



    def stop_mcsm(self):

        try:

            # MCSM守护进程停止
            if sys.platform.startswith("win"):

                os.system(
                    "taskkill /f /im node.exe"
                )

            else:

                os.system(
                    "pkill -f mcsmanager"
                )


            fmts.print_suc(
                "MCSM已停止"
            )

            os._exit(0)


        except Exception as e:

            fmts.print_err(
                f"MCSM关闭失败:{e}"
            )

            os._exit(1)



entry = plugin_entry(FateArkBotAliveChecker)