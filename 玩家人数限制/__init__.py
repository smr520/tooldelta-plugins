from tooldelta import Plugin, cfg as config, game_utils, Player, plugin_entry


class PlayerLimitPlugin(Plugin):
    name = "玩家人数限制"
    author = "SuperScript"
    version = (0, 0, 3)

    def __init__(self, frame):
        super().__init__(frame)
        CFG = {"最大人数限制": 20}
        cfg, _ = config.get_plugin_config_and_version(
            self.name, config.auto_to_std(CFG), CFG, self.version
        )
        self.maxinum_player = cfg["最大人数限制"]
        self.ListenPlayerJoin(self.on_player_join)
        self.ListenPreload(self.on_preload)

    def on_preload(self):
        chatbar = self.GetPluginAPI("聊天栏菜单", force=False)
        if chatbar is not None:
            chatbar.add_new_trigger(
                ["人数"],
                [],
                "查看当前在线人数与上限（OP）",
                self.cmd_show_count,
                op_only=True,
            )

    def on_player_join(self, player: Player):
        playername = player.name
        if (
            len(self.game_ctrl.allplayers) > self.maxinum_player
            and not game_utils.is_op(playername)
        ):
            self.game_ctrl.sendwocmd(f'kick "{playername}" 已达到租赁服最大人数限制')

    def cmd_show_count(self, player, _args):
        player.show(
            f"§e当前在线：§f{len(self.game_ctrl.allplayers)} §7/ §f{self.maxinum_player}"
        )


entry = plugin_entry(PlayerLimitPlugin)
