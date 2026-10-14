# 06-reward-contract 研究笔记（ruggrogue v1.0.1 首版奖励契约）

> 决策票据：`.scratch/wayfinding/issues/06-reward-contract.md`
> 前置：03（ruggrogue v1.0.1 唯一首发）、02（VM 无头+Xvfb、纯 CPU、几天预算、网页游戏、roguelike）
> 本票只定契约，不实现识别器；数值权重为初值，实现期按吞吐实测校准。

## 1 决策总览

- **奖励来源**：回合内 HUD OCR 差分（dense）+ 结算屏终局统计（sparse terminal）。
- **策略观测**：只给游戏画面像素；OCR 结构化数值仅走奖励通道，永不拼入观测（§8 防泄漏）。
- **公式结构**：差分塑形 + 深度棘轮 + 步罚 + 终局结算；另有 OCR 可信度门、阶段状态机、终局锁存。

## 2 信号来源（唯一选定）

| 信号 | 来源 | 用途 | 依据 |
|---|---|---|---|
| `Depth` / `Level` / `Experience` / `Health(hp/max_hp)` 差分 | 回合内 HUD OCR（`src/ui.rs`，等宽高对比） | dense 塑形奖励 | 03 号票：HUD 字段清单出自仓库主源码 |
| 胜负 / `Depth` / `Turns` / `Kills` / 伤害统计 / 死因 | 死亡-胜利结算屏 OCR（`src/modes/game_over.rs`） | 终局奖励与日志指标 | 03 号票：结算屏字段出自仓库主源码 |
| `Turn`（HUD） | 回合计数器 | 步数预算与停滞检测的权威时钟 | 回合制、每按键推进一步（03） |

**排除**：分数差分（无 score 字段）；console `Game seed`（非奖励信号）；像素变化启发式（噪声大、HUD 已够用）；逐回合 Kills（HUD 无该字段，结算屏才有，记为指标不计奖）。

**理由**：roguelike 终局信号极度稀疏，纯终局 ±1 在 CPU+几天预算下 PPO 学不动；HUD 每回合可用且 OCR 友好，是唯一的 dense 通道；Kills 等只在结算出现，天然适合终局。

## 3 奖励公式（v1，唯一）

适配器维护回合状态：`maxDepth`、`prevLevel`、`prevXP`、`prevHP`、`phase`。每回合（动作注入→等一回合→截图→OCR）：

- `r_depth = +1.0 × max(0, depth_t − maxDepth_{t−1})` —— 棘轮：只奖新纪录深度；上楼/回旧层得 0。`maxDepth` 初始化为首个 certain 读到的 depth（起始深度不免费得分）。
- `r_level = +0.5 × max(0, level_t − level_{t−1})`
- `r_xp = +0.001 × max(0, xp_t − xp_{t−1})`；**若本回合 level 上升，忽略 xp 差分**（防升级清零/扣阈值导致的漏算或双算；升级奖励已由 r_level 支付）。
- `r_dmg = −0.01 × max(0, hp_{t−1} − hp_t)` —— 只罚掉血，不奖回血（防治疗刷分）。
- `r_step = −0.001` —— 每回合时间成本；显式等待（`.`）严格为负。
- 终局（结算屏检出，见 §4）：死亡 `r_term = −1.0`；胜利 `r_term = +10.0`；截断 `r_term` 见 §5。
- **Hunger 不进公式**：饥饿是游戏内建 soft timer（官方源码指南确认：饱食度耗尽→停回血→掉血可致死），通过 r_dmg 与 r_step 自然传导；v1 不直接奖惩 Hunger 数值，避免与游戏机制打架。

权重初值按"深度主导、战斗次之、生存约束"设定；α/β/步罚实现期校准。

## 4 阶段状态机与触发时机

- `phase ∈ {TITLE, DUNGEON, GAMEOVER}`；奖励逻辑只在 `DUNGEON` 激活。
- 回合时钟以 HUD `Turn` 为准（非按键计数）：菜单/结算屏按键不推进 Turn 的回合奖励为 0，且不计入预算与停滞检测。
- 结算屏检出顺序优先：先判终局（胜/死），再算回合差分；**死亡当回合跳过 r_dmg**（致命伤不双罚，−1.0 已覆盖）。
- 终局锁存：terminated/truncated 置位后，env 拒绝继续 step 直到 reset；终局奖励恰好发放一次（防结算屏重复解析刷 +10）。

## 5 terminated 与 truncated（语义区分）

- `terminated=True`（真实终局，价值不 bootstrap）：
- 死亡（结算屏报负）：`r_term = −1.0`
- 胜利（结算屏报胜）：`r_term = +10.0`（胜利触发文本实现期核实）
- `truncated=True`：
- 回合预算：HUD Turn 达 5000（初值）→ 标准 time-limit 语义，`r_term = 0`，SB3 正常 bootstrap（不视为"安全退场"套利：价值函数仍计入未来回报）。
- 停滞检测：连续 300 回合无进展（maxDepth/level/xp 任一无正向 certain 变化）→ `r_term = −0.5`，不 bootstrap。残余套利上界约 0.2（300×步罚 + 饥饿），可接受，权重可调。
- OCR/链路连续失败 20 步 → `r_term = 0`，`info["reason"]="ocr_failure"`，不 bootstrap，按 09 要求单独计数上报。
- 冲突优先级：胜/死终局 > 回合预算 > 停滞 > OCR 失败（同回合既到预算又死亡，按死亡结算）。
- 截断时游戏仍在运行：重置路径不得加载中途存档（03：quit/下楼会写档，死亡不写）。实现期用全新 context 或清档，具体机制归实现，约束在此。

