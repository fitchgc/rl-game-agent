# 评估协议研究笔记

## 1. 范围与已定配置

本笔记规定 `rl-game-agent` 的评估口径、模型选择、链路异常分类与 `evaluate.py` 实现契约，不重新讨论游戏、观测或算法选型。

| 项目 | 已定配置 |
|---|---|
| 游戏 | ruggrogue v1.0.1，回合制 roguelike，MIT |
| 算法 | stable-baselines3 PPO + `CnnPolicy` |
| 观测 | Playwright 截取 canvas，84×84 灰度图 |
| 动作 | `Discrete(10)`：0–7 八向移动，8 等待，9 下楼宏 |
| 奖励 | HUD OCR 差分 dense + 结算屏 sparse |
| 游戏随机性 | `game_seedable=False` |
| 训练规模 | `total_timesteps=400_000`，每 10,000 步保存 checkpoint |
| 运行环境 | 单 env 起步，纯 CPU，VM 无头 + Xvfb |
| 日志与预算 | TensorBoard；整体墙钟预算为几天 |

**核心原则：以原生游戏表现选模型，链路健康单独报告，不以训练 shaped reward 代替策略质量。**

## 2. 评估调度与执行模式

### 2.1 回合数与频率

- 每个 checkpoint 评估 **10 个 attempts**，配置 `n_eval_episodes=10`，采用 SB3 常见的 10 回合评估惯例。
- 训练环境每累计 10,000 steps 触发一次，和 checkpoint 对齐；400,000 步对应最多 40 个周期评估点。
- `attempt` 指一次回合启动及其后续运行。`fault` 也消耗 attempt 名额，**不补跑到 10 个有效回合**。
- `n_eval_episodes` 在本协议中表示目标 attempts 数；有效策略样本数另记 `valid_episodes`。
- 单 env 时 `eval_freq=10_000`。未来使用多个 env 时，须按累计环境 steps 校正 callback 调用频率。

### 2.2 确定性执行

训练模型评估统一调用：

```python
action, state = model.predict(obs, deterministic=True)
```

这里采用确定性策略而非从策略分布采样。需要特别澄清“policy 均值动作”的表述：

- 对连续动作策略，通常指执行分布均值。
- 本项目是 `Discrete(10)`，不存在可直接执行的“均值动作”；SB3 的确定性执行为选择 categorical 分布的最高概率动作。

确定性策略不代表游戏过程可重复：游戏初始状态仍不可 seed。

### 2.3 单次评估墙钟上限与降级

初始设置：

```yaml
n_eval_episodes: 10
eval_freq: 10000
deterministic: true
max_eval_minutes: 30
degraded_n_eval_episodes: 5
```

`30` 分钟是待端到端校准的工程初值，不是实测性能结论。上限覆盖 reset、浏览器操作、回合执行和必要的故障恢复；超时操作必须能被取消或通过终止独立评估进程打断。

降级规则：

1. 在 10k 步端到端校准中验证成本；若 10 attempts 无法稳定满足上限，后续评估统一降为 `n=5`，记录 `eval_mode="degraded"`。
2. 降级须在评估开始前决定，不得看到分数后提前停止。
3. 已开始的 `n=10` 评估触及上限时，记录 `evaluation_complete=false`，不把已完成的前 5 个回合追认为合格的 `n=5` 评估。
4. 全局墙钟超限不是游戏 `budget` 截断；未完成的 attempt 不纳入策略指标，单列为行政性中断。
5. 未完成评估点不可选型。发生降级后，候选模型及 random 基线应按相同评估档位重新比较；不得直接混排不同档位结果。
6. 若 `n=5` 仍无法满足上限，停止该评估并报告错误，不继续静默减样本。

## 3. 初始条件与不可 seed 的处理

`game_seedable=False`，无法构造固定、可重放的游戏 seed 集合。因此采用：

- 固定 attempts 数量的回合集合；
- 相同游戏版本、viewport、reset 流程与适配器契约；
- 相同截断阈值与统计口径；
- 每项回合级数值指标报告 `mean ± std`、`median`、`min/max` 及实际样本数。

