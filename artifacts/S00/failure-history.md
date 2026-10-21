# S00 失败与修正记录

- 初版 36 项测试中 5 项失败（`tests-initial.log`）：共享额度退避返回值、Git 临时 index 提交后普通 index 不同步，导致干净工作树/依赖连续执行/自修改下轮加载等断言失败。已修正，后续有重复运行与提交/JSON 恢复测试覆盖。
- 一次补丁暂时导致 scheduler.py:396 IndentationError（`python3 -m py_compile scheduler.py` 实际退出 1，工具输出保留于会话）；修正缩进后完整测试通过。未把该次命令记为成功。
- 之后 36 项本地测试通过（second/third/fourth 日志）；扩展到 46、48 项后通过。较早 Git 失败注入采用 pre-commit hook，最终实现禁用未声明 hooks，最终测试改用真实 Git ref lock 失败。
- 首次 `doctor` 实际退出 2：严格身份未通过。补充的协议诊断确认 initialize 可用，account/read 返回 workspace routing discovery failed，不是已认证成功。
- 真实烟测未执行到 exec，外层脚本退出 1、调度器退出 75。实际 model/list 已返回目录；不能把目录当推理权限。最终真实 CLI gate 保留阻塞，未密集重试或换模型。
- 真实安装脚本 cp 被只读文件系统拒绝，短 timer 被用户总线权限拒绝。systemd-analyze 虽退出 0，仍有 socket/bus 错误，不算运行验收成功。
- 最终 acceptance gate 因 live/timer 未通过退出 1，属于保留的必需阻塞，不应删除该 gate 或手改调度状态绕过。
