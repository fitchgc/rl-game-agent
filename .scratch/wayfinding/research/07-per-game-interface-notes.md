# 07-per-game-interface 研究笔记（草稿，待红队校准）

## 1. 研究依据（primary sources）

### Gymnasium Env API
- `reset(seed=None, options=None) -> tuple[ObsType, dict]`；`step(action) -> tuple[ObsType, SupportsFloat, bool, bool, dict]` 即 `(obs, reward, terminated, truncated, info)`。
- `terminated` = MDP 自然结束（胜/死）；`truncated` = 外部截断（步数/时间上限）。算法侧：terminated 不 bootstrap，truncated 需要 bootstrap 估计剩余价值。来源：Gymnasium migration guide（v0.21→v0.26+ `done` 拆分）与 farama.org terminated/truncated 说明。
- 来源：https://github.com/ccslab1/group-project/blob/HEAD/Gymnasium/docs/introduction/migration_guide.md

### SB3 自定义环境要求
- 必须继承 `gymnasium.Env`，实现 `__init__`（定义 action_space/observation_space）、`reset(seed, options)`、`step`、`close()`；`render()` 可选。
- 图像观测须为 `np.uint8` [0,255]；SB3 自动除以 255 归一化；`Discrete`/`MultiDiscrete` 要求 `start=0`（本项目 Discrete(10) start=0 ✓）。
- 用 `stable_baselines3.common.env_checker.check_env` 校验；训练时包一层 `DummyVecEnv`/`SubprocVecEnv`（SB3 侧处理 auto-reset，`terminal_observation` 进 info）。
- 来源：SB3 custom env 官方文档模式（多份 skill 引用一致，`stable-baselines3.readthedocs.io` guide/custom_env）。

### Playwright Python
- `page.keyboard.press('Enter')` 发送单键；`locator('canvas').screenshot()` 返回元素裁剪后的像素 buffer；`page.wait_for_function('...')` 等待 JS 条件；`browser.new_context()` 新建隔离上下文。
- 来源：Playwright API 文档（class-locator.md）与 playwright-python skill。

## 2. 架构决策：框架 Env + 适配器协议（非"适配器即 Env"）

- **公共框架**提供通用类 `BrowserGameEnv(gymnasium.Env)`：拥有浏览器/上下文/页面生命周期、截图、按键注入、回合同步等待、Gymnasium 元组装配。
- **per-game 脚本**提供一个 `GameAdapter` 协议对象：只声明本游戏知识（按键翻译表、奖励计算、回合判定信号提取、HUD 版式）。
- 否决"适配器直接继承 Env"：每个游戏会重复浏览器生命周期管理，框架无法复用 Playwright 基建；且 05/06 的契约（同步、OCR）天然是框架能力。

## 3. 接口表（最小）

`frame` 统指 `np.ndarray`，`uint8`，HWC，RGB（Playwright PNG 解码）。

