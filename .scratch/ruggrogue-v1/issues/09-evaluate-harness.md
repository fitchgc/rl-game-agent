# 09: 实现统一 evaluate.py

**What to build:** 实现统一评估 harness，使 checkpoint、random 和 wait-only 策略都能通过相同 episode 流程产生逐次记录与汇总指标。

**Blocked by:** 06 (接通奖励与回合结算).

**Status:** ready-for-agent

- [ ] checkpoint 使用 `deterministic=True`；random 从同一动作空间采样，wait-only 始终执行动作 8；支持固定 seed、策略选择和机器可读输出。
- [ ] 每个 checkpoint 固定执行 10 attempts；fault attempt 整回合剔除，不补跑成"10 个有效回合"，独立报告 fault 原因、数量及有效样本数。
- [ ] 主指标 `mean_max_depth` 仅对有效 attempts 的 episode 最大深度求均值；零有效样本输出不可用而非零，预算/停滞截断不自动视为 fault。
- [ ] 评估启动独立浏览器实例，不复用训练状态或更新模型；通过合成 fault 测试及真实 wait-only 短程冒烟，验证清理、剔除和汇总行为。
