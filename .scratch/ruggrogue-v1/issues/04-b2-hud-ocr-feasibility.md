# 04: B2｜HUD OCR 可行性

**What to build:** 对真实游戏截图运行 HUD OCR，输出带可信状态的结构化读数，证明同步与奖励所需字段可可靠读取。

**Blocked by:** 02 (B4｜Headless WebGL 与截图冒烟).

**Status:** resolved

- [x] 保存带人工标注的真实截图集，覆盖 TurnCount、Depth、等级、经验、生命值及其变化；可重放 OCR 并对照标注检查。
- [x] 明确定义并实现 `certain` 判定；同字段重复识别一致且标注样本上的 `certain` 结果正确，不把默认值或猜测标为可信。
- [x] 模糊、缺失或解析失败返回不可信状态，不沿用旧值冒充本帧读数。
- [x] 提供一条命令生成可行性报告；OCR 始终不能产出 `certain` 时明确报 B2，停止下游。

## Resolution

2026-10-14 完成，B2 未触发。关键发现：**tesseract 不可行，模板匹配可行**。

- **tesseract 路线已否决**：像素字体的系统性混淆（`1`→`4`、`0`→`@`），单字形孤立识别直接返回空；调参（psm/oem/二值化/放大）无法根治。
- **采用模板匹配**：`.scratch/ruggrogue-v1/probes/b2_probe.py`。Phase 1 从人工标注截图提取字形模板（归一化 12×18 二值图）；Phase 2 在全新截图上按列投影切分字形、模板最小平均差分匹配。`certain` 定义：全部字形匹配分差 ≤ 0.18 且模式合法（如 Health 必须含 `/`）；否则 `uncertain`，绝不猜测。
- **验证结果**：新截图上 Level=1、Experience=0、Health=30/30、Depth=1、Turn=5 全部 `certain`（分差 0.074–0.146，远低于阈值）。
- **覆盖范围诚实声明**：当前模板仅覆盖 {0,1,3,5,/}；未覆盖数字自动判 `uncertain`（符合 06 契约的失败处理），在 05/06 号票测试中按"采集-标注-入库"流程补齐。
- **产物**：`artifacts/b2/`（annotate.png、verify.png、templates/、report.json）。
