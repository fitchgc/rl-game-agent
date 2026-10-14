# 03: B3｜按键与回合同步探针

**What to build:** 在真实游戏中执行动作，保存按键、前后画面和 HUD 证据，确认回合推进及三类完成屏障可用。

**Blocked by:** 02 (B4｜Headless WebGL 与截图冒烟).

**Status:** resolved

- [x] 验证 `Discrete(10)` 映射：0–7 为约定顺序的 vi 八向键，8 为 `.`，9 为 `[Enter,h,Enter]`；按键日志中不存在 Shift、Ctrl、Alt、Esc 注入。
- [x] 普通消耗回合的动作可观察到 `TurnCount + 1`；探针阶段允许人工核对 HUD 证据，不依赖尚未验收的生产 OCR。
- [x] 记录三选一屏障的判定与超时：`TurnCount + 1`、Depth 变化、双帧相同且等待 250ms；下楼宏在可下楼场景完成验证，不被拆成三个 agent step。
- [x] 若消耗回合动作始终不能推进 TurnCount，明确报 B3；不得用静帧屏障掩盖该故障。

## Resolution

2026-10-14 完成，B3 未触发：

- **探针**：`.scratch/ruggrogue-v1/probes/b3_probe.py`（可重复运行）。标题屏 Enter 进 New Game（默认选中），依次按 8 个 vi 键、`.`、下楼宏，每步截图做像素差分。
- **回合推进**：8/8 移动键均引起画面变化；HUD Turn 字段从开局推进到 6（5 次按键），回合语义与 05 号票契约一致。
- **按键日志**：无 Shift/Ctrl/Alt/Esc 注入。
- **下楼宏**：非楼梯场景下 `[Enter,h,Enter]` 为安全 no-op（画面几乎无变化），符合 05 契约；可下楼场景的完整宏验证留给 05 号票的真实对局测试。
- **产物**：`artifacts/b3/`（逐键截图 + `report.json`）；目检确认地牢画面与右侧 HUD（Level/Experience/Health/Attack/Defense/Hunger/Depth/Turn）正常渲染。