## 6 信号缺失 / OCR 不确定处理

- 单步某字段 OCR 失败：沿用上次值，该步记 `uncertain`；**差分奖励要求两端读数皆 certain**，否则该分量为 0。
- 基线只用 certain 读数更新；uncertain 区间恢复后**重新定基线，不补发**跳过的区间奖励（保守：宁可漏发，不得多发）。
- 单步可信度门（防正向噪声套利）：`0 ≤ hp ≤ max_hp`；单回合 `|Δdepth| ≤ 1`、`Δlevel ≤ 1`、`Δxp ≤ 上限（实现期按怪物经验表定，初值宽松）`；跨字段一致（hp 下降而 Health 条未变→ uncertain）。违例字段记 uncertain。
- uncertain 连续 ≤20 步：carry-forward 继续；>20 步：按 §5 截断。

## 7 刷分漏洞审计（已封堵/已缓解）

| 漏洞 | 状态 |
|---|---|
| 原地等待刷回合 | 已封堵：r_step<0，且饥饿 soft timer 会饿死挂机者 |
| 反复上下楼 | 已封堵：深度棘轮，上楼 0 分，下回 0 分 |
| 自杀骗保 | 已封堵：死亡 −1.0 主导；Kills 只记指标不给分 |
| 治疗刷分 | 已封堵：只罚掉血不奖回血 |
| OCR 正向噪声（误读升高→回落不扣） | 已封堵：§6 可信度门 + 两端 certain 才计分 |
| uncertain 边界洗伤害 | 已封堵：uncertain 差分不计分；恢复重定基线不补发 |
| 终局重复结算刷 +10 | 已封堵：终局锁存，一次发放 |
| 截断逃死（濒死拖到截断） | 已缓解：预算截断走标准 bootstrap（非免费退场）；停滞截断 −0.5；饥饿+步罚使拖延有成本；残余上界小 |
| 浅层无限刷怪 | 已缓解：怪物有限 + 饥饿 timer + 步罚；eval 期监控 xp/turn（归 09） |
| 抢进度后弃局（拿分即死） | 接受：塑形固有 trade-off；死亡 −1.0 与胜利 +10.0 对冲；权重可调 |
| 回血掩盖承伤（同回合受伤+回血净零） | 接受并记录：HUD 只显示终值，无法区分；β 保守初值，实现期评估 |

## 8 防信息泄漏规则

- 策略观测 = 游戏画面像素（04 定裁剪/预处理；HUD 作为原生渲染可出现在画面中，类比 Atari 计分板，允许）。
- OCR 结构化数值（depth/xp/hp 等）**仅限奖励通道**：在适配器内计算，永不拼入观测、永不作为 side-channel 特征。
- 适配器回合历史（maxDepth/prev 值）驻留适配器进程，不进 env observation。
- 结算屏聚合（Kills/伤害/死因）：终局奖励 + 日志指标，不喂给策略。
- 理由：数值是特权信息（像素玩家需自行估计）；喂给策略会练出依赖 OCR 通道的策略，无法迁移到纯视觉。

## 9 明确拒绝的替代方案

- 纯稀疏终局 ±1：CPU+几天预算下学不动，拒绝。
- 奖励 Turn 数：直接奖励等待，拒绝。
- 逐回合 Kills 密集奖励：HUD 无 kills，需精灵差分，噪声大，v1 拒绝。
- 奖励 Hunger 数值 / 吃口粮：与游戏内建机制耦合过深，v1 拒绝（饥饿经 r_dmg/r_step 传导已足够）。

## 10 红队审查（llmapi gpt-6-astra，2026-10-14）

- 发现 10 类漏洞与 10 处边缘情况；本契约已采纳修复：阶段状态机、终局锁存、冲突优先级、OCR 可信度门、基线更新规则、跨局状态重置、预算截断 bootstrap 语义、XP 升级回合特殊处理。
- 未采纳：改用势函数塑形 `γΦ(s′)−Φ(s)`（v1 保持显式差分公式以便实现与调试；08/09 若发现塑形偏差再议）。

## 11 残余风险 / 实现期校准（不属本票）

- α/β/步罚/预算与阈值（5000/300/20）均为初值，按 04/05 实测吞吐校准。
- XP 单调性与升级清零行为、HP 解析格式、胜利触发文本、Depth 起始值：实现期对照源码/实测确认。
- 截断重置的具体机制（全新 context vs 清档）。
- 刷怪收益的长期监控（09 评估协议）。

## 12 来源

- ruggrogue 仓库主源码（v1.0.1，`src/ui.rs` HUD 字段、`src/modes/game_over.rs` 结算字段、`src/gamekey.rs` 等待键）：https://github.com/tung/ruggrogue
- 官方源码指南·饥饿与回血（饥饿为 soft timer，starving 掉血可致死）：https://tung.github.io/ruggrogue/source-code-guide/hunger-and-regeneration.html
- 本项目 03 号票研究笔记：`.scratch/wayfinding/research/03-first-game-notes.md`（HUD/结算屏字段清单、重置流程、回合制语义）