这里“固定集合”指固定采样规模和执行协议，**不是固定地图或配对初始状态**。不得宣称模型与基线在同一游戏 seed 上做了配对比较。

console 捕获的 game seed 仅写入 `observed_game_seed`，用于追溯：

- 不注入游戏；
- 不据此声称可复现；
- 不据此筛选有利初始状态；
- 未捕获时记为 `null`。

`--seed` 仅控制 random 基线的动作 RNG，不控制游戏。

## 4. 指标与统计口径

### 4.1 原生游戏表现

| 级别 | 指标 | 定义 |
|---|---|---|
| 主指标 | `mean_max_depth` | 有效回合中，各回合最大确认下潜深度的平均值 |
| 次指标 | `mean_survival_turns` | 有效回合最终确认存活回合数的平均值 |
| 记录项 | `win_rate` | 有效回合胜利比例，仅记录，不设验收门槛 |

深度与回合数来自适配器确认的 HUD/结算信息：

- 最大深度使用有效观测的 `depth` 最大值。
- 存活回合使用 `turn`，不是 env steps；一次宏动作可能不等于一个游戏回合。
- `hud_certain=False` 或 `obs_stale=True` 的读数不得推进最大深度或存活回合计数。
- 保留最后一次可信读数；无法形成可信终值时标记该指标缺失，报告 `metric_missing_episodes`，不填零、不猜测。
- 存在未解决的核心指标缺失时，该评估点不参与选型。

### 4.2 辅助指标

| 指标 | 分母/统计对象 | 用途 |
|---|---|---|
| `shaped_return_mean` | 有效策略回合的累计 reward | 奖励设计诊断，不用于主排序 |
| `fault_rate` | fault attempts / 已启动 attempts | **链路指标** |
| `obs_stale_rate` | `obs_stale=True` 的 steps / 全部已记录 steps | **链路指标** |
| `ocr_uncertain_rate` | `hud_certain=False` 的 steps / 全部已记录 steps | **链路指标** |
| `sync_latency_ms_p50/p95` | 全部可用 `sync_latency_ms` 样本 | **链路指标** |

链路统计包含 fault 回合中的已记录 steps，避免剔除失败回合后产生虚假的健康结果。缺失字段和未能返回 step 的操作故障另计，不默认视为健康样本。

`std` 使用样本标准差；有效样本少于 2 时记为 `null`。比率同时报告分子、分母；零有效回合时策略指标为 `null`，不是 0。

## 5. 低成本基线

所有基线走同一评估 harness、观测流程、动作适配器、奖励计算与截断规则；不因策略不读取图像而跳过截图/OCR。

### 5.1 Uniform random

```python
action = baseline_rng.integers(0, 10)
```

- 对全部 10 个动作均匀采样。
- 使用 `--baseline random`。
- `--seed` 仅复现动作 RNG 序列。
- 基线有意随机，不受模型 `deterministic=True` 的采样语义约束。

### 5.2 Wait-only

```python
action = 8
```

- 使用 `--baseline wait`。
- 检查纯等待的存活能力，以及停滞检测、奖励累积是否异常。
- 仍执行正常的 300 回合无进展检测，不能绕过 stagnation 截断。

### 5.3 可选人类参照

人类试玩可作为 stretch，记录最大深度、存活回合和操作条件。不作为本轮交付依赖，也不与自动评估结果混成同一个样本集。

## 6. 训练与评估隔离

必须通过工厂新建独立 `BrowserGameEnv`：

```python
from rl_game_agent.envs import ENV_REGISTRY
train_env = ENV_REGISTRY["ruggrogue-v1"]()  # 07 号票工厂：每次调用返回全新实例
eval_env = ENV_REGISTRY["ruggrogue-v1"]()   # 独立浏览器 context / 页面 / 适配器 / 缓存
```

要求：

