# 08-training-plan 研究笔记：SB3 算法与训练方案

## 1. 输入约束（来自已决票据）

- 02：VM 无头 Linux，无 GPU 纯 CPU；墙钟预算几天；第一阶段网页游戏；roguelike。
- 03：ruggrogue v1.0.1（MIT/CC0/WTFPL），回合制，一按键一回合；自托管静态文件 + Playwright/Chromium。
- 04：Playwright headless Chromium 对 canvas 元素截图；TurnCount 同步；无帧堆叠；单帧完全可观测；84×84/灰度等训练预处理归本票。
- 05：动作空间 `Discrete(10)`，1 env step = 1 逻辑动作；SB3 原生支持。
- 06：奖励 = HUD OCR 差分（dense）+ 结算屏终局（sparse）；depth +1.0 / level +0.5 / xp +0.001 / 掉血 −0.01 / 步罚 −0.001 / 死亡 −1.0 / 胜利 +10.0；5000 回合预算截断、300 回合停滞截断、OCR 连续失败截断；truncated 走标准 bootstrap；OCR 数值永不进观测。
- 07：`BrowserGameEnv(gymnasium.Env)` + `GameAdapter` 协议；`ENV_REGISTRY["ruggrogue-v1"]` 工厂；observation_space 为 `Box uint8 HWC`；`frame_shape` 数值待定；游戏不可 seed（`info["game_seedable"]=False`）。

**核心现实**：浏览器自动化慢速环境。每 step = 按键注入（<50ms）+ TurnCount 等待 + canvas 截图 + HUD OCR，吞吐预计每秒几步，远低于向量化仿真环境。纯 CPU。几天墙钟预算。

## 2. 一手事实核验（SB3 2.9.0 源码，pip 下载 wheel 解包）

- **PPO 默认超参数**（`stable_baselines3/ppo/ppo.py`）：`lr=3e-4, n_steps=2048, batch_size=64, n_epochs=10, gamma=0.99, gae_lambda=0.95, clip_range=0.2, normalize_advantage=True, ent_coef=0.0, vf_coef=0.5, max_grad_norm=0.5`。
- **DQN 默认超参数**（`stable_baselines3/dqn/dqn.py`, v2.9.0）：`lr=1e-4, buffer_size=1_000_000, learning_starts=100, batch_size=32, train_freq=4, gradient_steps=1, target_update_interval=10000, exploration_fraction=0.1, eps 1.0→0.05, gamma=0.99, tau=1.0, max_grad_norm=10`。
- 注意：`learning_starts` 在 v2.9.0 已改为 100（旧文档 v1.6.2 为 50000）。本项目 `pyproject` 要求 `stable-baselines3>=2.0`，以 2.9.0 源码为准。
- 官方文档确认 SB3 核心 DQN 仅为 vanilla（无 Double/Dueling/PER）：https://stable-baselines3.readthedocs.io/en/v1.6.2/modules/dqn.html
- **NatureCNN**（`stable_baselines3/common/torch_layers.py`）：`CnnPolicy` 默认特征提取器；要求输入 CxHxW（channels first），注释明确 "Re-ordering will be done by pre-preprocessing or wrapper"；默认校验 `uint8` 且值域 `[0, 255]`（`normalized_image=False`）→ **不要手动 /255**，保持 uint8。
- **VecTransposeImage**：我们的 env 按 07 决议输出 HWC，train.py 必须包 `VecTransposeImage` 转 CHW（SB3 PyTorch 约定；Atari 官方示例同样做法）。
- **ReplayBuffer dtype**（`stable_baselines3/common/buffers.py:213`）：`dtype=observation_space.dtype` → uint8 图像按 uint8 存储。内存账：84×84×1 uint8 单帧 7056 字节；`buffer_size=1M` 时 obs+next_obs 两数组 ≈ 14 GB；100k ≈ 1.4 GB；50k ≈ 0.7 GB。默认 1M 在本 VM 不可行。

## 3. 吞吐 / 预算数学（待验证假设；实现期必须先测端到端吞吐再承诺全量）

假设单步耗时主要来自 TurnCount 等待 + 截图 + OCR。**仅采样**耗时：

| 步速 | 400k 步采样 | 500k 步采样 |
|---|---|---|
| 1 step/s | 111 小时（4.6 天） | 139 小时（5.8 天） |
| 2 step/s | 55.6 小时 | 69.4 小时 |
| 3 step/s | 37 小时 | 46.3 小时 |

红队纠正：此前"500k = 2步/秒×3天"按 100% 采样占空比计算，**未含梯度更新、评估、重置、故障恢复**。500k 步在 2 步/秒下仅采样就占 69.4 小时，3 天预算只剩约 2.6 小时给其他一切——不可靠。

