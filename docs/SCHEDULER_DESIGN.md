# 开发调度与跨会话恢复设计

S00 实施记录（2026-10-22）：新版源码与本地故障测试已落地，48 项通过；真实 model/list 已返回目录，但身份路由发现失败，真实小任务未到 exec；timer 部署/触发也受当前权限阻塞。详见 `acceptance/S00.md`，仍不得标记 S00 完成。以下保留设计与完整后续约束，首段中的 bootstrap 描述为实施前基线。

现有实现是 bootstrap，仅可执行线性单阶段。首个 S00 由 Sol High 通过现有调度器实现下列加固；当前架构模型不直接编写产品功能或调度器实现。已有 systemd timer 正常工作，沿用一个定时来源，避免同时创建 Codex 自动化和 systemd 重复启动。默认阶段已下调为 Sol Medium 20、Sol High 28、Astra High 2、Astra xHigh 0；xHigh 保留为未来有证据的显式复核档。

## 模型选择

| level | 首选模型 | effort | 任务 |
|---|---|---|---|
| ordinary | gpt-6.1-sol | medium | 文档、目录/参照注册、报告、打包安装、已定义实验操作 |
| complex | gpt-6.1-sol | high | 桌面/服务/CAD/训练集成、调度器和复杂测试 |
| critical | gpt-6-astra | high | 坐标惯量、动力学、机器人任务、诊断和统计核心 |
| critical_xhigh | gpt-6-astra | xhigh | 当前队列不启用；未来有证据才显式分配 |

每任务创建独立 CLI 进程，保存请求 model/effort、完整命令（凭据脱敏）、thread id、可用的会话元数据、usage 和最终结果。模型输出自称身份不作证据。优先通过 `codex app-server` 的已支持 `model/list` 查询可用模型及 effort；按本机协议初始化。gpt-6.1-sol 不可用时，只有查询证实的同类 gpt-6-sol 可作显式记录的替代；Astra 不可用则该关键任务 wait_model，不静默降档。

不得因为共享额度耗尽自动换模型继续刷请求。默认不自动升到更高成本档；如连续实现失败需要升级，在调度状态记为建议并由既定任务中单独 review/recovery 阶段执行，保留原失败证据。

## 每轮流程

1. 获取独占文件锁；恢复中断状态并写开始记录。重复触发安全返回；无待办不调用模型、不查额度。
2. 验证任务图、phase ids、prompt 路径、测试 argv、完成证据、Git HEAD 和外部修改。按顺序选择依赖已完成且不处于 backoff/硬件等待的任务；独立任务不被 GPU 阻塞拖死。
3. 严格 ChatGPT 身份预检，移除继承 API credentials，设置已支持的 `forced_login_method=chatgpt` 和 OpenAI ChatGPT provider，避免用户自定义 provider 偷换成付费后端。认证过期保存 auth_required，不能把任意 Logged in 当作 ChatGPT。
4. 可选只读 app-server 查询额度：保存 primary/secondary 及 model bucket、window/reset、timestamp。缺失为 unknown。默认 primary 使用率达到 90% 或 secondary 达到 95% 停本轮，6 小时后再查；没有官方百分比时允许一次有界 exec，由明确 quota/rate-limit 事件停止。不得消耗 reset credit/购额或后台登录弹窗。
5. 读取任务说明、架构相关章节、PROGRESS、前次摘要与 diff，启动正确模型；不把整库/视频塞入 prompt。`--output-schema`/`--output-last-message` 保存结构化 completed/partial/blocked 结果。流式写 JSONL，保留进程退出与 turn.completed/turn.failed，不能只看退出码。
6. 实现阶段写人类摘要和验收材料；调度器运行声明的测试 argv，每个测试独立日志、返回码、耗时。gate 必须有实际测试/结果，禁止 empty discovery 或用全部 skip 充当通过。
7. 只有结构化 completed、无 blocker、gate 全通过、必要 artifact 存在且内容合法，才提交该阶段并标完成。Git 提交失败有独立状态，可重试提交而不重做阶段。保留 run evidence 和完成 commit 的关联。
8. partial/failure/quota/timeout 保存完整日志、阶段摘要与 WIP 恢复信息。模型不可修改 `.scheduler/state.json`。需要 WIP Git 时只纳入本轮获授权的代码与文档，不包含密钥/用户 CAD/视频；不 reset/clean/stash 用户改动。已知外部变更先识别后隔离，不盲目 git add -A。
9. 每轮默认最多 3 个阶段，总墙钟上限 4 小时，单任务 70 分钟，测试最多 20 分钟；剩余预算不够不启动新任务。每次成功后重新读取状态/配置。首轮 bootstrap 原进程只运行 S00，下一轮使用新版。
10. signal/timeout 必须终止整个子进程组、写 interrupted 状态并释放锁；重启恢复不得重复标完成。训练作业使用独立 checkpoints，不能伴随终止留下无限孤儿进程。

## 状态与事务

状态包含 task statuses、attempt history、HEAD、last checkpoint、quota snapshot、next eligible time、blocked reason、usage。文件原子写 + fsync；Git 与 JSON 无法原子跨系统提交，用 write-ahead journal/commit trailers 实现崩溃恢复，覆盖“commit 已完成但 JSON 未更新”和反向状态。最少保留 stdout/stderr、prompt hash、config hash、test logs、structured result 和摘要。

失败分类 `quota_wait/auth_required/wait_model/blocked_hardware/blocked_input/partial/test_failed/timeout/interrupted/commit_failed/internal_error`。错误分类基于结构化错误，不让正文中的“429 示例”触发停机。认证/额度异常不进行密集重试；每轮最多一次外部失败尝试。网络短暂错误最多一次带退避重试且不得重复应用修改。

产品实验运行中返回 waiting_experiment，保存 job id，后续先检查 job 状态；无需持续启动语言模型来轮询纯计算。重试预算用 step/time 上限，不能把预算耗尽当作训练成功。

## 必须的调度器测试

四档参数路由、真实 CLI 能力查询（可 unavailable）、ChatGPT only、额度预检/429、正文误匹配、依赖排序、模型不可用、无任务、并发锁、超时/信号子进程清理、崩溃恢复、测试失败/全 skip、模型 partial 退出 0、不合法输出、日志逐项保存、Git 提交失败恢复、已有用户改动保护、自修改后下轮加载、无 API key 路径。

真实端到端至少覆盖一个小任务在临时 Git 仓库经 CLI 执行、真实测试、提交、恢复不重复；测试用例可用 fake CLI 验证故障路径，但报告明确区分真实与模拟。为节约额度，已有 Sol Medium/Astra xHigh READY 的历史探测可作为模型命令可调用的记录，不能替代开发阶段验收。

## 定时服务

已有 `urdftools-dev.timer`：`OnCalendar=*-*-* 00/6:00:00`，Persistent=true。本机 Linger=yes，用户 systemd 可在注销后继续；关机/睡眠期间不会执行，开机恢复后 catch-up 不补跑所有错过轮次。使用本地 Asia/Shanghai 的 00/06/12/18 点。service TimeoutStartSec=5h、KillMode=control-group；round timeout 比 service 短，给保存留时间。修订部署后必须重载并用短临时 timer 真实验证触发，不能只测试手动 start 就说自动触发已验证。

所有必需阶段完成后自然 no-op，并记录 final release path；可禁用 timer 以免空跑，但必须保留进度和日志供用户查看。独立硬件阻塞应明确展示且允许其它工作继续。
