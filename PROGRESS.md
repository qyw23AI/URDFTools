# URDFTools 项目进度

2026-10-22：已完成需求基线、整体架构、开源研究、评估方法、数据契约和阶段队列设计。产品功能尚未实现，不标记任何开发阶段完成。

已存在：bootstrap 调度器、Git 仓库和 6 小时 systemd timer。历史轻量探测曾验证 Sol Medium/Astra xHigh 可通过 ChatGPT CLI 返回响应，不能据此宣称功能完成。

下一任务：S00，由 Sol High 加固调度器；随后按依赖图和额度逐阶段执行。当前架构聊天在启动交接后结束，不直接实现产品功能。

已知约束：GPU 驱动不可用；需要独立开发 Python 3.12/Node 工具链；用户未提供自己的机器人文件，因此初始验收用公开合法参考模型与自制变体，不能声称已评估用户真实机器人。

各阶段完成后追加摘要、测试结果、产物路径、剩余问题及下一任务。机器状态以 `.scheduler/state.json` 和完成 commit 为准；本文件不替代自动验收。

## 2026-10-22 — S00 实现与本地验收，真实验收受阻

已替换 bootstrap 为有界、ChatGPT only 的调度实现：模型/额度协议预检、完整依赖图、结构化结果和非空测试 gate、信号/进程组清理、证据日志、WIP/checkpoint 与 Git journal/trailer 恢复。50 个阶段及原有任务级别、依赖和 gate 保留，仅追加 S00 真实验收门禁；未实现未来产品功能。

实际本地故障测试：48 项通过，0 skip；包括真实子进程/数值断言/Git 事务，见 `artifacts/S00/unit-report.json` 与逐例压缩证据。配置图验证通过。真实 CLI 小任务在临时仓库尝试，model/list 成功，但 account/read 的 workspace routing discovery 失败，严格预检停机，未执行真实模型开发闭环。timer 部署因只读用户目录失败，短 timer 触发因 systemd 总线权限被拒绝，均未冒充通过。

验收文档：`docs/acceptance/S00.md`。S00 附加 gate 会因真实 CLI/timer 未通过而返回非零，**S00 保持未完成**；下一任务仍为补齐 S00 的真实验收。项目 `.scheduler/state.json` 未改，项目 Git HEAD 未改、未 commit/push。剩余风险包括同 UID 并发编辑识别、checkpoint 硬崩溃人工恢复、CLI 版本兼容和日志容量管理，详见验收记录。已有 6 小时 timer 配置保留；修订后的 service 尚未部署。

## 2026-10-22 — S00 复核修正，真实验收仍阻塞

本轮修复隔离登录目录写出项目的问题，改用工作区临时目录；故障测试统一使用自制身份，归档排除登录目录/软链接。补充锁内重新读状态、预检 RPC 429 立即共享退避、gate 后保护输入校验、原始测试日志证据哈希，以及已安装 timer/service 比对。真实烟测的后续独立临时仓库改放项目内部，避免当前 CLI 拒绝 /tmp helper；没有激活任何 API key 或自定义付费后端。

实际最终本地测试 **54 项通过、0 skip**，包含真实数值/子进程/Git/恢复断言；另以实际 systemd calendar 解析断言三个六小时间隔均为 21600 秒。50 阶段图验证通过，完整后续计划未改。本轮失败迭代和修正记录保留；中间两份跟随登录链接的本地归档已删除，最终归档无 auth.json 条目。

真实 CLI 本轮仅尝试一次小任务：initialize/model/list 成功，account/read 仍返回 workspace routing discovery failed，未进入 exec，不能视为真实开发闭环通过。用户 systemd 总线仍拒绝访问，且只读比对显示部署 unit 与源码不一致，未部署或验证触发。附加 gate 实际退出 1（本地通过、live/timer 未通过）；项目 dry-run 因外层调度器持锁实际退出 3。**S00 仍未完成，下一任务仍是 S00**，没有将未来阶段标记完成。

验收及继续入口：`docs/acceptance/S00.md`、`artifacts/acceptance/S00.json`。项目 state 与 HEAD 的前后哈希另存 `artifacts/S00/project-invariants.json`；本轮未编辑 state、未创建项目 Git 提交。需要在可用的既有 ChatGPT 路由和用户 systemd 权限环境补齐真实烟测/部署，然后由调度器验收决定完成。