修正后规划锚点：`total_timesteps = 400_000`（`--timesteps` 可覆盖）。2 步/秒下采样 55.6h ＋ 梯度更新（400k/1024×160 ≈ 6.25 万次 minibatch，CPU 上约 1–2h）＋ 评估/重置/故障余量约 20% ≈ 70–75h ≈ 3 天。若实测只有 1 步每秒，总步数上限砍到约 200k，超参数按比例下调。

**硬性前置**：实现期先跑 10k 步端到端（含一次梯度更新 + 一次评估），实测"步/秒（含训练开销）"后再锁定 total_timesteps；不凭纯环境测速承诺预算。

PPO 迭代墙钟（n_steps=1024, 2 step/s，**仅采样**）：rollout 约 8.5 分钟（2048 则为 17.1 分钟）。注意 n_steps 缩小**不减少总梯度更新量**（固定总步数/batch/epochs 时总量基本不变），收益是首次更新更早、策略迭代更频繁；代价是更依赖 rollout 边界 bootstrap、单 rollout 数据相关性更高。

## 4. 算法比较：PPO（候选）vs DQN（唯一对照）

| 维度 | PPO（on-policy） | DQN（off-policy, SB3 vanilla） |
|---|---|---|
| 样本效率（env 步） | 低：每轮迭代后丢弃 rollout 数据 | 高：replay 跨迭代复用；慢速环境下这是决定性优势 |
| 稳定性 | 高：clip + advantage 归一化，对奖励尺度不敏感；全新自研 env/reward 链路下最不易"训飞" | 中低：vanilla 无 Double/Dueling/PER，有高估偏置；对奖励尺度更敏感（我们的 xp 奖励是 1e-3 量级） |
| 冷启动 | 无：第一个 rollout 即更新 | v2.9.0 `learning_starts=100` 已无碍（旧版本 50k 是大坑，现已修复） |
| 内存（CPU VM） | 可忽略（rollout buffer = n_steps×obs） | 默认 buffer 1M ≈ 14 GB 不可行；必须手调到 50–100k（0.7–1.4 GB） |
| 探索 | 熵（ent_coef）+ 随机策略 | eps-greedy 1.0→0.05；稀疏胜利奖励（+10 罕见）下主要靠 dense 塑形，两者相当 |
| 调参面 | 小：n_steps/batch/epoch 为主 | 大：buffer、target 间隔、探索计划、train_freq |
| 与回合制/单帧契约 | 契合（GAE + truncated bootstrap；06 的截断语义 SB3 原生支持） | 契合（Discrete(10) 是 DQN 舒适区） |

**工程判断**（红队后修正的诚实版本）：v1 首要目标是"第一条基线端到端跑通并给出信号"（09 票验收语境）。**选 PPO 的理由是运维稳健性与可调试性**（clip + advantage 归一化、对奖励尺度不敏感、调参面小、无 replay 内存硬伤），**不是样本效率更高**——红队正确指出：在慢速 env 下 DQN 的 replay 跨迭代复用是真实优势，PPO 每轮迭代后丢弃 rollout 数据，样本效率处于下风。vanilla DQN（无 Double/Dueling/PER）的过估计与不稳定性是真实反方风险，但不足以在零实测时断言 PPO 必胜。

因此：**首选 PPO 跑 v1（求稳求通）**；**DQN 为具名备选，触发条件**：PPO 在约 150k 步后仍无学习信号（§7 规则 2 触发且排除奖励 bug 后），或 v2 做**相同墙钟预算下的对照实验**（比步数、比算法名都没有意义，以墙钟内的任务指标为准）。备选排除说明：QR-DQN 在 sb3-contrib（新增依赖，v1 不引入）；RecurrentPPO（04 已定单帧完全可观测，无需时序建模）；MaskablePPO（05 明确 v1 不用 action masking）。

备选排除说明：QR-DQN 在 sb3-contrib（新增依赖，v1 不引入）；RecurrentPPO（04 已定单帧完全可观测，无需时序建模）；MaskablePPO（05 明确 v1 不用 action masking）。

## 5. 决策：首版算法与配置

