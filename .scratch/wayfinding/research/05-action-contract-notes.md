# 05-action-contract 研究笔记

- 票据：wayfinder `05-action-contract`（动作契约）
- 首游：`tung/ruggrogue` v1.0.1（tag `9f7ffd5c1a4b3630a6c88a5fe87f1c4e3c8d4f04`），MIT 许可
- 一手来源：仓库 v1.0.1 源码（`src/gamekey.rs`、`src/player.rs`、`src/modes/dungeon.rs`、`src/modes/yes_no_dialog.rs`）+ SB3 官方文档 `guide/custom_env.html`
- 证据标签：= 已从源码逐行核实；= 浏览器/WASM 行为或实现期需实测

## 1. 按键映射（gamekey.rs，全文件 L0–L53）

`from_keycode`（L7–L53）：

- 八向移动：`Y/Kp7`=UpLeft，`K/Up/Kp8`=Up，`U/Kp9`=UpRight，`H/Left/Kp4`=Left，`L/Right/Kp6`=Right，`B/Kp1`=DownLeft，`J/Down/Kp2`=Down，`N/Kp3`=DownRight（L11–L25）。即 vi 键 `y u h j k l b n` 全覆盖八向。
- 等待：`Kp5 | Space` → `Wait`（L35）；`Period` 无 shift → `Wait`（L37）。
- 下楼：`Period` + shift → `Descend`；`Greater`（`>`）→ `Descend`（L37–L39）。
- `Escape` → `Cancel`（L41）；`Return | KpEnter` → `Confirm`（L43）。
- 物品键：`V`=ViewMap，`,/G`=PickUp，`I`=Inventory，`E/W`=Equip，`R`=Remove，`A`=Use，`D`=Drop（L45–L53）。

## 2. 回合语义（player.rs / dungeon.rs）



- `try_move_player`（player.rs L736–L832）：目标格有可战斗实体 → 加入近战队列，`took_time=true`（L782–L786）；目标格可走 → 移动，`took_time=true`（L788–L794）；撞墙/不可走 → `took_time` 保持 false。结尾 `took_time? TurnDone: NoResult`（L832）。**结论：撞墙不耗回合；撞怪=近战攻击，耗 1 回合。**
- `wait_player`（player.rs L834–L878）：`rest_in_place=false`（即无 shift）时直接落到 L878 返回 `TurnDone`。**结论：`.`/Space 无 shift 等待恒耗 1 回合。**
- `player_input`（player.rs L1036–L1164）：八向 → `try_move_player(world, dx, dy, shift)`，注意第四个参数是 shift，即**移动键带 shift 会触发 auto_run**（L1128–L1142）；`Wait` → `wait_player(world, shift)`，**等待键带 shift 会触发 rest 回血**（L1144）；`Cancel`（Esc）→ `ShowOptionsMenu` 弹菜单（L1146）；`Descend | Confirm` → `TryDescend`（L1150）；未映射键 → `NoResult`（L1164）。
- `player_try_descend`（player.rs L897–L911）：仅当脚下是 `Tile::DownStairs` 返回 true（L903），否则消息 "There is no way down here." 返回 false。dungeon.rs L199–L204：true → 压入 `YesNoDialogMode("Descend to the next level?", yes_default=false)`；false → `time_passed=false`，不耗回合。
- `YesNoDialogModeResult::Yes`（dungeon.rs L114–L122）：执行 `player_do_descend` 后返回 `time_passed=false`。**结论：下楼确认本身不耗回合。**
- `player_do_descend`（player.rs L913–L952）：`map.depth += 1`（L925），重建楼层；**不碰 TurnCount**。
- 回合时钟：dungeon.rs L216–L221，`time_passed=true` 时怪物行动、饥饿 tick，最后 `TurnCount += 1`（L220）。**结论：TurnCount 是唯一回合计数器；下楼不增加它。**
- `yes_no_dialog.rs`：构造 `new(prompt, yes_default)`（L40–L42）；`Left` → `yes_selected=true`（L81）；`Confirm`（Enter）→ 按 `yes_selected` 返回 Yes/No（L85）；`Cancel`（Esc）→ No（L85–L86）。**结论：下楼确认框默认 No，确认序列为 `Left`（或 `h`）+ `Enter`。**

