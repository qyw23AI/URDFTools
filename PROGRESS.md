# URDFTools 项目进度

> 当前状态（2026-10-22 11:50 CST）：**S00 已由调度器正式完成**，完成提交 `52929b2`，50 阶段中完成 1 项。S01 的第一次与一次人工重试均在只读额度预检停轮，尚未进入模型 exec；最早可重试 15:49:19 CST，四小时 timer 下一次可执行轮次为 16:00。timer active/enabled，GNOME 进度终端持续刷新。下文保留此前各轮的历史记录，以机器状态 `.scheduler/state.json` 为准。

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


## 2026-10-22 — 当前 Codex 会话接手 S00（timer 已按用户要求暂停）

自动 `urdftools-dev.timer` 已执行 `disable --now`，确认 `ActiveState=inactive`、`UnitFileState=disabled`、无下次触发；service 主进程为 0（unit 保留之前 failed 状态）。没有运行自动 scheduler/CLI 轮次。当前 Codex 会话只读执行 `scheduler.py doctor` 成功：`auth=chatgpt`，额度 `limitId=codex`（Plus），primary 19%/300 分钟，secondary 83%/10080 分钟；这明确是 Codex 使用桶，不是 ChatGPT Chat 消息额度。随后重跑本地 S00 检查：54 tests、0 failures/errors/skips；`scheduler.py validate`：50 阶段全部配置有效。`completed=[]`、S00 `retry_requested`，阶段仍未验收完成。

未启动真实 CLI 小任务，因为用户要求停掉自动 CLI 并在当前 Codex 会话续做；S00 的真实 CLI 开发闭环仍需之后单独验收。timer 也刻意保持 disabled，因此 systemd 的已部署 unit 匹配及实际调度触发验收仍未完成。续做证据详见 `docs/acceptance/S00.md`。

当前会话补充：在不启动产品 timer/service 的情况下，独立两秒 `systemd-run --user` probe 实际触发并写出 token 标记，耗时 2.076 秒。综合 verifier 仍为 blocked，因为永久 timer 按要求保持 disabled，且已安装 unit 与源码 hash 不匹配；报告在 `artifacts/S00/manual-paused-timer-probe/report.json`。


## 2026-10-22 — S00 真实 CLI 烟测通过，准备自动部署

当前会话从项目内独立临时仓库运行 `scripts/scheduler_live_smoke.py`。首次预检在 `account/rateLimits/read` 被拒并安全进入 `quota_wait`，未执行模型；只读诊断随后成功，第二次有界运行（63.721 秒）以 Sol Medium 完成数值小任务，四项数值断言通过，由隔离调度器创建一次 Git 完成提交，重复运行无重复提交。报告为 `artifacts/S00/live-smoke/report.json`。S00 主项目仍未完成，须通过安装 timer 和正式 S00 gate。

2026-10-22 11:29：`install-timer.sh` 已将源码 unit 部署到用户 systemd，六小时 timer active/enabled，下次触发为当日 12:00 CST。实际两秒 transient timer probe 于 2.135 秒触发，部署 hash 完全匹配。S00 三项机器 gate 全部通过（3/3）；主项目状态仍是 S00 `retry_requested`，待调度器正式执行并保存阶段完成事务。

## 2026-10-22 11:35 — S00 当前源码复核，修复 Git 证据重试及结构化 429

复现并修复两个缺口：Git ref-lock 提交失败后的重试原会重新接受被改写的验收日志，现于 gate 后在 journal 固定证据哈希，恢复不符即停止且不再调用模型；嵌套 HTTP 429/401 和大小写变体错误枚举现正确识别，明确 429 不再作为 unknown 放行 exec。新增 5 项回归，先失败日志保留；旧 pending journal 缺少证据哈希须人工核对，已有 Git trailer 哈希格式保持兼容。

实际完整测试 **59 项通过，0 failures/errors/skips**；50 阶段配置图及全部原计划比较通过，六小时 calendar 三个间隔均为 21600 秒。没有缩减或执行未来阶段。当前源码真实 CLI 烟测只尝试一次，3.853 秒后因 account/read 的 `workspace routing discovery failed` 记录 auth_required，内层退出 75，未到 exec，不能沿用旧源码的成功来宣告完成。systemd 本轮受沙箱总线权限拒绝，已安装 unit 哈希仍匹配，永久 timer 未改；11:29 的同版本 timer 真实触发记录保留。

S00 综合 gate 退出 1（local/历史同版本 timer 通过、当前源码 live 阻塞，2/3）。**S00 未完成，下一任务仍为 S00 真实复验**。项目 `.scheduler/state.json`、Git HEAD、完整 phase 图均未改，未创建项目 Git commit/push。临时 fixture 仓库中的 Git 操作仅用于实际事务验收。详见 `docs/acceptance/S00.md` 最新复核、`artifacts/acceptance/S00.json`、`artifacts/S00/review-20261022/`。


## 2026-10-22 — 30 秒启动验证与四小时长期调度

用户指定的 30 秒临时 systemd timer 实际触发，`urdftools-dev.service` 于 11:31:49 CST 启动 S00，当前 GNOME 系统终端持续显示真实状态和 CLI 日志。该轮 S00 补强 Git 恢复证据校验及嵌套 HTTP 429/401 识别，本地 59 项测试通过；由于模型沙箱内的登录路由/systemd 总线受限，阶段返回 blocked_input，改动由调度器保存为 checkpoint。操作会话已用调度器恢复方法取回 checkpoint，按用户最新指令改为四小时 timer 和 14400 秒额度退避，实际部署与短探针通过。针对最新源码重新运行 59 项测试、Sol Medium 真实 CLI 数值任务、Git 提交/去重和 timer 验证，`check_s00_acceptance.py` **3/3 通过**。S00 主项目状态仍为 blocked_input，待调度器正式重试与提交；没有提前标记完成。

## 2026-10-22 11:46 — S00 保留 WIP 续接验收就绪

先检查 diff，保留既有调度实现与四小时 timer。本轮实际运行声明测试：59/59 通过、0 skip；50 阶段图有效；综合 gate 3/3，全部退出 0。独立 fixture 的数值重算 4/4，通过 24 项只读断言核对宿主源码/测试/部署哈希、真实 CLI 的 ChatGPT/Sol Medium 请求、Git 父提交及证据 trailer、重复运行 no-op、timer 原始进程和 2.113 秒触发标记。宿主报告均与当前文件匹配，按任务授权复用；未另启模型或 systemd 探针。

更新验收首页与机器摘要，保留旧 blocked 摘要及失败记录。证据见 `artifacts/S00/resume-review-20261022/`、`docs/acceptance/S00.md`、`artifacts/acceptance/S00.json`。源码/测试/timer/verifier 未再修改；项目 HEAD、state 及 scheduler.json 前后哈希相同，未创建项目提交，未来 49 阶段与基线完全一致。S00 实现及验收材料已就绪，正式阶段完成和提交仍交外层调度器决定。旧 pending journal、同 UID 并发编辑、硬崩溃、协议兼容及日志容量风险继续如实保留。
