Labels: wayfinder:research
Type: research
Status: resolved
Blocked by: 04, 05, 06
Mode: AFK

## Question

每个游戏的轻量适配脚本对公共框架暴露什么最小接口？

基于已定观测、动作与奖励契约，定型一份语言无歧义的 Python 接口规格：输入输出、数据类型、状态归属、调用顺序、异常语义，以及启动、重置、清理的责任边界。

明确公共框架负责哪些能力，per-game 脚本负责哪些能力；说明其如何映射 Gymnasium 的 `reset` / `step` 返回值，并接入现有环境注册表。若所选游戏没有可靠重置路径，应暴露阻塞而非隐去问题。

交付接口表与文字时序，不编写模块、函数体或适配脚本。

## Answer

**决策：框架 `BrowserGameEnv(gymnasium.Env)` + per-game `GameAdapter` 协议对象。** 否决"适配器直接继承 Env"（浏览器生命周期无法复用）与"框架做 OCR"（HUD 语义是 per-game 知识，且 06 防泄漏要求 OCR 数值只走奖励通道）。

**适配器最小接口（20 项，详见研究笔记 §3）：** 身份与空间（`name`、`Discrete(10)` action_space、`Box uint8 HWC` observation_space、`frame_shape` 契约常量）；启动声明（`launch_url`、`canvas_selector`、`required_files`、`webgl_required`）；`reset_keys()` / `reset_reward_state()` / `seed_baselines(first)` / `smoke_probe_keys()`；动作翻译 `action_to_keys()`（纯静态查表）+ `needs_dialog_check()` + `dialog_suffix()` + `detect_dialog()`（05 授权的唯一状态相关分支）；`detect_phase()`（TITLE/DUNGEON/GAMEOVER）；`read_hud()`（允许 uncertain）；`on_frame(prev,cur)` **原子**返回 `{reward, terminated, truncated, reason, diag}`（合并奖励与终局判定，消除终局锁存的顺序 hazard）；可选 `close()`。

**状态归属：** 适配器拥有奖励基线/终局锁存/停滞计数/OCR 失败计数；框架拥有浏览器/上一帧/prev 透传；跨边界只走方法参数与返回值；OCR 数值永不进观测。

**责任边界：** 框架 = 浏览器生命周期、按键注入（<50ms、无修饰键、try/finally 保 keyup）、回合同步、截图、Gymnasium 元组装配、VecEnv 兼容；脚本 = 按键翻译表、奖励计算、回合判定信号提取（`read_hud`/`on_frame`/`detect_phase`）。

**关键时序修正（红队后）：** step 完成屏障四选一（TurnCount+1 / Depth 变化 / GAMEOVER / 双帧相同+250ms）且在"满足条件的截图"上判定，等待循环内同时检查终局（致死动作直切结算屏不再误判超时）；超时只重试等待不重发按键；reset 有界轮询 DUNGEON + 重建 context 重试一次后才判致命；`seed_baselines` 显式提交初始基线（uncertain 重拍 ≤3 次）；`truncated_kind` 区分 budget/stagnation/fault；`_episode_over` 守卫终局后 step。

**Gymnasium 映射：** `reset(*, seed=None, options=None)` 调 `super().reset(seed=seed)`（游戏不可 seed，`info["game_seedable"]=False`）；非法 action 抛 `ValueError`；terminated/truncated 互斥；info 固定键（phase/turn/depth/hud_certain/reward_breakdown/end_reason/truncated_kind/obs_stale/dialog_seen/sync_latency_ms/adapter）。`ENV_REGISTRY["ruggrogue-v1"] = lambda: BrowserGameEnv(adapter=make_adapter(), viewport=(1280,800))`，工厂保证 VecEnv 实例隔离。

**"脚本输出动作"语义：** 脚本只做静态翻译，不选动作；唯一状态分支是 05 授权的下楼对话框握手（句法级检测、固定后缀、记 `dialog_seen` 审计）；标题/结算屏 Enter 走框架 reset，不进动作空间。

**暴露的阻塞（未隐去）：** B1 自托管缺 `ruggrogue.wasm`/`deps/ruggrogue.data` → `required_files` 门禁硬阻塞；B2 OCR 永不 certain → 启动冒烟硬阻塞；B3 TurnCount 探针不前进 → 硬阻塞；B4 headless WebGL 探测失败 → 硬阻塞（04 降级路径）；已接受局限：游戏不可 seed、`frame_shape` 数值待实现期实测。

**红队：** llmapi gpt-6-astra 提出 14 项（4 严重/6 高/4 中），全部采纳或部分采纳，已回写规格（笔记 §11）。

详细接口表、时序、异常矩阵、否决备选：`.scratch/wayfinding/research/07-per-game-interface-notes.md`
