# 项目运行与交接

源码根目录 `/home/qyw/URDFTools`；架构于 2026-10-22 生成。当前实现从 S00 开始，由调度器启动独立 Codex CLI，按 `scheduler.json` 的 level 实际指定模型。

现有可用命令：

```bash
cd ~/URDFTools
python3 scheduler.py status
python3 scheduler.py validate
python3 scheduler.py run --dry-run
python3 scheduler.py doctor
systemctl --user status urdftools-dev.timer
systemctl --user start --no-block urdftools-dev.service
journalctl --user -u urdftools-dev.service -n 50
```

`run --dry-run` 根据依赖和等待状态选任务，不启动模型、不改 state。`validate` 检查完整图与测试配置；其计数是配置节点数，不代表产品功能通过。`doctor` 使用临时隔离配置进行只读模型/身份/额度查询，不启动登录或推理。模型目录只证明 CLI 列出了候选模型，不证明当前额度足以执行。

运行 `run` 前工作树和 index 应干净；已知用户改动会阻止运行，不 reset/clean/stash。认证/额度失败有共享退避，不因 timer 重触发密集调用。修复输入/认证/硬件后，操作者可执行 `python3 scheduler.py retry S00` 显式解除该任务的等待，然后再 `run`；此命令不跳过 gate、不标完成，也不清除失败证据。不要在仍活动的开发任务中调用 retry。

本地验证与真实验收分开执行：

```bash
python3 scripts/run_scheduler_checks.py
python3 scripts/scheduler_live_smoke.py
bash install-timer.sh
python3 scripts/check_s00_acceptance.py
```

本地测试使用故障 peer，但进程、数值断言和 Git 事务实际运行；逐例输入和日志压缩在 `artifacts/S00/fault-evidence.tar.gz`。真实烟测只针对独立临时 Git 仓库。当前用户级 timer 每小时整点检查，systemd 不重启活动中的 service，调度器独占锁再次阻止并发；已用短临时 timer 验证实际触发。当前源码的最新烟测因真实 Codex 主窗口达到 90% 停机阈值而未执行模型，详见 `docs/acceptance/S00.md`。

隔离登录目录位于所选工作区 `.scheduler/codex-homes`，仅链接现有 auth.json，不写全局配置；故障测试只用自制身份且归档排除登录目录。真实烟测仓库位于项目 `.scheduler/live-repositories`；成功/失败都保留独立仓库供复核。timer 证据包含部署 unit 哈希一致、已启用的每小时持久 calendar 和实际短 timer 触发。

每阶段的验收记录在 `docs/acceptance/<id>.md`，总进度在 `PROGRESS.md`，机器状态在 `.scheduler/state.json`。源码本地 Git 提交是断点；日志在 `.scheduler/runs/`。用户可手动停止 service 保留 checkpoint；暂停定时器使用 `systemctl --user stop urdftools-dev.timer`（停止 timer 不会自动杀死正在运行的 service）。

认证：使用现有 `codex login` 的 ChatGPT 会话。会话过期需用户自行重新登录；不得把 token 写进项目。额度读取 RPC 返回 429 时记为额度未知，在 ChatGPT 身份与目标模型已确认后，当轮仅允许一次有界模型调用；模型调用明确报额度耗尽或读到使用率阈值时停止。不要自动兑换重置次数。

额度字段说明：`auth=chatgpt` 只表示登录方式；`account/rateLimits/read` 返回的 `rateLimits.limitId=codex` 才是此调度器用于停轮的 Codex 限额桶（`primary` 为 5 小时窗口、`secondary` 为周窗口）。它不查询普通 ChatGPT Chat 的消息上限；Chat 与 Work/Codex 使用规则按产品和计划区分，具体以账号 Usage 页面为准。OpenAI 文档：[Codex usage with a ChatGPT plan](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)、[GPT-6 usage limits and product distinctions](https://help.openai.com/en/articles/20001354-gpt-6-and-other-models-in-chatgpt).

开发引导观测到的可用路径（S01 要验证并写工具链清单）：

- Codex CLI：`/usr/lib/chatgpt/resources/codex`（0.160.0）
- Python 3.12：`/home/qyw/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`
- Node 24：`/home/qyw/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`
- pnpm：`/home/qyw/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm`

CLI 子进程可能没有交互 shell 的 PATH；引导脚本显式处理路径，禁止修改全局环境去影响其它项目。产品 venv、依赖 lock 和安装包必须独立，不依赖上述 Codex 缓存的长期存在。

硬件：GPU 驱动当前不可用，仅记录检测结果；不自动重装驱动。纯 CPU 功能继续实现，GPU 实验保留 waiting_hardware。训练队列默认节流、可断点续训，不把未跑的全量基准报告为完成。

当前 S01 的未完成工作保存在 `.scheduler/checkpoints/20261022T040140Z-S01-50b70e56`，按哈希核对了 356 个文件；`retry S01` 已请求下轮恢复。自动检查下一次为 13:00 CST。不要手工删除检查点或对工作树执行 `git clean`。

### 2026-10-22 S02 Git 事务恢复

S02 模型产物和 gate 已通过并生成提交 `c670677`，但旧调度器比较 `.git/index` 的原始 SHA256；Git 刷新索引缓存后会改变文件字节，即使暂存内容仍等于阶段开始时的提交。旧代码因此记录 `blocked_input`，每小时 timer 只返回 no-op。运维在独占锁下验证索引与原基线语义相等、提交逐文件对应 gate 清单，随后同步索引并调用事务恢复，使 S02 正式完成。调度器现比较暂存内容与原基线/新提交，真实用户暂存改动仍会拦截。回归 65/65 与阶段图 50/50 通过。