- 独立浏览器 context、页面、游戏状态和适配器实例；
- 不共享 HUD 缓存、回合计数、恢复状态或奖励差分状态；
- 游戏版本、viewport、截图预处理、动作映射和适配器契约一致；
- 包裹方式与训练一致，包括适用的 `VecTransposeImage`；
- 若使用带统计状态的 wrapper，评估应使用训练统计并冻结更新；
- 基线与模型使用相同任务条件，仅策略不同。

**禁止复用训练 env 做评估**，否则会污染训练轨迹和评估初始状态。

已核验的 SB3 官方行为：

- `EvalCallback` 使用独立测试 env 周期评估。
- `best_model_save_path` 保存其判定的最优模型。
- `log_path` 写入 `evaluations.npz`。
- 训练/评估包裹方式不一致可能产生警告。
- 本项目必须显式使用 `deterministic=True`。

标准 `EvalCallback` 的 reward 统计不能满足本协议全部要求。应使用自定义 callback/评估循环采集原生游戏指标，并明确区分“SB3 按 reward 的 best”与“本协议按深度的 best”。

## 7. 模型选择与日志

合格评估点按下列字典序排序：

1. `mean_max_depth` 更高；
2. 若相同，`mean_survival_turns` 更高；
3. 若仍相同，`fault_rate` 更低；
4. 若完全相同，保留较早 checkpoint，避免无理由替换。

使用未四舍五入数值比较。`LINK-RED`、未完成评估或核心指标缺失的点不可参与选型。

产物至少保留：

- `best_depth_model.zip`：按上述规则选择；
- `final_model.zip`：训练结束时模型，无论是否优于 best；
- 周期 checkpoint 及其评估记录。

训练期自定义 callback 将以下字段写入 TensorBoard：

```text
eval/mean_max_depth
eval/mean_survival_turns
eval/shaped_return_mean
eval/fault_rate
eval/obs_stale_rate
eval/ocr_uncertain_rate
eval/sync_latency_ms_p50
eval/sync_latency_ms_p95
eval/valid_episodes
eval/link_red
```

`EvalCallback` 默认围绕 reward 记录和选优，不会自动提供本项目的 depth 选型逻辑。训练奖励曲线仅用于诊断，不是选型依据。

## 8. 初始验收目标（未实测）

以下是**初始验收目标（未实测）**，不表示当前系统已达到：

| 目标 | 判据 |
|---|---|
| 优于 random | 模型与 random 的平均最大深度 95% CI 不重叠，且模型 CI 下界高于 random CI 上界 |
| 链路 fault | `fault_rate < 5%` |
| 观测陈旧 | `obs_stale_rate < 10%` |

CI 以有效回合为独立采样单位，对 `max_depth` 的均值采用非参数 bootstrap，重采样 10,000 次，报告 percentile 95% CI。统计重采样使用单独记录的固定内部 RNG，不复用 `--seed` 的语义。

注意：

- 不使用 step 级样本伪增样本量，不做游戏 seed 配对推断。
- 10 个 attempts 下 CI 较不稳定；不重叠是本项目的保守验收约定，不等同于完整统计显著性证明。
- 从多个 checkpoint 选出 best 后，须用新回合集合对 best 和 random 做独立确认，减少选型偏差。
- 正式确认优先使用标准 `n=10`；仅有降级结果时须显式标记证据不足。
- `n=10` 或 `n=5` 时，`fault_rate <5%` 实际要求该批次零 fault；零 fault 不证明真实长期故障率低于 5%。

## 9. 异常处理与核心分类法

### 9.1 回合处理

| 情况 | 策略指标 | 链路报告/说明 |
|---|---|---|
| `truncated_kind="fault"` | 整个回合剔除 | 计入 fault 率，记录 `end_reason` |
| `truncated_kind="stagnation"` | 计入 | 300 回合无进展，属于策略停滞；奖励含 `-0.5` |
| `truncated_kind="budget"` | 计入 | 5000 steps 的长存活截断；训练侧保持 bootstrap 语义 |
| 可信 death | 计入 | 死亡属于策略结果 |
| `obs_stale=True` | 回合仍计入并标记，陈旧读数不用作指标更新 | 单独计入链路异常 |
| `hud_certain=False` | 不将不确定读数作为策略表现证据 | 单独计入 OCR uncertain |
| 截图/操作超时故障 | 按适配器 fault 契约处理 | 记录故障类型和 `end_reason` |

