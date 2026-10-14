Labels: wayfinder:research
Type: research
Status: open
Blocked by: 04, 05, 06
Mode: AFK

## Question

每个游戏的轻量适配脚本对公共框架暴露什么最小接口？

基于已定观测、动作与奖励契约，定型一份语言无歧义的 Python 接口规格：输入输出、数据类型、状态归属、调用顺序、异常语义，以及启动、重置、清理的责任边界。

明确公共框架负责哪些能力，per-game 脚本负责哪些能力；说明其如何映射 Gymnasium 的 `reset` / `step` 返回值，并接入现有环境注册表。若所选游戏没有可靠重置路径，应暴露阻塞而非隐去问题。

交付接口表与文字时序，不编写模块、函数体或适配脚本。
