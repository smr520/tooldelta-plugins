from tooldelta import Plugin, utils, plugin_entry


class BigCharReplace(Plugin):
    author = "ToolDelta"
    name = "前置-大字替换"
    version = (0, 0, 2)

    @staticmethod
    def replaceBig(t: str):
        """
        将给定的字符串中的所有可替换符号替换为大字符号
        Args:
            t (str): 原字符串
        Returns:
            str: 替换后的字符串
        """
        return utils.simple_fmt(
            {
                "0": "０",
                "1": "１",
                "2": "２",
                "3": "３",
                "4": "４",
                "5": "５",
                "6": "６",
                "7": "７",
                "8": "８",
                "9": "９",
                "a": "ａ",
                "b": "ｂ",
                "c": "ｃ",
                "d": "ｄ",
                "e": "ｅ",
                "f": "ｆ",
                "g": "ｇ",
                "h": "ｈ",
                "i": "ｉ",
                "j": "ｊ",
                "k": "ｋ",
                "l": "ｌ",
                "m": "ｍ",
                "n": "ｎ",
                "o": "ｏ",
                "p": "ｐ",
                "q": "ｑ",
                "r": "ｒ",
                "s": "ｓ",
                "t": "ｔ",
                "u": "ｕ",
                "v": "ｖ",
                "w": "ｗ",
                "x": "ｘ",
                "y": "ｙ",
                "z": "ｚ",
                "A": "Ａ",
                "B": "Ｂ",
                "C": "Ｃ",
                "D": "Ｄ",
                "E": "Ｅ",
                "F": "Ｆ",
                "G": "Ｇ",
                "H": "Ｈ",
                "I": "Ｉ",
                "J": "Ｊ",
                "K": "Ｋ",
                "L": "Ｌ",
                "M": "Ｍ",
                "N": "Ｎ",
                "O": "Ｏ",
                "P": "Ｐ",
                "Q": "Ｑ",
                "R": "Ｒ",
                "S": "Ｓ",
                "T": "Ｔ",
                "U": "Ｕ",
                "V": "Ｖ",
                "W": "Ｗ",
                "X": "Ｘ",
                "Y": "Ｙ",
                "Z": "Ｚ",
            },
            t,
        )


entry = plugin_entry(BigCharReplace, "大字替换")
