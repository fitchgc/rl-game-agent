Labels: wayfinder:research
Type: research
Status: resolved
Blocked by: 02, 03
Mode: AFK

## Question

首发游戏采用哪一套画面获取与观测生成方案？

比较至多 3 种适用方案，例如窗口截图、桌面区域截图、浏览器或游戏提供的画面帧接口；最终选择一种，并说明它是否仍满足"以游戏画面为观测"的约束。

决策规格需覆盖：截图后端、目标窗口定位、分辨率与色彩格式、裁剪缩放、采样频率、帧堆叠、动作后取帧顺序，以及失焦、遮挡、陈旧帧的处理原则。区分文档可证实的能力与实现阶段仍需测量的延迟，不编造性能数据。

## Answer

**决策：主路径 = Playwright Python 在 headless Chromium 中对 `canvas` 做元素截图（CDP 合成后像素）；仅当 headless WebGL 启动探测失败时降级为 Xvfb + mss 整桌面截图；`canvas.toDataURL` 直接抓帧否决。**

- **截图后端**：Playwright Python + headless Chromium，`page.locator('canvas').screenshot()`；无需 X server。headless 经 SwiftShader 软件渲染支持 WebGL（Playwright 自动加 `--enable-unsafe-swiftshader`），与 headed 同渲染管线——均为文档可证实，仍需在目标 VM 做启动门禁探测。
- **目标定位**：独占 browser context + 单 page，定位全屏 `canvas`；启动确认唯一、可见、尺寸非零。
- **分辨率与色彩**：启动固定 viewport（建议 1280x800，非已测最优），`scale="css"`，PNG bytes → numpy RGB 并校验尺寸。
- **裁剪缩放**：元素边界即裁剪，不含浏览器外框/桌面；84x84 下采样、灰度化等训练预处理归 08 号票。
- **采样**：无固定 FPS，每 step 一观测（+ 初始化一张）。
- **帧堆叠**：不使用——回合制单帧完全可观测，无运动时序问题。
- **按键后取帧顺序**：读当前 HUD `TurnCount` → `keyboard.press(key)` → `wait_for_function` 等 `TurnCount` 文本变化 → 截图 → 解码。TurnCount 是天然同步信号，陈旧帧按构造排除。
- **异常**：等待超时重试等待一次（不重发按键）；再超时则 `truncated=True` 中止本局并告警；截图/解码失败不得用旧帧冒充。
- **失焦/遮挡**：headless 下按构造不存在；独占 context 避免跨页竞争。
- **启动门禁**：`page.evaluate` 探测 webgl2；失败则试 headed+Xvfb+SwiftShader flags（切方案 B）；仍失败则硬阻塞，不盲训。
- **满足"以游戏画面为观测"**：是。截取的是与玩家所见一致的合成后渲染像素；HUD 是画面的一部分，仅用于同步时机，不拼入观测特征；降级方案裁剪后仍只含游戏画面。

**否决理由（方案 C）**：Khronos 规范确认 `preserveDrawingBuffer=false`（默认值）时合成后缓冲被清空，之后 `toDataURL`/`readPixels` 行为未定义；Emscripten 默认不设该 flag，抓帧时序脆弱。

**残余风险 / 实现期测量**：截图延迟、SwiftShader 下 ruggrogue 渲染帧率、`TurnCount` 等待超时阈值——均未在本票填数，必须实现期实测。

详细研究笔记：`.scratch/wayfinding/research/04-visual-observation-notes.md`
