# wayfinder 决策票研究笔记：ruggrogue 浏览器画面捕获

## 决策

**选用方案 A：通过 Playwright Python 在 headless Chromium 中截取 `canvas` 元素的合成后像素，以“每次按键推进一回合、每回合一张 PNG”的方式生成观测；仅在 headless WebGL 启动探测失败时降级至方案 B。**

适用范围：`rl-game-agent` 首发游戏 `ruggrogue v1.0.1`。游戏由 Rust + SDL2 + Emscripten 编译为浏览器 WASM，通过自托管静态 `index.html` 运行，使用全屏 `canvas` 和纯键盘操作。部署环境为无 GPU 的无头 Linux VM，允许使用 Xvfb。

## 三方案比较表

| 方案 | 捕获路径 | 适配性与优势 | 限制与风险 | 决策 |
|---|---|---|---|---|
| **A：Playwright `canvas` 元素截图** | `page.locator('canvas').screenshot()`；经 CDP 获取合成后页面像素 | 【文档可证实】不依赖 WebGL 绘图缓冲保留，不受 `preserveDrawingBuffer=false` 影响；headless 键盘输入可用；无需 X server；可直接定位游戏画面 | 【实现期仍需测量】纯 CPU 环境下的截图延迟、SwiftShader 渲染表现和回合同步等待阈值 | **选中** |
| **B：Xvfb + `mss` 桌面截图** | headed Chromium 在 Xvfb 中运行，`mss` 截取桌面后裁剪 | 【文档可证实】`mss` 自 v10.2 起在 Linux 使用 XCB 后端及 XShm 共享内存加速；Xvfb 提供 X server，满足使用条件 | 需维护浏览器窗口几何到游戏画面的坐标换算与裁剪；headed 浏览器更重；仍需验证 WebGL 可用 | **备选／降级**，仅在 headless WebGL 探测失败时启用 |
| **C：`canvas.toDataURL()` 直接抓帧** | 在 `page.evaluate()` 中读取 WebGL `canvas` | 实现路径短，但读取的是绘图缓冲，不是稳定的合成后截图路径 | 【文档可证实】`preserveDrawingBuffer=false` 为默认值；合成后缓冲不保证保留，此时调用 `toDataURL()` / `readPixels()` 不能保证获得期望帧，可能为空白。Emscripten 默认不设置该 flag | **否决**，捕获时序脆弱 |

【文档可证实】headless Chromium 可通过 SwiftShader 软件渲染支持 WebGL；Playwright 自动添加 `--enable-unsafe-swiftshader`。新版 headless 与 headed 使用同一渲染管线。**这些能力说明不替代目标 VM 上的启动门禁。**

【外部实测引用】`game-qa` WebGL deep dive 与 `HEADLESS.md` 可作为 headless WebGL、SwiftShader 部署经验的参考，但不是本项目的性能实测。

## 决策规格

| 项目 | 规格 |
|---|---|
| **截图后端** | 主路径使用 Playwright Python + headless Chromium，通过 `locator('canvas').screenshot()` 获取合成后像素。`page.screenshot()` 保留为页面级诊断入口，不作为常规观测来源。无需 Xvfb。 |
| **目标定位** | 使用独占 `browser context` 和单 `page`，定位游戏 `canvas`；启动时确认目标唯一、可见且尺寸非零，避免误截其他元素。 |
| **分辨率与色彩** | 启动时固定 viewport；`1280×800` 为建议值，不是已测最优值。固定 `scale="css"`，以 PNG bytes 输出，解码为 `numpy` RGB 数组，并校验实际尺寸。 |
| **裁剪缩放** | 主路径直接使用元素边界裁剪，不包含浏览器外框或桌面。方案 B 必须完成窗口几何换算并裁剪至同一游戏画面区域。`84×84` 下采样、灰度化等训练预处理由 **08 号票**决定，本票不定。 |
| **采样** | 无固定 FPS；每个 `step` 产生一次观测。初始化完成后获取一张初始观测。 |
| **帧堆叠** | 不使用。基于已核实的游戏特性，单帧网格与 HUD 即提供完整观测；回合制不需要借助历史帧恢复运动信息，也不存在实时运动带来的时序 aliasing。 |
| **按键后取帧顺序** | 记录当前 HUD `TurnCount` → `page.keyboard.press(key)` → `page.wait_for_function(...)` 等待 HUD `TurnCount` 文本变化 → 截取 `canvas` → 解码为 RGB 观测。 |
| **异常处理** | `TurnCount` 等待超时后，**重试等待一次，不重复发送按键**；再次超时则置 `truncated=True`，中止本局并告警。截图或解码失败不得用旧帧伪装为本步观测。 |
| **启动门禁** | 通过 `page.evaluate()` 探测 `webgl2`。headless 探测失败时，尝试 headed + Xvfb + SwiftShader flags 组合，并启用方案 B；若仍缺失，则硬阻塞，不允许盲训。 |

### 同步与隔离约束

