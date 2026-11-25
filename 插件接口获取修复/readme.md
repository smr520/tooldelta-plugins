# 插件接口获取修复 0.0.1
> 其它插件缺少所需 API 时，提示从插件市场自动下载对应插件。

收录自 ToolDelta 官方插件市场，原作者 `ToolDelta`；本仓库有标准化修改。

## 功能
- 加载时保存框架的 `self.frame.plugin_group.get_plugin_api`，并把它替换成自己的包装方法；此后其它插件调用 `GetPluginAPI()` 都会经过该包装。
- 包装方法先执行原逻辑；捕获 `PluginAPINotFoundError` 时打印「插件API X 未找到」，捕获 `PluginAPIVersionError` 时打印「插件API X 版本过低」，然后询问是否自动下载。
- 控制台询问 `尝试自动从市场下载插件吗 (y/n): `；输入 `y` 或直接回车（默认按 `y`）时，用 `market.get_plugin_data_from_market(api_name)` 在市场源中查找包含该 API 的插件，再用 `market.download_plugin()` 下载。
- 下载成功打印「已下载包含接口 X 的插件, 请重启 ToolDelta」，随后 `raise SystemExit` 结束当前 ToolDelta 进程；需要手动重启后新插件才会加载。
- 输入 `n` 或市场请求抛 `requests.RequestException` 时，打印「尝试失败」并重新抛出原始异常，不改变原有报错行为。
- 只接管 `GetPluginAPI` 的这两类异常；其它异常、插件自身加载失败等不在处理范围内。

## 前置插件
| 插件 ID | 最低版本 | 用途 |
|---|---|---|
| 无 | - | 不依赖其它插件 |

本插件没有注册 API；它通过替换框架方法工作，必须被正常加载才会生效。

## 安装
1. 将 `插件接口获取修复/` 复制到实例的 `插件文件/ToolDelta类式插件/`；
2. 启动实例，或在 ToolDelta 控制台执行 `reload`；
3. 也可以把本仓库添加为自定义插件市场源后直接安装。

## 配置
无配置文件，开箱即用。运行中唯一的交互是触发下载前的控制台 `y` / `n` 询问。

## 指令
本插件无手动指令。触发报错时控制台会出现 `尝试自动从市场下载插件吗 (y/n): ` 询问：输入 `y` 或回车下载，输入 `n` 放弃。

## 依赖与兼容
- ToolDelta 1.3.7 类式插件（FateArk / MCSM 面板）。
- 第三方库 `requests`：代码 `import requests` 并捕获 `requests.RequestException`；`requests` 是 ToolDelta 自身的依赖，正常安装的框架环境中已存在。
- 依赖 ToolDelta 内部模块 `tooldelta.plugin_market.market` 与 `tooldelta.plugin_load.exceptions` 的异常类型，升级 ToolDelta 后需要回归。
- 必须配置可用的插件市场源并能联网，否则市场查找失败，只会打印「尝试失败」并继续抛原异常。
- 仅在自身加载完成后才接管 `get_plugin_api`；在此之前发生的 API 获取不会被处理。
- 下载完成后直接 `SystemExit` 退出进程，不会自动重载，也不保证已下载插件能立即加载。

## 版本记录
- `0.0.1`（官方市场版本，原作者 `ToolDelta`）：收录本版本；本仓库仅统一文档格式与文件名，代码未改动。
