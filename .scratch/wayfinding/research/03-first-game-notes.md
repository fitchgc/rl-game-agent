# 03-first-game 研究笔记

## 1 决策

- 【文档可证实】选择 `tung/ruggrogue`：游戏使用 Rust + SDL2，并通过 Emscripten 移植到浏览器。
- 【用户已决策】第一阶段采用网页游戏（02 号票）。
- 原生 Linux 二进制（`cargo build`）是自动化更简单的 fallback，但本票不采用，仅记录。

## 2 版本与来源固定

- 【文档可证实】仓库：https://github.com/tung/ruggrogue
- 【文档可证实】版本固定为 `v1.0.1`，为最新 release；对应 tag：`9f7ffd5c1a4b3630a6c88a5fe87f1c4e3c8d4f04`。
- 【文档可证实】`master` HEAD：`164ff8380deb21964cbe65bd60db7c5cd7dbd107`。
- 【文档可证实】标题屏 `VERSION_STR` 也是 `v1.0.1`。

## 3 许可

- 【文档可证实】代码采用 MIT 许可，见 `LICENSE.txt`。
- 【文档可证实】tile 图采用 CC0 许可，来自 Urizen 1Bit Tilesets。
- 【文档可证实】字体 GohuFont 采用 WTFPL 许可。
- 【文档可证实】本地训练使用合规。

## 4 运行模式

- 【文档可证实】浏览器版本通过 Emscripten 移植。
- 【文档可证实】`BUILD.md` 给出使用 `python3 -m http.server` 静态托管的流程。
- 【文档可证实】`index.html` 将 canvas 全屏，并将 IDBFS 挂载到 `/ruggrogue` 用于存档。
- 原生 Linux 二进制（`cargo build`）仅作为 fallback 记录，不属于本票采用的运行模式。

## 5 输入与动作空间

【文档可证实】游戏采用纯键盘操作，无鼠标。来源：`src/gamekey.rs`、`README` 的 Controls 部分。

| 标签 | 操作 | 按键 |
|---|---|---|
| 【文档可证实】 | 移动 | 方向键、vi 键、小键盘八向 |
| 【文档可证实】 | 等待一回合，天然 no-op | `.`、`Space`、小键盘 `5` |
| 【文档可证实】 | Confirm | `Enter`，对应 `Keycode::Return \| KpEnter` |
| 【文档可证实】 | Cancel | `Esc` |
| 【文档可证实】 | 物品键 | `i` / `g` / `a` / `d` / `w` / `e` / `r` |

## 6 回合制与 step 语义

- 【文档可证实】游戏为回合制，每次按键输入推进一回合，使用 `TurnCount` 计数。
- 【文档可证实】RL step 语义天然对齐。

## 7 重置流程

来源：`src/modes/title.rs`、`src/modes/game_over.rs`。

- 【文档可证实】死亡后进入结算屏，在结算屏按 `Enter` 返回标题屏。
- 【文档可证实】存档只在 quit 确认、下楼梯、胜利时写入；死亡不写存档。
- 【文档可证实】全新浏览器 context 下，IDBFS 无存档；标题菜单首项为 `New Game` 且默认选中，按 `Enter` 直接开局。
- 【文档可证实】开局时通过 `post_game_cleanup` 重新随机生成 `GameSeed`。
- 【文档可证实】开局时 `println!("Game seed: {}", ...)` 打印种子到 stdout（src/modes/title.rs `print_game_seed`）。
- 【待验证假设】Web 下 stdout 是否进浏览器 console、Playwright 捕获 `Game seed` 的实际可行性仍需验证。

## 8 奖励信号来源（HUD/结算屏）

### 8.1 回合内 HUD

- 【文档可证实】`src/ui.rs` 中的 HUD 字段包括：
  - `Level`
  - `Experience`：条形显示 + 数字
  - `Health`：条形显示 + `hp/max_hp`
  - `Attack`
  - `Defense`
  - `Hunger`
  - `Depth`
  - `Turn`
- 【文档可证实】HUD 使用等宽字体、高对比显示，OCR 友好。

### 8.2 结算屏

- 【文档可证实】`src/modes/game_over.rs` 中的结算屏字段包括：
  - 胜负
  - `Defeated by`
  - `Level`
  - `Experience`
  - `Health`
  - `Attack`
  - `Defense`
  - `Depth`
  - `Turns`
  - `Items carried`
  - `Weapon`
  - `Armor`
  - `Damage dealt/taken`
  - `Foes defeated`（kills）

## 9 自托管缺口

- 【文档可证实】`BUILD.md` 明确要求 Emscripten `1.39.20`，并注明新版不行。
- 【文档可证实】Web 构建产物为：
  - `ruggrogue.wasm`
  - `ruggrogue.js`
  - `deps/ruggrogue.data`
- 【文档可证实】仓库根目录已包含 `index.html` 和 `ruggrogue.js`，但缺少 `.wasm` 和 `.data`。
- 【待验证假设】自托管产物获取路径二选一：
  1. 按 `BUILD.md` 自建旧工具链。
  2. 从官方托管页获取预构建产物。
- 【待验证假设】具体 URL 与字节一致性需在 04 号票或实现期验证。

## 10 淘汰理由

- **DCSS webtiles**：用户已否决安装 Docker，而其 Web 部署硬依赖 Docker；此外，复杂度和动作空间大。
- **Desktop Dungeons HTML5**：属于 2010 年第三方转换版，现代浏览器兼容与许可风险最高。

## 11 待验证假设清单

以下归属用于安排验证工作，不表示已完成验证。

| 标签 | 待验证项 | 验证归属 |
|---|---|---|
| 【待验证假设】 | 自托管产物获取路径：按 `BUILD.md` 自建旧工具链，或从官方托管页获取预构建产物；验证具体 URL 与字节一致性 | 04 / 实现期 |
| 【待验证假设】 | Playwright 键盘注入与 canvas 截图在 Xvfb 下的延迟、焦点行为 | 05 / 实现期 |
| 【待验证假设】 | console 捕获 `Game seed` 的可行性 | 05 / 实现期 |
| 【待验证假设】 | 单局时长与步数吞吐 | 06 / 实现期 |

## 12 来源 URL 列表

- 【文档可证实】GitHub 仓库：https://github.com/tung/ruggrogue
- 【文档可证实】官网（含浏览器试玩入口）：https://tung.github.io/ruggrogue/
- 【文档可证实】itch.io 页：https://tungtn.itch.io/ruggrogue
- 【文档可证实】源码：`src/modes/title.rs`、`src/modes/game_over.rs`、`src/modes/dungeon.rs`、`src/ui.rs`、`src/gamekey.rs`、`src/item.rs`、`BUILD.md`、`index.html`（均为仓库内主源码，`v1.0.1` tag / master `164ff838`）