## 3. 修饰键禁令的依据

player.rs L1128–L1144 + L1064–L1108：

- 移动键带 shift → `try_move_player(..., start_run=true)` → 可能启动 `AutoRun`（走廊/直线自动跑，limit 200，L812–L832），之后每回合自动移动直到手动打断。**策略将失去对回合的控制。**
- 等待键带 shift → `wait_player(world, rest_in_place=true)` → 若可回血则启动 `RestInPlace` auto_run（limit 400，L872–L878）。**同上。**
- 结论：v1 注入永不带 Shift/Ctrl/Alt；下楼不用 `>`/`Shift+.`，改用与之等价的 `Enter`（`Descend|Confirm → TryDescend`，player.rs L1150；游戏内提示 "(Press 'Enter' to descend.)"，player.rs L1028–L1033）。

## 4. SB3 动作空间支持

SB3 官方文档 `guide/custom_env.html`：

- 自定义环境只需实现 gymnasium 接口；示例直接用 `spaces.Discrete(N_DISCRETE_ACTIONS)`（L104–L107）。
- 限制：`Discrete`/`MultiDiscrete` 不支持 `start!= 0`（L26–L28），我们的 `Discrete(10)` start=0，无需 wrapper。
- 实现期用 `stable_baselines3.common.env_checker.check_env` 校验（L150–L162）。

## 5. 被排除的替代方案及理由

| 方案 | 结论 | 依据 |
|---|---|---|
| 方向键八向 | 不用。方向键只有四向；vi 键是唯一单键八向且布局稳定 | gamekey.rs L11–L25 |
| 小键盘八向 | 不用。依赖物理小键盘与 NumLock，浏览器事件翻译验证面大 | gamekey.rs L11–L25；浏览器行为 |
| `Space` 等待 | 不用。失焦时浏览器滚屏；`.` 无此风险 | gamekey.rs L35；滚屏 |
| `>`/`Shift+.` 下楼 | 不用。依赖修饰键+键盘布局；`Enter` 等价且无修饰键 | gamekey.rs L37–L39，player.rs L1150 |
| 物品键（i/g/a/d/w/e/r） | v2。进模态菜单，破坏"一步一回合"同步 | player.rs L1152–L1162（各进 modal）；v2 协议未定 |
| `Esc` | 永不注入。dungeon 内 Esc 弹 options 菜单 | player.rs L1146 |
| action masking | v1 不用。脚本禁读状态替策略筛选动作（防规则机器人） | 项目契约决策 |

## 6. 待验证清单（实现期）

1. WASM 前端按键事件 → `Keycode` 翻译与桌面端 `gamekey::from_keycode` 等价（源码是 SDL2 桌面构建路径）。
2. Xvfb + Chromium 下 Playwright 注入延迟、焦点行为、`<50ms` 按保持目标。
3. 同步三条件（TurnCount+1 / Depth 变化 / 双帧相同+250ms）的误判率，尤其是"画面未更新"被误判为 no-op。
4. 下楼确认框出现时延 vs 300ms 等待上限。
5. `check_env` 校验 + 墙/怪/等待/楼梯/非楼梯/重置场景测试。

## 7. 起草说明

- 本票起草经 llmapi（gpt-6.1-sol）辅助，结论与行号引用由本代理逐条校准；llmapi 草稿曾把"动作 9 条件宏 vs 禁止状态分支"标为未决阻塞项，已由本票决议收敛为"UI 握手例外"（见票据 Answer §5），不再是开放问题。
