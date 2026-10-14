Labels: wayfinder:research
Type: research
Status: resolved
Blocked by: 02, 07
Mode: AFK

## Question

首版采用哪一套 SB3 算法与训练方案？

在既定动作空间、视觉观测、接口时序和资源预算下，选择一个 SB3 算法及策略网络配置。以现有 PPO 配置为候选而非既定答案，比较至多一个有实际意义的替代方案。

产出首版训练决策：关键超参数、总交互步数与墙钟预算上限、种子、检查点策略、单环境或并行环境安排，以及训练阶段的中止条件。说明 `train.py`、环境注册表和配置文件分别需要承担什么职责；无法预知的吞吐或学习效果标为待验证假设。

## Answer

**决策：首版算法 = PPO + `CnnPolicy`（NatureCNN）；DQN 为具名备选。**

**选择理由（红队后诚实版本）**：选 PPO 是因为运维稳健性与可调试性（clip + advantage 归一化、对奖励尺度不敏感、调参面小、无 replay 内存硬伤），**不是因为样本效率更高**——在慢速 env 下 DQN 的 replay 跨迭代复用是真实优势（已承认）。v1 首要目标是端到端跑通并给出信号；DQN 触发条件：PPO 约 150k 步后仍无学习信号（排除奖励 bug 后），或 v2 做相同墙钟预算对照。备选排除：QR-DQN（sb3-contrib 新增依赖）、RecurrentPPO（04 已定单帧可观测）、MaskablePPO（05 明确 v1 不用）。

**一手事实**（SB3 2.9.0 源码已核验）：PPO 默认 `lr=3e-4/n_steps=2048/batch=64/epochs=10/gamma=0.99`；DQN 默认 `buffer=1M/learning_starts=100（旧版 50k 已改）/batch=32/train_freq=4/target=10k/eps 1.0→0.05`，核心仅 vanilla（无 Double/Dueling/PER）；NatureCNN 要求 CxHxW，`preprocess_obs` 内部 /255（env 保持 uint8 不手动归一化）；ReplayBuffer 按 `observation_space.dtype` 存储 → 默认 1M buffer 在 uint8 下约 14GB，本 VM 不可行。

**首版配置**（`configs/ruggrogue_ppo_v1.yaml`，实现期新建）：`total_timesteps=400_000`（红队修正预算数学：500k 在 2 步/秒下仅采样 69.4h，3 天预算不闭合；实现期先跑 10k 步端到端校准再锁定）；`n_steps=1024`（首次更新约 8.5min；缩小不减少总量，只提前更新时机）；`ent_coef=0.01` 起始按监控动态调；`gamma=0.99`（已知局限：千步后胜利 +10 折扣至约 4e-5，v1 实际优化下潜/生存）；`checkpoint_freq=10_000`；tensorboard 必开（监控 approx_kl/clip_fraction/explained_variance）。

**观测预处理**（04 交由本票）：灰度 84×84 uint8 HWC → `VecTransposeImage` → CHW；`frame_shape=(84,84,1)` 写入适配器契约。实现期硬门禁：人工抽查实际 84×84 输入中 tile/敌我/楼梯可辨识（奖励用全分辨率 OCR 而策略看压缩图，混叠风险）。

**单 env 起步**（前约 50k 步），随后实测 2-env 吞吐再定并行；rollout 总量 = n_steps × n_envs；eval 用独立浏览器实例（输入 09）。

**DQN 备选覆盖参数**：`lr=1e-4, buffer_size=50_000（约0.7GB）, learning_starts=5_000, batch=32, train_freq=4, gradient_steps=1, target_update_interval=5_000, exploration 1.0→0.05/fraction=0.1`；注意 checkpoint 默认不含 replay buffer。

**职责**：config 管所有数字；`train.py` 只做装配（ENV_REGISTRY 取工厂 → DummyVecEnv + VecTransposeImage + Monitor → 建模 → Checkpoint/EvalCallback → learn）；`ENV_REGISTRY` 保证实例隔离。

**中止规则**：fault 截断率 >20%/50局 或 OCR uncertain >30% → 停修 env；150k 步后滑动窗口回报无改善 → 停查奖励 bug 再议 DQN；墙钟 72h 硬上限（只做安全停机，不伪造奖励）；approx_kl 持续 >0.05 → 停。

**待验证假设**：H1 单步吞吐、H2 84×84 语义保留、H3 n_steps trade-off、H4 ent 探索、H5 CPU/内存、H6 输入可辨识度、H7 端到端吞吐——全部实现期实测。

详细笔记：`.scratch/wayfinding/research/08-training-plan-notes.md`（含 SB3 源码核验、预算数学、红队 12 项处置）。
