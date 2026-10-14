# 01: B1｜游戏文件与静态托管

**What to build:** 获取并固定 ruggrogue v1.0.1 完整运行文件，通过本地静态服务提供可启动的游戏 URL。

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] 记录文件来源、版本和校验值；`ruggrogue.wasm`、`ruggrogue.data` 及启动页所需资源齐全，不以占位文件绕过检查。
- [ ] 提供一条命令启动静态服务；浏览器请求游戏及资源成功，无关键资源 404 或加载错误。
- [ ] `required_files` 门禁在启动浏览器前检查资源；缺文件时明确报 B1，停止执行。
- [ ] 无法取得合法可用的完整文件时，保存阻塞报告，不标记解除、不推进下游。
