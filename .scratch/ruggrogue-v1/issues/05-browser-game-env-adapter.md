# 05: 打通 BrowserGameEnv 与 adapter

**What to build:** 实现公共 `BrowserGameEnv(gymnasium.Env)` 和 ruggrogue adapter，注册到 `ENV_REGISTRY`，让脚本通过标准 `reset/step/close` 完成真实游戏交互。

**Blocked by:** 01, 02, 03, 04 (B1/B4/B3/B2 验证票).

**Status:** resolved

- [x] 落实已定的 20 项 `GameAdapter` 协议，包含资源门禁、静态按键翻译、阶段检测、HUD 读取及 `on_frame` 原子返回；公共 env 不硬编码游戏专属逻辑。
- [x] `reset()` 可重复启动新局；`step()` 按键后等待已定屏障，再采集当前帧；超时明确报 fault，不无限等待。
- [x] observation 为玩家所见完整画面的单帧灰度 `84×84` 图像（含 HUD 像素），无帧堆叠；OCR 数值不拼入 observation 做额外特征。
- [x] 固定 `info` 键及类型并测试；Gymnasium 接口检查和真实多步冒烟通过，`close()` 释放浏览器资源。此票奖励可暂为零，不宣称训练可用。

## Resolution

2026-10-14 实现完成（未 commit，留给 parent）：

**新增文件**
- `src/rl_game_agent/envs/hud_ocr.py`：模板 OCR（复用 b2 探针逻辑），`certain`/`uncertain` 语义；数字模板 0-9+slash 随包发布（`envs/data/templates/`，从真实截图提取并逐字校验）。
- `src/rl_game_agent/envs/browser_env.py`：`BrowserGameEnv(gymnasium.Env)` + `GameAdapter` 协议。负责：B1 门禁（MANIFEST.json sha256 校验）、B4 WebGL 门禁、浏览器生命周期（reset 用全新 context，无存档干扰）、canvas 截图、按键注入（<50ms、无修饰键）、四选一 step 屏障（TurnCount+1 / Depth 变化 / GAMEOVER / 双帧相同+250ms；超时重试等待一次后 truncated fault）。
- `src/rl_game_agent/envs/ruggrogue.py`：`RuggrogueAdapter`，`Discrete(10)` 静态查表（0-7 vi 八向、8='.'、9=[Enter,h,Enter]；Shift/Ctrl/Alt/Esc 永不注入，有断言），`detect_phase`（HUD 确定→DUNGEON，否则中局非地牢→GAMEOVER），`detect_dialog`（中央区域像素差分，阈值 0.02，按无对话框基线 0.0 标定），`on_frame` 原子返回（本票 reward=0.0 占位，terminated/truncated 结构已定，06 票填公式）。
- `envs/__init__.py`：`ENV_REGISTRY["ruggrogue-v1"]` 工厂注册；`pyproject.toml` 新增 `playwright`、`pillow` 依赖 + 模板 package-data。

**验证结果**
- `check_env` 通过（SB3 2.9.0；唯一的 shape 警告为 2D 灰度 obs 的预期提示，CnnPolicy 处理）。
- 真机 15 步冒烟：reset→15 步（移动/等待/下楼宏）→close 全绿；Turn 2→14 单调推进（两次撕裂帧读出 uncertain，被屏障正确降级处理，无 fault）；动作 9 非楼梯场景 `dialog_seen=False` 安全 no-op；二次 reset 可重复（Turn 回 1）。
- step 平均同步延迟 ~550–950ms（约 1.5 步/秒），落在 08 票预算内。

**实测发现（已处理）**
- SwiftShader 下偶发渲染撕裂帧（文字重影）→ OCR 判 uncertain，屏障降级通过，不误报 fault。
- 极个别按键事件延迟可达数秒（游戏输入缓冲队列化，非丢失）→ 屏障按"超时重试等待一次、不重发按键"处理；本次 15 步零 fault。

**残余风险**
- `detect_dialog` 的有对话框正样本未实测（需走到楼梯）；当前保守阈值偏向"无对话框"=安全 no-op，已记 `dialog_seen` 审计。
- GAMEOVER 整局流程未实测（冒烟未死亡）；`detect_phase` 的 GAMEOVER 分支靠 HUD 缺失判定，实现期需一次真实死亡验证。
- 奖励恒 0（06 票接线）；`frame_shape` 灰度可辨识度待 08 票人工门禁。
