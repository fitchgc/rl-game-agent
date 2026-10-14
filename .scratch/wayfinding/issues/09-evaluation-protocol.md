Labels: wayfinder:research
Type: research
Status: resolved
Blocked by: 08
Mode: AFK

## Question

采用什么评估协议判断首版代理达标，并区分策略失败与环境链路失败？

确定评估回合数、随机种子或初始条件集合、策略是否确定性执行、评估频率、主指标与辅助指标，以及至少一个可执行的低成本基线。

明确训练与评估的隔离方式、达标阈值的依据、异常回合如何记录和计入结果，并规定截图、控制或重置故障如何单独报告。不得仅以训练奖励上升宣告成功。

产出 `evaluate.py` 所需的决策规格与验收清单。完成时核对地图 Destination 的四项条件；仍有影响实现的未决事项则记录为阻塞，不以"后续再定"宣告路线探明。

## Answer

**决策：评估协议 = 原生游戏表现选型 + 链路健康独立报告，二者永不混淆。** 详细笔记：`.scratch/wayfinding/research/09-evaluation-protocol-notes.md`（llmapi gpt-6-astra 起草、已按 07 号票工厂接口校准）。

### 调度与执行
- 每 checkpoint（10k steps，08 号票）评估 **10 个 attempts**（`n_eval_episodes=10`，SB3 惯例）；fault 消耗名额，**不补跑**。
- 统一 `deterministic=True`（Discrete(10) 下为最高概率动作；与 SB3 EvalCallback 默认一致）。
- 单次评估墙钟上限 30 分钟（初值，待 08 的 10k 步端到端校准）；超限则该点不可选型；若 10 attempts 稳定超限则开跑前降级为 n=5 并标记 `eval_mode="degraded"`，不得事后追认。

### 初始条件（游戏不可 seed）
- `game_seedable=False`（07）：用固定 attempts 数 + 相同版本/viewport/截断阈值/统计口径替代；指标报告 mean±std、median、min/max。
- console 捕获的 game seed 仅记 `observed_game_seed` 用于追溯，不注入、不筛选；`--seed` 仅控制基线 RNG。

### 指标
- **主指标**：`mean_max_depth`（有效回合最大确认下潜深度均值）；次要：`mean_survival_turns`；`win_rate` 仅记录不设门（v1 预期≈0）。
- **辅助/链路指标**（永不参与选型排序）：shaped 回报均值（诊断用）、`fault_rate`、`obs_stale_rate`、`ocr_uncertain_rate`、`sync_latency_ms` p50/p95。`hud_certain=False`/`obs_stale=True` 的读数不得推进原生指标。

### 基线（走同一 harness）
- `uniform random`（Discrete(10) 均匀采样）与 `wait-only`（恒动作 8，检验停滞检测与饥饿计时器），`--baseline {random,wait}`；人类试玩为可选 stretch，不混入样本集。

### 训练/评估隔离
- 评估 env = `ENV_REGISTRY["ruggrogue-v1"]()` 全新实例（07 工厂保证隔离）：独立浏览器 context/页面/适配器/缓存；包裹方式与训练一致（含 VecTransposeImage）；版本、viewport、适配器契约相同，仅策略不同。**严禁复用训练 env 做评估**（SB3 官方警告：会同时污染双方）。

### 模型选择
- 按 `mean_max_depth` 排序，tie-break 依次为 `mean_survival_turns`、`fault_rate` 更低、全同则保留较早 checkpoint；同时保留 `final_model.zip`。
- **不以训练 episodic reward 选型**；训练期用自定义 callback 把 `eval/mean_max_depth` 等写入 TensorBoard（标准 EvalCallback 只记 reward，需扩展）。
- 从多 checkpoint 选出 best 后，用新回合集合对 best 与 random 做独立确认，削减选型偏差。

### 达标阈值（初始验收目标，未实测）
- 模型 vs random：平均最大深度 95% CI（bootstrap 10k 次）不重叠且模型下界高于 random 上界。
- `fault_rate < 5%`；`obs_stale_rate < 10%`。n=10 时 fault<5% 实为零 fault 要求——零 fault 不证明长期故障率达标。

### 异常回合（策略失败 vs 链路失败）
- `truncated_kind=fault`（OCR 连续失败 20 步、TurnCount 超时、截图/解码故障）：**整回合剔除出策略指标**，计入 fault 率并记 `end_reason`。
- 单次评估 `fault_attempts > 2` → 标记 **LINK-RED**，该点不可选型（退出码 2）。
- `stagnation`/`budget` 截断、可信死亡：**计入策略指标**（停滞=策略失败，长存活=好，死亡=策略结果）。
- `obs_stale` 回合计入但标记，陈旧读数不更新指标；链路错误永不被当作死亡/零深度扣分。

### evaluate.py 决策规格
- CLI：`--model`（必需；基线模式传 `unused` 占位）、`--episodes`（默认 10）、`--deterministic`（默认开）、`--baseline {none,random,wait}`、`--out`（默认 `artifacts/eval/<run_id>`）、`--max-eval-minutes`（默认 30）、`--seed`（默认 0）。
- 自定义循环采集全部 info 键（phase/turn/depth/hud_certain/reward_breakdown/end_reason/truncated_kind/obs_stale/dialog_seen/sync_latency_ms），落盘 `episodes.jsonl` + `summary.json`，终端打印主指标/链路率/延迟/健康状态表；退出码 0=正常 / 2=LINK-RED / 1=错误（错误时仍保留部分结果）。
- 实现验收清单见笔记 §11（18 项：独立 env、fault 剔除规则测试、depth 排序 tie-break 测试、退出码覆盖等）。

### Destination 四项核对
1. 游戏选定 ✓ —— 03：ruggrogue v1.0.1（MIT，回合制，game_seedable=False）。
2. 画面方案 ✓ —— 04：Playwright canvas 截图 + TurnCount 同步；84×84 灰度（08）。
3. 适配接口 ✓ —— 07：BrowserGameEnv + GameAdapter，info 固定键，truncated_kind 三分类；05/06：Discrete(10)、OCR 差分奖励契约。
4. 算法/训练/评估 ✓ —— 08：PPO+CnnPolicy、400k steps、10k checkpoint、CPU 单 env、中止规则；本票补齐评估与选型协议。
- **已知实现期硬门禁**（已归属 prior 票据，非本轮未决）：B1 WASM 缺失、B2 OCR 冒烟、B3 TurnCount 探针、B4 WebGL 门禁（07）；H1–H7 与 10k 步端到端校准（08）。地图路线探明完成，无新增阻塞。