- **算法**：PPO；**策略**：`CnnPolicy`（默认 NatureCNN，不自定义）。
- **观测预处理**（04 deferred 到本票，现决定）：canvas RGB → 灰度 → resize 84×84 → `uint8 [0,255] HWC`（env 侧，`frame_shape=(84,84,1)` 写入 07 的适配器契约常量）；train.py 侧 `VecTransposeImage` → CHW。**不手动 /255**：SB3 policy 的 `preprocess_obs`（`normalize_images=True` 默认）在内部做 `float()/255`，env 若预先归一化会触发 NatureCNN 的 uint8 校验失败或双重缩放；env 保持 uint8 [0,255] 即可。
- 灰度理由：CPU 上 3 通道输入成本 ×3；ruggrogue HUD 高对比，形状/位置信息为主。RGB 列为 v2 消融。
- 84×84 理由：de-facto 标准；NatureCNN 为该尺度设计；CPU 前向便宜。
- **红队 gate（实现期硬门禁）**："单帧完全可观测"是 04 的断言，但实际喂给策略的 84×84 灰度图未必保留 tile 类别/敌我/楼梯可辨识度，而奖励用的却是全分辨率 HUD OCR——存在"奖励依赖的信息对策略不可辨认"的混叠风险。训练启动前必须人工抽查实际策略输入帧确认关键状态可辨；否则回退 RGB/更高分辨率并修订本票。
- **gamma 的已知局限**（红队）：`gamma=0.99` 有效视野约 100 回合，`0.99^1000 ≈ 4.3e-5`，千步后的胜利 +10 几乎传不到当前决策。**v1 实际优化目标是下潜/升级/生存（dense 塑形），胜利只是弱远信号**——接受此 trade-off，不靠调大 gamma 解决（0.999 会加重长程估计难度）。若 v1 出现"刷浅层 XP 不下潜"，v2 再议 gamma 或胜利塑形。
- **起始超参数**（`configs/ruggrogue_ppo_v1.yaml`，实现期新建；现有 `ppo_default.yaml` 保留为通用模板）：

```yaml
algo: PPO
env: ruggrogue-v1
policy: CnnPolicy
total_timesteps: 400_000 # 见 §3 修正数学；--timesteps 可覆盖
seed: 0
hyperparams:
learning_rate: 3.0e-4
n_steps: 1024 # 首次更新约 8.5min（2步/秒）；更小则边界 bootstrap 噪声更大
batch_size: 64
n_epochs: 10
gamma: 0.99
gae_lambda: 0.95
clip_range: 0.2
normalize_advantage: true
ent_coef: 0.01 # 起始值；按监控到的熵/有效动作率动态决定是否衰减，不写死
vf_coef: 0.5
max_grad_norm: 0.5
checkpoint_freq: 10_000 # 2步/秒下约 1.4h 一次；浏览器长期运行故障损失可控
tensorboard_log: runs/ # 必开；监控 approx_kl / clip_fraction / explained_variance
```

- **单环境 vs 并行**：v1 **单 env 起步**（前约 50k 步调试期：链路最简单、吞吐测量最干净），随后**实测 2-env 吞吐**再决定是否加并行——不从"纯 CPU"直接推出单 env 最优（多浏览器进程可能隐藏等待时间，也可能争用 CPU/内存；必须实测 1/2/4，不能预设）。rollout 总量 = `n_steps × n_envs`，callback 频率按实际 transition 数换算。Eval 必须用**独立浏览器实例**（输入 09 票），不得复用训练实例。
- **terminal_observation 要求**（红队）：truncated 的 bootstrap 必须用**截断前最终观测**（经相同图像变换），不得用 reset 后首帧；`Monitor` 位置决定日志奖励口径；实现期单测覆盖。
- **种子策略**：`--seed` 同时 seed SB3（torch/numpy/动作采样）与 env action_space；游戏本身不可 seed（07），`info["game_seedable"]=False`，跨 run 方差含游戏随机性，必须在报告中声明。默认 seed 0；**不做多 seed**（墙钟不够），第二个 seed 仅当首个 seed 出现学习信号后作为 v2 复现项。每次 run 存 config 副本 + git sha。
- **DQN 备选的具体覆盖参数**（触发时直接可用，不重新决策）：

```yaml
algo: DQN
policy: CnnPolicy
total_timesteps: 400_000
hyperparams:
learning_rate: 1.0e-4
buffer_size: 50_000 # obs+next_obs uint8 约 0.7GB；100k≈1.4GB 太重；默认 1M≈14GB 不可行
learning_starts: 5_000 # 2步/秒下约 40 分钟随机预热（v2.9.0 默认 100 太短，Q 初始化不稳）
batch_size: 32
train_freq: 4 # 每 4 env 步 1 次 CPU 梯度更新，可承受；慢 env 下不加大 gradient_steps 以免 CPU 成为瓶颈
gradient_steps: 1
target_update_interval: 5_000 # 2步/秒下约 42 分钟；默认 10k 在慢 env 下太久
exploration_fraction: 0.1 # eps 在前 40k 步退火到 0.05；长程 roguelike 是否够用待实测，未论证
exploration_initial_eps: 1.0
exploration_final_eps: 0.05
gamma: 0.99
```
注：DQN checkpoint 默认**不含 replay buffer**；中断后只恢复权重会丢失最昂贵的经验，需另存 buffer（磁盘成本另计）。obs 若意外存成 float32，50k buffer 两项升至约 2.8GB——实现期断言 dtype。

