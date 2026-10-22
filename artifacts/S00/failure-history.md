# S00 失败与修正记录

- 初版 36 项测试中 5 项失败（`tests-initial.log`）：共享额度退避返回值、Git 临时 index 提交后普通 index 不同步，导致干净工作树/依赖连续执行/自修改下轮加载等断言失败。已修正，后续有重复运行与提交/JSON 恢复测试覆盖。
- 一次补丁暂时导致 scheduler.py:396 IndentationError（`python3 -m py_compile scheduler.py` 实际退出 1，工具输出保留于会话）；修正缩进后完整测试通过。未把该次命令记为成功。
- 之后 36 项本地测试通过（second/third/fourth 日志）；扩展到 46、48 项后通过。较早 Git 失败注入采用 pre-commit hook，最终实现禁用未声明 hooks，最终测试改用真实 Git ref lock 失败。
- 首次 `doctor` 实际退出 2：严格身份未通过。补充的协议诊断确认 initialize 可用，account/read 返回 workspace routing discovery failed，不是已认证成功。
- 真实烟测未执行到 exec，外层脚本退出 1、调度器退出 75。实际 model/list 已返回目录；不能把目录当推理权限。最终真实 CLI gate 保留阻塞，未密集重试或换模型。
- 真实安装脚本 cp 被只读文件系统拒绝，短 timer 被用户总线权限拒绝。systemd-analyze 虽退出 0，仍有 socket/bus 错误，不算运行验收成功。
- 最终 acceptance gate 因 live/timer 未通过退出 1，属于保留的必需阻塞，不应删除该 gate 或手改调度状态绕过。

## 本轮 S00 复核（2026-10-22）

- 初次重跑：48 tests，36 failures / 1 error，原因是旧实现向只读 ~/.codex/tmp 创建隔离目录，返回 Errno 30。完整失败输出保留 retry-initial-unit-tests.log / retry-initial-unit-report.json。
- 工作区隔离修正后的中间迭代：48 tests，2 failures / 1 error（codex_home 测试调用未同步、commit_failed 被重复输入检查误归类为 blocked_input）；输出保留 retry-second-unit-tests.log / retry-second-unit-report.json。随后 52 tests 的中间迭代仍有 2 failures；限制输入复核只在 running 阶段执行后修复。最终新增 timer 断言后的完整套件为 54 tests，全部通过，0 skip。
- 工作区隔离修正暴露测试归档问题：崩溃留下的登录软链接被 copytree 跟随，两个新本地归档包含 auth 路径。两个归档立即删除，未上传；全部故障测试改为自制身份 fixture，归档排除 codex-homes 且不跟随软链接。最终归档已扫描确认无 auth.json / codex-homes 条目；未输出凭据内容。失败日志和计数仍保留。
- 真实 CLI 小任务本轮只尝试一次：model/list 返回，account/read 为 workspace routing discovery failed。没有 exec 或模型产生的数值/Git验收。/tmp helper 的警告已记录，后续烟测目录改为项目 .scheduler/live-repositories；最终代码尚未通过真实烟测，不反复刷请求。
- timer 本轮读状态和短触发均被用户总线 Operation not permitted 拒绝。新增加的只读比对还发现已安装 service/timer 与源码不一致；部署未执行。calendar 第一次使用带 Asia/Shanghai 后缀的 --base-time 参数被 systemd-analyze 拒绝（退出 1），改用 TZ=Asia/Shanghai 和不带时区的 base-time 后成功，最终测试实际断言 3 个 21600 秒间隔。
- 项目 dry-run 实际退出 3：外层调度器持锁。没有强制解锁，也没有修改 state。最终 S00 gate 退出 1，本地证据通过、真实 CLI/timer 未通过，S00 未完成。