| # | 成员 | 种类 | 签名 / 类型 | 说明 |
|---|------|------|-------------|------|
| 1 | `name` | 数据 | `str` | 如 `"ruggrogue-v1"`，进 info 与日志 |
| 2 | `action_space` | 数据 | `gymnasium.spaces.Discrete(10)`，`start=0` | 05 契约；SB3 原生支持 |
| 3 | `observation_space` | 数据 | `gymnasium.spaces.Box(0,255,shape=(h,w,3),dtype=np.uint8)` | 原始截图空间；`(h,w)` 取自 `frame_shape`；84x84 灰度等预处理归 08 |
| 4 | `frame_shape` | 数据 | `tuple[int,int]` = (h, w) | 适配器声明的画布像素尺寸契约常量；启动实测不符 → `AdapterFatalError` |
| 5 | `launch_url` | 数据 | `str` | 自托管静态文件 URL（`file://` 或本地 http） |
| 6 | `canvas_selector` | 数据 | `str` | 如 `"canvas"`；框架校验唯一/可见/尺寸非零 |
| 7 | `required_files` | 数据 | `list[str]` | 如 `["ruggrogue.wasm","deps/ruggrogue.data"]`；缺失 → 启动硬阻塞（B1） |
| 8 | `webgl_required` | 数据 | `bool` | True；`page.evaluate` webgl2 探测失败 → 硬阻塞（04/B4） |
| 9 | `reset_keys()` | 方法 | `-> list[str]` | 纯数据：新开一局的按键序列，如 `["Enter","Enter"]`（标题→开局） |
| 10 | `reset_reward_state()` | 方法 | `-> None` | 清空适配器奖励状态：maxDepth/prevLevel/prevXP/prevHP 基线、终局锁存、停滞计数、OCR 失败计数 |
| 11 | `smoke_probe_keys()` | 方法 | `-> list[str]` | 启动冒烟键，如 `["k"]`；框架注入后期望 TurnCount 前进，否则硬阻塞（B3） |
| 12 | `action_to_keys(a)` | 方法 | `(a: int) -> list[str]` | **纯静态查表**，不得读任何游戏状态。0–7→vi 单键，8→`"."`，9→`["Enter"]` |
| 13 | `needs_dialog_check(a)` | 方法 | `(a: int) -> bool` | 仅 9 返回 True（05 授权的 UI 握手例外） |
| 14 | `dialog_suffix(seen)` | 方法 | `(seen: bool) -> list[str]` | `seen` 为 True → `["h","Enter"]`，否则 `[]`；`seen` 的唯一来源是框架调用 `detect_dialog` 的返回值 |
| 15 | `detect_phase(frame)` | 方法 | `(frame) -> Phase` | `Phase = Literal["TITLE","DUNGEON","GAMEOVER"]`（06 状态机）；供框架校验 reset 落点与终局检测 |
| 16 | `detect_dialog(frame)` | 方法 | `(frame) -> bool` | 仅检测"下楼确认框出现与否"（句法级 UI 状态，不读游戏语义）；05 例外的唯一状态读取点 |
| 17 | `read_hud(frame)` | 方法 | `(frame) -> HudReading` | OCR；允许 `certain=False`（06 单步失败语义） |
| 18 | `on_frame(prev,cur)` | 方法 | `(prev: HudReading, cur: HudReading) -> FrameOutcome` | **原子**奖励+终局判定（见 §5）；合并计算避免终局锁存与奖励的顺序 hazard |
| 19 | `close()` | 方法 | `-> None`（可选） | 适配器自有资源清理（如 OCR 引擎）；框架 `close()` 时调用 |
| 20 | `seed_baselines(first)` | 方法 | `(first: HudReading) -> None` | 显式提交初始奖励基线；`uncertain` 时框架重拍（≤3 次）仍失败 → `AdapterFatalError`；基线提交后首步即正常计分，**不补算**未知区间增量 |

`HudReading`：`{certain: bool, turn: int|None, depth: int|None, level: int|None, xp: int|None, hp: int|None, max_hp: int|None}`——全字段可空，`certain=False` 时框架沿用旧值（06）。

`FrameOutcome`：`{reward: float, terminated: bool, truncated: bool, reason: str|None, diag: dict}`——`terminated` 与 `truncated` 互斥，冲突时 terminated 优先；`diag` 进 info（reward_breakdown 等）。

## 4. 状态归属

- **适配器拥有**：奖励基线（maxDepth/prevLevel/prevXP/prevHP）、终局锁存、停滞计数、OCR 连续失败计数、回合预算计数。框架永不直接读写。
- **框架拥有**：browser/context/page、viewport、上一帧、`prev: HudReading`（在两次 `on_frame` 之间传递）、注入时序、info 组装。
- **禁区**：OCR 结构化数值永不拼入观测（06 防泄漏）；适配器永不触碰 browser/page；框架永不解释 HUD 语义（只透传 `read_hud` 结果）。
- 跨边界数据只走方法参数/返回值；无共享可变状态。

## 5. 调用顺序（文字时序）

