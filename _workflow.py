"""生成 ToolDelta 插件市场源所需的索引文件。

用法（仓库根目录）：
    python _workflow.py

会重新生成：
    market_tree.json     插件市场总索引（SourceName / Greetings / MarketPlugins）
    plugin_ids_map.json  插件 ID -> 插件目录名
    latest_versions.json 插件 ID -> 最新版本
    directory_tree.json  完整文件树（ToolDelta 客户端按此下载）
    directory.json       每个目录下的文件列表

参考 ToolDelta 官方插件市场（ToolDelta-Basic/PluginMarket）的 _workflow.py。
"""

import json
import os
import re
from pathlib import Path

MARKET_TREE_FILE = "market_tree.json"


def generate_json(directory):
    """directory.json：{相对目录: [文件名, ...]}"""
    data = {}
    if not os.path.isdir(directory):
        print("目录不存在或不是一个目录")
        return data
    for root, _, files in os.walk(directory):
        relative_path = os.path.relpath(root, directory)
        if any(item in relative_path for item in [".", ".git"]):
            continue
        data[relative_path] = list(files)
    return data


def get_latest_versions(directory):
    """latest_versions.json：{plugin-id: version}"""
    v_dict = {}
    for p1 in os.listdir(directory):
        if p1.startswith("[pkg]"):
            continue
        datas_path = os.path.join(directory, p1, "datas.json")
        if os.path.isfile(datas_path):
            with open(datas_path, encoding="utf-8") as f:
                dat = json.load(f)
            v_dict[dat["plugin-id"]] = dat["version"]
    return json.dumps(v_dict, indent=2, ensure_ascii=False)


def flush_basic_datas():
    """更新 market_tree.json 的 MarketPlugins / Packages。"""
    with open(MARKET_TREE_FILE, encoding="utf-8") as f:
        market_d = json.load(f)
    market_d["MarketPlugins"] = {}
    market_d["Packages"] = {}
    for path in os.listdir():
        datpath = os.path.join(path, "datas.json")
        if os.path.isfile(datpath):
            with open(datpath, encoding="utf-8") as f:
                dat = json.load(f)
            if not path.startswith("[pkg]"):
                market_d["MarketPlugins"][dat["plugin-id"]] = {
                    "name": path,
                    "author": dat["author"],
                    "version": dat["version"],
                    "plugin-type": dat["plugin-type"],
                }
            else:
                market_d["Packages"][path[5:]] = {
                    "plugin-ids": dat["plugin-ids"],
                    "description": dat["description"],
                    "author": dat["author"],
                    "version": dat["version"],
                }

    # 前置插件排在列表最后，方便客户端先展示主插件
    format_tree_depen = {}
    format_tree_main = {}
    for k, v in market_d["MarketPlugins"].items():
        if "前置" in v["name"]:
            format_tree_depen[k] = v
        else:
            format_tree_main[k] = v
    market_d["MarketPlugins"] = {**format_tree_main, **format_tree_depen}

    with open(MARKET_TREE_FILE, "w", encoding="utf-8") as f:
        json.dump(market_d, f, indent=2, ensure_ascii=False)


def flush_plugin_ids_map():
    """plugin_ids_map.json：{plugin-id: 目录名}"""
    mapper = {}
    for path in os.listdir():
        if path.startswith("[pkg]"):
            continue
        datpath = os.path.join(path, "datas.json")
        if os.path.isfile(datpath):
            with open(datpath, encoding="utf-8") as f:
                dat = json.load(f)
            mapper[dat["plugin-id"]] = path
    with open("plugin_ids_map.json", "w", encoding="utf-8") as f:
        json.dump(mapper, f, indent=2, ensure_ascii=False)


def get_tree(basepath: str = ""):
    """directory_tree.json：{目录/文件: {...} | 0}"""
    dirs = {}
    for path in sorted(os.listdir(basepath) if basepath else os.listdir()):
        new_path = os.path.join(basepath, path) if basepath else path
        if os.path.isfile(new_path):
            dirs[path] = 0
        else:
            if path.startswith(".") or path == "__pycache__":
                continue
            dirs[path] = get_tree(new_path)
    return dirs


def get_valid_plugins_amount():
    amount = 0
    for directory in Path().iterdir():
        if (
            directory.is_dir()
            and directory.name != "__pycache__"
            and directory.name != ".git"
            and (directory / "__init__.py").is_file()
            and (directory / "datas.json").is_file()
        ):
            amount += 1
    return amount


def get_valid_plugin_packages_amount():
    amount = 0
    for directory in Path().iterdir():
        if (
            directory.is_dir()
            and directory.name != "__pycache__"
            and directory.name.startswith("[pkg]")
            and (directory / "datas.json").is_file()
        ):
            amount += 1
    return amount


def modify_readme():
    """如果 README 里写了「**N 个插件** / **N 个整合包**」，同步数量。"""
    if not os.path.isfile("README.md"):
        return
    with open("README.md", encoding="utf-8") as f:
        md_content = f.read()
    md_content = re.compile(r"\*\*([0-9]*) 个插件\*\*").sub(
        f"**{get_valid_plugins_amount()} 个插件**", md_content
    )
    md_content = re.compile(r"\*\*([0-9]*) 个整合包\*\*").sub(
        f"**{get_valid_plugin_packages_amount()} 个整合包**", md_content
    )
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(md_content)


def main():
    directory = "."

    with open("directory.json", "w", encoding="utf-8") as json_file:
        json.dump(generate_json(directory), json_file, indent=4, ensure_ascii=False)

    with open("latest_versions.json", "w", encoding="utf-8") as f:
        f.write(get_latest_versions(directory))

    with open("directory_tree.json", "w", encoding="utf-8") as f:
        json.dump(get_tree(), f, indent=4, ensure_ascii=False)

    modify_readme()
    flush_basic_datas()
    flush_plugin_ids_map()

    print(
        f"索引已生成：{get_valid_plugins_amount()} 个插件、"
        f"{get_valid_plugin_packages_amount()} 个整合包"
    )


if __name__ == "__main__":
    main()