单次评估：

```python
link_red = fault_attempts > 2
```

超过 2 个 fault 时标记 `LINK-RED`，该点不可选型；`n=5` 降级档也使用同一绝对阈值。此健康红线与验收 `fault_rate <5%` 是不同层级的判据。

### 9.2 分类边界

**策略失败：**

- `hud_certain=True` 且终局证据可信的死亡；
- stagnation 截断；
- 链路干净但最大下潜深度低。

**链路失败或链路质量异常：**

- fault 截断，包括连续 OCR 失败 20 步等；
- `obs_stale`；
- OCR uncertain；
- 截图失败、同步超时及其他适配链路故障。

“链路失败永不混入策略指标”指：不得把链路错误当作死亡、零深度或策略停滞来扣分。**不意味着任一 stale step 都要剔除整个回合**。非 fault 回合仍按可信游戏读数统计，同时单独报告链路异常；fault 回合则整体剔除。不能可信归因的事件不强行归为策略失败。

## 10. `evaluate.py` 决策规格

### 10.1 CLI

| 参数 | 规则 |
|---|---|
| `--model` | 必需；`baseline=none` 时加载该 SB3 模型 |
| `--episodes` | 正整数，默认 `10`，表示目标 attempts |
| `--deterministic` | 默认开启；可提供 `--no-deterministic` 供诊断，非确定性结果不可用于正式选型 |
| `--baseline` | `{none,random,wait}`，默认 `none` |
| `--out` | 输出目录，默认 `artifacts/eval/<run_id>` |
| `--max-eval-minutes` | 正数，默认 `30` |
| `--seed` | 仅用于基线动作 RNG，默认 `0` |

为保持统一 CLI，基线模式仍要求 `--model` 参数，但不加载模型，并记录 `model_used=false`；可传入明确占位值 `unused`。

```bash
python evaluate.py \
  --model checkpoints/ppo_10000_steps.zip \
  --episodes 10 --deterministic \
  --out artifacts/eval/step_10000 --max-eval-minutes 30

python evaluate.py \
  --model unused --baseline random --seed 42 \
  --episodes 10 --out artifacts/eval/random

python evaluate.py \
  --model unused --baseline wait \
  --episodes 10 --out artifacts/eval/wait
```

### 10.2 自定义循环

不得仅调用返回 reward/length 的评估工具后丢弃 `info`。每个 step 采集完整 `info`，至少校验：

```text
phase
turn
depth
hud_certain
reward_breakdown
end_reason
truncated_kind
obs_stale
dialog_seen
sync_latency_ms
```

保留额外键，不静默丢弃。若使用自动 reset 的向量环境，必须从终局 step 获取 terminal 信息，不能用下一个回合的 reset 信息覆盖。

每个 attempt：

1. 新回合 reset，并记录初始状态和可观测 game seed。
2. 执行动作，保存 reward、终止标志及完整 `info`。
3. 维护可信 `max_depth`、`survival_turns` 和链路计数。
4. 结束后先分类，再决定是否进入策略指标。
5. 立即落盘，防止后续浏览器故障丢失已完成结果。

### 10.3 产物

**`episodes.jsonl`**：每行一个 attempt，包含：

- attempt ID、模型/基线、起止时间；
- `observed_game_seed`、回合指标、累计 reward；
- `terminated`、`truncated`、`truncated_kind`、`end_reason`；
- 策略统计资格及剔除原因；
- 链路计数；
- `step_infos`：完整逐步 `info`，保持 JSON 可序列化。

**`summary.json`**：

- 游戏、SB3、适配器、wrapper、viewport 与模型身份信息；
- 完整评估配置及 `eval_mode`；
- 目标/启动/完成/有效/fault/中断 attempts 数；
- 指标统计、CI、分母与缺失计数；
- `evaluation_complete`、`link_red`、`selection_eligible`；
- 墙钟用时和错误详情。