### reset(seed, options) → (obs, info)
1. SB3（经 VecEnv）调用 `env.reset(seed)`；框架记录 seed（`info["game_seedable"]=False`，ruggrogue web 无种子控制——已接受的局限）。
2. 框架关闭旧 context → 新建 context（03：全新 context，无存档）→ `goto(launch_url)`。
3. 启动门禁：`required_files` 存在性、`page.evaluate` webgl2 探测、canvas 唯一/可见/尺寸非零、`frame_shape` 一致性；任一失败 → `AdapterFatalError` 硬阻塞（B1/B4）。
4. 冒烟：注入 `smoke_probe_keys()` 后 TurnCount 前进 → 否则硬阻塞（B3）；HUD 首帧 `read_hud` 须 `certain` → 否则硬阻塞（B2）。
5. 注入 `reset_keys()` 后**有界轮询** `detect_phase` 确认 `DUNGEON`（浏览器加载/标题过渡/新局生成均可异步，短暂 TITLE 不算失败）；超时 → 重建 context **重做一次**完整 reset；仍失败 → `AdapterFatalError`（重置路径不可靠必须暴露，但不因加载抖动误杀）。
6. `adapter.reset_reward_state()`；截图 → `read_hud` → `adapter.seed_baselines(first)`（`prev=cur`）；`uncertain` 则重拍 ≤3 次，仍失败 → `AdapterFatalError`（开局不能是瞎的，与 B2 一致）。
7. 返回 `(obs=frame, info={phase:"DUNGEON", adapter:name, seed, game_seedable:False})`。
8. 框架 Env 签名（Gymnasium 合规）：`reset(self, *, seed=None, options=None) -> tuple[np.ndarray, dict]`，内部调用 `super().reset(seed=seed)`；`step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]`；`metadata={"render_modes":["rgb_array"]}`；`render()` 返回最近帧。

### step(a) → (obs, reward, terminated, truncated, info)
1. 框架校验 `0 <= a < 10`，非法 → `ValueError`（调用方 bug，不静默裁剪）。
2. `keys = adapter.action_to_keys(a)`（纯查表）；框架经 Playwright `keyboard.press` 逐键注入：即按即放、单键保持 `<50ms`、down 必配 up；Shift/Ctrl/Alt/Esc 永不注入（05）。
3. 若 `adapter.needs_dialog_check(a)`：300ms 内 `detect_dialog` 轮询 → `suffix = adapter.dialog_suffix(seen)` 注入；`info["dialog_seen"]=seen`（05 审计要求）；超时按 `seen=False` 安全结束。
4. 回合同步（**完成屏障**，在轮询新截图上判定，满足条件的帧即本步观测帧，杜绝 HUD/地图/奖励错帧）——任一即完成：
   a) TurnCount +1；b) Depth 变化；c) `phase==GAMEOVER`（致死动作可能直接切结算屏，**必须**在等待循环内同时检查终局，确认即停等走终局判定，不可误判为超时截断）；d) 连续两帧像素相同 + 250ms（撞墙等"输入已处理但 0 回合"的合法轨迹，不得误截断）。
   超时 → **只重试等待/读取一次，不重发按键**（非幂等输入重发会多走一步）；仍超时 → `truncated=True, reason="sync-timeout", reward=0.0`，obs 取最近有效帧并标 `obs_stale=True`，返回。
   跨楼层：Depth 变化时适配器重定本层基线（prevLevel/prevXP/prevHP 从 cur 重置），`maxDepth` 棘轮保留（06 公式天然兼容）。
5. 截图 → PNG→np RGB → 尺寸校验（≠`frame_shape` → `AdapterFatalError`）；**永不用旧帧冒充**。
6. `phase=detect_phase(frame)`；`cur=read_hud(frame)`；`outcome=adapter.on_frame(prev, cur)`；`prev←cur`。`uncertain` 读数**不得**更新基线；停滞计数只计 certain 无进展回合，与 OCR 失败计数彻底分离（06 可信度门控的接口层重申）。
7. 组装：`obs=frame`；`reward=outcome.reward`；`terminated/truncated=outcome`（互斥，terminated 优先）；`info={phase, turn, depth, hud_certain, reward_breakdown: outcome.diag, end_reason: outcome.reason, truncated_kind, obs_stale, dialog_seen, sync_latency_ms, adapter}`，其中 `truncated_kind ∈ {"budget","stagnation","fault", None}`（fault 类截断的 bootstrap 为已知近似，由"连续 3 局 capture-failure 升级 raise"封顶损害；v1 不做 transition 丢弃机制）。
8. 终局/截断后框架原子关闭本局（`_episode_over` 守卫；终局/截断后继续 `step()` 按标准 Gymnasium 语义抛错，防适配器锁存与框架路径冲突）；不自动建新局；下一次 `reset()` 走全新 context（VecEnv auto-reset 会调用它）。

### close()
框架关闭 context→browser；调用适配器 `close()`（若定义）。

## 6. 异常语义

