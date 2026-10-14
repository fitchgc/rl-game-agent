Labels: wayfinder:map

## Destination

为 `rl-game-agent` 探明一套"截图观测 + per-game 适配脚本"的 Stable-Baselines3 自动玩游戏框架路线。以下决策全部落定后，可直接进入实现：

1. 首个目标游戏确定，运行平台、启动与回合重置条件明确。
2. 画面获取方案确定，包括截图来源、窗口定位、采样节奏与观测预处理。
3. 每个游戏的适配脚本接口定型，覆盖奖励计算、策略动作到游戏输入的转换，以及回合生命周期。
4. SB3 算法、训练配置策略与评估协议确定，并明确如何接入现有项目。

本轮只产出决策、接口规格与验收标准，不编写实现、不运行训练。

## Notes

- **领域**：视觉强化学习、桌面/浏览器游戏自动化、Gymnasium 环境设计、SB3 训练与评估。
- **项目现状**：
  - Python 项目，`pyproject` 已依赖 `stable-baselines3[extra]`、`gymnasium`。
  - 已有 `src/rl_game_agent/train.py`、`evaluate.py`、`envs/` 环境注册表。
  - 已有 `configs/ppo_default.yaml`；这不代表最终必须选择 PPO。
- **每 session 应查阅的 skills**：
  - wayfinding / breadth-first planning：控制范围、维护地图和阻塞关系。
  - 当前议题对应的领域 skill：SB3/Gymnasium、截图与输入自动化、RL 奖励设计或实验评估。
  - 涉及项目接入时，查阅 Python 项目结构与配置管理 skill。
  - 以上为能力类别；以当前环境实际提供的 skill 为准，不假设同名文件存在。缺失时记录，并改查官方文档。
- **llmapi 路由偏好**：`simple → gpt-6.1-sol`；`complex → gpt-6-astra`。
  - 简单资料归纳、约束核对、tracker 更新走 `simple`。
  - 跨方案权衡、奖励与时序设计、接口和算法决策走 `complex`。
- **规划方式**：先横向消除游戏、运行条件、截图、动作、奖励等主要雾区，再收敛接口、算法与评估。当前可并行 frontier 为 `01`、`02`。
- **票据约定**：
  - `research` 标记 `AFK`，可独立查阅资料完成。
  - `grilling` / `prototype` 标记 `HITL`，需要用户参与。
  - 本批不设 prototype，避免越过"只做决策"的边界。
  - 每票记录一个决策、依据、被排除的替代方案及残余风险；完成后回写本地图。
  - AFK 票遇到必须由用户确认的事实时，不自行假设，记录阻塞并提出最小补充问题。
- **接口语义提醒**："脚本输出动作"须明确是把 SB3 策略动作转换为游戏输入，还是由脚本自主选动作。后者不能默认替代正在学习的策略。

## Decisions so far

- 采用现有 Python、Gymnasium、SB3 项目作为基础，不另起训练框架。
- 使用游戏画面作为策略观测；截图是主要候选，具体获取方式尚未确定。
- 每个游戏提供轻量适配脚本，负责奖励与动作相关适配；具体协议尚未定型。
- 使用本地 Markdown tracker：
  - 地图：`.scratch/wayfinding/map.md`
  - 子票：`.scratch/wayfinding/issues/NN-<slug>.md`
