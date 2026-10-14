Labels: wayfinder:research
Type: research
Status: resolved

## Answer

**决策：首版唯一奖励定义 = HUD OCR 差分（dense）+ 结算屏终局（sparse），公式如下。**

**信号来源**：回合内 HUD（Depth/Level/Experience/Health，等宽 OCR 友好，`src/ui.rs`）做差分塑形；死亡/胜利结算屏（胜负/Depth/Turns/Kills/伤害/死因，`src/modes/game_over.rs`）做终局。排除：分数（无该字段）、逐回合 Kills（HUD 无）、Turn 计数奖励（直接奖励等待）。

**公式（每回合，适配器维护 maxDepth/prevLevel/prevXP/prevHP）**：
- `+1.0 × max(0, depth − maxDepth)` —— 棘轮，只奖新纪录深度（起始深度不免费得分；上楼 0 分，封死反复上下楼）
- `+0.5 × max(0, Δlevel)`；`+0.001 × max(0, Δxp)`（升级回合忽略 xp 差分，防清零双算）
- `−0.01 × max(0, hp下降)` —— 只罚掉血不奖回血；`−0.001` 步罚（等待严格为负）
- 终局：死亡 `−1.0`、胜利 `+10.0`；回合预算 5000 截断走标准 bootstrap（`r_term=0`）；300 回合无进展截断 `−0.5`；OCR 连续失败 20 步截断 `r_term=0` 并单独上报
- Hunger 不进公式：官方确认为 soft timer（饿停回血、可饿死），经掉血/步罚自然传导

**触发与状态机**：`phase ∈ {TITLE, DUNGEON, GAMEOVER}`，奖励只在 DUNGEON；回合时钟以 HUD `Turn` 为准；结算屏检出优先于差分（死亡当回合跳过 r_dmg）；终局锁存保证终局奖励只发一次；新局重置全部基线。

**缺失/不确定**：单步失败沿用旧值记 uncertain；差分要求两端 certain 否则 0 分；基线只用 certain 更新，恢复后重定基线不补发；单步可信度门（`0≤hp≤max_hp`、`|Δdepth|≤1`、`Δlevel≤1`、跨字段一致）。

**漏洞审计**：等待/上下楼/自杀骗保/治疗刷分/OCR 正向噪声/终局重复结算已封堵；截断逃死与浅层刷怪已缓解（残余上界小，权重可调）；抢进度后弃局为塑形固有 trade-off（死亡 −1.0 / 胜利 +10 对冲）。

**防泄漏（关键）**：OCR 结构化数值仅走奖励通道，永不拼入策略观测；画面可含原生 HUD（类比 Atari 计分板）；适配器历史不进 observation；结算聚合只做终局奖励+日志。

**残余/实现期**：权重与阈值（5000/300/20）为初值待吞吐校准；XP 单调性、胜利触发文本、截断重置机制（全新 context vs 清档）待实现期确认。llmapi gpt-6-astra 红队审查发现 10 类漏洞，本契约已采纳修复（势函数塑形方案暂不采用）。

详细契约：`.scratch/wayfinding/research/06-reward-contract-notes.md`
Blocked by: 02, 03
Mode: AFK

## Question

首发游戏采用什么回报与回合判定契约？

选定奖励信号来源及唯一的首版奖励定义，说明采用画面识别、分数差分或获准使用的其他信号的理由。明确奖励公式、尺度、触发时机、胜负判定，以及 `terminated` 与 `truncated` 的区分。

同时规定信号缺失或识别不确定时的处理原则，检查刷分、停滞、重复奖励等漏洞。非画面信息若用于奖励或判定，必须注明是否允许进入策略观测，防止信息泄漏。本票不实现识别器。