| 情况 | 类型 | 处理 |
|------|------|------|
| 启动门禁任一失败（文件缺失/webgl/canvas/冒烟/OCR 首帧） | `AdapterFatalError` | 硬阻塞，不开训（B1–B4） |
| reset 后 phase 非 DUNGEON（超时） | `AdapterFatalError` | 重置路径不可靠，暴露 |
| 单步 OCR 失败 | in-band（`certain=False`） | 沿用旧值；连续 20 步 → 适配器经 `on_frame` 判 truncated（06） |
| 回合同步超时 | 框架内 `SyncTimeout` | 重试等待一次 → 仍超时则 truncated(reason="sync-timeout")（04） |
| 截图/解码失败 | in-band | 重试一次 → 仍失败则本局 truncated(reason="capture-failure")；框架统计连续 ≥3 局则升级为 raise（防静默中毒） |
| 非法 action（越界/非 int） | `ValueError` | 调用方 bug，直接抛 |
| 浏览器崩溃/canvas 永久脱离 | `AdapterFatalError` | 不可恢复，抛给训练循环 |
| 按键注入中浏览器异常 | 分类处理 | `try/finally` 保证 keyup 释放（防按键卡住）；(a) keydown 前异常 → 安全重试一次；(b) keydown 后结果未知 → `truncated(reason="input-unknown", truncated_kind="fault")`；(c) page/context 死亡 → `AdapterFatalError` |
| 终局/截断后继续 `step()` | 框架 `_episode_over` 守卫抛错 | 标准 Gymnasium 语义；任何结束路径原子关闭本局，`on_frame` 不再被调用，适配器锁存保持一致 |
| 连续截图失败计数 | 框架实例属性 | **不**归适配器（`reset_reward_state` 不清零它，避免永远无法升级）；成功局清零；`≥3` 局连续 → 升级为 raise |

`AdapterFatalError` 仅适配器/框架在"不可恢复"时抛出；可恢复的全部走 in-band（uncertain/truncated+reason），保证训练循环可观测、可审计。

## 7. ENV_REGISTRY 接入

- per-game 模块：`src/rl_game_agent/envs/ruggrogue_adapter.py` 暴露工厂 `make_adapter() -> GameAdapter`（工厂而非单例：VecEnv 多实例状态隔离）。
- 框架类：`src/rl_game_agent/envs/browser_env.py` 的 `BrowserGameEnv(gymnasium.Env)`（实现期命名，08/实现票可调整）。
- 注册（`envs/__init__.py`）：`ENV_REGISTRY["ruggrogue-v1"] = lambda: BrowserGameEnv(adapter=make_adapter(), viewport=(1280, 800))`。
- `train.py` 按 `config["env"]` 查注册表（已有 stub 待接线）；`check_env` 为实现期验收项（05 已列）。
- VecEnv 说明：多实例 = 多 Chromium，CPU-only VM 上资源沉重；`n_envs` 取值归 08，本接口保证实例间无共享状态即可支持。

## 8. "脚本输出动作"语义（重申 05 裁决）

- `action_to_keys` 是纯静态表；脚本**不**选择/掩码/替换/重排策略动作。
- 唯一状态相关分支是 05 明确授权的 UI 握手：`detect_dialog`（句法级）→ `dialog_suffix`（固定后缀），且每次记 `dialog_seen` 供审计；不得推广到其他动作。
- 标题屏/结算屏的 `Enter` 由框架 reset 流程驱动，不进策略动作空间。
- 适配器禁读墙/怪/楼梯/血量等游戏语义来影响动作（05 禁做清单）。

## 9. 暴露的阻塞（不隐去）

- **B1**：自托管静态包缺 `ruggrogue.wasm` / `deps/ruggrogue.data`（03 残余风险）→ `required_files` 启动门禁硬阻塞。归属：实现期验证。
- **B2**：OCR 链路（Tesseract/引擎缺失或 HUD 永不 certain）→ 启动冒烟硬阻塞；运行期 20 步连续失败 truncated（06）。归属：实现期。
- **B3**：TurnCount 同步（按键到不了游戏）→ 冒烟探针硬阻塞；运行期超时 truncated（04）。归属：实现期实测阈值。
- **B4**：headless WebGL 探测失败 → 硬阻塞（04 已裁决），降级路径 Xvfb+mss 仅当探测失败时启用。
- **已接受的非阻塞局限**：游戏不可 seed（`info["game_seedable"]=False`）；`frame_shape` 具体数值待实现期实测填入（04 只定了 viewport 1280x800，未测 canvas 像素尺寸）。

