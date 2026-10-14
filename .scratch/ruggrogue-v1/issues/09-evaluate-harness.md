# 09: 实现统一 evaluate.py

**What to build:** 实现统一评估 harness，使 checkpoint、random 和 wait-only 策略都能通过相同 episode 流程产生逐次记录与汇总指标。

**Blocked by:** 06 (接通奖励与回合结算).

**Status:** resolved

- [x] checkpoint 使用 `deterministic=True`；random 从同一动作空间采样，wait-only 始终执行动作 8；支持固定 seed、策略选择和机器可读输出。
- [x] 每个 checkpoint 固定执行 10 attempts；fault attempt 整回合剔除，不补跑成"10 个有效回合"，独立报告 fault 原因、数量及有效样本数。
- [x] 主指标 `mean_max_depth` 仅对有效 attempts 的 episode 最大深度求均值；零有效样本输出不可用而非零，预算/停滞截断不自动视为 fault。
- [x] 评估启动独立浏览器实例，不复用训练状态或更新模型；通过合成 fault 测试及真实 wait-only 短程冒烟，验证清理、剔除和汇总行为。

## Resolution

2026-10-14 实现完成。改动：`src/rl_game_agent/evaluate.py`（占位 → 完整 harness，约 330 行）。

**实现要点**
- CLI：`--model/--episodes/--deterministic/--no-deterministic/--baseline{none,random,wait}/--out/--max-eval-minutes/--seed`；`--model` 仅在 baseline=none 时必需。
- 自定义循环（不用 SB3 EvalCallback），逐 step 采集全部 info 键；fault 分类与汇总逻辑为纯函数（`classify_attempt`/`summarize`），可脱离浏览器单测。
- fault 定义：`truncated_kind ∈ {fault, ocr}` 或 attempt 内异常 → 整回合剔除；budget/stagnation/死亡计入策略指标；`fault_attempts > 2` → LINK-RED（退出码 2）；零有效样本 → 指标 UNAVAILABLE。
- 评估 env 为 `ENV_REGISTRY["ruggrogue-v1"]()` 全新实例（独立浏览器；每 attempt 的 reset 建全新 context）；`--model` 路径 obs 预处理与 08 号票训练约定一致（(84,84)→(1,84,84) 当模型期望 3 维）。
- 产物：`episodes.jsonl`（逐 attempt）+ `summary.json` + 终端表；退出码 0/2/1。

**验证**
- 合成 fault 测试（`/tmp/test_eval_logic.py`，4 组全过）：fault/ocr/crash 剔除、budget/stagnation 计入、零有效→unavailable、LINK-RED 阈值（>2 触发、=2 不触发）。
- 真实 wait-only 冒烟（2 attempts，约 9.8 分钟）：均 300 步后 stagnation 截断，verdict 均为 valid；mean_max_depth=1.00，fault_rate=0%，LINK-RED=False，退出码 0；报告与 jsonl/summary 正常落盘（`/tmp/eval-smoke/`）。

**重要发现（影响 08 号票）**：实测吞吐约 **1.0 step/s**（sync p50 649ms + 截图/OCR 开销），慢于 08 号票预算数学假设的 ~2 step/s。按此速度 400k 步需约 111 小时，超过 72h 墙钟预算——08 号票执行前建议重校步数预算或先做 10k 步吞吐校准（08 票已有该校准项）。

**残余风险**：`--model` 路径未实测（无已训练模型；训练是 08 号票）；obs 通道顺序约定依赖 07 号实现票的训练 env 采用同一封装；ocr_uncertain_rate 19%（wait-only 下）， uncertain 读数按契约不参与差分。
