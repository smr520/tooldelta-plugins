# pip模块支持 0.0.6
> 为 ToolDelta 与第三方插件安装 pip 模块，并提供控制台安装入口。

## 功能
- 控制台提供 `pip-install` 指令，把指定 Python 包安装到本插件的数据目录，并加入 `sys.path` 供其它插件导入。
- 面向其它插件提供三个方法（用 `GetPluginAPI("pip")` 取得实例后调用）：
  - `install(packages: list[str], upgrade=False)`：安装一组包；
  - `require(模块名 / 列表 / {pip 名: 导入名})`：先尝试 `import`，缺失时才安装，兼容三种参数写法；
  - `upgrade(*模块名)`：带 `--upgrade` 重新安装。
- 安装前检查已安装版本：已安装且未固定版本号时跳过，或已安装版本与 `包名==版本` 一致时跳过。
- 安装过程实时把 pip 的 stdout / stderr 打印到控制台，前缀分别为 `§e pips` 和 `§c pips`；成功后打印安装成功提示。
- 本目录为第三方插件的本地修改版：原作者 `SuperScript`。

## 前置插件
| 插件 ID | 最低版本 | 用途 |
|---|---|---|
| 无 | - | 不依赖其它插件 |

其它插件可把它作为前置，用 `GetPluginAPI("pip")` 调用上述方法；本插件 `datas.json` 的 `plugin-id` 为 `pip`。

## 安装
1. 将 `pip模块支持/` 复制到实例的 `插件文件/ToolDelta类式插件/`；
2. 启动实例，或在 ToolDelta 控制台执行 `reload`；
3. 也可以把本仓库添加为自定义插件市场源后直接安装。

## 配置
无配置文件，开箱即用。被安装的第三方库会放在插件数据目录（`self.data_path`，访问时自动创建）并追加到 `sys.path`。

## 指令
| 位置 | 指令 / 触发词 | 权限 | 说明 |
|---|---|---|---|
| 控制台 | `pip-install <模块名> [更多模块名 ...]` | 无 | 安装指定 pip 包，可写 `包名==版本` 固定版本 |

不带参数时提示 `请输入要安装的模块名`。

## 依赖与兼容
- ToolDelta 1.3.7 类式插件（FateArk / MCSM 面板）；
- 本插件自身只用标准库（`sys`、`importlib`、`subprocess`）与 ToolDelta 内置模块，无第三方 import；安装动作依赖可用的 `pip` 与网络；
- 固定使用清华 PyPI 镜像 `https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple`，离线或镜像不可达时安装失败；
- 根据 `sys.executable` 是否包含 `py` 选择启动方式：包含时执行 `python -m pip`，否则直接调用系统 `pip` 命令（打包运行时需要 PATH 中有 pip）；
- 安装失败会打印错误并 `raise SystemExit`：控制台入口会捕获，`require()` / `upgrade()` 的调用方会直接收到该异常。

## 版本记录
- `0.0.6`（2026-10-27，原作者 `SuperScript`）：本地修正 `require()` 处理列表时的变量遮蔽写法；改用 `self.data_path`，不再调用已弃用的 `make_data_path()`；版本号沿用官方 0.0.6。
