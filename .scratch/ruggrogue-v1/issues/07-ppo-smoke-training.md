# 07: PPO 短程训练冒烟

**What to build:** 将 `train.py` 和配置接入真实环境，完成一次短程 PPO 学习、保存和恢复，验证训练链路而非学习效果。

**Blocked by:** 06 (接通奖励与回合结算).

**Status:** claimed

- [ ] 使用 PPO `CnnPolicy`、单 env、`n_steps=1024` 和单帧灰度 `84×84`；至少完成两个 rollout 及参数更新，无 observation shape、dtype 或通道顺序错误。
- [ ] 生成 TensorBoard 日志和模型文件；加载模型后可对独立新局预测并执行动作。
- [ ] checkpoint 的 10k 步周期有自动化测试；短程结束仍保存最终模型，记录累计 timesteps。
- [ ] 接通明确的中止规则：B1–B4 复现、非有限奖励/损失及不可恢复运行故障不会静默继续；日志区分游戏结束、截断与技术 fault。
