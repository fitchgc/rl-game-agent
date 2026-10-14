# 05: 打通 BrowserGameEnv 与 adapter

**What to build:** 实现公共 `BrowserGameEnv(gymnasium.Env)` 和 ruggrogue adapter，注册到 `ENV_REGISTRY`，让脚本通过标准 `reset/step/close` 完成真实游戏交互。

**Blocked by:** 01, 02, 03, 04 (B1/B4/B3/B2 验证票).

**Status:** ready-for-agent

- [ ] 落实已定的 20 项 `GameAdapter` 协议，包含资源门禁、静态按键翻译、阶段检测、HUD 读取及 `on_frame` 原子返回；公共 env 不硬编码游戏专属逻辑。
- [ ] `reset()` 可重复启动新局；`step()` 按键后等待已定屏障，再采集当前帧；超时明确报 fault，不无限等待。
- [ ] observation 为玩家所见完整画面的单帧灰度 `84×84` 图像（含 HUD 像素），无帧堆叠；OCR 数值不拼入 observation 做额外特征。
- [ ] 固定 `info` 键及类型并测试；Gymnasium 接口检查和真实多步冒烟通过，`close()` 释放浏览器资源。此票奖励可暂为零，不宣称训练可用。
