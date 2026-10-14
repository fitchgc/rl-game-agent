# 04: B2｜HUD OCR 可行性

**What to build:** 对真实游戏截图运行 HUD OCR，输出带可信状态的结构化读数，证明同步与奖励所需字段可可靠读取。

**Blocked by:** 02 (B4｜Headless WebGL 与截图冒烟).

**Status:** ready-for-agent

- [ ] 保存带人工标注的真实截图集，覆盖 TurnCount、Depth、等级、经验、生命值及其变化；可重放 OCR 并对照标注检查。
- [ ] 明确定义并实现 `certain` 判定；同字段重复识别一致且标注样本上的 `certain` 结果正确，不把默认值或猜测标为可信。
- [ ] 模糊、缺失或解析失败返回不可信状态，不沿用旧值冒充本帧读数。
- [ ] 提供一条命令生成可行性报告；OCR 始终不能产出 `certain` 时明确报 B2，停止下游。
