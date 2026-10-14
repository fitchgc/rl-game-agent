# 01: B1｜游戏文件与静态托管

**What to build:** 获取并固定 ruggrogue v1.0.1 完整运行文件，通过本地静态服务提供可启动的游戏 URL。

**Blocked by:** None (can start immediately).

**Status:** resolved

- [x] 记录文件来源、版本和校验值；`ruggrogue.wasm`、`ruggrogue.data` 及启动页所需资源齐全，不以占位文件绕过检查。
- [x] 提供一条命令启动静态服务；浏览器请求游戏及资源成功，无关键资源 404 或加载错误。
- [x] `required_files` 门禁在启动浏览器前检查资源；缺文件时明确报 B1，停止执行。
- [x] 无法取得合法可用的完整文件时，保存阻塞报告，不标记解除、不推进下游。

## Resolution

2026-10-14 完成，无阻塞：

- **来源**：官方站点 https://tung.github.io/ruggrogue/play/ 的预构建产物（MIT/CC0/WTFPL，与源码同许可）；源码仓库 `tung/ruggrogue` 已按 tag `v1.0.1`（`9f7ffd5`）浅克隆到 `vendor/ruggrogue-v1.0.1/` 备查。仓库内无预构建产物（`ruggrogue.js` 仅 134 字节胶水桩），且无 GitHub Release 附件，故采用官方站产物。
- **版本确认**：wasm 二进制内含 `v1.0.1` 字符串（标题屏 VERSION_STR），与 03 号票锁定的版本一致。
- **文件清单与校验**（见 `vendor/ruggrogue-web/MANIFEST.json`）：`index.html`、`ruggrogue.js`、`ruggrogue.wasm`（3.9MB）、`deps/ruggrogue.data`（41KB），各附 sha256。
- **静态托管**：`python3 -m http.server 8901 --directory vendor/ruggrogue-web`；curl 实测四个资源全部 200、无 404（canvas id 为 `#canvas`，与 04/07 票的 `canvas_selector` 一致）。
- **`required_files` 门禁**：清单与校验值已定型为 `MANIFEST.json`（05 号票的 `BrowserGameEnv` 启动浏览器前读取此文件逐项校验，缺失/损坏即报 B1 中止）。
- `vendor/` 已加入 `.gitignore`（二进制不进 git）；当前 8901 端口服务保持运行，供 02 号票直接使用。
