# 03: B3｜按键与回合同步探针

**What to build:** 在真实游戏中执行动作，保存按键、前后画面和 HUD 证据，确认回合推进及三类完成屏障可用。

**Blocked by:** 02 (B4｜Headless WebGL 与截图冒烟).

**Status:** ready-for-agent

- [ ] 验证 `Discrete(10)` 映射：0–7 为约定顺序的 vi 八向键，8 为 `.`，9 为 `[Enter,h,Enter]`；按键日志中不存在 Shift、Ctrl、Alt、Esc 注入。
- [ ] 普通消耗回合的动作可观察到 `TurnCount + 1`；探针阶段允许人工核对 HUD 证据，不依赖尚未验收的生产 OCR。
- [ ] 记录三选一屏障的判定与超时：`TurnCount + 1`、Depth 变化、双帧相同且等待 250ms；下楼宏在可下楼场景完成验证，不被拆成三个 agent step。
- [ ] 若消耗回合动作始终不能推进 TurnCount，明确报 B3；不得用静帧屏障掩盖该故障。
