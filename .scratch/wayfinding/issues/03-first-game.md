Labels: wayfinder:research
Type: research
Status: resolved
Blocked by: 01, 02
Mode: AFK

## Question

首个目标游戏最终选择哪一个？

依据 `01` 的候选与 `02` 的边界，选择唯一首发目标，并固定游戏版本或发行来源、运行平台及预期运行模式。优先保证截图、控制、重置和奖励可行，而不是追求游戏复杂度。

产出选型决策、淘汰其他候选的理由，以及足以进入后续设计的可行性证据。若没有候选满足硬约束，明确阻塞原因并回开候选票，不把未经确认的条件视为成立。

## Answer

**决策：`tung/ruggrogue` 为唯一首发目标**（用户已否决 Docker，确认走 ruggrogue）。

- **版本/来源固定**：`v1.0.1`（tag `9f7ffd5c1a4b3630a6c88a5fe87f1c4e3c8d4f04`，最新 release；标题屏 `VERSION_STR` 亦为 `v1.0.1`）。仓库：https://github.com/tung/ruggrogue
- **许可**：代码 MIT，tile 图 CC0，字体 WTFPL —— 本地训练合规。
- **运行模式**：自托管静态文件（`python3 -m http.server`，见 `BUILD.md`）+ Playwright/Chromium + Xvfb；截图取 canvas，键盘注入为动作。

**可行性证据**（均出自仓库主源码，详见研究笔记）：

- 回合制：每次按键推进一回合（`TurnCount`），与 RL step 语义天然对齐。
- 纯键盘操作，无鼠标：8 向移动、`.`/Space/小键盘 5 为显式等待（天然 no-op）、Enter=Confirm、Esc=Cancel。
- 重置流程干净：死亡→结算屏按 Enter→标题屏；存档只在 quit/下楼梯/胜利时写入，死亡不写；全新浏览器 context 下 IDBFS 无存档，标题菜单首项 New Game 默认选中，按 Enter 直接开局；开局重随机 `GameSeed`。兜底：page reload + 全新 context。
- 奖励信号：回合内 HUD（Level/Experience/Health/Attack/Defense/Hunger/Depth/Turn，等宽高对比，OCR 友好）+ 结算屏（Depth/Turns/Kills/伤害统计/死因等）。

**淘汰理由**：

- DCSS webtiles：用户否决装 Docker（其 web 部署硬依赖），且复杂度/动作空间大。
- Desktop Dungeons HTML5：2010 年第三方转换版，现代浏览器兼容与许可风险最高。

**残余风险 / 待验证**（未在本票伪称已验证，归属 04/05/06 与实现期）：自托管产物缺口（仓库缺 `ruggrogue.wasm` + `deps/ruggrogue.data`，二选一：Emscripten 1.39.20 自建或取官方预构建）；Playwright 键鼠注入与截图在 Xvfb 下的延迟/焦点；console 捕获 `Game seed`；单局时长与步数吞吐。

详细研究笔记：`.scratch/wayfinding/research/03-first-game-notes.md`