- 此阶段只做路线决策，不做实现；尚未选定具体游戏、截图后端或算法。
- [首游候选短名单（01-game-shortlist，已 resolved）](.scratch/wayfinding/issues/01-game-shortlist.md)：按 02 号票约束（仅网页、roguelike、回合制优先、无头+Xvfb、纯 CPU、几天预算）排序为 ① DCSS 自建 webtiles Sprint（morgue 局末奖励，复杂度最高）→ ② ruggrogue web（MIT、可本地静态托管、最轻）→ ③ Desktop Dungeons HTML5（第三方转换版，备选）；上一轮 Atari/Dino/ViZDoom 因不符合新约束淘汰；三者均待本机闭环验证，待用户确认复杂度/简单度/第三方版接受度及 Docker+浏览器安装意愿。
- [运行与资源边界已确认](.scratch/wayfinding/issues/02-operating-envelope.md)：VM 无头 Linux + Xvfb，无 GPU（纯 CPU），墙钟预算几天；第一阶段只做网页游戏（浏览器自动化可接受），类型先用 roguelike。
- [首个目标游戏已选定：ruggrogue v1.0.1（03-first-game，已 resolved）](.scratch/wayfinding/issues/03-first-game.md)：tung/ruggrogue，MIT，回合制纯键盘；版本固定 v1.0.1（tag 9f7ffd5c）；运行模式为自托管静态文件 + Playwright/Chromium + Xvfb；重置流程干净（死亡→Enter→标题→Enter，全新 context 无存档）；奖励信号来自 HUD 与结算屏（OCR 友好）。DCSS 因用户否决 Docker 淘汰，DD 因第三方旧转换风险淘汰。残余风险：自托管缺 `ruggrogue.wasm`+`deps/ruggrogue.data`（04/实现期验证）、输入延迟与单局吞吐待测。
- [动作契约已定型：Discrete(10)（05-action-contract，已 resolved）](.scratch/wayfinding/issues/05-action-contract.md)：0–7=vi 键八向移动，8=`.` 等待，9=`[Enter,h,Enter]` 下楼宏；无组合键，Shift/Ctrl/Alt/Esc 永不注入（防 auto_run/rest 劫持）；1 step=1 逻辑动作，同步条件为 TurnCount+1 / Depth 变化 / 双帧相同+250ms；策略是唯一决策者，脚本只做静态翻译（UI 握手例外：仅允许检测下楼确认框出现与否以完成宏，有严格边界）；物品键与 action masking 延至 v2。
- [回报与回合判定契约已定（06-reward-contract，已 resolved）](.scratch/wayfinding/issues/06-reward-contract.md)：HUD OCR 差分 dense（深度棘轮 +1.0/升级 +0.5/xp +0.001/掉血 −0.01/步罚 −0.001）+ 结算屏终局（死亡 −1.0 / 胜利 +10.0）；terminated=真实胜死，truncated=预算（bootstrap）/停滞 −0.5/OCR 失败；OCR 两端 certain 才计分、可信度门、终局锁存；OCR 数值仅走奖励通道不进策略观测；llmapi 红队 10 类漏洞已封堵或缓解；权重阈值待实现期校准。
- [画面获取与观测方案已确定（04-visual-observation，已 resolved）](.scratch/wayfinding/issues/04-visual-observation.md)：主路径 Playwright Python 在 headless Chromium 中对 `canvas` 做元素截图（CDP 合成后像素，无需 X server；SwiftShader 软件 WebGL 由 Playwright 自动启用）；仅 headless WebGL 探测失败时降级为 Xvfb + mss 整桌面截图；`canvas.toDataURL` 因 `preserveDrawingBuffer=false` 默认行为否决。回合制简化：每 step = 按键 → 等 HUD `TurnCount` 变化 → 截图，无固定 FPS，不做帧堆叠；超时重试一次等待，再超时 `truncated=True` 中止；启动做 webgl2 门禁探测，失败硬阻塞。仍满足"以游戏画面为观测"（HUD 仅用于同步时机，不拼入观测）。残余风险：截图延迟、SwiftShader 渲染帧率、TurnCount 超时阈值均待实现期实测。
- [per-game 适配脚本接口已定型（07-per-game-interface，已 resolved）](.scratch/wayfinding/issues/07-per-game-interface.md)：框架 `BrowserGameEnv(gym.Env)` + 适配器 `GameAdapter` 协议（20 项：空间/启动声明/reset_keys/seed_baselines/静态动作查表+对话框握手/detect_phase/detect_dialog/read_hud/原子 on_frame）；适配器拥有奖励基线与终局锁存，框架拥有浏览器与注入时序，OCR 数值永不进观测；step 完成屏障四选一且等待循环内查终局（防死亡误判超时）；reset 有界轮询+重建重试；`ENV_REGISTRY["ruggrogue-v1"]` 经 `make_adapter()` 工厂接入；B1–B4（WASM 缺失/OCR 冒烟/TurnCount 探针/WebGL 门禁）全部硬阻塞暴露；llmapi 红队 14 项已采纳回写。

- [训练方案已确定：PPO 首选 + DQN 备选（08-training-plan，已 resolved）](.scratch/wayfinding/issues/08-training-plan.md)：PPO + CnnPolicy（NatureCNN）；灰度 84×84 uint8 HWC（env 侧）→ VecTransposeImage → CHW，SB3 内部 /255；n_steps=1024、ent_coef=0.01 起始（按监控动态调）、total_timesteps=400_000（红队修正：500k 在 2 步/秒下仅采样 69.4h，预算不闭合）；单 env 起步、50k 步后实测再定并行；检查点每 10k 步 + tensorboard 必开；seed 0（游戏不可 seed，跨 run 方差声明）；DQN 备选参数已具名（buffer 50k≈0.7GB，target 间隔 5k）；中止规则：fault 率/150k 步无学习信号/墙钟 72h/数值发散；墙钟耗尽只做安全停机不伪造奖励。实现期硬门禁：10k 步端到端吞吐校准 + 84×84 输入可辨识度人工抽查。gamma=0.99 的远期失效记为已知局限（v1 优化下潜/生存）。llmapi 红队 12 项已采纳或记录。

## Not yet specified

1. **首个游戏与运行边界**：平台、许可、输入控制权限、可重置性、训练预算是否满足要求。
2. **视觉观测链路**：截图来源、时序同步、延迟、裁剪缩放、帧堆叠及失焦/遮挡处理。
3. **游戏适配语义**：动作空间、按键持续时间、奖励信号、终止与重置，以及脚本和框架的责任边界。
4. **学习方案**：算法、策略网络、采样吞吐假设、训练预算与阶段性停止条件。
5. **评估标准**：独立评估条件、基线、指标、种子及失败判定，如何证明学到了策略而不是利用漏洞。

## Out of scope

- 编写环境、截图后端、游戏脚本、训练或评估代码。
- 实际安装部署、运行原型、采集数据或执行训练实验。
- 同时适配多个游戏、构建通用游戏插件市场或分布式训练平台。
- 绕过反作弊、规避访问限制，或在未获许可的在线对战环境自动操作。
