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

`run --dry-run` 根据依赖和等待状态选任务，不启动模型、不改 state。`validate` 检查完整图与测试配置；其计数是配置节点数，不代表产品功能通过。`doctor` 使用临时隔离配置进行只读模型/身份/额度查询，不启动登录或推理。当前沙箱中真实 account/read 路由发现失败，因此不能凭 model/list 目录宣称推理成功。

运行 `run` 前工作树和 index 应干净；已知用户改动会阻止运行，不 reset/clean/stash。认证/额度失败有共享退避，不因 timer 重触发密集调用。修复输入/认证/硬件后，操作者可执行 `python3 scheduler.py retry S00` 显式解除该任务的等待，然后再 `run`；此命令不跳过 gate、不标完成，也不清除失败证据。不要在仍活动的开发任务中调用 retry。

本地验证与真实验收分开执行：

```bash
python3 scripts/run_scheduler_checks.py
python3 scripts/scheduler_live_smoke.py
bash install-timer.sh
python3 scripts/check_s00_acceptance.py
```

本地测试使用故障 peer，但进程、数值断言和 Git 事务实际运行；逐例输入和日志压缩在 `artifacts/S00/fault-evidence.tar.gz`。真实烟测只针对独立临时 Git 仓库；预检失败不会绕过身份检查调用 exec。安装脚本保留原六小时 timer，重载后另用一个短临时 timer 实际触发无模型的 probe；不会将手动启动 service 算作自动触发。当前部署及触发均受权限阻塞，S00 附加 gate 因此返回非零，详见 `docs/acceptance/S00.md`。

隔离登录目录位于所选工作区 `.scheduler/codex-homes`，仅链接现有 auth.json，不写全局配置；故障测试只用自制身份且归档排除登录目录。真实烟测仓库位于项目 `.scheduler/live-repositories`，避开当前 CLI 的 /tmp helper 限制；成功/失败都保留独立仓库供复核。timer 证据必须同时包含部署 unit 哈希一致、已启用的六小时持久 calendar 和实际短 timer 触发；通过 calendar 数值测试或仅触发无关 probe 均不能替代完整运行验收。

每阶段的验收记录在 `docs/acceptance/<id>.md`，总进度在 `PROGRESS.md`，机器状态在 `.scheduler/state.json`。源码本地 Git 提交是断点；日志在 `.scheduler/runs/`。用户可手动停止 service 保留 checkpoint；暂停定时器使用 `systemctl --user stop urdftools-dev.timer`（停止 timer 不会自动杀死正在运行的 service）。

认证：使用现有 `codex login` 的 ChatGPT 会话。会话过期需用户自行重新登录；不得把 token 写进项目。CLI app-server 额度读取由 S00 实测，无法读取时明确显示 unavailable，按实际限额事件退出。不要自动兑换重置次数。

开发引导观测到的可用路径（S01 要验证并写工具链清单）：

- Codex CLI：`/usr/lib/chatgpt/resources/codex`（0.160.0）
- Python 3.12：`/home/qyw/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`
- Node 24：`/home/qyw/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`
- pnpm：`/home/qyw/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm`

CLI 子进程可能没有交互 shell 的 PATH；引导脚本显式处理路径，禁止修改全局环境去影响其它项目。产品 venv、依赖 lock 和安装包必须独立，不依赖上述 Codex 缓存的长期存在。

硬件：GPU 驱动当前不可用，仅记录检测结果；不自动重装驱动。纯 CPU 功能继续实现，GPU 实验保留 waiting_hardware。训练队列默认节流、可断点续训，不把未跑的全量基准报告为完成。

当前开发目录在 writable root 内，用户 systemd 目录不在写入范围，用户总线也被当前沙箱拒绝；本次没有部署修订或验证自动触发。已有定时部署授权无需重复请求，但必须在具备这些权限的执行环境完成，禁止通过 symlink、全局不受限 sandbox 或修改总线地址绕过限制。
