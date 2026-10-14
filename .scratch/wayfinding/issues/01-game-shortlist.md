Labels: wayfinder:research
Type: research
Status: resolved
Blocked by: 无
Mode: AFK

## Question

哪些游戏应进入首个目标游戏的候选短名单？

限定比较至多 3 个候选，以官方文档或可信公开资料核对：可合法本地运行、画面可获取、输入可自动化、可稳定重置、回合较短、奖励可识别、资源需求适中。

产出一个排序短名单，为每个候选注明支持的平台、主要风险和待用户确认的条件。此票只决定候选范围，不替用户确定运行条件，也不最终选择游戏。

## Answer

**建议短名单排序：① DCSS 自建 webtiles Sprint → ② ruggrogue web → ③ Desktop Dungeons HTML5。**

02 号票约束已落实：仅网页、roguelike、回合制优先；目标环境为无头 Linux + Xvfb、纯 CPU，墙钟预算几天。本机已确认无 Docker、无 Chromium/Firefox；**三者均未完成本机闭环与吞吐验证**。

| 候选 | 是否回合制 | 重置方式 | 奖励信号来源 | 主要风险 | 待确认条件 |
|---|---|---|---|---|---|
| **1. DCSS webtiles Sprint** | 是 | 菜单开新局；文档有种子模式，Sprint 组合与自动化待验 | 【文档可证实】morgue 局末统计（score/XL/深度/死因）；【待验证】局内 HUD OCR | 复杂度高、动作多；需装 Docker；GPLv2 合规 | 接受复杂度及动作裁剪；愿装 Docker/浏览器；验证步数、字段稳定性和输入延迟 |
| **2. ruggrogue web** | 是 | 开新局，具体按键与流程待验 | 【待验证】深度、等级、击杀等 HUD 字段及读取方式 | 代表性可能偏弱；焦点、重置和奖励接口未验证 | 接受简单度；愿装浏览器；验证本地静态运行、canvas 输入和单局时长 |
| **3. Desktop Dungeons HTML5** | 是，偏回合解谜 | 拟用重开按钮，位置与流程待验 | 【待验证】分数显示及读取方式 | 旧第三方转换，兼容性与维护风险最高；许可需核查 | 接受第三方转换；验证现代浏览器运行、鼠标交互及重开闭环 |

**来源 URL：**

- DCSS：https://github.com/nkhoit/dcss-webtiles（Docker 自建，含 Sprint/种子/教程模式，GPLv2）；官方在线入口 https://crawl.develz.org/；morgue 说明 https://wiki.tilde.institute/w/dcss
- ruggrogue：https://github.com/tung/ruggrogue（MIT，仓库自带 web 构建可本地静态托管）；网页版 https://tung.github.io/ruggrogue/
- Desktop Dungeons：http://www.desktopdungeons.net/HTML5（官方站链接的 Laurent Vaucher 第三方转换版）；官方免费页 https://www.desktopdungeons.net/media/；RPS 报道 https://www.rockpapershotgun.com/the-deeper-dungeons-desktop-dungeons-out-next-week

**淘汰一句话**：Brogue CE、Shattered Pixel Dungeon 缺少官方 web 路径；上一轮 Atari Pong / Chrome Dino / ViZDoom 不满足"仅网页 + roguelike"新约束；2048 非 roguelike；NetHack 公共服务器受 ToS、自动化许可及网络依赖限制。

**待用户确认**：DCSS 复杂度与动作裁剪接受度；ruggrogue 简单度接受度；DD 第三方转换版接受度；是否愿在本机安装 Docker 和浏览器（若不愿装 Docker，优先 ruggrogue 本地静态版）。

详细研究笔记：`.scratch/wayfinding/research/01-game-shortlist-notes.md`