## 6. 职责划分

- `configs/ruggrogue_ppo_v1.yaml`（新建）：算法名、env 名、policy、总步数、全部超参数、seed、检查点/评估频率。**所有数字只活在 config 里**，train.py 不硬编码。
- `train.py`：解析 config → 从 `ENV_REGISTRY` 取工厂 → 包 `DummyVecEnv` + `VecTransposeImage`（+ `Monitor`）→ 按 `algo` 建 SB3 模型 → 挂 `CheckpointCallback` / `EvalCallback` → `learn()` → 存模型。只做装配，不含游戏知识。
- `ENV_REGISTRY`（07 已定）：`"ruggrogue-v1" -> 工厂函数`，保证每次调用返回全新隔离实例。

## 7. 中止条件（训练期硬规则）

1. **环境坏了就停**：最近 50 局中 fault 截断（`truncated_kind=fault`，07）> 20%，或 OCR uncertain 持续 > 30% 步数 → 停，修 env/OCR，不烧墙钟。
2. **没学到就停**：初始 100k 步后，滑动窗口（50k 步）平均回合回报不升反降或长期平坦 → 停；先查奖励 bug（06 审计清单），再考虑切 DQN 备选。
3. **墙钟硬上限**：`--max-wall-hours`（默认 72），到点即停并存档。
4. **数值发散**：`approx_kl` 持续 > 0.05 或 value loss 爆炸 → 停，降 lr / 查奖励尺度。
5. **墙钟耗尽 ≠ episode 结束**：`--max-wall-hours` 到点只做安全停机（rollout 边界停、存档），不得伪造死亡/截断奖励记入训练数据。
6. 通过标准本身由 09 票定义；本票只定"何时停"，不定"何谓成功"。

## 8. 待验证假设（实现期必须实测，不在本票填数）

- H1：单步吞吐（目标 ≥1 step/s；§3 的预算数学全系于此）。
- H2：84×84 灰度是否保留足够语义（HUD 数字 OCR 不在本观测内，无影响；tile 可辨识度待看）。
- H3：n_steps=1024 的更新频率 vs GAE 方差 trade-off 是否合适。
- H4：ent_coef=0.01 是否足够探索（备选 0.0 / 0.02）。
- H5：单 Chromium + OCR 在 VM 上的 CPU/内存占用（决定 v2 并行可行性）。
- H6：84×84 灰度策略输入中 tile/敌我/楼梯是否可辨识（§5 红队 gate；奖励用全分辨率 OCR 而策略看压缩图的混叠风险）。
- H7：端到端吞吐（含梯度更新+评估+重置），§3 的 10k 步校准实验即测此项。

## 9. 红队记录

- llmapi gpt-6-astra 红队审查：2026-10-14，两轮共 12+12 项。全部采纳或记录为已知局限：
  1. 预算数学错误（500k 按 100% 占空比）→ 修正为 400k + 10k 步端到端校准前置。
  2. 84×84 可观测性 gate → §5 硬门禁。
  3. 按键/OCR 可靠性 → 采纳 04/05/06 结论 + 07 B1–B4 门禁为启动前置，不重裁。
  4. 截断语义污染 bootstrap → 06 已裁决（死亡/胜利=terminated；预算/停滞/故障=truncated+bootstrap）；记录停滞语义张力（若学出"等截断"套利则升级为 terminated，需修订 06）；terminal_observation 必须用截断前帧。
  5. PPO 首选理由 → 诚实重述为"稳健可调试"而非"样本效率"；DQN 备选 + 相同墙钟对照触发器。
  6. DQN 参数补全 → 备选 yaml 已含 train_freq/gradient_steps/探索计划及未论证声明。
  7. gamma=0.99 远期失效 → 记录为已知局限（v1 优化下潜/生存，胜利为弱信号）。
  8. n_steps 澄清 → 不减少总量；加 approx_kl/clip_fraction/explained_variance 监控。
  9. ent_coef → 起始 0.01，按监控动态调整，不写死。
  10. 单 env → 起步单 env + 50k 步后实测 2-env；eval 独立实例（输入 09）。
  11. DQN 内存 → 确认 50k≈0.7GB；checkpoint 不含 buffer；dtype 断言。
  12. 检查点 → 10k 步；四层恢复区分（模型/优化器/经验/游戏状态）。