- 每次有效按键恰好推进一回合，`TurnCount` 是天然的回合同步信号。
- 截图必须发生在**画面 HUD 的本回合 `TurnCount` 更新后**。在这一同步契约成立的前提下，上一回合的陈旧帧按构造被排除，而不是靠固定 `sleep` 猜测渲染完成时间。
- `wait_for_function` 的具体实现必须落实 HUD 文本的读取路径；不能仅凭使用该 API 就假定 `canvas` 文本可以像 DOM 文本一样直接查询，也不能改用隐藏游戏状态冒充画面更新信号。
- 主路径没有 OS 窗口，因此不存在桌面窗口失焦或被其他窗口遮挡的问题；独占 context、单 page 避免跨页面输入竞争。
- 【文档可证实】Playwright 提供 `page.keyboard.press()`，可在 headless 模式下发送键盘输入。

## 仍满足画面观测论证

**满足“以游戏画面为观测”的要求。**

1. **观测来自渲染结果。**  
   【文档可证实】方案 A 获取的是浏览器合成后的页面像素，而非游戏内部地图、实体坐标、WASM 内存或未渲染状态；其内容对应玩家所见的游戏画面。

2. **HUD 本身属于画面。**  
   网格与 HUD 一并保留在截图中。读取 HUD `TurnCount` 仅用于判定何时截图，不将该数值另行拼接为观测特征，也不引入画面外信息。

3. **同步与观测严格分离。**  
   `TurnCount` 变化决定捕获时机，`webgl2` 探测决定运行是否可启动；二者均不成为 agent 的额外状态输入。agent 接收的观测仍是截图解码后的 RGB 数组。

4. **降级不改变观测语义。**  
   方案 B 只改变像素捕获后端；裁剪后仍只保留游戏画面，不把桌面、窗口装饰或调试界面纳入观测。

## 证据标签说明与来源URL

| 标签 | 含义与使用边界 |
|---|---|
| **【文档可证实】** | 可由 API 文档、源码或规范讨论核查的机制与能力；不表示已在目标 VM 上测得性能。 |
| **【实现期仍需测量】** | 必须在本项目、实际浏览器版本和目标 VM 上验证的数值或阈值；本文不填入未经测量的数据。 |
| **【外部实测引用】** | 外部项目的运行经验；用于支持可行性判断或排障，不直接外推成本项目的吞吐、延迟或成功率。 |

### 来源

- 【文档可证实】Playwright Python 截图 API（`page.screenshot()` / `locator.screenshot()`，参数 `type`/`quality`/`clip`/`full_page`/`animations`/`scale`/`omit_background`）：
  - https://screenshotone.com/blog/playwright-python-screenshots/
  - https://github.com/commoncapital/manus-ai_clone/blob/HEAD/public/deep-agent/skills/playwright-python-skill/API_REFERENCE.md
  - https://dev.to/zt4ff_1/playwright-tutorial-for-beginners-8-screenshots-4h69
- 【文档可证实】`python-mss` v10.2.0：Linux 改用 XCB 后端 + XShm 共享内存加速。  
  https://github.com/bobotig/python-mss/blob/HEAD/docs/source/release-history/v10.2.0.md
- 【外部实测引用】`game-qa` WebGL deep dive：headless WebGL 与截图路径的外部调研参考。  
  https://github.com/jonmumm/skills
- 【外部实测引用】`HEADLESS.md`：headless / SwiftShader 环境部署经验。  
  https://github.com/remotional/gargantua-binary-kerr
- 【文档可证实】Khronos `public_webgl` 邮件列表：`preserveDrawingBuffer=false` 时合成后缓冲被清空、之后 `toDataURL`/`readPixels` 行为未定义。  
  https://www.khronos.org/webgl/public-mailing-list/public_webgl/1306/msg00019.php

上述仓库及邮件列表为来源入口；未提供的具体讨论 permalink、测试数据及版本对照不作补写。

## 残余风险

| 实现期测量项 | 需要记录的内容 | 对决策的影响 |
|---|---|---|
| **【实现期仍需测量】截图延迟** | 在固定 viewport 下测量 `canvas` 截图调用耗时；分别记录 PNG 解码耗时与整体观测生成耗时，关注波动及长尾 | 决定可达到的环境步吞吐；不能以外部项目数据代替 |
| **【实现期仍需测量】SwiftShader 下 `ruggrogue` 渲染帧率** | 在目标纯 CPU VM 上测量实际渲染帧率，并观察不同场景负载下的变化 | 判断软件渲染是否构成瓶颈；不因此改为固定 FPS 采样 |
| **【实现期仍需测量】`TurnCount` 等待超时阈值** | 测量按键发送至 HUD 回合更新的延迟分布，区分正常长尾与卡死；据此确定首次等待及一次重试的阈值 | 避免过早截断正常回合，同时确保异常运行能及时停止 |

**本文不承诺具体截图延迟、渲染 FPS 或等待超时数值；这些数值必须由实现期测量给出。**
