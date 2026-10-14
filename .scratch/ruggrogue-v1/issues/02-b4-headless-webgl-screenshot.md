# 02: B4｜Headless WebGL 与截图冒烟

**What to build:** 使用 Playwright headless Chromium 加载真实游戏，验证 WebGL 可用并保存 canvas 截图。

**Blocked by:** 01 (B1｜游戏文件与静态托管).

**Status:** ready-for-agent

- [ ] 提供可重复运行的探针，记录 Chromium 版本、启动参数、WebGL 探测结果及页面错误。
- [ ] 游戏成功渲染；截图来自 `canvas_selector` 指定元素，而非整页，尺寸有效且不是空白或错误画面。
- [ ] WebGL 不可用或游戏渲染失败时明确报 B4；不得用 headed 模式成功代替 headless 验收。
- [ ] 探针结束后关闭浏览器与页面，产物写入 `artifacts/`。