## 11. 红队审查记录（llmapi gpt-6-astra，2026-10-14）

| # | 严重度 | 发现 | 处置 |
|---|--------|------|------|
| 1 | 严重 | 等待 TurnCount 时若动作致死切 GAMEOVER，会被误判为超时截断 | ✅ 采纳：等待循环内同时检查终局，确认即停等走 `terminated`（§5-4c） |
| 2 | 严重 | 动作 9 的对话框握手在 step 流程中无调用位置，有等待死锁风险 | ✅ 已覆盖并加固：握手在注入后、同步等待前执行（§5-3），且动作 9 的完成屏障含 Depth 变化/双帧静止兜底 |
| 3 | 严重 | TurnCount 变化作必要条件会误截断撞墙等 0 回合合法轨迹 | ✅ 采纳：完成屏障四选一（TurnCount+1 / Depth 变化 / GAMEOVER / 双帧相同+250ms），区分"已处理未推进"与"无响应" |
| 4 | 严重 | "超时重试一次"未定义是否重发按键，非幂等输入可能执行两次 | ✅ 采纳：只重试等待/读取，永不重发按键（04 原决议的重申与加固） |
| 5 | 高 | TurnCount 先更新、画面后提交导致错帧；跨楼层计数器基线问题 | ✅ 采纳：屏障在轮询新截图上判定、满足帧即观测帧；跨楼层重定本层基线，maxDepth 棘轮保留 |
| 6 | 高 | 截图失败截断时无有效观测，旧帧冒充污染 bootstrap | ✅ 采纳：`obs_stale` 标记 + 连续 3 局升级 raise；单局为已知近似 |
| 7 | 高 | 所有可恢复故障统一 truncated，fault 类不满足 bootstrap 前提 | ✅ 部分采纳：`truncated_kind` 区分 budget/stagnation/fault 并文档化近似；v1 不做 transition 丢弃（需定制 VecEnv，超本票范围） |
| 8 | 高 | 终局锁存归属与框架提前返回路径冲突 | ✅ 采纳：框架 `_episode_over` 原子关闭本局，终局/截断后 step 抛错 |
| 9 | 高 | reset 缺 Gymnasium 签名与种子语义 | ✅ 采纳：补 `reset(*, seed=None, options=None)`、`super().reset(seed=seed)`、`metadata`/`render()`（§5-8） |
| 10 | 高 | reset 以"按键后立刻 DUNGEON"判致命，加载异步会误杀 | ✅ 采纳：有界轮询 + 重建 context 重试一次后才判致命 |
| 11 | 中 | 初始基线提交协议不完整，uncertain 首帧易漏算/错算 | ✅ 采纳：新增 `seed_baselines(first)`，uncertain 重拍 ≤3 次仍失败则致命，不补算未知区间 |
| 12 | 中 | uncertain 时基线/停滞计数更新未定义 | ✅ 采纳：uncertain 永不更新基线；停滞计数与 OCR 失败计数分离（06 门控的接口层重申） |
| 13 | 中 | 按键注入与等待中的浏览器异常映射不完整，按键可能卡住 | ✅ 采纳：try/finally 保 keyup，三分类恢复（§6） |
| 14 | 中 | "连续 3 局截图失败"计数器归属与清零规则缺失 | ✅ 采纳：框架实例持有，成功局清零，`reset_reward_state` 不碰 |

## 10. 否决的备选

- **适配器直接 subclass `gym.Env`**：否决。浏览器生命周期在每游戏重复，且 04/05 的同步与注入逻辑无法复用。
- **框架做 OCR、适配器只给版式**：否决。HUD 版式/字段语义是 per-game 知识，OCR 与奖励同属适配器内聚单元；且 06 防泄漏要求 OCR 数值只走奖励通道，放在适配器内最易审计。
- **`compute_reward` 与 `check_end` 拆分为两个方法**：否决。终局锁存（06：终局奖励只发一次）与奖励计算共享状态，拆分会引入调用顺序 hazard；`on_frame` 原子返回消除该类 bug。
- **info 塞入 HUD 结构化数值"方便调试"**：否决。06 防泄漏——info 可被 SB3 记录/回调读取，数值只允许出现在 `reward_breakdown`（已是标量聚合）与 `diag`，不得出现逐字段原始 OCR。
