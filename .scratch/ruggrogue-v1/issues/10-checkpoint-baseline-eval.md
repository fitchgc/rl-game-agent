# 10: 执行 checkpoint 与基线评估

**What to build:** 对正式训练的每个 checkpoint 及两种基线执行统一评估，产出可审计的深度表现对比。

**Blocked by:** 08 (执行 400k 正式训练), 09 (实现统一 evaluate.py).

**Status:** ready-for-agent

- [ ] 每个 checkpoint 评估 10 attempts；random、wait-only 各执行同样数量，使用一致的 seed 列表、回合预算、奖励配置和 fault 判定。
- [ ] 保存每个 attempt 的策略、checkpoint、seed、最大深度、结束原因、fault 状态及必要诊断产物，支持追溯和重跑。
- [ ] 输出 checkpoint 对比表及 `mean_max_depth` 曲线，同时列出有效样本数和 fault 统计；不混入被剔除回合，也不把缺失评估当作零分。
- [ ] 报告与基线的差异及仅 10 attempts 的样本限制；评估成功以流程完整和结果可信为准，不以 PPO 必须优于基线为验收条件。
