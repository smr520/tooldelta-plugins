import time
from tooldelta import Plugin, constants, plugin_entry


class TPSCalculator(Plugin):
    name = "前置-TPS计算器"
    author = "SuperScript"
    version = (0, 0, 2)

    def __init__(self, frame):
        super().__init__(frame)
        self.ListenPacket(constants.PacketIDS.IDSetTime, self.listener)
        self.last_time = time.monotonic()
        self.last_server_time = None
        self._tps = 20.0
        self._real_tps = 20.0
        self._warned = False

    def listener(self, pkt):
        self.calc_tps(pkt)
        return False

    def calc_tps(self, pkt):
        ntime = time.monotonic()
        server_time = pkt["Time"]
        if self.last_server_time is None:
            # 第一包没有上一包可比较，先记录基准
            self.last_time = ntime
            self.last_server_time = server_time
            return
        server_time_delta = server_time - self.last_server_time
        real_time_delta = ntime - self.last_time
        if server_time_delta == 0:
            if not self._warned:
                self._warned = True
                self.print("§6警告: 无法正确取得租赁服 tps。你需要在设置中将§e昼夜更替§6打开。")
            return
        if real_time_delta <= 0:
            return
        # IDSetTime 的 Time 是游戏刻，每秒 20 刻；直接相除即为 TPS
        tps = server_time_delta / real_time_delta
        self._real_tps = tps
        self._tps = max(0.0, min(20.0, tps))
        self.last_time = ntime
        self.last_server_time = server_time


    def get_tps(self):
        if time.monotonic() - self.last_time > 40:
            # server maybe dead
            return 0
        else:
            return self._tps


entry = plugin_entry(TPSCalculator, "tps计算器")