**终端表格**至少打印主指标、存活回合、shaped return、胜率、fault/stale/uncertain 率、延迟 p50/p95、有效样本数和健康状态。

### 10.4 退出码

| 退出码 | 含义 |
|---|---|
| `0` | 正常完成，非 `LINK-RED`；不代表已通过性能验收 |
| `2` | 已形成有效报告，但 `fault_attempts > 2`，即 `LINK-RED` |
| `1` | 参数、模型加载、不可恢复执行错误，或墙钟超限导致评估未完成 |

错误优先级为 `1` 高于 `2`；即使退出 `1`，已有 fault 数及 `link_red` 状态仍写入报告。可恢复的环境 fault 不是脚本崩溃，应按 attempt 处理。

## 11. 实现验收清单

- [ ] 每 10k steps 同步保存 checkpoint 并触发独立评估。
- [ ] 默认 10 attempts，fault 不补跑；降级 5 attempts 在开跑前确定。
- [ ] 墙钟上限可打断阻塞操作，超限产物可追溯且不可选型。
- [ ] 训练/评估使用独立 env、context、适配器和缓存。
- [ ] wrapper、游戏版本、viewport 与适配器契约一致。
- [ ] 离散模型确定性评估实际执行最高概率动作。
- [ ] random 与 wait 基线通过同一 harness 运行。
- [ ] `--seed` 不被宣称为游戏 seed。
- [ ] 所有 `info` 键与 terminal 信息完整落盘。
- [ ] fault 剔除、stagnation/budget/death 纳入规则有测试。
- [ ] stale/uncertain 读数不会推进原生指标，也不会被记作策略死亡。
- [ ] fault 分母、step 级链路分母及缺失字段明确。
- [ ] 第 3 个 fault 能触发 `LINK-RED` 并阻止选型。
- [ ] depth 排序及两级 tie-break 有测试；final 始终保留。
- [ ] TensorBoard 包含 depth 与链路指标，不仅包含 reward。
- [ ] 输出 `episodes.jsonl`、`summary.json` 和表格。
- [ ] 退出码 `0/2/1` 有覆盖，错误时保留部分结果。
- [ ] CI、样本数、降级状态和独立确认结果可追溯。

## 12. Destination 与既有门禁核对

### 12.1 Destination 四项

| Destination | 本协议采用的结论 | 来源 |
|---|---|---|
| 游戏选定 | ruggrogue v1.0.1，MIT，回合制 roguelike，游戏不可 seed | **03：游戏选定票据** |
| 画面方案 | Playwright canvas 截图，84×84 灰度；VM 无头 + Xvfb | **04：画面方案票据** |
| 适配接口 | `Discrete(10)`、HUD OCR 差分奖励、结算 sparse、固定 `info` 键与截断分类 | **07：适配接口票据** |
| 算法训练评估 | PPO + `CnnPolicy`、400k steps、10k checkpoint、CPU 单 env、TensorBoard；本笔记补齐评估与选型协议 | **08：算法训练评估票据 + 本票** |

来源按已提供的票据编号引用；本笔记不臆造仓库文件路径或未提供的实现证据。

### 12.2 已归属 prior 票据的实现期门禁

以下均为**已归属 prior 票据的实现期门禁**，不是本轮未决事项，也不因文档完成而自动视为通过：

| 门禁 | 实现期核验内容 | 归属/来源 |
|---|---|---|
| B1 | WASM 缺失问题及可运行资源完整性 | prior 票据中的 B1 |
| B2 | OCR 冒烟测试 | prior 票据中的 B2 |
| B3 | `TurnCount` 探针验证 | prior 票据中的 B3 |
| B4 | WebGL 可用性门禁 | prior 票据中的 B4 |
| H1–H7 | 按原票据逐项满足训练实现硬门禁 | **08** |
| 10k 步端到端校准 | 校准吞吐、墙钟预算、评估档位、回合统计与链路健康 | **08** |

本票负责定义评估协议及验收证据格式；上述门禁的实现和通过证据仍由原票据负责。
