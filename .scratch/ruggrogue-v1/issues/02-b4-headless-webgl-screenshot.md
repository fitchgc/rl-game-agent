# 02: B4｜Headless WebGL 与截图冒烟

**What to build:** 使用 Playwright headless Chromium 加载真实游戏，验证 WebGL 可用并保存 canvas 截图。

**Blocked by:** 01 (B1｜游戏文件与静态托管).

**Status:** resolved

- [x] 提供可重复运行的探针，记录 Chromium 版本、启动参数、WebGL 探测结果及页面错误。
- [x] 游戏成功渲染；截图来自 `canvas_selector` 指定元素，而非整页，尺寸有效且不是空白或错误画面。
- [x] WebGL 不可用或游戏渲染失败时明确报 B4；不得用 headed 模式成功代替 headless 验收。
- [x] 探针结束后关闭浏览器与页面，产物写入 `artifacts/`。

## Resolution

2026-10-14 完成，B4 未触发（无需降级）：

- **Chromium**：Google Chrome for Testing 156.0.8078.4（Playwright 1.64.0 对应版本 chromium-1248）。`playwright install` 的 Node 下载器走代理失败，改用 curl 直下官方 CDN 后手动部署到 `~/.cache/ms-playwright/`（完整版 + headless shell 两个 build）。
- **WebGL**：headless 下 WebGL2 可用，经 SwiftShader 软件渲染（`ANGLE ... SwiftShader Device`），04 号票主路径成立。
- **渲染验证**：`.scratch/ruggrogue-v1/probes/b4_probe.py`（可重复运行）加载真游戏，`#canvas` 元素截图 1280×800；目检为真实标题画面（RUGG ROGUE logo、New Game/Load Game/Options 菜单），左下角显示 `v1.0.1`，与锁定版本一致。
- **产物**：`artifacts/b4/canvas.png` + `artifacts/b4/report.json`（Chromium 版本、WebGL 探测、canvas 尺寸、页面错误）。
- 备注：中途 VM 被运行时替换导致 /tmp 丢失，重做时改把安装包放在 `~/workspace/.tmp-dl/`（持久化）。
